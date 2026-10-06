"""Lab 3 测量助手：真实 TCP、共同计时、按内层五元组分类抓包；不改变路由和限速。"""

import argparse
from collections import Counter
import json
import os
import platform
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import time


ENDPOINTS = {
    **{f"h{r}{h}": f"10.0.{r}.{11 if h == 'a' else 12}"
       for r in range(1, 5) for h in "ab"},
    **{f"t{r}{h}": f"192.168.10.{11 if r == 1 else 12}"
       for r in (1, 3) for h in "ab"},
}


def decode_ipv4(packet):
    """解码本实验无 VLAN 的 IPv4 TCP/UDP；忽略非首片，绝不把它猜成端口。"""
    if len(packet) < 20 or packet[0] >> 4 != 4:
        return None
    hlen = (packet[0] & 15) * 4
    total = int.from_bytes(packet[2:4], "big")
    if hlen < 20 or len(packet) < total or total < hlen:
        return None
    if int.from_bytes(packet[6:8], "big") & 0x1FFF:
        return None
    payload = packet[hlen:total]
    proto = packet[9]
    if proto not in (6, 17) or len(payload) < (20 if proto == 6 else 8):
        return None
    sport, dport = struct.unpack_from("!HH", payload)
    row = {"key": (socket.inet_ntoa(packet[12:16]), sport,
                   socket.inet_ntoa(packet[16:20]), dport), "proto": proto}
    if proto == 6:
        thlen = (payload[12] >> 4) * 4
        if thlen < 20 or thlen > len(payload):
            return None
        row.update(syn=bool(payload[13] & 2 and not payload[13] & 16),
                   seq=int.from_bytes(payload[4:8], "big"),
                   payload_bytes=len(payload) - thlen)
    else:
        row["payload"] = payload[8:]
    return row


def packets(path):
    """读取 tcpdump 的经典 Ethernet pcap；其他格式明确报错。"""
    with path.open("rb") as stream:
        header = stream.read(24)
        orders = {b"\xd4\xc3\xb2\xa1": "<", b"\xa1\xb2\xc3\xd4": ">"}
        if len(header) != 24 or header[:4] not in orders:
            raise ValueError(f"不是支持的经典 pcap：{path}")
        order = orders[header[:4]]
        if struct.unpack_from(order + "I", header, 20)[0] != 1:
            raise ValueError(f"需在具体 Ethernet 接口抓包，不能用 -i any：{path}")
        while record := stream.read(16):
            if len(record) != 16:
                raise ValueError("pcap 记录头不完整")
            size = struct.unpack_from(order + "I", record, 8)[0]
            data = stream.read(size)
            if len(data) != size:
                raise ValueError("pcap 记录不完整")
            yield data


def classify(paths, flows, mode):
    groups = [Counter() for _ in flows]
    syns = [set() for _ in flows]
    other = 0
    total = 0
    for path in paths:
        interface = path.stem
        for frame in packets(path):
            total += 1
            outer_port = None
            vni = None
            row = decode_ipv4(frame[14:]) if frame[12:14] == b"\x08\x00" else None
            if mode == "vxlan":
                if row and row["proto"] == 17 and row["key"][3] == 4789:
                    outer_port = row["key"][1]
                    vx = row["payload"]
                    if len(vx) >= 22 and vx[0] & 8 and vx[20:22] == b"\x08\x00":
                        vni = int.from_bytes(vx[4:7], "big")
                        row = decode_ipv4(vx[22:])
                    else:
                        row = None
                else:
                    row = None
            matched = False
            if row and row["proto"] == 6:
                for i, flow in enumerate(flows):
                    # 租户复用同一 IP，必须同时匹配 VNI，不能只看五元组。
                    if row["key"] != flow["key"] or (mode == "vxlan" and vni != flow["vni"]):
                        continue
                    matched = True
                    group = (interface, outer_port)
                    groups[i][(*group, "packets")] += 1
                    if row["payload_bytes"]:
                        groups[i][(*group, "data_packets")] += 1
                        groups[i][(*group, "tcp_payload_bytes_with_retransmissions")] += row["payload_bytes"]
                    if row["syn"]:
                        syns[i].add((interface, row["seq"]))
                    break
            if not matched:
                other += 1
    result = []
    for counts, syn in zip(groups, syns):
        keys = sorted({(iface, port) for iface, port, field in counts})
        rows = [{"interface": iface, "outer_source_port": port,
                 **{field: counts[(iface, port, field)] for field in
                    ("packets", "data_packets", "tcp_payload_bytes_with_retransmissions")}}
                for iface, port in keys]
        result.append({"syn_paths": sorted({iface for iface, seq in syn}),
                       "syn_observations": len(syn), "groups": rows})
    return {"captured_packets": total, "unmatched_packets": other, "flows": result}


