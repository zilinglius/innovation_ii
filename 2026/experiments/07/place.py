"""给作业选位置、预测一种放置，并把几次作业的放置与结果排成一张表（给定）。只读文件，不需要 root。

用法（在本目录执行）：
  python3 place.py rack   [--ps h1a] [--n 4]                 # 同机架优先：只看机架标签
  python3 place.py random [--seed 1] [--n 4]                 # 随机：什么都不看
  python3 place.py score   --profile 画像.json [--shared] [--top 5]    # 按画像打分（需要 TODO 1、2；--shared 需要 TODO 3）
  python3 place.py predict --profile 画像.json --ps h1a --workers h1b,h2a,h3a,h4a [--shared]   # 预测一种放置（TODO 1）
  python3 place.py report LABEL [LABEL ...]                  # 读 /tmp/lab06-results 下的结果，排成表

rack、random 与 score 的第一行是 "--ps … --workers …"，可以直接交给 jobrun.py：
  sudo python3 jobrun.py --label rack $(python3 place.py rack)
  sudo python3 jobrun.py --label score $(python3 place.py score --profile 画像.json | head -1)

作业的大小用 --n、--model-mb、--rounds、--compute-ms 指定，默认值与 jobrun.py 相同。

report 各列：
    PS、worker   这次作业的放置
    JCT          作业完成时间，秒
    每轮         JCT ÷ 轮数，ms
    最慢上传     平均每轮“算完 → PS 收齐这份梯度”最久的 worker 及其用时，ms
    最慢下发     平均每轮“barrier → 收齐模型”最久的 worker 及其用时，ms
"""

import argparse
import json

from jobrun import RESULTS, measured_jct
from netprof import schema
from netprof.hosts import load_hosts
from sched import cost, strategy
from sched.model import Job, Placement, ProfileGap, Table


class LabelTable:
    """没有画像时的主机表：只有主机名和机架标签，够 rack 与 random 用。"""

    def __init__(self):
        hosts = load_hosts()
        self.hosts = sorted(hosts)
        self.rack = {name: info["rack"] for name, info in hosts.items()}


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


def load_table(path):
    try:
        return Table(schema.load(path))
    except (OSError, schema.ProfileError, ProfileGap) as exc:
        raise SystemExit(f"读不了画像 {path}：{exc}")


def job_options(parser):
    parser.add_argument("--n", type=int, default=4, help="worker 数（默认 4）")
    parser.add_argument("--model-mb", type=float, default=1.0, help="模型大小，MB（默认 1）")
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--compute-ms", type=float, default=200.0, help="每个 worker 每轮的计算时间（默认 200）")


def job_of(args):
    return Job(n=args.n, model_bytes=int(args.model_mb * 1e6), rounds=args.rounds, compute_s=args.compute_ms / 1000)


def todo(exc):
    raise SystemExit(f"这一步需要先完成 {exc}（见 sched/cost.py 与 sched/strategy.py）。")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    rack = sub.add_parser("rack", help="同机架优先")
    rack.add_argument("--ps", default="h1a", help="参数服务器所在主机（默认 h1a）")
    rack.add_argument("--n", type=int, default=4, help="worker 数（默认 4）")
    rand = sub.add_parser("random", help="随机")
    rand.add_argument("--seed", type=int, default=1)
    rand.add_argument("--n", type=int, default=4)
    score = sub.add_parser("score", help="按画像打分，列出预测最好的几种放置")
    score.add_argument("--profile", required=True)
    score.add_argument("--shared", action="store_true", help="做共享上联修正（TODO 3）")
    score.add_argument("--top", type=int, default=5, help="列出前几名（默认 5）")
    job_options(score)
    predict = sub.add_parser("predict", help="预测一种放置的每轮时间与 JCT")
    predict.add_argument("--profile", required=True)
    predict.add_argument("--ps", required=True)
    predict.add_argument("--workers", required=True, help="逗号分隔")
    predict.add_argument("--shared", action="store_true")
    job_options(predict)
    rep = sub.add_parser("report", help="把几次作业排成表")
    rep.add_argument("labels", nargs="+")
    args = parser.parse_args()

    if args.command == "report":
        report(args.labels)
        return
    if args.command in ("rack", "random"):
        table = LabelTable()
        if not 1 <= args.n <= len(table.hosts) - 1:
            raise SystemExit(f"--n 应在 1 到 {len(table.hosts) - 1} 之间")
        if args.command == "rack":
            if args.ps not in table.hosts:
                raise SystemExit(f"没有主机 {args.ps}")
            print(strategy.rack_first(table, args.n, args.ps).args())
        else:
            print(strategy.random_placement(table, args.n, args.seed).args())
        return

    table, job = load_table(args.profile), job_of(args)
    try:
        if args.command == "predict":
            placement = Placement(args.ps, tuple(args.workers.split(",")))
            unknown = [name for name in (placement.ps, *placement.workers) if name not in table.hosts]
            if unknown or placement.ps in placement.workers or len(set(placement.workers)) != len(placement.workers):
                raise SystemExit(f"放置不合法：{placement.args()}")
            job = Job(n=len(placement.workers), model_bytes=job.model_bytes, rounds=job.rounds, compute_s=job.compute_s)
            parts = cost.predict_round(table, placement, job, shared=args.shared)
            print(f"{placement.args()}")
            print(f"每轮 {parts['round'] * 1000:.1f} ms = 计算 {parts['compute'] * 1000:.1f} + 上传 {parts['upload'] * 1000:.1f}"
                  f" + 下发 {parts['download'] * 1000:.1f}；{job.rounds} 轮预测 JCT {job.rounds * parts['round']:.2f} s"
                  + ("（含共享上联修正）" if args.shared else ""))
            return
        ranked = strategy.rank_placements(table, job, lambda t, p, j: cost.predict_jct(t, p, j, shared=args.shared))
    except NotImplementedError as exc:
        todo(exc)
    best = ranked[0][0]
    print(ranked[0][1].args())
    print(f"# 候选 {len(ranked)} 种；预测最好 {best:.2f} s，最差 {ranked[-1][0]:.2f} s；"
          f"与最好相差 2% 以内的有 {sum(value <= best * 1.02 for value, _ in ranked)} 种"
          + ("；含共享上联修正" if args.shared else ""))
    for rank, (value, placement) in enumerate(ranked[:args.top], start=1):
        print(f"# {rank:>2}  {value:>7.2f} s  {placement.args()}")


if __name__ == "__main__":
    main()
