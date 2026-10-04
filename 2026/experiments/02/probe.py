#!/usr/bin/env python3
"""
单向 UDP 探针：量“一条在传的数据流被打断了多久”。

  接收端（先起）：sudo ip netns exec h2a python3 2026/experiments/02/probe.py recv
  发送端：        sudo ip netns exec h1a python3 2026/experiments/02/probe.py send --to 10.0.2.11 --seconds 30

发送端每个包带序号与发送时刻；接收端按序号找空洞，用**发送端的时间戳**算每个空洞的长度
（首个丢失序号的发送时刻 → 空洞之后第一个收到的包的发送时刻），所以不需要两端时钟同步。
100 pps 时分辨率 10 ms。

与 ping 的差别：ping 的丢包同时包含去程与回程两个方向的收敛；探针只量一个方向，
去程与回程可以分开量（把 send / recv 两端调换即可）。

只用标准库，直接用系统 python3 运行即可。
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import time

MAGIC = b"LSRP"
FMT = "!4sqd"                 # magic, seq (int64), 发送时刻 (double, time.time())
SIZE = struct.calcsize(FMT)
END_SEQ = -1


def send(args: argparse.Namespace) -> int:
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  if args.sport:
    sock.bind(("", args.sport))
  dst = (args.to, args.port)
  interval = 1.0 / args.pps
  total = int(args.seconds * args.pps)
  payload_pad = b"\0" * max(0, args.size - SIZE)
  print(f"sending {total} packets to {args.to}:{args.port} at {args.pps} pps "
        f"({args.seconds}s, {args.size} bytes each, sport {args.sport or 'ephemeral'})")
  t_start = time.perf_counter()
  for seq in range(total):
    sock.sendto(struct.pack(FMT, MAGIC, seq, time.time()) + payload_pad, dst)
    target = t_start + (seq + 1) * interval
    now = time.perf_counter()
    if target > now:
      time.sleep(target - now)
  for _ in range(5):
    sock.sendto(struct.pack(FMT, MAGIC, END_SEQ, time.time()), dst)
    time.sleep(0.05)
  print(f"done: {total} packets in {time.perf_counter() - t_start:.2f}s")
  return 0


def recv(args: argparse.Namespace) -> int:
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.bind(("", args.port))
  sock.settimeout(1.0)
  print(f"listening on udp/{args.port} (Ctrl-C or END marker to finish)")
  got = {}                  # seq -> 发送时刻
  t_first = None
  deadline = None
  try:
    while True:
      try:
        data, _ = sock.recvfrom(65535)
      except socket.timeout:
        if deadline is not None and time.time() > deadline:
          break
        continue
      if len(data) < SIZE or data[:4] != MAGIC:
        continue
      _, seq, ts = struct.unpack(FMT, data[:SIZE])
      if seq == END_SEQ:
        break
      if t_first is None:
        t_first = ts
        deadline = None
      got[seq] = ts
      if args.report and seq % (args.report) == 0:
        print(f"  seq {seq:6d}  received so far {len(got)}", flush=True)
  except KeyboardInterrupt:
    pass
  return report(got, t_first)


def report(got: dict, t_first) -> int:
  if not got:
    print("no packets received")
    return 1
  max_seq = max(got)
  expected = max_seq + 1
  lost = expected - len(got)
  print(f"received {len(got)} / {expected} (up to seq {max_seq}), lost {lost} "
        f"({100.0 * lost / expected:.1f}%)")
  # 找空洞：连续的缺失序号段
  gaps = []
  seq = 0
  while seq <= max_seq:
    if seq in got:
      seq += 1
      continue
    start = seq
    while seq <= max_seq and seq not in got:
      seq += 1
    end = seq - 1                          # 最后一个丢失的序号
    # 空洞长度：用发送端时间戳——上一个收到的包 与 下一个收到的包 的发送时刻之差
    prev_ts = got.get(start - 1)
    next_ts = got.get(end + 1)
    if prev_ts is not None and next_ts is not None:
      length = next_ts - prev_ts
    else:
      length = None
    gaps.append((start, end, length))
  if not gaps:
    print("no gaps: the flow was never interrupted")
    return 0
  print(f"{len(gaps)} gap(s):")
  for start, end, length in gaps:
    when = got[start - 1] - t_first if (start - 1) in got else 0.0
    n = end - start + 1
    if length is None:
      print(f"  seq {start}..{end}  {n} packets  (at the very edge, length unknown)")
    else:
      print(f"  seq {start}..{end}  {n} packets  {length * 1000:.0f} ms  (starting {when:.1f}s into the run)")
  longest = max((g for g in gaps if g[2] is not None), key=lambda g: g[2], default=None)
  if longest:
    print(f"longest interruption: {longest[2] * 1000:.0f} ms ({longest[1] - longest[0] + 1} packets)")
  return 0


def main(argv) -> int:
  p = argparse.ArgumentParser(description="单向 UDP 探针：测数据流被打断的时长")
  sub = p.add_subparsers(dest="mode", required=True)
  ps = sub.add_parser("send")
  ps.add_argument("--to", required=True, help="接收端地址")
  ps.add_argument("--port", type=int, default=9100)
  ps.add_argument("--sport", type=int, default=0, help="固定源端口（ECMP 实验用）")
  ps.add_argument("--pps", type=int, default=100)
  ps.add_argument("--seconds", type=float, default=30)
  ps.add_argument("--size", type=int, default=64, help="报文大小（字节）")
  pr = sub.add_parser("recv")
  pr.add_argument("--port", type=int, default=9100)
  pr.add_argument("--report", type=int, default=0, help="每收到这么多包打印一行进度（0 = 不打印）")
  args = p.parse_args(argv)
  return send(args) if args.mode == "send" else recv(args)


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
