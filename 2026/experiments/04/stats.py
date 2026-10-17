"""课堂统计助手：把 ping 输出或逐行数字变成样本统计量。

  ping … | python3 2026/experiments/04/stats.py            # 分位数、均值、总体标准差
  ping … | python3 2026/experiments/04/stats.py --jitter   # 另算相邻差（IPDV）与相对最小值（PDV）
  printf '95.1\\n95.4\\n' | python3 2026/experiments/04/stats.py --ci   # 另算均值的 95% t 区间

ping 输出按 icmp_seq 排序后取 time= 的值；否则每行取一个数。
分位数用最近秩法：第 p 分位数取从小到大第 ceil(p·n) 个样本。换一种分位数算法，小样本的结果会不同，
所以报告里要写明方法。只用标准库，可直接用系统 python3 运行。
"""

import argparse
import math
import re
import statistics
import sys

# 自由度 1–30 的双侧 95% t 分位数；超过 30 时用 30 的值，偏保守。
T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
       2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
       2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def read_samples(text):
    pings = re.findall(r"icmp_seq=(\d+).*?time=([0-9.]+) ms", text)
    if pings:
        return [float(value) for _, value in sorted(pings, key=lambda row: int(row[0]))]
    return [float(line) for line in text.split() if line.strip()]


def rank(sorted_values, p):
    return sorted_values[max(1, math.ceil(p * len(sorted_values))) - 1]


def describe(values):
    ordered = sorted(values)
    return (f"n={len(values)} min={ordered[0]:.3f} p10={rank(ordered, 0.1):.3f} "
            f"p50={rank(ordered, 0.5):.3f} p90={rank(ordered, 0.9):.3f} max={ordered[-1]:.3f} "
            f"mean={statistics.fmean(values):.3f} sd={statistics.pstdev(values):.3f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jitter", action="store_true", help="另算 IPDV 与 PDV")
    parser.add_argument("--ci", action="store_true", help="另算均值的 95%% t 区间")
    args = parser.parse_args()
    values = read_samples(sys.stdin.read())
    if not values:
        sys.exit("没有读到样本")
    print("样本  ", describe(values))
    if args.jitter and len(values) > 1:
        ipdv = [abs(b - a) for a, b in zip(values, values[1:])]
        floor = min(values)
        print("|IPDV|", describe(ipdv), " # 相邻两个样本之差的绝对值")
        print("PDV   ", describe([v - floor for v in values]), " # 每个样本减去样本最小值")
    if args.ci and len(values) > 1:
        mean = statistics.fmean(values)
        s = statistics.stdev(values)
        t = T95[min(len(values) - 1, len(T95)) - 1]
        half = t * s / math.sqrt(len(values))
        print(f"均值 95% t 区间：{mean:.3f} ± {half:.3f}（s={s:.3f}，t={t}，n={len(values)}）")


if __name__ == "__main__":
    main()
