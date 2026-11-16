"""算力画像（给定）：逐个实例发几个只有计算的探测请求，量出它的算力。需要 root 和已启动的实例。

用法（在本目录执行）：
  sudo python3 cpuprof.py                          # 写到 /tmp/lab07-results/cpu-profile.json
  sudo python3 cpuprof.py --probes 5 --work-ms 100 --out 文件

做法：实例空闲时，从客户端依次发 probes 个请求，每个请求输入 1 kB、计算 work_ms 毫秒（CPU 时间）；
一次只测一个实例、一次只有一个请求在算。实例回报计算开始与结束的时刻，
    rate = 工作量 ÷ 计算用的墙上时间
rate 为 1.0 表示相当于一个不受限的核；0.3 表示同样的计算要花 3.3 倍的时间。取各次的中位数。
画像只说明测量时的算力：限额改了、实例上有别的负载，都要重测。
"""

import argparse
import json
from pathlib import Path
import statistics
import time

from edge_client import enter, running_instances, send
from netprof import sysrun
from netprof.hosts import load_hosts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--probes", type=int, default=5, help="每个实例探测几次（默认 5）")
    parser.add_argument("--work-ms", type=float, default=100.0, help="每次探测的计算量（默认 100）")
    parser.add_argument("--client", default="h1a")
    parser.add_argument("--out", default="/tmp/lab07-results/cpu-profile.json")
    args = parser.parse_args()
    sysrun.require_root()
    enter(args.client)
    hosts = load_hosts()
    instances = {}
    for name in running_instances():
        walls = []
        for k in range(args.probes):
            record = send(k, 1000, args.work_ms, hosts[name]["ip"])
            walls.append((record["end"] - record["start"]) * 1000)
            time.sleep(0.05)
        rate = args.work_ms / statistics.median(walls)
        instances[name] = {"rate": round(rate, 4), "work_ms": args.work_ms,
                           "wall_ms": {"median": round(statistics.median(walls), 1), "min": round(min(walls), 1),
                                       "max": round(max(walls), 1), "n": len(walls)}}
        print(f"[算力] {name}  {args.work_ms:g} ms 的计算用了 {statistics.median(walls):.1f} ms"
              f"（{min(walls):.1f}–{max(walls):.1f}，n={len(walls)}）  rate {rate:.3f}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema": "lab07.cpuprofile/v1", "client": args.client, "instances": instances},
                              ensure_ascii=False, indent=2) + "\n")
    print(f"[完成] 算力画像 {out}")


if __name__ == "__main__":
    main()
