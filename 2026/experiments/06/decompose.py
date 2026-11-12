"""打印一次作业的时间拆账（给定，调用 TODO 1、2）。

用法：python3 decompose.py /tmp/lab06-results/LABEL.json [更多 JSON ...]
"""

import json
from pathlib import Path
import sys

from jobkit.decompose import PHASES, job_breakdown

NAMES = {"compute": "计算", "upload": "上传", "wait": "等待", "download": "下载"}


def show(path):
    result = json.loads(Path(path).read_text())
    config = result["config"]
    if config["algo"] != "ps":
        print(f"作业 {result['label']} 是 {config['algo']}，没有 PS 的四段时间，请用 compare.py。")
        return
    summary = job_breakdown(result)
    print(f"作业 {result['label']}：{config['algo']}，N={len(config['workers'])}，"
          f"模型 {config['model_bytes'] / 1e6:g} MB，{config['rounds']} 轮，{config['cc']}")
    print(f"JCT = {summary['jct']:.3f} s")
    print(f"{'worker':<8}" + "".join(f"{NAMES[p] + ' s':>10}" for p in PHASES) + f"{'合计 s':>10}")
    for name, row in sorted(summary["per_worker"].items()):
        print(f"{name:<8}" + "".join(f"{row[p]:>10.3f}" for p in PHASES) + f"{row['total']:>10.3f}")
    print(f"{'平均':<8}" + "".join(f"{summary['mean'][p]:>10.3f}" for p in PHASES)
          + f"{sum(summary['mean'].values()):>10.3f}")
    print(f"{'占比':<8}" + "".join(f"{summary['share'][p] * 100:>9.1f}%" for p in PHASES))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for index, path in enumerate(sys.argv[1:]):
        if index:
            print()
        show(path)


if __name__ == "__main__":
    main()