def parse_flow(value):
    try:
        source, destination, sport, dport = value.split(":")
        sport, dport = int(sport), int(dport)
        if not (1024 <= sport <= 65535 and 1024 <= dport <= 65535):
            raise ValueError("端口须在 1024–65535")
        sip, dip = ENDPOINTS[source], ENDPOINTS[destination]
        return {"source_ns": source, "destination_ns": destination,
                "key": (sip, sport, dip, dport),
                "vni": (100 if source.endswith("a") else 200) if source.startswith("t") else None}
    except (ValueError, KeyError) as error:
        raise argparse.ArgumentTypeError(f"流格式应为 h1a:h3a:40001:5201：{error}") from error


def stop(process, sig=signal.SIGTERM):
    if process.poll() is None:
        process.send_signal(sig)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def measure(args):
    if os.geteuid() != 0:
        raise RuntimeError("请使用 sudo 执行测量；离线测试不需要 root。")
    receivers = [(f["destination_ns"], f["key"][3]) for f in args.flow]
    senders = [(f["source_ns"], f["key"][1]) for f in args.flow]
    if len(set(receivers)) != len(receivers) or len(set(senders)) != len(senders):
        raise ValueError("同轮的服务端端口和客户端绑定端口不能重复使用")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "run.json").write_text(json.dumps({
        "command": sys.argv, "kernel": platform.release(), "machine": platform.machine(),
        "flows": args.flow, "bytes_per_flow": args.bytes, "capture": args.capture,
        "timing_poll_seconds": 0.005,
    }, ensure_ascii=False, indent=2) + "\n")
    children, handles, captures = [], [], []
    script = Path(__file__).with_name("transfer.py")

    def launch(command, name):
        stdout = (args.output / f"{name}.json").open("w")
        stderr = (args.output / f"{name}.stderr").open("w")
        handles.extend([stdout, stderr])
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        children.append(process)
        return process

    def wait_until(predicate, process, label):
        deadline = time.monotonic() + 5
        while not predicate():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"{label} 未就绪；查看本轮 stderr")
            time.sleep(0.05)

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        for leaf in args.leaf or ["r1"]:
            for spine in (5, 6):
                name = f"{leaf}-r{spine}"
                path = args.output / f"{name}.pcap"
                cap = launch(["ip", "netns", "exec", leaf, "tcpdump", "--immediate-mode",
                              "-U", "-n", "-s", "0", "-i", name, "-Q", "out", "-w", str(path),
                              "tcp" if args.capture == "tcp" else "udp dst port 4789"], name)
                captures.append((cap, path))
                wait_until(lambda n=name: "listening on" in (args.output / f"{n}.stderr").read_text(), cap, name)
        servers = []
        for i, flow in enumerate(args.flow):
            ns, port = flow["destination_ns"], flow["key"][3]
            occupied = subprocess.check_output(["ip", "netns", "exec", ns, "ss", "-H", "-ltn", f"sport = :{port}"])
            if occupied:
                raise RuntimeError(f"{ns}:{port} 已有服务端，先结束上一轮或换端口")
            server = launch(["ip", "netns", "exec", ns, sys.executable, str(script), "server", "--port", str(port)], f"server-{i+1}")
            servers.append(server)
            wait_until(lambda n=ns, p=port: bool(subprocess.check_output(
                ["ip", "netns", "exec", n, "ss", "-H", "-ltn", f"sport = :{p}"])), server, f"{ns}:{port}")
        clients, launches, finished = [], [], {}
        start = time.monotonic()
        for i, flow in enumerate(args.flow):
            sip, sport, dip, dport = flow["key"]
            launches.append(time.monotonic() - start)
            clients.append(launch(["ip", "netns", "exec", flow["source_ns"], sys.executable,
                                   str(script), "client", "--source", sip, "--source-port", str(sport),
                                   "--destination", dip, "--port", str(dport), "--bytes", str(args.bytes)], f"client-{i+1}"))
        deadline = start + args.timeout
        while len(finished) < len(clients):
            for i, process in enumerate(clients):
                status = process.poll()
                if status not in (None, 0):
                    raise RuntimeError("客户端失败；本轮无有效共同窗口，查看 client-*.stderr")
                if status == 0 and i not in finished:
                    finished[i] = time.monotonic() - start
            if len(finished) == len(clients):
                break
            if time.monotonic() > deadline:
                raise TimeoutError("本轮超时；本轮不产生成功汇总")
            time.sleep(0.005)
        elapsed = max(finished.values())
        if any(p.returncode != 0 for p in clients):
            raise RuntimeError("客户端失败；查看 client-*.stderr")
        receipts = []
        for i, server in enumerate(servers):
            if server.wait(timeout=5) != 0:
                raise RuntimeError("服务端失败；查看 server-*.stderr")
            result = json.loads((args.output / f"client-{i+1}.json").read_text())
            receipt = json.loads((args.output / f"server-{i+1}.json").read_text())
            if result["received_bytes"] != args.bytes or receipt["received_bytes"] != args.bytes:
                raise ValueError("应用接收字节不符")
            result.update(launch_offset_seconds=launches[i], finish_offset_seconds=finished[i])
            receipts.append(result)
        for cap, path in captures:
            if cap.poll() is not None:
                raise RuntimeError("抓包提前退出，不能生成有效路径汇总")
            stop(cap, signal.SIGINT)
        classification = classify([path for cap, path in captures], args.flow, args.capture)
        if any(not flow["groups"] for flow in classification["flows"]):
            raise RuntimeError("至少一条流未在所选 leaf 出口捕获；检查 --leaf、路径和过滤条件")
        volume = args.bytes * len(args.flow)
        summary = {"bytes": volume, "wall_seconds": elapsed, "shared_window_mbps": 8*volume/elapsed/1e6,
                   "flows": [{**f, **r, "capture": c} for f, r, c in zip(args.flow, receipts, classification["flows"])],
                   "capture": {k: v for k, v in classification.items() if k != "flows"},
                   "capture_stats": {path.stem: path.with_suffix(".stderr").read_text() for cap, path in captures}}
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
        print(f"[共同窗口] {volume/1e6:.2f} MB，{elapsed:.3f} s，{summary['shared_window_mbps']:.2f} Mbit/s")
        for flow in summary["flows"]:
            print(f"[流] {flow['source_ns']} → {flow['destination_ns']}，SYN 出口 {flow['capture']['syn_paths']}")
        print(f"[结果] {args.output}/summary.json；原始 pcap 与 stderr 同目录。")
    finally:
        for process in reversed(children):
            stop(process, signal.SIGINT if any(process is p for p, path in captures) else signal.SIGTERM)
        for handle in handles:
            handle.close()
        signal.signal(signal.SIGTERM, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow", action="append", type=parse_flow, required=True,
                        help="发送节点:接收节点:源端口:服务端端口，可重复")
    parser.add_argument("--leaf", action="append", choices=["r1", "r2", "r3", "r4"], help="抓包的发送 leaf，默认 r1")
    parser.add_argument("--capture", choices=["tcp", "vxlan"], default="tcp")
    parser.add_argument("--output", type=Path, required=True, help="新目录；拒绝覆盖已有结果")
    parser.add_argument("--bytes", type=int, default=30_000_000)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    if args.bytes <= 0 or args.timeout <= 0:
        parser.error("字节数和超时必须为正")
    try:
        measure(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"测量失败：{error}\n")
    except KeyboardInterrupt:
        parser.exit(130, "测量已中断；本轮子进程已清理，路由和拓扑请按指导书恢复。\n")


if __name__ == "__main__":
    main()
