"""打印作业某一轮的原始时间戳（给定），用来手算四段时间。

时间单位 ms，以这一轮最早的 compute_start 为 0。各列含义：
    计算开始、计算结束   worker 本地的时间戳
    sendall返回          上传调用返回的时刻，只代表数据交给了本地 TCP
    PS收齐               PS 收到这个 worker 梯度最后一个字节的时刻
    barrier              PS 收齐全部梯度并聚合完的时刻（每行相同）
    模型收齐             worker 收到模型最后一个字节的时刻

用法：python3 2026/experiments/lecture08_prep/timeline.py /tmp/lab06-results/LABEL.json [--round 5]
"""

import argparse
import json
from pathlib import Path

COLUMNS = ("计算开始", "计算结束", "sendall返回", "PS收齐", "barrier", "模型收齐")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job")
    parser.add_argument("--round", type=int, default=5, help="第几轮，从 0 数")
    args = parser.parse_args()
    job = json.loads(Path(args.job).read_text())
    config = job["config"]
    if config["algo"] != "ps":
        raise SystemExit(f"作业 {job['label']} 是 {config['algo']}，timeline.py 只读参数服务器的时间戳，请用 compare.py。")
    if not 0 <= args.round < config["rounds"]:
        raise SystemExit(f"--round 应在 0 到 {config['rounds'] - 1} 之间")
    index = args.round
    barrier = job["server"]["aggregates"][index]["barrier_done"]
    origin = min(worker["rounds"][index]["compute_start"] for worker in job["workers"].values())
    print(f"作业 {job['label']}：N={len(config['workers'])}，模型 {config['model_bytes'] / 1e6:g} MB，第 {index} 轮（从 0 数），单位 ms")
    print(f"{'worker':<8}" + "".join(f"{name:>13}" for name in COLUMNS))
    for name in sorted(job["workers"]):
        worker = job["workers"][name]["rounds"][index]
        server = job["server"]["workers"][name][index]
        values = (worker["compute_start"], worker["compute_end"], worker["local_send_done"],
                  server["grad_last"], barrier, worker["model_last"])
        print(f"{name:<8}" + "".join(f"{(value - origin) * 1000:>13.1f}" for value in values))


if __name__ == "__main__":
    main()
