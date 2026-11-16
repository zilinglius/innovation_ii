"""作业的进程入口（给定），由 jobrun.py 在各 namespace 里启动。

参数服务器一轮的时间线（worker i）：
    compute_start → 本地计算 → compute_end → 上传梯度 → PS 收齐（grad_last）
    → 等 barrier（所有 worker 都收齐）→ PS 下发模型 → model_last

Ring AllReduce 一轮：compute_start → 本地计算 → compute_end → 环上交换 → ring_end。
没有 PS，也没有显式的 barrier，节点靠“等左邻居的数据”自然同步。

每个进程结束时在标准输出打印一行 JSON，时间戳都是 time.monotonic()。
"""

import argparse
import hashlib
import json
import queue
import random
import socket
import sys
import threading
import time

from jobkit.compute import NumpyCompute, SleepCompute
from jobkit.ring import ring_allreduce, split_chunks
from jobkit.wire import read_exact, recv_msg, send_msg, set_cc


def serve(args):
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        set_cc(listener, args.cc)
        listener.bind(("0.0.0.0", args.port))
        listener.listen(args.workers)
        listener.settimeout(30)
        conns = []
        for _ in range(args.workers):
            conn, _ = listener.accept()
            conn.settimeout(600)
            set_cc(conn, args.cc)
            hello = bytearray(64)
            read_exact(conn, memoryview(hello))
            name = hello.decode().strip()
            conns.append((name, conn))
    conns.sort()
    records = {name: [{} for _ in range(args.rounds)] for name, _ in conns}
    aggregates = [{} for _ in range(args.rounds)]
    gradients = {}
    model = bytearray(args.model_bytes)
    round_box = [0]
    weights = [None]  # numpy 模式下的全局权重，第一次聚合时按梯度长度初始化

    def aggregate():
        # barrier 的动作：最后一个到达的线程执行一次，此时全部梯度都已收齐。
        index = round_box[0]
        started = time.monotonic()
        if args.compute == "numpy":
            import numpy as np

            parts = [np.frombuffer(gradients[name], dtype=np.float64) for name, _ in conns]
            mean = np.mean(parts, axis=0)
            if weights[0] is None:
                weights[0] = np.zeros(mean.shape)
            weights[0] -= args.learning_rate * mean
            model[:] = weights[0].tobytes()
        aggregates[index] = {"agg_start": started, "barrier_done": time.monotonic()}
        round_box[0] = index + 1

    barrier = threading.Barrier(args.workers, action=aggregate)
    failures = []

    def worker_loop(name, conn):
        buffer = bytearray(args.model_bytes)
        try:
            for index in range(args.rounds):
                _, length, first, last = recv_msg(conn, buffer)
                records[name][index].update(grad_first=first, grad_last=last, grad_bytes=length)
                if args.compute == "numpy":
                    gradients[name] = bytes(buffer[:length])
                barrier.wait()
                started = time.monotonic()
                send_msg(conn, index, model)
                records[name][index].update(model_send_start=started, model_send_end=time.monotonic())
        except Exception as error:  # 让其他线程不会永远卡在 barrier 上
            failures.append(f"{name}: {error}")
            barrier.abort()

    threads = [threading.Thread(target=worker_loop, args=item) for item in conns]
    for thread in threads:
        thread.start()
    for _, conn in conns:
        conn.sendall(b"G")
    for thread in threads:
        thread.join()
    for _, conn in conns:
        conn.close()
    if failures:
        raise SystemExit("PS 失败：" + "; ".join(failures))
    print(json.dumps({"role": "server", "workers": records, "aggregates": aggregates}))


def connect(args):
    deadline = time.monotonic() + 10
    while True:
        sock = socket.socket()
        set_cc(sock, args.cc)
        sock.settimeout(600)
        try:
            sock.connect((args.server, args.port))
            return sock
        except OSError:
            sock.close()
            if time.monotonic() > deadline:
                raise
            time.sleep(0.05)


