"""Lab 4 体检工具：测主机对之间的往返时间与吞吐，输出网络画像（profile.json，格式见 netprof/schema.py）。

从仓库根目录、在实验床搭好后运行（需要 root）：
  sudo 2026/experiments/04/.venv/bin/python 2026/experiments/04/checkup.py                  # 全部主机对
  sudo 2026/experiments/04/.venv/bin/python 2026/experiments/04/checkup.py --src h1a        # 只测 h1a 一行
  sudo 2026/experiments/04/.venv/bin/python 2026/experiments/04/checkup.py --dry-run        # 只看计划与预计用时

往返时间对每个无序主机对只测一次；吞吐对每个有向主机对按次重复，同一时刻只测一对（--concurrent 除外）。
原始输出（ping 文本、iperf3 JSON 等）存在画像旁的 .raw 目录，报告中的数字应能回溯到它们。
"""

import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

from netprof import extras, hosts as hostlib, measure, parse, schema, summary, sysrun

LAB = Path(__file__).resolve().parent
TRANSFER = LAB.parent / "03/transfer.py"
SPINES = ("r5", "r6")


def options():
    parser = argparse.ArgumentParser(description="Lab 4 体检工具：输出网络画像 profile.json")
    parser.add_argument("--hosts", help="主机表 JSON（默认用实验床的 8 台主机）")
    parser.add_argument("--src", help="只测这些源主机，逗号分隔，如 h1a,h2a")
    parser.add_argument("--dst", help="只测这些目的主机，逗号分隔")
    parser.add_argument("--pairs", help="直接给出有向主机对，如 h1a:h3a,h4a:h1a（覆盖 --src/--dst）")
    parser.add_argument("--rtt-count", type=int, default=20, help="每个无序对的 ping 次数（默认 20）")
    parser.add_argument("--rtt-interval", type=float, default=0.05, help="ping 间隔，秒（默认 0.05）")
    parser.add_argument("--tput-seconds", type=int, default=2, help="iperf3 计入统计的秒数 -t（默认 2）")
    parser.add_argument("--tput-omit", type=int, default=1, help="iperf3 开头忽略的秒数 -O（默认 1）")
    parser.add_argument("--tput-repeats", type=int, default=3, help="每个有向对重复次数（默认 3）")
    parser.add_argument("--skip-rtt", action="store_true", help="不测往返时间")
    parser.add_argument("--skip-tput", action="store_true", help="不测吞吐")
    parser.add_argument("--by-path", action="store_true", help="进阶：跨机架对分别钉在 r5、r6 上各测一遍吞吐")
    parser.add_argument("--owd", type=int, default=0, metavar="N", help="进阶：每个有向对发 N 个单向延迟探针")
    parser.add_argument("--curve", help="进阶：传输时间曲线的数据量（字节），逗号分隔，如 100000,1000000,10000000")
    parser.add_argument("--concurrent", action="store_true", help="挑战：所选有向对同时各测一次吞吐")
    parser.add_argument("--out", help="画像文件路径（默认 /tmp/lab04-results/profile-时间.json）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划与预计用时，不测量")
    return parser.parse_args()


def names(text):
    return None if not text else [part.strip() for part in text.split(",") if part.strip()]


def plan(opts, hostmap):
    if opts.pairs:
        pairs = hostlib.parse_pair_list(opts.pairs)
        unknown = {n for pair in pairs for n in pair} - set(hostmap)
        if unknown:
            raise SystemExit(f"主机表里没有：{', '.join(sorted(unknown))}")
    else:
        pairs = hostlib.ordered_pairs(hostmap, names(opts.src), names(opts.dst))
    if not pairs:
        raise SystemExit("没有可测的主机对：检查 --src、--dst 或 --pairs。")
    rtt_pairs = [] if opts.skip_rtt else hostlib.unordered_pairs(pairs, hostmap)
    tput_pairs = [] if opts.skip_tput else pairs
    path_pairs = [p for p in tput_pairs if opts.by_path and not hostlib.same_rack(hostmap, *p)]
    sizes = [int(s) for s in names(opts.curve)] if opts.curve else []
    # 每项开销中的常数（起停服务端、建连、进程启动）来自备课实测，量级正确即可。
    seconds = len(rtt_pairs) * (opts.rtt_count * opts.rtt_interval + 0.3)
    run = opts.tput_seconds + opts.tput_omit + 0.6
    seconds += (1 if opts.concurrent else len(tput_pairs) * opts.tput_repeats) * run
    seconds += len(path_pairs) * len(SPINES) * opts.tput_repeats * run
    seconds += len(pairs) * (opts.owd * 0.02 + 0.8) if opts.owd else 0
    seconds += len(pairs) * sum(0.6 + 8 * size / 40e6 for size in sizes)
    print(f"[计划] {len(pairs)} 个有向对；往返时间 {len(rtt_pairs)} 个无序对 × {opts.rtt_count} 个探测；"
          f"吞吐 {len(tput_pairs)} 对 × {1 if opts.concurrent else opts.tput_repeats} 次 × "
          f"(-O {opts.tput_omit} + -t {opts.tput_seconds}) 秒"
          + (f"；分路 {len(path_pairs)} 对" if path_pairs else "")
          + (f"；单向延迟 {opts.owd} 包" if opts.owd else "")
          + (f"；传输曲线 {len(sizes)} 档" if sizes else ""))
    print(f"[计划] 预计约 {seconds / 60:.1f} 分钟")
    return pairs, rtt_pairs, tput_pairs, path_pairs, sizes


