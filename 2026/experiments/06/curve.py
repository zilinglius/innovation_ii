"""测传输时间与数据量的关系 T(m)（给定）。

一条长连接上按打乱的顺序发送各种大小的消息，接收端收齐后回 1 字节，发送端收到回执才停表，
所以测到的是“对端确实收齐”的时间，而不是 sendall 返回的时间。两次发送之间空闲 --gap-ms，
模拟作业两轮通信之间的计算阶段。结果写到 --out，格式 lab06.curve/v1，打印每个大小的中位数。

用法：sudo python3 2026/experiments/06/curve.py --src h1a --dst h3a
"""

import argparse
import json
import os
from pathlib import Path
import random
import socket
import statistics
import subprocess
import sys
import time

from jobkit.wire import recv_msg, send_msg, set_cc
from jobrun import RESULTS, host_ip, in_ns

DEFAULT_SIZES = "1000,10000,100000,1000000,4000000,16000000"


def receiver(args):
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        set_cc(listener, args.cc)
        listener.bind(("0.0.0.0", args.port))
        listener.listen(1)
        listener.settimeout(30)
        conn, _ = listener.accept()
    conn.settimeout(120)
    set_cc(conn, args.cc)
    buffer = bytearray(1 << 20)
    with conn:
        for _ in range(args.count):
            recv_msg(conn, buffer)
            conn.sendall(b"A")


def sender(args):
    sizes = [int(item) for item in args.sizes.split(",")]
    plan = [size for size in sizes for _ in range(args.trials)]
    random.Random(args.seed).shuffle(plan)
    with socket.socket() as sock:
        set_cc(sock, args.cc)
        sock.settimeout(120)
        deadline = time.monotonic() + 10
        while True:
            try:
                sock.connect((args.dest, args.port))
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)
        # 第一条消息只用来建立连接状态，不计入样本。
        send_msg(sock, 0, bytes(1000))
        sock.recv(1)
        samples = {size: [] for size in sizes}
        blocks = {size: bytes(size) for size in sizes}
        for size in plan:
            time.sleep(args.gap_ms / 1000)
            started = time.monotonic()
            send_msg(sock, 1, blocks[size])
            if sock.recv(1) != b"A":
                raise SystemExit("回执错误")
            samples[size].append(time.monotonic() - started)
    print(json.dumps({str(size): values for size, values in samples.items()}))


def orchestrate(args):
    if os.geteuid() != 0:
        raise SystemExit("需要 root：sudo python3 2026/experiments/06/curve.py ...")
    if not Path("/run/lab04/namespaces").exists():
        raise SystemExit("实验床尚未搭建，请先执行 sudo bash 2026/experiments/06/lab4_topo.sh up。")
    sizes = [int(item) for item in args.sizes.split(",")]
    base = [sys.executable, str(Path(__file__).resolve()), "--cc", args.cc, "--port", str(args.port)]
    count = len(sizes) * args.trials + 1
    server = subprocess.Popen(in_ns(args.dst, [*base, "--role", "recv", "--count", str(count)]))
    try:
        output = subprocess.run(
            in_ns(args.src, [*base, "--role", "send", "--dest", host_ip(args.dst), "--sizes", args.sizes,
                             "--trials", str(args.trials), "--gap-ms", str(args.gap_ms), "--seed", str(args.seed)]),
            check=True, capture_output=True, text=True, timeout=args.timeout).stdout
        server.wait(timeout=30)
    finally:
        if server.poll() is None:
            server.terminate()
    samples = {int(size): values for size, values in json.loads(output).items()}
    result = {"schema": "lab06.curve/v1", "label": args.label, "src": args.src, "dst": args.dst, "cc": args.cc,
              "gap_ms": args.gap_ms, "samples": {str(size): values for size, values in samples.items()}}
    out = Path(args.out) if args.out else RESULTS / f"{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result))
    print(f"[{args.label}] {args.src}→{args.dst} {args.cc}，空闲 {args.gap_ms:g} ms，每个大小 {args.trials} 次")
    print(f"{'字节':>10} {'中位数 ms':>11} {'最小 ms':>10} {'最大 ms':>10}")
    for size in sorted(samples):
        values = samples[size]
        print(f"{size:>10} {statistics.median(values) * 1000:>11.2f} {min(values) * 1000:>10.2f} {max(values) * 1000:>10.2f}")
    print(f"结果：{out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--role", choices=["run", "send", "recv"], default="run")
    parser.add_argument("--label", default="curve")
    parser.add_argument("--src", default="h1a")
    parser.add_argument("--dst", default="h3a")
    parser.add_argument("--dest", default="")
    parser.add_argument("--sizes", default=DEFAULT_SIZES)
    parser.add_argument("--trials", type=int, default=9)
    parser.add_argument("--gap-ms", type=float, default=300.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--cc", default="cubic")
    parser.add_argument("--port", type=int, default=7601)
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    {"run": orchestrate, "send": sender, "recv": receiver}[args.role](args)


if __name__ == "__main__":
    main()
