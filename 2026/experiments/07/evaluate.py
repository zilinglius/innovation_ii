"""在当前场景下比较几种放置策略（给定）。需要 root 和已搭好的实验床；打分策略需要 TODO 1、2。

用法（在本目录执行）：
  sudo python3 evaluate.py --profile 画像.json                       # 同机架优先、3 个随机种子、按画像打分，各跑 2 次
  sudo python3 evaluate.py --profile 画像.json --seeds 1,2 --repeats 3 --tag rack2
  python3 evaluate.py --show rack2                                   # 重新打印已有的结果，不运行作业，不需要 root

做的事：
  1. 用各策略选出放置：rack（同机架优先）、random-种子、score（按画像打分的第一名）；
     完成 TODO 3 后再加 score-shared（做共享上联修正后的第一名，与 score 相同时不重复运行）；
  2. 为每种放置算预测 JCT（不修正与修正两种，后者需要 TODO 3）；
  3. 每种放置用 jobrun.py 实际运行 repeats 次，记下每次的 JCT；
  4. 打印对照表，并把结果写到 /tmp/lab07-results/TAG.json。

各列：
    预测         predict_jct(shared=False)，秒
    共享预测     predict_jct(shared=True)，秒；没做 TODO 3 时显示 "-"
    实测         每次运行的 JCT，秒（表里保留两位小数，结果文件里是完整的数）
    平均         实测的平均值
    后悔值       这种放置的平均 JCT ÷ 各策略中最小的平均 JCT；1.00 表示它就是最好的

画像要与当前场景对应：画像里记着测量时的场景名，与实验床当前的场景不同时会提示。
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from jobrun import RESULTS, measured_jct
from netprof import schema, sysrun
from sched import cost, strategy
from sched.model import Job, ProfileGap, Table

HERE = Path(__file__).resolve().parent
OUT = Path("/tmp/lab07-results")


def run_job(label, placement, job):
    command = [sys.executable, str(HERE / "jobrun.py"), "--label", label, "--ps", placement.ps,
               "--workers", ",".join(placement.workers), "--model-mb", str(job.model_bytes / 1e6),
               "--rounds", str(job.rounds), "--compute-ms", str(job.compute_s * 1000)]
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"作业 {label} 运行失败：{(done.stderr or done.stdout).strip()[-300:]}")
    return measured_jct(json.loads((RESULTS / f"{label}.json").read_text()))


def predicted(table, placement, job, shared):
    try:
        return cost.predict_jct(table, placement, job, shared=shared)
    except NotImplementedError:
        return None


def print_table(rows):
    """对照表。每行不超过 86 个字符宽，3 次重复时在阅读版里也不折行。"""
    repeats = max(len(row["measured_s"]) for row in rows)

    def cell(value, width):
        return f"{value:>{width}.2f}" if value is not None else f"{'-':>{width}}"

    print(f"{'策略':<11}{'PS':<4}{'worker':<17}{'预测':>5}{'共享预测':>5}   实测{' ' * (7 * (repeats - 1))}{'平均':>5}{'后悔值':>4}")
    for row in rows:
        runs = "".join(f"{value:>7.2f}" for value in row["measured_s"]).ljust(7 * repeats)
        print(f"{row['strategy']:<13}{row['ps']:<4}{','.join(row['workers']):<17}{cell(row['predicted_s'], 7)}"
              f"{cell(row['predicted_shared_s'], 9)}{runs}{row['mean_s']:>7.2f}{row['regret']:>7.2f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", help="当前场景下测得的画像")
    parser.add_argument("--show", metavar="TAG", help="只重新打印 /tmp/lab07-results/TAG.json 里的结果")
    parser.add_argument("--seeds", default="1,2,3", help="随机策略的种子，逗号分隔（默认 1,2,3）")
    parser.add_argument("--repeats", type=int, default=2, help="每种放置运行几次（默认 2）")
    parser.add_argument("--tag", default="eval", help="结果文件名与作业标签的前缀")
    parser.add_argument("--n", type=int, default=4)
    parser.add_argument("--model-mb", type=float, default=1.0)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--compute-ms", type=float, default=200.0)
    args = parser.parse_args()
    if args.show:
        path = OUT / f"{args.show}.json"
        if not path.exists():
            raise SystemExit(f"找不到 {path}：先用 --profile 与 --tag {args.show} 运行一次评估。")
        print_table(json.loads(path.read_text())["rows"])
        return
    if not args.profile:
        parser.error("需要 --profile（运行评估）或 --show TAG（重新打印已有的结果）")
    sysrun.require_root()
    try:
        profile = schema.load(args.profile)
        table = Table(profile)
    except (OSError, schema.ProfileError, ProfileGap) as exc:
        raise SystemExit(f"读不了画像 {args.profile}：{exc}")
    job = Job(n=args.n, model_bytes=int(args.model_mb * 1e6), rounds=args.rounds, compute_s=args.compute_ms / 1000)

    now = sysrun.environment().get("scenario", "baseline")
    then = profile.environment.get("scenario", "baseline")
    if now != then:
        print(f"[提示] 画像是在场景 {then} 下测的，实验床现在是 {now}；预测与实测可能对不上。")

    chosen = [("rack", strategy.rack_first(table, job.n))]
    chosen += [(f"random-{seed}", strategy.random_placement(table, job.n, int(seed))) for seed in args.seeds.split(",") if seed]
    try:
        ranked = strategy.rank_placements(table, job, lambda t, p, j: cost.predict_jct(t, p, j))
        chosen.append(("score", ranked[0][1]))
    except NotImplementedError as exc:
        print(f"[提示] 没有 score 策略：需要先完成 {exc}。")
    try:
        ranked = strategy.rank_placements(table, job, lambda t, p, j: cost.predict_jct(t, p, j, shared=True))
        if ("score", ranked[0][1]) not in chosen:
            chosen.append(("score-shared", ranked[0][1]))
        else:
            print("[提示] 做共享上联修正后选出的放置与 score 相同，不重复运行。")
    except NotImplementedError:
        pass

    rows = []
    for name, placement in chosen:
        print(f"[运行] {name:<13}{placement.args()}", flush=True)
        measured = [run_job(f"{args.tag}-{name}-{k}", placement, job) for k in range(1, args.repeats + 1)]
        rows.append({"strategy": name, "ps": placement.ps, "workers": list(placement.workers),
                     "predicted_s": predicted(table, placement, job, False),
                     "predicted_shared_s": predicted(table, placement, job, True),
                     "measured_s": measured, "mean_s": sum(measured) / len(measured)})
    best = min(row["mean_s"] for row in rows)
    for row in rows:
        row["regret"] = row["mean_s"] / best

    print()
    print_table(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{args.tag}.json"
    out.write_text(json.dumps({"schema": "lab07.evaluate/v1", "profile": str(args.profile), "scenario_profile": then,
                               "scenario_now": now, "job": {"n": job.n, "model_bytes": job.model_bytes, "rounds": job.rounds,
                                                            "compute_s": job.compute_s},
                               "rows": rows}, ensure_ascii=False, indent=2) + "\n")
    print(f"\n[完成] 结果 {out}；每次作业的时间戳在 {RESULTS}/{args.tag}-*.json")


if __name__ == "__main__":
    main()
