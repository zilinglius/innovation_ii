"""在实验床上运行一次分布式作业，把各进程的时间戳合并成一个 JSON（给定）。

--algo ps 是参数服务器；--algo ring 是 Ring AllReduce（需要先完成 TODO 5），没有 PS，
--order 决定环序：given 按 --workers 的顺序，random 用 --order-seed 打乱，topo 用 TODO 7。

需要 root 和已搭好的实验床（lab4_topo.sh up）。PS 默认在 h1a；--n N 取默认 worker 列表的前 N 台，
--workers 可以直接列出主机。每轮本地计算时间可以用 --compute-ms 指定（每个 worker 相同），也可以用 --compute-total-ms
指定总计算量（每个 worker 分到 总量/N，用来做“加 worker 划不划算”的对照）。

结果写到 --out，格式 lab06.jobrun/v1；同时打印实测 JCT。
"""

import argparse
import json
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
DEFAULT_WORKERS = "h3a,h2a,h4a,h1b,h2b,h3b,h4b"
HOSTS_ALL = [f"h{rack}{side}" for rack in range(1, 5) for side in "ab"]
RESULTS = Path("/tmp/lab06-results")


def host_ip(name):
    match = re.fullmatch(r"h([1-4])([ab])", name)
    if not match:
        raise SystemExit(f"未知主机 {name}（应为 h1a–h4b）")
    return f"10.0.{match.group(1)}.{11 if match.group(2) == 'a' else 12}"


def rack_of(name):
    host_ip(name)
    return int(name[1])


def cross_rack_edges(order):
    if len(order) < 2:
        return 0
    return sum(rack_of(a) != rack_of(b) for a, b in zip(order, order[1:] + order[:1]))


def in_ns(name, argv):
    return ["ip", "netns", "exec", name, *argv]


def parse_straggler(text):
    if not text:
        return {}
    result = {}
    for item in text.split(","):
        name, _, factor = item.partition(":")
        host_ip(name)
        result[name] = float(factor)
    return result


def interpreter(compute):
    if compute == "sleep":
        return sys.executable
    venv = HERE / ".venv/bin/python"
    if not venv.exists():
        raise SystemExit("--compute numpy 需要先执行 uv sync --project 2026/experiments/06 --frozen")
    return str(venv)


def read_tx_bytes():
    """读 8 台 host 的 eth0 累计收发字节，用来核对接口上真实走过的流量。"""
    counters = {}
    for rack in range(1, 5):
        for side in "ab":
            name = f"h{rack}{side}"
            values = []
            for field in ("tx_bytes", "rx_bytes"):
                path = f"/sys/class/net/eth0/statistics/{field}"
                values.append(int(subprocess.run(in_ns(name, ["cat", path]), check=True, capture_output=True, text=True).stdout))
            counters[name] = values
    return counters


def counter_delta(before, after):
    return {name: {"tx": after[name][0] - before[name][0], "rx": after[name][1] - before[name][1]} for name in before}


def ring_order(args, workers):
    if args.order == "given":
        return workers
    if args.order == "random":
        shuffled = list(workers)
        random.Random(args.order_seed).shuffle(shuffled)
        return shuffled
    from jobkit.ring import topology_ring_order

    return topology_ring_order(workers, rack_of)


