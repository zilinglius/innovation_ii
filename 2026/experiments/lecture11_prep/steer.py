"""请求分发器（给定；第 11 讲用的副本，joint、reported 与 estimate 要到 Lab 7 B 段完成 TODO 后才能用）：按策略把一批请求发给各个实例，记录每个请求的四段时间。需要 root 和已启动的实例。

用法（在本目录执行；先 lab4_topo.sh up，再 edge.sh up）：
  sudo python3 steer.py run --policy nearest --workload compute --label c-near
  sudo python3 steer.py run --policy joint   --workload mixed --requests 40 --gap-ms 50 --label m-joint
  python3 steer.py report LABEL [LABEL ...]      # 把几次运行排成表（只读文件，不需要 root）
  python3 steer.py show LABEL                    # 一次运行里各实例收到的请求数与四段时间
  python3 steer.py estimate --workload compute   # 用两张画像估计一个请求在各实例上的完成时间（TODO 4）

策略 --policy：
    nearest    就近：只看网络画像
    strongest  算力最强：只看算力画像
    least      最空闲：选还没返回的请求数最少的实例
    joint      联合代价：预计最早做完的实例（TODO 4、5）
    reported   按实例上报的状态估计（需要 TODO 4）：每隔 --report-ms 毫秒向各实例查询一次积压，两次查询之间不更新
    only:HOST  全部发给一个实例，用来单独观察它
    split:A,B  按请求类型分流：输入不小于 100 kB 的发给 A，其余发给 B（自己定一条规则时用）

负载 --workload（--requests 个请求，每隔 --gap-ms 毫秒发出一个）：
    upload     大输入、轻计算：输入 1 MB，计算 20 ms
    compute    小输入、重计算：输入 10 kB，计算 150 ms
    mixed      两种交替
    也可以用 --input-kb 与 --work-ms 自己指定

画像：--net 是 checkup.py 测的网络画像（至少包含客户端到各实例的主机对），--cpu 是 cpuprof.py 测的算力画像。
结果写到 /tmp/lab07-results/steer-LABEL.json。每个请求的四段：
    传输   发出 → 实例收齐输入          排队   收齐 → 开始计算
    计算   开始计算 → 算完              返回   算完 → 客户端收到结果
完成时间是四段之和；“批完成”是最后一个请求完成的时刻减第一个请求发出的时刻。
report 的表里只列前三段的平均值；“返回”通常只有一两毫秒，用 show 可以看到。
"""

import argparse
import json
from pathlib import Path
import threading
import time

from edge_client import enter, send, stat
from netprof import schema, sysrun
from netprof.hosts import load_hosts
from sched import steering

OUT = Path("/tmp/lab07-results")
WORKLOADS = {"upload": [(1_000_000, 20.0)], "compute": [(10_000, 150.0)],
             "mixed": [(1_000_000, 20.0), (10_000, 150.0)]}
POLICIES = {"nearest": steering.nearest, "strongest": steering.strongest, "least": steering.least}


def load_instances(net_path, cpu_path, client):
    try:
        net = schema.load(net_path)
        cpu = json.loads(Path(cpu_path).read_text())
    except (OSError, ValueError) as exc:
        raise SystemExit(f"读不了画像：{exc}")
    instances = []
    for name, info in cpu["instances"].items():
        mbps, rtt = net.throughput(client, name), net.rtt(client, name)
        if mbps is None or rtt is None:
            raise SystemExit(f"网络画像里没有 {client} → {name}：用 checkup.py --src {client} --dst 各实例 测一次。")
        instances.append(steering.Instance(name, mbps, rtt, info["rate"]))
    return instances


class Reported:
    """按实例上报的状态决策（任务 9）。每隔 report_ms 查询一次各实例的积压，换算成 free_at；
    两次查询之间，分发器不知道自己刚发出去的请求让实例变忙了多少。"""

    def __init__(self, hosts, report_ms, cc):
        self.hosts, self.every, self.cc = hosts, report_ms / 1000, cc
        self.free_at, self.last, self.polls = {}, None, 0

    def choose(self, request, instances, now):
        if self.last is None or now - self.last >= self.every:
            for item in instances:
                backlog = stat(self.hosts[item.name]["ip"], self.cc)["backlog_ms"]
                self.free_at[item.name] = now + backlog / 1000 / item.rate
            self.last, self.polls = now, self.polls + 1
        return min(instances, key=lambda item: steering.estimate(request, item, now, self.free_at[item.name])["finish"]).name


