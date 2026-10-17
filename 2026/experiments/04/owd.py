"""单向延迟探针：发送端在报文里写入发送时刻，接收端用同一时钟减去它。

本实验床的所有 namespace 跑在同一台主机上，共用内核的 CLOCK_MONOTONIC，
两端读数可以直接相减；真实网络里两台主机的时钟须先同步（第 08 讲）。
先在接收端启动 recv，再在发送端启动 send；接收端结束后打印一行 JSON 摘要（单位 ms）。
recv 加 --samples FILE 时，另把每个包的单向延迟按序号写入 FILE（一行一个，丢失的包不写）。
"""

import argparse
import json
import socket
import statistics
import struct
import time

MAGIC = b"OWD1"
FMT = "!4sIq"  # magic、序号、发送时刻（ns）
SIZE = struct.calcsize(FMT)


def summarize(delays, count):
    values = sorted(delays.values())
    summary = {"sent": count, "received": len(values), "lost": count - len(values)}
    if values:
        deciles = statistics.quantiles(values, n=10) if len(values) > 1 else values * 9
        summary.update(
            min_ms=round(values[0], 3),
            median_ms=round(statistics.median(values), 3),
            p90_ms=round(deciles[-1], 3),
            max_ms=round(values[-1], 3),
        )
    return summary


def receive(port, count, wait, samples):
    delays = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", port))
        # 第一个包最多等 wait 秒；之后 1 秒内没有新包就认为发送已经结束。
        sock.settimeout(wait)
        while len(delays) < count:
            try:
                data, _ = sock.recvfrom(2048)
            except TimeoutError:
                break
            now = time.monotonic_ns()
            sock.settimeout(1)
            if len(data) < SIZE:
                continue
            magic, seq, sent = struct.unpack_from(FMT, data)
            if magic == MAGIC and seq < count:
                delays.setdefault(seq, (now - sent) / 1e6)
    if samples:
        with open(samples, "w") as stream:
            stream.writelines(f"{delays[seq]:.3f}\n" for seq in sorted(delays))
    print(json.dumps(summarize(delays, count)))


def send(destination, port, count, interval):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for seq in range(count):
            sock.sendto(struct.pack(FMT, MAGIC, seq, time.monotonic_ns()), (destination, port))
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    server = commands.add_parser("recv")
    server.add_argument("--port", type=int, default=9200)
    server.add_argument("--count", type=int, default=50)
    server.add_argument("--wait", type=float, default=10, help="等待第一个包的秒数")
    server.add_argument("--samples", help="把逐包单向延迟（ms）写入此文件")
    client = commands.add_parser("send")
    client.add_argument("--to", required=True, help="接收端地址")
    client.add_argument("--port", type=int, default=9200)
    client.add_argument("--count", type=int, default=50)
    client.add_argument("--interval", type=float, default=0.02, help="发送间隔（秒）")
    args = parser.parse_args()
    if args.count <= 0:
        parser.error("--count 必须大于零")
    if args.mode == "recv":
        receive(args.port, args.count, args.wait, args.samples)
    else:
        send(args.to, args.port, args.count, args.interval)


if __name__ == "__main__":
    main()
