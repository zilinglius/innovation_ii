"""长尾延迟测量：在一台 host 的 namespace 里运行，向后端扇出请求并统计延迟。

  sudo ip netns exec h1a python3 tailbench.py --fanout 10 --rounds 300 --slow-prob 0.01

一轮同时向 N 个分片发请求，全部回来才算完成。输出轮次延迟、单请求延迟、备份请求比例和按主副本的延迟，
并把完整样本写入 /tmp/lab05-results/<label>.json。只用 Python 标准库。
"""

import argparse
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tailkit import policy as policies  # noqa: E402
from tailkit import report, runner  # noqa: E402
from tailkit.rpc import Service  # noqa: E402

# 与 lab4_topo.sh 的地址约定一致：机架 i 用 10.0.i.0/24，host a、b 分别为 .11、.12。
ADDRESSES = {f"h{rack}{side}": f"10.0.{rack}.{ip}" for rack in range(1, 5) for side, ip in (("a", 11), ("b", 12))}
OTHERS = ["h1b", "h2a", "h2b", "h3a", "h3b", "h4a", "h4b"]


def hosts(text):
    names = [name for name in text.split(",") if name]
    for name in names:
        if name not in ADDRESSES:
            raise argparse.ArgumentTypeError(f"未知主机 {name}")
    return names


def parse():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fanout", type=int, default=10, help="每轮扇出的分片数 N")
    parser.add_argument("--rounds", type=int, default=300, help="计入统计的轮数")
    parser.add_argument("--warmup", type=int, default=5, help="预热轮数，不计入统计")
    parser.add_argument("--base-ms", type=float, default=5.0, help="每个请求的基础服务时间")
    parser.add_argument("--slow-ms", type=float, default=100.0, help="慢响应多等的时间")
    parser.add_argument("--slow-prob", type=float, default=0.0, help="单个请求变慢的概率 p")
    parser.add_argument("--resp-bytes", type=int, default=128, help="每个响应的字节数")
    parser.add_argument("--primaries", type=hosts, default=OTHERS, help="主副本主机，逗号分隔")
    parser.add_argument("--backups", type=hosts, default=[], help="备份副本主机，逗号分隔；对冲时必须给出")
    parser.add_argument("--hedge-ms", type=float, help="固定对冲延迟（毫秒）；不给就不对冲")
    parser.add_argument("--adaptive", type=float, metavar="Q", help="自适应对冲：用最近样本的第 Q 分位数（TODO 4）")
    parser.add_argument("--budget", type=float, metavar="RATIO", help="备份请求不超过主请求的 RATIO（TODO 5）")
    parser.add_argument("--max-inflight", type=int, metavar="K", help="同一轮最多 K 个请求同时在途（TODO 6）")
    parser.add_argument("--gap-ms", type=float, default=0.0, help="两轮之间的间隔（毫秒）")
    parser.add_argument("--port", type=int, default=7000)
    parser.add_argument("--cc", default="cubic", help="前端连接使用的拥塞控制算法")
    parser.add_argument("--label", default="run", help="结果文件名 /tmp/lab05-results/<label>.json")
    args = parser.parse_args()
    if (args.hedge_ms is not None or args.adaptive is not None) and not args.backups:
        parser.error("对冲需要同时给出 --backups")
    if args.budget is not None and args.hedge_ms is None and args.adaptive is None:
        parser.error("--budget 要与 --hedge-ms 或 --adaptive 一起用")
    return args


def choose_policy(args):
    if args.adaptive is not None:
        chosen = policies.AdaptiveDelay(q=args.adaptive)
    elif args.hedge_ms is not None:
        chosen = policies.FixedDelay(args.hedge_ms)
    else:
        return policies.NoHedge()
    return policies.BudgetedHedge(chosen, args.budget) if args.budget is not None else chosen


def main():
    args = parse()
    service = Service(args.resp_bytes, args.base_ms, args.slow_ms, args.slow_prob)
    policy = choose_policy(args)
    result = asyncio.run(runner.run(args.fanout, args.rounds, service, policy, args.primaries, args.backups,
                                    ADDRESSES, args.port, args.cc, args.warmup, args.gap_ms, args.max_inflight))
    result["config"] = vars(args) | {"policy": policy.name}
    path = report.save(result, args.label)

    extra = result["backups"] / result["requests"] * 100
    print(f"[{args.label}] N={args.fanout} 轮数={args.rounds} p={args.slow_prob:g} 对冲={policy.name} cc={args.cc}")
    print(f"  轮次延迟 ms   {report.line(report.describe(result['round_ms']))}")
    print(f"  单请求延迟 ms {report.line(report.describe(result['request_ms']))}")
    print(f"  请求 {result['requests']}，备份 {result['backups']}（额外负载 {extra:.1f}%），备份先回 {result['backup_wins']}")
    for host, values in sorted(result["per_host_ms"].items()):
        block = report.describe(values)
        print(f"  主副本 {host}: p50={block['p50']:.1f} p99={block['p99']:.1f} ms")
    print(f"  用时 {result['wall_seconds']:.1f} s；样本：{path}")


if __name__ == "__main__":
    main()