def run(args):
    sysrun.require_root()
    enter(args.client)
    hosts = load_hosts()
    if args.policy.startswith("only:"):
        instances = [steering.Instance(args.policy[5:], 0.0, 0.0, 0.0)]
        choose = lambda request, items, outstanding: items[0].name            # noqa: E731
    elif args.policy.startswith("split:"):
        big, small = args.policy[6:].split(",")
        instances = [steering.Instance(name, 0.0, 0.0, 0.0) for name in dict.fromkeys((big, small))]
        choose = lambda request, items, outstanding: big if request.input_bytes >= 100_000 else small   # noqa: E731
    else:
        instances = load_instances(args.net, args.cpu, args.client)
        choose = POLICIES.get(args.policy)
    joint = steering.Joint() if args.policy == "joint" else None
    if args.policy == "reported":
        joint = Reported(hosts, args.report_ms, args.cc)
    if choose is None and joint is None:
        raise SystemExit(f"没有策略 {args.policy}")
    kinds = [(int(args.input_kb * 1000), args.work_ms)] if args.input_kb is not None else WORKLOADS[args.workload]
    requests = [steering.Request(i, *kinds[i % len(kinds)]) for i in range(args.requests)]
    unknown = [item.name for item in instances if item.name not in hosts]
    if unknown:
        raise SystemExit(f"没有主机 {unknown[0]}")
    outstanding = {item.name: 0 for item in instances}
    lock = threading.Lock()
    records, threads = [], []

    def worker(request, name, record):
        try:
            record.update(send(request.id, request.input_bytes, request.work_ms, hosts[name]["ip"], args.cc))
        except OSError as exc:
            record["error"] = str(exc)
        with lock:
            outstanding[name] -= 1

    origin = time.monotonic()
    for request in requests:
        target = origin + request.id * args.gap_ms / 1000
        time.sleep(max(0.0, target - time.monotonic()))
        now = time.monotonic() - origin
        try:
            with lock:
                snapshot = dict(outstanding)
            name = joint.choose(request, instances, now) if joint else choose(request, instances, snapshot)
        except NotImplementedError as exc:
            raise SystemExit(f"第 11 讲的副本不带这一项（{exc}）：课上按 3.1 节手算，程序在 Lab 7 B 段完成。")
        with lock:
            outstanding[name] += 1
        record = {"id": request.id, "input_bytes": request.input_bytes, "work_ms": request.work_ms, "instance": name}
        records.append(record)
        thread = threading.Thread(target=worker, args=(request, name, record))
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()
    failed = [r for r in records if "error" in r]
    if failed:
        raise SystemExit(f"{len(failed)} 个请求失败，例如发给 {failed[0]['instance']} 的：{failed[0]['error']}；实例起来了吗（edge.sh status）？")
    for record in records:
        for key in ("sent", "recv_done", "start", "end", "done"):
            record[key] -= origin
    if args.policy == "reported":
        print(f"[上报] 间隔 {args.report_ms:g} ms，共查询 {joint.polls} 次")
    result = {"schema": "lab07.steer/v1", "label": args.label, "policy": args.policy, "workload": args.workload,
              "requests": args.requests, "gap_ms": args.gap_ms, "client": args.client, "cc": args.cc,
              "instances": [vars(item) for item in instances], "records": records}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"steer-{args.label}.json").write_text(json.dumps(result, ensure_ascii=False) + "\n")
    print(summary_line(result))


def stages(record):
    return (record["recv_done"] - record["sent"], record["start"] - record["recv_done"],
            record["end"] - record["start"], record["done"] - record["end"])