def todo(exc):
    raise SystemExit(f"还没有完成：{exc}。先补全 netprof/ 中对应的函数，并通过离线测试。") from exc


def measure_rtt(opts, hostmap, rtt_pairs, raw):
    results = {}
    for a, b in rtt_pairs:
        text = measure.ping(a, hostmap[b]["ip"], opts.rtt_count, opts.rtt_interval)
        (raw / f"rtt-{a}-{b}.txt").write_text(text)
        try:
            parsed = parse.parse_ping(text)
            block = summary.summarize_rtt(parsed)
        except NotImplementedError as exc:
            todo(exc)
        except ValueError as exc:
            results[(a, b)] = (None, [f"ping 输出无法解析：{exc}"])
            print(f"[RTT]  {a} ⇄ {b}  解析失败：{exc}")
            continue
        errors = [] if block else ["ping 全部丢失"]
        results[(a, b)] = (block, errors)
        shown = "全部丢失" if block is None else f"p50 {block['p50']:.3f} ms  p90 {block['p90']:.3f} ms  丢 {block['lost']}/{parsed['sent']}"
        print(f"[RTT]  {a} ⇄ {b}  {shown}")
    return results


def measure_tput(opts, hostmap, pairs, raw, tag=""):
    results = {}
    for src, dst in pairs:
        def save(index, report, src=src, dst=dst):
            (raw / f"tput{tag}-{src}-{dst}-{index}.json").write_text(json.dumps(report, ensure_ascii=False))
        try:
            runs, errors = measure.throughput_runs(src, dst, hostmap[dst]["ip"], opts.tput_seconds,
                                                   opts.tput_omit, opts.tput_repeats, save=save)
            block = summary.summarize_throughput([r["mbps"] for r in runs]) if runs else None
        except NotImplementedError as exc:
            todo(exc)
        results[(src, dst)] = (block, runs, errors)
        shown = "全部失败" if block is None else f"{block['median']:.1f} Mbit/s（{block['min']:.1f}–{block['max']:.1f}，n={block['n']}）"
        print(f"[吞吐{tag}] {src} → {dst}  {shown}" + (f"  错误 {len(errors)} 次" if errors else ""))
    return results


