"""作业内部的报文格式（给定）：12 字节头（轮次、长度）加负载。

时间戳一律用 time.monotonic()。所有 namespace 跑在同一台机器上，共用一个单调时钟，
不同进程的读数可以直接相减；真实集群要先做时钟同步（第 07 讲 2.3 节）。
"""

import socket
import struct
import time

HEADER = struct.Struct("!IQ")
CHUNK = 1 << 20


def set_cc(sock, cc):
    """显式指定拥塞控制算法并关闭 Nagle，不依赖系统默认值。"""
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_CONGESTION, cc.encode())
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


def send_msg(sock, round_id, payload):
    """发送一条消息。返回只代表数据已交给本地 TCP，不代表对端收到。"""
    sock.sendall(HEADER.pack(round_id, len(payload)))
    sock.sendall(payload)


def read_exact(sock, view):
    """把 view 读满；对端提前关闭时抛 ConnectionError。"""
    got = 0
    while got < len(view):
        count = sock.recv_into(view[got:], min(len(view) - got, CHUNK))
        if count == 0:
            raise ConnectionError("对端提前关闭了连接")
        got += count


def recv_msg(sock, buffer):
    """接收一条消息到 buffer（bytearray，必要时扩容）。

    返回 (轮次, 负载长度, 首字节到达时刻, 末字节到达时刻)，负载在 buffer[:长度] 中。
    首字节时刻取报文头收齐的时刻。
    """
    head = bytearray(HEADER.size)
    read_exact(sock, memoryview(head))
    first = time.monotonic()
    round_id, length = HEADER.unpack(head)
    if len(buffer) < length:
        buffer.extend(bytes(length - len(buffer)))
    read_exact(sock, memoryview(buffer)[:length])
    return round_id, length, first, time.monotonic()