def work(args):
    if args.compute == "numpy":
        computer = NumpyCompute(args.model_bytes, args.iters, args.seed)
    else:
        computer = SleepCompute(args.compute_seconds, args.slow_prob, args.slow_seconds, args.seed)
    blank = bytes(args.model_bytes)
    records = []
    buffer = bytearray(args.model_bytes)
    sock = connect(args)
    with sock:
        sock.sendall(args.name.encode().ljust(64))
        if sock.recv(1) != b"G":
            raise SystemExit("没有收到开始信号")
        for index in range(args.rounds):
            compute_start = time.monotonic()
            computer.step()
            compute_end = time.monotonic()
            send_msg(sock, index, computer.payload() if args.compute == "numpy" else blank)
            local_done = time.monotonic()
            _, length, first, last = recv_msg(sock, buffer)
            if args.compute == "numpy":
                computer.apply_model(buffer, length)
            records.append({"compute_start": compute_start, "compute_end": compute_end,
                            "local_send_done": local_done, "model_first": first, "model_last": last})
    print(json.dumps({"role": "worker", "name": args.name, "rounds": records,
                      "bytes_sent": args.model_bytes * args.rounds, "compute": computer.info()}))


def xor_bytes(a, b):
    """环上的合并操作：按位异或，满足交换律和结合律，只用标准库。"""
    return (int.from_bytes(a, "little") ^ int.from_bytes(b, "little")).to_bytes(len(a), "little")


def local_vector(rank, length):
    return random.Random(10_000 + rank).randbytes(length)


def expected_digest(size, length):
    """全部节点向量的异或结果的摘要；只用来在最后一轮核对结果是否正确。"""
    total = bytes(length)
    for rank in range(size):
        total = xor_bytes(total, local_vector(rank, length))
    return hashlib.sha256(total).hexdigest()


def ring(args):
    """环上的一个节点：向右邻居建一条连接，从左邻居接一条连接。"""
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        set_cc(listener, args.cc)
        listener.bind(("0.0.0.0", args.port))
        listener.listen(1)
        listener.settimeout(30)
        right = connect(args) if args.size > 1 else None
        left = None
        if args.size > 1:
            left, _ = listener.accept()
            left.settimeout(600)
            set_cc(left, args.cc)
    computer = SleepCompute(args.compute_seconds, args.slow_prob, args.slow_seconds, args.seed)
    vector = local_vector(args.rank, args.model_bytes)
    chunks = split_chunks(vector, args.size)
    outbox = queue.Queue()
    buffer = bytearray(len(chunks[0]) + 1)
    sent = [0]
    failures = []
    marks = []

    def pump():
        # 发送放在单独的线程里，主线程同时收，避免环上所有节点都卡在发送上。
        try:
            while (payload := outbox.get()) is not None:
                send_msg(right, 0, payload)
        except OSError as error:
            failures.append(str(error))
            left.close()

    sender = threading.Thread(target=pump, daemon=True)
    if args.size > 1:
        sender.start()

    def exchange(payload):
        outbox.put(payload)
        sent[0] += len(payload)
        _, length, _, _ = recv_msg(left, buffer)
        marks.append(time.monotonic())
        return bytes(buffer[:length])

    print("READY", flush=True)
    sys.stdin.readline()
    records = []
    result = chunks
    for _ in range(args.rounds):
        compute_start = time.monotonic()
        computer.step()
        compute_end = time.monotonic()
        marks.clear()
        result = ring_allreduce(args.rank, args.size, chunks, exchange, xor_bytes)
        records.append({"compute_start": compute_start, "compute_end": compute_end, "ring_end": time.monotonic(),
                        "step_ends": list(marks)})
    if args.size > 1:
        outbox.put(None)
        sender.join(timeout=30)
    if failures:
        raise SystemExit("发送失败：" + "; ".join(failures))
    correct = hashlib.sha256(b"".join(result)).hexdigest() == expected_digest(args.size, args.model_bytes)
    for sock in (right, left):
        if sock is not None:
            sock.close()
    print(json.dumps({"role": "ring", "name": args.name, "rank": args.rank, "rounds": records,
                      "bytes_sent": sent[0], "correct": correct, "compute": computer.info()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["server", "worker", "ring"])
    parser.add_argument("--rank", type=int, default=0)
    parser.add_argument("--size", type=int, default=1)
    parser.add_argument("--slow-prob", type=float, default=0.0)
    parser.add_argument("--slow-seconds", type=float, default=0.0)
    parser.add_argument("--name", default="")
    parser.add_argument("--server", default="")
    parser.add_argument("--port", type=int, default=7600)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--model-bytes", type=int, required=True)
    parser.add_argument("--compute", choices=["sleep", "numpy"], default="sleep")
    parser.add_argument("--compute-seconds", type=float, default=0.2)
    parser.add_argument("--iters", type=int, default=50)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=0.5)
    parser.add_argument("--cc", default="cubic")
    args = parser.parse_args()
    {"server": serve, "worker": work, "ring": ring}[args.role](args)


if __name__ == "__main__":
    main()
