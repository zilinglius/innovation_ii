"""服务实例（给定）。由 edge.sh up 在各 host 的 namespace 里各启动一个。

一个请求分三步：客户端上传输入 → 实例做一段计算 → 实例返回一行结果。
实例由两个进程组成：
  收发进程   接受连接、收输入、回结果；不受 CPU 限额约束；
  计算进程   一次只算一个请求，先到先算；它的进程号写进 --pidfile，由 edge.sh 放进建好的 cgroup，受 cpu.max 限制。
             （ip netns exec 里看不到 /sys/fs/cgroup，所以这一步由 namespace 外面的 edge.sh 来做。）
这样“传输”和“计算”互不干扰：实例再忙，收数据也不变慢。

请求格式：一行 JSON {"id":…, "input_bytes":…, "work_ms":…}，后面跟 input_bytes 字节的输入。
应答格式：一行 JSON，时间戳都是 time.monotonic()（所有 namespace 共用同一个单调时钟）：
  recv_done  收齐输入的时刻；start、end  计算开始与结束的时刻；ahead  收齐时排在它前面的请求数（含正在算的）。
{"op": "stat"} 查询实例当前的状态：{"queued": 排队与在算的请求数, "backlog_ms": 这些请求还没算完的工作量之和}。
"""

import argparse
import json
import multiprocessing
import queue
import socket
import threading
import time

CHUNK = 1 << 16


def burn(work_ms):
    """消耗 work_ms 毫秒的 CPU 时间（不是墙上时间）；CPU 被限额时，墙上时间会更长。"""
    target = work_ms / 1000
    begin = time.process_time()
    while time.process_time() - begin < target:
        pass


def compute_loop(pipe):
    while True:
        work_ms = pipe.recv()
        start = time.monotonic()
        burn(work_ms)
        pipe.send((start, time.monotonic()))


class Instance:
    def __init__(self, name, pidfile):
        self.name = name
        self.jobs = queue.Queue()
        self.lock = threading.Lock()
        self.queued = 0
        self.backlog_ms = 0.0
        self.pipe, child_end = multiprocessing.Pipe()
        self.child = multiprocessing.Process(target=compute_loop, args=(child_end,), daemon=True)
        self.child.start()
        if pidfile:
            with open(pidfile, "w") as stream:
                stream.write(str(self.child.pid))
        threading.Thread(target=self.feed, daemon=True).start()

    def feed(self):
        """把请求一个一个交给计算进程，先到先算。"""
        while True:
            work_ms, done = self.jobs.get()
            self.pipe.send(work_ms)
            done["start"], done["end"] = self.pipe.recv()
            with self.lock:
                self.queued -= 1
                self.backlog_ms -= work_ms
            done["event"].set()

    def handle(self, conn):
        with conn, conn.makefile("rb") as stream:
            header = json.loads(stream.readline())
            if header.get("op") == "stat":
                with self.lock:
                    reply = {"name": self.name, "queued": self.queued, "backlog_ms": round(self.backlog_ms, 3)}
                conn.sendall(json.dumps(reply).encode() + b"\n")
                return
            left = header["input_bytes"]
            while left:
                chunk = stream.read(min(CHUNK, left))
                if not chunk:
                    return
                left -= len(chunk)
            recv_done = time.monotonic()
            done = {"event": threading.Event()}
            with self.lock:
                ahead = self.queued
                self.queued += 1
                self.backlog_ms += header["work_ms"]
            self.jobs.put((header["work_ms"], done))
            done["event"].wait()
            reply = {"id": header["id"], "name": self.name, "recv_done": recv_done, "start": done["start"],
                     "end": done["end"], "ahead": ahead}
            conn.sendall(json.dumps(reply).encode() + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True)
    parser.add_argument("--port", type=int, default=7700)
    parser.add_argument("--pidfile", help="把计算进程的进程号写到这个文件")
    parser.add_argument("--cc", default="cubic", help="拥塞控制算法，显式指定")
    args = parser.parse_args()
    instance = Instance(args.name, args.pidfile)
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.setsockopt(socket.IPPROTO_TCP, socket.TCP_CONGESTION, args.cc.encode())
        listener.bind(("0.0.0.0", args.port))
        listener.listen(128)
        while True:
            conn, _ = listener.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=instance.handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