def measure_concurrent(opts, hostmap, pairs, raw):
    """所选有向对同时各测一次：每对一个服务端端口，所有客户端同时启动。"""
    results, servers, clients = {}, [], []
    try:
        for i, (src, dst) in enumerate(pairs):
            port = 5301 + i
            server = subprocess.Popen(["ip", "netns", "exec", dst, "iperf3", "-s", "-1", "-p", str(port)],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            servers.append(server)
            if not sysrun.wait_listening(dst, port):
                raise SystemExit(f"{dst} 的 iperf3 服务端没有在 {port} 端口监听")
        for i, (src, dst) in enumerate(pairs):
            args = ["ip", "netns", "exec", src, "iperf3", "-c", hostmap[dst]["ip"], "-p", str(5301 + i),
                    "-t", str(opts.tput_seconds), "-O", str(opts.tput_omit), "-J"]
            clients.append(subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        for (src, dst), client in zip(pairs, clients):
            out, _ = client.communicate(timeout=opts.tput_seconds + opts.tput_omit + 30)
            (raw / f"tput-concurrent-{src}-{dst}.json").write_text(out)
            try:
                run = parse.parse_iperf3(json.loads(out))
                results[(src, dst)] = (summary.summarize_throughput([run["mbps"]]), [run], [])
            except NotImplementedError as exc:
                todo(exc)
            except ValueError as exc:
                results[(src, dst)] = (None, [], [f"并发测量失败：{exc}"])
            block = results[(src, dst)][0]
            print(f"[并发] {src} → {dst}  " + ("失败" if block is None else f"{block['median']:.1f} Mbit/s"))
    finally:
        for proc in servers + clients:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    return results


def measure_owd(opts, hostmap, pairs, raw):
    results = {}
    for src, dst in pairs:
        samples = raw / f"owd-{src}-{dst}.txt"
        recv = subprocess.Popen(["ip", "netns", "exec", dst, sys.executable, str(LAB / "owd.py"), "recv",
                                 "--count", str(opts.owd), "--samples", str(samples)],
                                stdout=subprocess.PIPE, text=True)
        time.sleep(0.3)
        sysrun.run_in(src, [sys.executable, str(LAB / "owd.py"), "send", "--to", hostmap[dst]["ip"],
                            "--count", str(opts.owd)], timeout=opts.owd * 0.05 + 30)
        recv.communicate(timeout=30)
        values = [float(v) for v in samples.read_text().split()] if samples.exists() else []
        try:
            block = summary.summarize_rtt({"samples": values, "sent": opts.owd, "received": len(values)})
        except NotImplementedError as exc:
            todo(exc)
        results[(src, dst)] = block
        print(f"[单向] {src} → {dst}  " + ("全部丢失" if block is None else f"p50 {block['p50']:.3f} ms  p90 {block['p90']:.3f} ms"))
    return results


def transfer_once(src, dst, hostmap, size, port=5401):
    """一次定量传输的完成时间（秒）。源端口交给内核挑选（0），避免与上一条处于 TIME_WAIT 的连接冲突。"""
    server = subprocess.Popen(["ip", "netns", "exec", dst, sys.executable, str(TRANSFER), "server",
                               "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not sysrun.wait_listening(dst, port):
            raise RuntimeError(f"{dst} 的 transfer.py 服务端没有在 {port} 端口监听")
        result = sysrun.run_in(src, [sys.executable, str(TRANSFER), "client", "--destination", hostmap[dst]["ip"],
                                     "--port", str(port), "--source", hostmap[src]["ip"], "--source-port", "0",
                                     "--bytes", str(size)], timeout=300)
        if result.returncode != 0:
            lines = result.stderr.strip().splitlines()
            raise RuntimeError(lines[-1] if lines else f"transfer.py 退出码 {result.returncode}")
        return json.loads(result.stdout)["completion_seconds"]
    finally:
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


def measure_curve(hostmap, pairs, sizes, raw):
    """用 Lab 3 的 transfer.py 测不同数据量的完成时间（接收端确认收齐才停表），再拟合直线。"""
    results, errors = {}, {}
    for src, dst in pairs:
        try:
            seconds = [transfer_once(src, dst, hostmap, size) for size in sizes]
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            errors[(src, dst)] = [f"传输曲线失败：{exc}"]
            print(f"[曲线] {src} → {dst}  失败：{exc}")
            continue
        (raw / f"curve-{src}-{dst}.json").write_text(json.dumps({"sizes_bytes": sizes, "seconds": seconds}))
        points = "，".join(f"{size / 1e6:g} MB {t * 1000:.1f} ms" for size, t in zip(sizes, seconds))
        print(f"[曲线] {src} → {dst}  {points}")
        try:
            fit = extras.fit_transfer_curve(sizes, seconds)
        except NotImplementedError as exc:
            todo(exc)
        except ValueError as exc:
            errors[(src, dst)] = [f"传输曲线无法拟合：{exc}"]
            print(f"[曲线] {src} → {dst}  无法拟合：{exc}")
            continue
        results[(src, dst)] = {"sizes_bytes": sizes, "seconds": [round(s, 4) for s in seconds],
                               "intercept_s": round(fit["intercept_s"], 4), "rate_mbps": round(fit["rate_mbps"], 2),
                               "max_residual_s": round(fit["max_residual_s"], 4)}
        print(f"[曲线] {src} → {dst}  a = {fit['intercept_s'] * 1000:.1f} ms，b = {fit['rate_mbps']:.1f} Mbit/s，"
              f"最大残差 {fit['max_residual_s'] * 1000:.1f} ms")
    return results, errors


def matrix(title, hostmap, pairs_block, cell):
    names_ = list(hostmap)
    print(f"\n{title}（行＝源，列＝目的）")
    print("        " + "".join(f"{n:>8}" for n in names_))
    for src in names_:
        row = []
        for dst in names_:
            entry = pairs_block.get((src, dst))
            row.append(f"{'·':>8}" if src == dst else f"{cell(entry):>8}")
        print(f"{src:>8}" + "".join(row))


def main():
    # 逐对进度行即时输出：通过管道（如 | grep）查看时也不会等到结束才出现
    sys.stdout.reconfigure(line_buffering=True)
    opts = options()
    hostmap = hostlib.load_hosts(opts.hosts)
    pairs, rtt_pairs, tput_pairs, path_pairs, sizes = plan(opts, hostmap)
    if opts.dry_run:
        return
    sysrun.require_root()
    sysrun.require_tools("ping", "iperf3", "ss")
    missing = [n for n in hostmap if not sysrun.namespace_exists(n)]
    if missing:
        raise SystemExit(f"实验床里没有这些 namespace：{', '.join(missing)}；先执行 topo.sh up。")
    stamp = datetime.datetime.now().astimezone()
    out = Path(opts.out or f"/tmp/lab04-results/profile-{stamp:%Y%m%d-%H%M%S}.json")
    raw = out.with_suffix(".raw")
    if out.exists() or raw.exists():
        raise SystemExit(f"{out} 或 {raw} 已存在：换一个 --out，避免覆盖上一次的证据。")
    raw.mkdir(parents=True)
    env = sysrun.environment()
    started = time.monotonic()

    rtt = measure_rtt(opts, hostmap, rtt_pairs, raw) if rtt_pairs else {}
    if opts.concurrent and tput_pairs:
        tput = measure_concurrent(opts, hostmap, tput_pairs, raw)
    else:
        tput = measure_tput(opts, hostmap, tput_pairs, raw) if tput_pairs else {}
    by_path = {}
    if path_pairs:
        for spine in SPINES:
            for src in sorted({s for s, _ in path_pairs}):
                sysrun.topo("pin", src, spine)
            try:
                chosen = measure_tput(opts, hostmap, path_pairs, raw, tag=f"-{spine}")
            finally:
                sysrun.topo("unpin")
            for pair, (block, _, _) in chosen.items():
                if block is not None:
                    by_path.setdefault(pair, {})[spine] = block
    owd = measure_owd(opts, hostmap, pairs, raw) if opts.owd else {}
    curve, curve_errors = measure_curve(hostmap, pairs, sizes, raw) if sizes else ({}, {})
    env["loadavg_end"] = sysrun.loadavg()

    entries = []
    for src, dst in pairs:
        key = tuple(sorted((src, dst), key=list(hostmap).index))
        rtt_block, rtt_errors = rtt.get(key, (None, []))
        tput_block, runs, tput_errors = tput.get((src, dst), (None, [], []))
        try:
            marks = summary.flags(rtt_block, runs, sent=opts.rtt_count if rtt_pairs else 0)
            if tput_pairs and not runs and "unreachable" not in marks:
                marks.append("unreachable")
            values = [r["mbps"] for r in runs]
            if len(values) >= 3 and extras.is_bimodal(values):
                marks.append("bimodal")
        except NotImplementedError as exc:
            if "TODO 7" not in str(exc):
                todo(exc)
        entry = {"src": src, "dst": dst, "rtt_ms": rtt_block, "throughput_mbps": tput_block, "flags": marks}
        errors = rtt_errors + tput_errors + curve_errors.get((src, dst), [])
        if errors:
            entry["errors"] = errors
        if runs:
            entry["cpu_max_pct"] = round(max(max(r["cpu_host"], r["cpu_remote"]) for r in runs), 1)
        if (src, dst) in owd:
            entry["owd_ms"] = owd[(src, dst)]
        if (src, dst) in by_path:
            entry["by_path"] = by_path[(src, dst)]
        if (src, dst) in curve:
            entry["transfer_curve"] = curve[(src, dst)]
        entries.append(entry)

    profile = {
        "schema": schema.SCHEMA,
        "created": stamp.isoformat(timespec="seconds"),
        "environment": env,
        "method": {
            "rtt": None if not rtt_pairs else {
                "tool": "ping", "count": opts.rtt_count, "interval_s": opts.rtt_interval,
                "pairs": "unordered", "statistic": "nearest-rank"},
            "throughput": None if not tput_pairs else {
                "tool": "iperf3", "seconds": opts.tput_seconds, "omit_s": opts.tput_omit,
                "repeats": 1 if opts.concurrent else opts.tput_repeats, "reading": "receiver",
                "concurrent": bool(opts.concurrent), "statistic": "median; ci95 = mean ± t·s/√n"},
        },
        "hosts": hostmap,
        "pairs": entries,
    }
    schema.validate(profile)
    out.write_text(json.dumps(profile, ensure_ascii=False, indent=1) + "\n")

    table = {(e["src"], e["dst"]): e for e in entries}
    if rtt_pairs:
        matrix("往返时间 p50（ms）", hostmap, table,
               lambda e: "—" if not e or e["rtt_ms"] is None else f"{e['rtt_ms']['p50']:.3f}")
    if tput_pairs:
        matrix("吞吐中位数（Mbit/s）", hostmap, table,
               lambda e: "—" if not e or e["throughput_mbps"] is None else f"{e['throughput_mbps']['median']:.1f}")
    marked = [f"{e['src']}→{e['dst']}：{','.join(e['flags'])}" for e in entries if e["flags"]]
    print("\n[标记] " + ("；".join(marked) if marked else "无"))
    print(f"[完成] 用时 {(time.monotonic() - started) / 60:.1f} 分钟；画像 {out}；原始输出 {raw}/")


if __name__ == "__main__":
    main()
