"""把 tailbench.py 保存的结果排成一张表（给定）。只读 /tmp/lab05-results/ 下的文件，不发送任何报文。

  python3 2026/experiments/05/compare.py a-off a-on b-off b-on
  python3 2026/experiments/05/compare.py --predict --fast 8 --slow 108 amp-n1 amp-n10 amp-n100
  python3 2026/experiments/05/compare.py --tail 12 loss1

“慢轮”是轮次延迟超过 --slow-threshold 毫秒的轮。--predict 用 TODO 1、3 算出每一行的理论慢轮比例和
分位数预测；TODO 没写时只显示实测。--tail 另外列出最慢的若干轮，用来看延迟分布有没有断层。
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tailkit import predict, report  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("labels", nargs="+", help="tailbench.py 的 --label")
    parser.add_argument("--slow-threshold", type=float, default=50.0, help="慢轮的判定阈值（毫秒）")
    parser.add_argument("--tail", type=int, metavar="K", help="另外列出最慢的 K 轮（毫秒，从小到大）")
    parser.add_argument("--predict", action="store_true", help="另算理论慢轮比例与分位数预测")
    parser.add_argument("--fast", type=float, help="预测用：没有慢请求时一轮的延迟（毫秒）")
    parser.add_argument("--slow", type=float, help="预测用：有慢请求时一轮的延迟（毫秒）")
    args = parser.parse_args()
    if args.predict and (args.fast is None or args.slow is None):
        parser.error("--predict 需要 --fast 与 --slow")

    print(f"{'标签':<14}{'N':>4}{'轮p50':>9}{'轮p90':>9}{'轮p99':>9}{'慢轮':>8}{'备份/请求':>11}{'备份先回':>9}")
    for label in args.labels:
        data = report.load(label)
        rounds = data["round_ms"]
        block = report.describe(rounds)
        slow = sum(value > args.slow_threshold for value in rounds) / len(rounds)
        extra = data["backups"] / data["requests"]
        config = data["config"]
        print(f"{label:<14}{config['fanout']:>4}{block['p50']:>9.1f}{block['p90']:>9.1f}{block['p99']:>9.1f}"
              f"{slow:>8.1%}{extra:>11.1%}{data['backup_wins']:>9}")
        if args.tail:
            print(f"{'':<14}最慢 {args.tail} 轮：" + " ".join(f"{value:.0f}" for value in sorted(rounds)[-args.tail:]))
        if args.predict:
            try:
                theory = predict.slow_round_probability(config["slow_prob"], config["fanout"])
                values = predict.predict_round(config["slow_prob"], config["fanout"], args.fast, args.slow)
            except NotImplementedError as exc:
                print(f"{'':<14}（{exc}，只显示实测）")
                continue
            print(f"{'  预测':<14}{'':>4}{values[0.5]:>9.1f}{values[0.9]:>9.1f}{values[0.99]:>9.1f}{theory:>8.1%}")


if __name__ == "__main__":
    main()
