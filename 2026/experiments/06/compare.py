"""把多次作业排成一张表（给定），只读文件，不需要 root，也不依赖 TODO。

用法：
  python3 2026/experiments/06/compare.py LABEL [LABEL ...]        # 结果在 /tmp/lab06-results 下
  python3 2026/experiments/06/compare.py --steps LABEL [LABEL ...]  # ring 每一步的平均用时
  python3 2026/experiments/06/compare.py --slow LABEL [LABEL ...]   # 注入随机变慢时，实际变慢的轮数

各列：
    算法、N、环序（ring）、跨机架边（ring）、JCT
    计算、通信    平均每轮每个 worker 的时间，ms；通信 = 这一轮的其余时间（ps 含等待 barrier）
    发送/S        平均每个 worker 每轮在应用层发出的字节数，以模型大小 S 为单位
    最忙发送      8 台 host 的 eth0 里发送最多的一台，MB，包含报文头和 ACK
"""

import json
from pathlib import Path
import sys

from jobrun import RESULTS, measured_jct


def row(label):
    job = json.loads((RESULTS / f"{label}.json").read_text())
    config = job["config"]
    workers = job["workers"]
    end_key = "ring_end" if config["algo"] == "ring" else "model_last"
    compute, communicate, sent = [], [], []
    for worker in workers.values():
        rounds = worker["rounds"]
        compute += [r["compute_end"] - r["compute_start"] for r in rounds]
        communicate += [r[end_key] - r["compute_end"] for r in rounds]
        sent.append(worker["bytes_sent"] / len(rounds) / config["model_bytes"])
    busiest = max(job["net"].items(), key=lambda item: item[1]["tx"])
    return (f"{label:<18}{config['algo']:<6}{len(workers):>3} {config.get('order', '-'):<8}"
            f"{str(config.get('cross_rack_edges', '-')):>5}{measured_jct(job):>10.3f}"
            f"{sum(compute) / len(compute) * 1000:>9.1f}{sum(communicate) / len(communicate) * 1000:>9.1f}"
            f"{sum(sent) / len(sent):>8.3f}{busiest[1]['tx'] / 1e6:>9.1f} {busiest[0]}")


def steps(label):
    """ring 的第 i 步用时：相邻两次 exchange 完成的时间差，第 1 步从本轮计算结束算起。"""
    job = json.loads((RESULTS / f"{label}.json").read_text())
    config = job["config"]
    if config["algo"] != "ring":
        raise SystemExit(f"{label} 不是 ring 作业")
    durations = []
    for worker in job["workers"].values():
        for record in worker["rounds"]:
            edges = [record["compute_end"], *record["step_ends"]]
            durations.append([b - a for a, b in zip(edges, edges[1:])])
    count = len(durations[0])
    means = [sum(row[i] for row in durations) / len(durations) * 1000 for i in range(count)]
    size = len(config["workers"])
    print(f"{label}：N={size}，每步传 {config['model_bytes'] // size} 字节，跨机架边 {config['cross_rack_edges']}，"
          f"共 {count} 步，平均每步用时（ms）")
    print("  " + " ".join(f"{value:.1f}" for value in means))


def slow_rounds(label):
    """一轮里只要有一个 worker 的计算时间超过 基础时间 + 变慢时间的一半，就算这一轮变慢了。"""
    job = json.loads((RESULTS / f"{label}.json").read_text())
    config = job["config"]
    threshold = (config["compute_ms_per_worker"] + config["slow_ms"] / 2) / 1000
    workers = list(job["workers"].values())
    if not config["slow_ms"]:
        print(f"{label:<18}{config['algo']:<6}N={len(workers):<3}JCT {measured_jct(job):>8.3f} s   未注入变慢")
        return
    slow = sum(any(w["rounds"][i]["compute_end"] - w["rounds"][i]["compute_start"] > threshold for w in workers)
               for i in range(config["rounds"]))
    print(f"{label:<18}{config['algo']:<6}N={len(workers):<3}JCT {measured_jct(job):>8.3f} s   "
          f"变慢的轮 {slow}/{config['rounds']}")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] in ("--steps", "--slow"):
        for label in sys.argv[2:]:
            (steps if sys.argv[1] == "--steps" else slow_rounds)(label)
        return
    print(f"{'标签':<16}{'算法':<4}{'N':>3} {'环序':<6}{'跨机架':>3}{'JCT s':>10}{'计算ms':>7}{'通信ms':>7}{'发送/S':>6}{'最忙发送MB':>6}")
    for label in sys.argv[1:]:
        print(row(label))


if __name__ == "__main__":
    main()