def summarize(result):
    records = result["records"]
    total = [r["done"] - r["sent"] for r in records]
    ordered = sorted(total)
    rank = lambda p: ordered[max(1, int(-(-len(ordered) * p // 1))) - 1]            # noqa: E731
    parts = [sum(stages(r)[k] for r in records) / len(records) for k in range(4)]
    counts = {}
    for record in records:
        counts[record["instance"]] = counts.get(record["instance"], 0) + 1
    return {"batch": max(r["done"] for r in records) - min(r["sent"] for r in records),
            "p50": rank(0.5), "p95": rank(0.95), "parts": parts, "counts": counts}


def summary_line(result):
    s = summarize(result)
    share = " ".join(f"{name}×{count}" for name, count in sorted(s["counts"].items()))
    return (f"[{result['label']}] {result['policy']} {result['workload']} {result['requests']} 个请求：批完成 {s['batch']:.3f} s，"
            f"单个请求 p50 {s['p50'] * 1000:.0f} ms、p95 {s['p95'] * 1000:.0f} ms；{share}")


def load(label):
    path = OUT / f"steer-{label}.json"
    if not path.exists():
        raise SystemExit(f"找不到 {path}：先用 steer.py run --label {label} 运行一次。")
    return json.loads(path.read_text())


def report(labels):
    print(f"{'标签':<7}{'策略':<12}{'负载':<6}{'批完成s'}{'p50ms':>6}{'p95ms':>6}{'传输':>3}{'排队':>3}{'计算':>3}  各实例请求数")
    for label in labels:
        result = load(label)
        s = summarize(result)
        share = " ".join(f"{name}×{count}" for name, count in sorted(s["counts"].items()))
        parts = "".join(f"{value * 1000:>5.0f}" for value in s["parts"][:3])
        print(f"{label:<9}{result['policy']:<14}{result['workload']:<8}{s['batch']:>7.3f}{s['p50'] * 1000:>6.0f}"
              f"{s['p95'] * 1000:>6.0f}{parts}  {share}")


def show(label):
    result = load(label)
    print(summary_line(result))
    print(f"{'实例':<6}{'请求数':>4}{'传输':>6}{'排队':>6}{'计算':>6}{'返回':>6}{'完成':>6}   （各段是该实例上请求的平均值，ms）")
    for name in sorted({r["instance"] for r in result["records"]}):
        rows = [r for r in result["records"] if r["instance"] == name]
        parts = [sum(stages(r)[k] for r in rows) / len(rows) * 1000 for k in range(4)]
        print(f"{name:<8}{len(rows):>7}" + "".join(f"{value:>8.1f}" for value in parts) + f"{sum(parts):>8.1f}")


def estimate_table(args):
    instances = load_instances(args.net, args.cpu, args.client)
    kinds = [(int(args.input_kb * 1000), args.work_ms)] if args.input_kb is not None else WORKLOADS[args.workload]
    try:
        steering.estimate(steering.Request(0, 1, 1.0), instances[0], 0.0, 0.0)
        print(f"{'输入kB':<6}{'计算ms':>6}  {'实例':<5}{'吞吐Mbit/s':>6}{'rate':>7}{'传输ms':>7}{'计算ms':>7}{'完成ms':>7}   （实例空闲、只发这一个请求时的估计）")
        for input_bytes, work_ms in kinds:
            request = steering.Request(0, input_bytes, work_ms)
            for item in instances:
                parts = steering.estimate(request, item, 0.0, 0.0)
                print(f"{input_bytes / 1000:<8g}{work_ms:>8g}  {item.name:<7}{item.mbps:>10.1f}{item.rate:>7.3f}"
                      f"{parts['transfer'] * 1000:>9.1f}{parts['compute'] * 1000:>9.1f}{parts['finish'] * 1000:>9.1f}")
    except NotImplementedError as exc:
        raise SystemExit(f"第 11 讲的副本不带这一项（{exc}）：课上按 3.1 节手算，程序在 Lab 7 B 段完成。")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    go = sub.add_parser("run", help="运行一批请求")
    go.add_argument("--policy", required=True)
    go.add_argument("--workload", choices=sorted(WORKLOADS), default="compute")
    go.add_argument("--input-kb", type=float, help="自定义输入大小，kB（10^3 字节）；与 --work-ms 一起用")
    go.add_argument("--work-ms", type=float, default=150.0, help="自定义计算量，毫秒 CPU 时间")
    go.add_argument("--requests", type=int, default=12)
    go.add_argument("--gap-ms", type=float, default=100.0, help="相邻两个请求的发出间隔")
    go.add_argument("--report-ms", type=float, default=0.0, help="reported 策略的查询间隔；0 表示每个请求之前都查询")
    go.add_argument("--label", required=True)
    go.add_argument("--client", default="h1a", help="分发器所在的主机（默认 h1a）")
    go.add_argument("--net", default="/tmp/lab07-results/net-profile.json")
    go.add_argument("--cpu", default="/tmp/lab07-results/cpu-profile.json")
    go.add_argument("--cc", default="cubic", help="拥塞控制算法，显式指定")
    rep = sub.add_parser("report", help="把几次运行排成表")
    rep.add_argument("labels", nargs="+")
    one = sub.add_parser("show", help="一次运行的分实例明细")
    one.add_argument("label")
    est = sub.add_parser("estimate", help="估计一个请求在各实例上的完成时间")
    est.add_argument("--workload", choices=sorted(WORKLOADS), default="compute")
    est.add_argument("--input-kb", type=float)
    est.add_argument("--work-ms", type=float, default=150.0)
    est.add_argument("--client", default="h1a")
    est.add_argument("--net", default="/tmp/lab07-results/net-profile.json")
    est.add_argument("--cpu", default="/tmp/lab07-results/cpu-profile.json")
    args = parser.parse_args()
    if args.command == "report":
        report(args.labels)
    elif args.command == "show":
        show(args.label)
    elif args.command == "estimate":
        estimate_table(args)
    else:
        if not sysrun.namespace_exists(args.client):
            raise SystemExit("实验床里没有客户端的 namespace；先执行 lab4_topo.sh up。")
        run(args)


if __name__ == "__main__":
    main()
