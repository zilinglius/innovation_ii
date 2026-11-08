"""拟合 α-β 并预测参数服务器作业（给定，调用 TODO 3、4）。

用法：
  python3 2026/experiments/06/fit.py /tmp/lab06-results/curve.json
  python3 2026/experiments/06/fit.py CURVE.json --max-bytes 1000000      # 只用不超过该大小的样本拟合
  python3 2026/experiments/06/fit.py CURVE.json --predict JOB.json ...   # 用拟合结果预测作业，与实测对比（ps 用 TODO 4，ring 用 TODO 6）
"""

import argparse
import json
from pathlib import Path
import statistics

from jobkit.alphabeta import fit_alpha_beta, predict_ps_round, predict_ring_round
from jobrun import measured_jct


def load_curve(path, max_bytes):
    data = json.loads(Path(path).read_text())
    sizes, medians = [], []
    for size, values in sorted(data["samples"].items(), key=lambda item: int(item[0])):
        if max_bytes is None or int(size) <= max_bytes:
            sizes.append(int(size))
            medians.append(statistics.median(values))
    return data, sizes, medians


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("curve")
    parser.add_argument("--max-bytes", type=int, default=None)
    parser.add_argument("--predict", nargs="*", default=[])
    args = parser.parse_args()
    data, sizes, medians = load_curve(args.curve, args.max_bytes)
    alpha, beta = fit_alpha_beta(sizes, medians)
    print(f"{data['src']}→{data['dst']} {data['cc']}，{len(sizes)} 种大小（每种取中位数）")
    print(f"α = {alpha * 1000:.2f} ms，β = {beta * 1e9:.2f} ns/字节，折合 {8 / beta / 1e6:.1f} Mbit/s")
    print(f"{'字节':>10} {'实测 ms':>10} {'拟合 ms':>10} {'偏差':>8}")
    for size, measured in zip(sizes, medians):
        fitted = alpha + beta * size
        print(f"{size:>10} {measured * 1000:>10.2f} {fitted * 1000:>10.2f} {(fitted - measured) / measured * 100:>7.0f}%")
    if args.predict:
        print()
        print(f"{'作业':<16}{'N':>3}{'预测 JCT s':>12}{'实测 JCT s':>12}{'偏差':>8}")
    for path in args.predict:
        job = json.loads(Path(path).read_text())
        config = job["config"]
        if config["compute"] != "sleep" or config["stragglers"] or config.get("slow_prob"):
            print(f"{job['label']:<16}跳过：TODO 4 的模型假设每个 worker 的计算时间相同且固定")
            continue
        predict = predict_ring_round if config["algo"] == "ring" else predict_ps_round
        predicted = predict(alpha, beta, config["model_bytes"], len(config["workers"]),
                            config["compute_ms_per_worker"] / 1000)["round"] * config["rounds"]
        actual = measured_jct(job)
        print(f"{job['label']:<16}{len(config['workers']):>3}{predicted:>12.3f}{actual:>12.3f}"
              f"{(predicted - actual) / actual * 100:>7.1f}%")


if __name__ == "__main__":
    main()
