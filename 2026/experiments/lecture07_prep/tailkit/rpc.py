"""一个最小的 RPC：协议、后端与客户端（给定，不需要改）。

一条 TCP 连接上可以同时有多个未完成的请求，靠请求号对应响应。协议是一行文本加响应体：

  请求  REQ <id> <resp_bytes> <base_ms> <slow_ms> <slow_prob>\n
  取消  CANCEL <id>\n
  响应  RSP <id> <resp_bytes> <slow>\n，后面跟 resp_bytes 字节

服务时间由请求自己带上，后端照做：先等 base_ms，再以 slow_prob 的概率多等 slow_ms。
这样一个后端进程不用重启就能跑不同的实验条件。每次抽样相互独立。
"""

import asyncio
from dataclasses import dataclass
import random
import socket

HEADER_LIMIT = 256


def tune(sock, cc):
    """关闭 Nagle；显式指定拥塞控制算法，不依赖系统默认值。"""
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_CONGESTION, cc.encode())


@dataclass
class Service:
    """本次实验要求后端模拟的服务时间与响应大小。"""

    resp_bytes: int = 128
    base_ms: float = 5.0
    slow_ms: float = 0.0
    slow_prob: float = 0.0


async def _serve_one(writer, pending, req_id, service, rng):
    try:
        slow = rng.random() < service.slow_prob
        delay = service.base_ms + (service.slow_ms if slow else 0.0)
        await asyncio.sleep(delay / 1000)
        writer.write(f"RSP {req_id} {service.resp_bytes} {int(slow)}\n".encode() + bytes(service.resp_bytes))
        await writer.drain()
    except (asyncio.CancelledError, ConnectionError):
        pass
    finally:
        pending.pop(req_id, None)


async def _handle(reader, writer, rng):
    pending = {}
    try:
        while line := await reader.readline():
            fields = line.decode().split()
            if fields[0] == "REQ":
                service = Service(int(fields[2]), float(fields[3]), float(fields[4]), float(fields[5]))
                pending[fields[1]] = asyncio.create_task(_serve_one(writer, pending, fields[1], service, rng))
            elif fields[0] == "CANCEL" and fields[1] in pending:
                pending[fields[1]].cancel()
    except ConnectionError:
        pass
    finally:
        for task in list(pending.values()):
            task.cancel()
        writer.close()


async def serve(port, cc="cubic", seed=None):
    """运行后端，直到进程被终止。"""
    rng = random.Random(seed)
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.setsockopt(socket.IPPROTO_TCP, socket.TCP_CONGESTION, cc.encode())
    listener.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    listener.bind(("0.0.0.0", port))
    server = await asyncio.start_server(
        lambda reader, writer: _handle(reader, writer, rng), sock=listener, backlog=1024)
    try:
        await asyncio.Event().wait()  # 一直运行，直到被取消或进程被终止。
    finally:
        # 不用 serve_forever 或 async with：Python 3.12 起，取消时它们要等全部连接结束，可能一直挂着。
        server.close()


@dataclass
class Reply:
    req_id: int
    host: str
    resp_bytes: int
    slow: bool


class RpcClient:
    """到一个后端的一条长连接。call() 立即发出请求，返回一个等待响应的 Future。"""

    def __init__(self, host, address, port, cc="cubic"):
        self.host = host
        self.address = address
        self.port = port
        self.cc = cc
        self.reader = self.writer = self._task = None
        self._waiting = {}

    async def connect(self):
        sock = socket.socket()
        tune(sock, self.cc)
        sock.setblocking(False)
        await asyncio.get_running_loop().sock_connect(sock, (self.address, self.port))
        self.reader, self.writer = await asyncio.open_connection(sock=sock)
        self._task = asyncio.create_task(self._read_loop())

    def call(self, req_id, service):
        future = asyncio.get_running_loop().create_future()
        self._waiting[req_id] = future
        self.writer.write(f"REQ {req_id} {service.resp_bytes} {service.base_ms} "
                          f"{service.slow_ms} {service.slow_prob}\n".encode())
        return future

    def cancel(self, req_id):
        """放弃一个请求：不再等它的响应，也通知后端不必继续做。"""
        future = self._waiting.pop(req_id, None)
        if future is not None:
            future.cancel()
            self.writer.write(f"CANCEL {req_id}\n".encode())

    async def _read_loop(self):
        closing = False
        try:
            while line := await self.reader.readline():
                _, req_id, size, slow = line.decode().split()
                if int(size):
                    await self.reader.readexactly(int(size))
                future = self._waiting.pop(int(req_id), None)
                if future is not None and not future.done():
                    future.set_result(Reply(int(req_id), self.host, int(size), slow == "1"))
        except asyncio.CancelledError:
            closing = True  # 本端主动关闭，不算连接故障。
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        for future in self._waiting.values():
            if not future.done():
                if closing:
                    future.cancel()
                else:
                    future.set_exception(ConnectionError(f"到 {self.host} 的连接已断开"))
        self._waiting.clear()

    async def close(self):
        if self._task:
            self._task.cancel()
        if self.writer:
            self.writer.close()
