"""给作业选位置，并把几次作业的放置与结果排成一张表（给定）。只读文件，不需要 root。

一个“放置”是两件事：参数服务器（PS）放在哪台主机，worker 用哪几台主机。

用法（在本目录执行）：
  python3 place.py rack   [--ps h1a] [--n 4]     # 同机架优先：只看机架标签
  python3 place.py random [--seed 1] [--n 4]     # 随机：什么都不看
  python3 place.py report LABEL [LABEL ...]      # 读 /tmp/lab06-results 下的结果，排成表

rack 与 random 打印一行 "--ps … --workers …"，可以直接交给 jobrun.py：
  sudo python3 jobrun.py --label rack $(python3 place.py rack)

第 10 讲的副本只带这两种不看画像的策略；按画像打分的策略课上手算，程序在 Lab 7 A 段完成。

report 各列：
    PS、worker   这次作业的放置
    JCT          作业完成时间，秒
    每轮         JCT ÷ 轮数，ms
    最慢上传     平均每轮“算完 → PS 收齐这份梯度”最久的 worker 及其用时，ms
    最慢下发     平均每轮“barrier → 收齐模型”最久的 worker 及其用时，ms
"""

import argparse
import json
import random

from jobrun import RESULTS, measured_jct
from netprof.hosts import load_hosts


def rack_first(hosts, ps, n):
    """同机架优先：先用与 PS 同机架的主机，再按机架号从小到大依次取；同一机架内按主机名排序。"""
    home = hosts[ps]["rack"]
    others = sorted((name for name in hosts if name != ps),
                    key=lambda name: (hosts[name]["rack"] != home, hosts[name]["rack"], name))
    return ps, others[:n]


def random_placement(hosts, n, seed):
    """随机：从全部主机里不放回地抽 n + 1 台，第一台作 PS。种子相同，结果相同。"""
    picked = random.Random(seed).sample(sorted(hosts), n + 1)
    return picked[0], picked[1:]


def mean(values):
    values = list(values)
    return sum(values) / len(values)


def report(labels):
    print(f"{'标签':<10}{'PS':<5}{'worker':<22}{'JCT s':>8}{'每轮ms':>9}  {'最慢上传':<16}{'最慢下发':<16}")
    for label in labels:
        path = RESULTS / f"{label}.json"
        if not path.exists():
            raise SystemExit(f"找不到 {path}：先用 jobrun.py --label {label} 运行这次作业。")
        job = json.loads(path.read_text())
        config = job["config"]
        if config["algo"] != "ps":
            raise SystemExit(f"作业 {label} 是 {config['algo']}；place.py report 只读参数服务器作业。")
        barriers = [item["barrier_done"] for item in job["server"]["aggregates"]]
        upload, download = {}, {}
        for name, worker in job["workers"].items():
            server = job["server"]["workers"][name]
            upload[name] = mean(s["grad_last"] - r["compute_end"] for s, r in zip(server, worker["rounds"]))
            download[name] = mean(r["model_last"] - b for r, b in zip(worker["rounds"], barriers))
        slow_up, slow_down = max(upload, key=upload.get), max(download, key=download.get)
        jct = measured_jct(job)
        up_text = f"{slow_up} {upload[slow_up] * 1000:.1f} ms"
        down_text = f"{slow_down} {download[slow_down] * 1000:.1f} ms"
        print(f"{label:<12}{config['ps']:<5}{','.join(config['workers']):<22}{jct:>8.3f}{jct / config['rounds'] * 1000:>9.1f}"
              f"  {up_text:<20}{down_text}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    rack = sub.add_parser("rack", help="同机架优先")
    rack.add_argument("--ps", default="h1a", help="参数服务器所在主机（默认 h1a）")
    rack.add_argument("--n", type=int, default=4, help="worker 数（默认 4）")
    rand = sub.add_parser("random", help="随机")
    rand.add_argument("--seed", type=int, default=1)
    rand.add_argument("--n", type=int, default=4)
    sub.add_parser("score", help="按画像打分（Lab 7 A 段）")
    rep = sub.add_parser("report", help="把几次作业排成表")
    rep.add_argument("labels", nargs="+")
    args = parser.parse_args()
    hosts = load_hosts()
    if args.command == "report":
        report(args.labels)
        return
    if args.command == "score":
        raise SystemExit("第 10 讲的副本不带按画像打分的策略：课上按 3.2 节手算，程序在 Lab 7 A 段完成。")
    if not 1 <= args.n <= len(hosts) - 1:
        raise SystemExit(f"--n 应在 1 到 {len(hosts) - 1} 之间")
    if args.command == "rack":
        if args.ps not in hosts:
            raise SystemExit(f"没有主机 {args.ps}")
        ps, workers = rack_first(hosts, args.ps, args.n)
    else:
        ps, workers = random_placement(hosts, args.n, args.seed)
    print(f"--ps {ps} --workers {','.join(workers)}")


if __name__ == "__main__":
    main()