def run_ring(args, workers, per_worker, stragglers, model_bytes):
    order = ring_order(args, workers)
    if sorted(order) != sorted(workers):
        raise SystemExit("环序必须是 worker 的一个排列")
    python = sys.executable
    children, names = [], []
    before = read_tx_bytes()
    try:
        for rank, name in enumerate(order):
            seconds = per_worker * stragglers.get(name, 1.0) / 1000
            argv = [python, str(HERE / "job.py"), "ring", "--name", name, "--rank", str(rank), "--size", str(len(order)),
                    "--server", host_ip(order[(rank + 1) % len(order)]), "--port", str(args.port),
                    "--rounds", str(args.rounds), "--model-bytes", str(model_bytes), "--cc", args.cc,
                    "--compute-seconds", str(seconds), "--slow-prob", str(args.slow_prob),
                    "--slow-seconds", str(args.slow_ms / 1000), "--seed", str(rank + 1 + args.seed * 1000)]
            children.append(subprocess.Popen(in_ns(name, argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True))
            names.append(name)
        for child, name in zip(children, names):
            if child.stdout.readline().strip() != "READY":
                raise SystemExit(f"{name} 没有就绪，见上面的错误输出。")
        for child in children:
            child.stdin.write("GO\n")
            child.stdin.flush()
        outputs = [child.stdout.read() for child in children]
        for child in children:
            child.wait(timeout=args.timeout)
        if any(child.returncode for child in children):
            raise SystemExit("有进程异常退出，见上面的错误输出。")
    finally:
        for child in children:
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
    results = [json.loads(text) for text in outputs]
    if not all(item["correct"] for item in results):
        raise SystemExit("AllReduce 结果不正确：至少一个节点拿到的向量和预期不同。")
    return {
        "schema": "lab06.jobrun/v1",
        "label": args.label,
        "config": {"algo": "ring", "ps": None, "workers": order, "order": args.order, "model_bytes": model_bytes,
                   "rounds": args.rounds, "compute": "sleep", "compute_ms_per_worker": per_worker,
                   "stragglers": stragglers, "slow_prob": args.slow_prob, "slow_ms": args.slow_ms, "cc": args.cc,
                   "cross_rack_edges": cross_rack_edges(order)},
        "workers": {item["name"]: item for item in results},
        "net": counter_delta(before, read_tx_bytes()),
    }


def run_job(args):
    workers = HOSTS_ALL if args.workers == "all" else [name for name in args.workers.split(",") if name]
    if args.n is not None:
        if not 1 <= args.n <= len(workers):
            raise SystemExit(f"--n 应在 1 到 {len(workers)} 之间")
        workers = workers[:args.n]
    if len(set(workers)) != len(workers):
        raise SystemExit("--workers 里有重复的主机")
    if args.algo == "ps" and args.ps in workers:
        raise SystemExit(f"PS 所在主机 {args.ps} 不能同时当 worker；环上才能用全部 8 台")
    if not Path("/run/lab04/namespaces").exists():
        raise SystemExit("实验床尚未搭建，请先执行 sudo bash 2026/experiments/06/lab4_topo.sh up。")
    per_worker = args.compute_total_ms / len(workers) if args.compute_total_ms is not None else args.compute_ms
    stragglers = parse_straggler(args.straggler)
    model_bytes = int(args.model_mb * 1_000_000)
    if args.compute == "numpy" and model_bytes % 8:
        raise SystemExit("--compute numpy 要求模型字节数是 8 的倍数")
    if args.algo == "ring":
        if args.compute != "sleep":
            raise SystemExit("--algo ring 只支持占位计算（--compute sleep）")
        return run_ring(args, workers, per_worker, stragglers, model_bytes)
    python = interpreter(args.compute)
    before = read_tx_bytes()
    common = [python, str(HERE / "job.py")]
    shared = ["--port", str(args.port), "--rounds", str(args.rounds), "--model-bytes", str(model_bytes),
              "--compute", args.compute, "--cc", args.cc]
    server = subprocess.Popen(in_ns(args.ps, [*common, "server", "--workers", str(len(workers)), *shared]),
                              stdout=subprocess.PIPE, text=True)
    children = [server]
    try:
        for index, name in enumerate(workers):
            seconds = per_worker * stragglers.get(name, 1.0) / 1000
            iters = round(args.iters * stragglers.get(name, 1.0))
            children.append(subprocess.Popen(
                in_ns(name, [*common, "worker", "--name", name, "--server", host_ip(args.ps), *shared,
                             "--compute-seconds", str(seconds), "--iters", str(iters),
                             "--slow-prob", str(args.slow_prob), "--slow-seconds", str(args.slow_ms / 1000),
                             "--seed", str(index + 1 + args.seed * 1000)]),
                stdout=subprocess.PIPE, text=True))
        outputs = [child.communicate(timeout=args.timeout)[0] for child in children]
        if any(child.returncode for child in children):
            raise SystemExit("有进程异常退出，见上面的错误输出。")
    finally:
        for child in children:
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
    server_result = json.loads(outputs[0])
    worker_results = [json.loads(text) for text in outputs[1:]]
    return {
        "schema": "lab06.jobrun/v1",
        "label": args.label,
        "config": {"algo": "ps", "ps": args.ps, "workers": workers, "model_bytes": model_bytes,
                   "rounds": args.rounds, "compute": args.compute, "compute_ms_per_worker": per_worker,
                   "stragglers": stragglers, "slow_prob": args.slow_prob, "slow_ms": args.slow_ms, "cc": args.cc},
        "server": server_result,
        "workers": {item["name"]: item for item in worker_results},
        "net": counter_delta(before, read_tx_bytes()),
    }


def measured_jct(result):
    records = [r for worker in result["workers"].values() for r in worker["rounds"]]
    key = "ring_end" if result["config"]["algo"] == "ring" else "model_last"
    return max(r[key] for r in records) - min(r["compute_start"] for r in records)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default="job")
    parser.add_argument("--algo", choices=["ps", "ring"], default="ps")
    parser.add_argument("--order", choices=["given", "random", "topo"], default="given", help="环序，只对 ring 有效")
    parser.add_argument("--order-seed", type=int, default=1)
    parser.add_argument("--slow-prob", type=float, default=0.0, help="每个 worker 每轮变慢的概率，只支持占位计算")
    parser.add_argument("--slow-ms", type=float, default=0.0, help="变慢时多等的时间")
    parser.add_argument("--seed", type=int, default=0, help="变慢抽样的种子")
    parser.add_argument("--ps", default="h1a")
    parser.add_argument("--workers", default=DEFAULT_WORKERS, help="逗号分隔的 worker 主机；all 表示全部 8 台（只用于 ring）")
    parser.add_argument("--n", type=int, default=None, help="只用 --workers 列表的前 N 台")
    parser.add_argument("--model-mb", type=float, default=1.0, help="梯度与模型的大小，MB（10^6 字节）")
    parser.add_argument("--rounds", type=int, default=10)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--compute-ms", type=float, default=200.0, help="每个 worker 每轮的计算时间")
    group.add_argument("--compute-total-ms", type=float, default=None, help="每轮总计算量，平分给 N 个 worker")
    parser.add_argument("--compute", choices=["sleep", "numpy"], default="sleep")
    parser.add_argument("--iters", type=int, default=50, help="numpy 模式下每轮的梯度计算次数")
    parser.add_argument("--straggler", default="", help="慢节点，如 h3a:3 表示 h3a 的计算时间乘 3")
    parser.add_argument("--cc", default="cubic", help="拥塞控制算法，显式指定，默认 cubic")
    parser.add_argument("--port", type=int, default=7600)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("需要 root：sudo python3 2026/experiments/06/jobrun.py ...")
    result = run_job(args)
    out = Path(args.out) if args.out else RESULTS / f"{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result))
    config = result["config"]
    print(f"[{args.label}] {config['algo']} N={len(config['workers'])} 模型 {args.model_mb:g} MB {config['rounds']} 轮 "
          f"{config['cc']}：JCT = {measured_jct(result):.3f} s，结果 {out}")


if __name__ == "__main__":
    main()
