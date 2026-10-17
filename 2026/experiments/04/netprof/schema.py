"""画像格式 v1：校验与读取。这是 Lab 4 与 Lab 9 之间的接口，Lab 9 的调度器直接 import 本模块。

一份画像回答“在某个时刻、用某种方法、在某种条件下，每对主机之间的往返时间与吞吐是多少、有多准”：

  {"schema": "lab04.netprofile/v1", "created": "...", "environment": {...}, "method": {...},
   "hosts": {"h1a": {"ip": "10.0.1.11", "rack": 1}, ...},
   "pairs": [{"src": "h1a", "dst": "h3a", "rtt_ms": {...}, "throughput_mbps": {...}, "flags": [...]}, ...]}

字段含义见指导书 3.4 节。单位写在字段名里：*_ms 为毫秒，*_mbps 为 10^6 bit/s，*_bytes 为字节。
"""

import json
import math

SCHEMA = "lab04.netprofile/v1"
FLAGS = {"cpu_bound", "lossy", "bimodal", "unreachable"}


class ProfileError(ValueError):
    pass


def _number(value, where, minimum=0.0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProfileError(f"{where} 应为有限数值，收到 {value!r}")
    if value < minimum:
        raise ProfileError(f"{where} 不应小于 {minimum}，收到 {value}")
    return value


def _count(value, where, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ProfileError(f"{where} 应为不小于 {minimum} 的整数，收到 {value!r}")
    return value


def _quantiles(block, where, need_n=True):
    if not isinstance(block, dict):
        raise ProfileError(f"{where} 应为对象")
    p50 = _number(block.get("p50"), f"{where}.p50")
    p90 = _number(block.get("p90"), f"{where}.p90")
    if p50 > p90:
        raise ProfileError(f"{where}：p50 {p50} 大于 p90 {p90}")
    if need_n:
        _count(block.get("n"), f"{where}.n", 1)


def _throughput(block, where):
    if not isinstance(block, dict):
        raise ProfileError(f"{where} 应为对象")
    low, mid, high = (_number(block.get(k), f"{where}.{k}") for k in ("min", "median", "max"))
    if not low <= mid <= high:
        raise ProfileError(f"{where}：应满足 min ≤ median ≤ max，收到 {low}、{mid}、{high}")
    n = _count(block.get("n"), f"{where}.n", 1)
    ci = block.get("ci95")
    if ci is not None:
        if not (isinstance(ci, list) and len(ci) == 2):
            raise ProfileError(f"{where}.ci95 应为 [下限, 上限] 或 null")
        lo, hi = (_number(v, f"{where}.ci95", -math.inf) for v in ci)
        if lo > hi:
            raise ProfileError(f"{where}.ci95 下限大于上限")
        if n < 2:
            raise ProfileError(f"{where}：n < 2 时 ci95 应为 null")


def validate(profile):
    """不合格时抛出 ProfileError，并指出第一个问题所在的位置。"""
    if not isinstance(profile, dict):
        raise ProfileError("画像应为 JSON 对象")
    if profile.get("schema") != SCHEMA:
        raise ProfileError(f"schema 应为 {SCHEMA!r}，收到 {profile.get('schema')!r}")
    for key in ("created", "environment", "method", "hosts", "pairs"):
        if key not in profile:
            raise ProfileError(f"缺少顶层字段 {key}")
    env = profile["environment"]
    if not isinstance(env, dict) or not {"kernel", "cpus", "scenario"} <= set(env):
        raise ProfileError("environment 至少要有 kernel、cpus、scenario")
    method = profile["method"]
    if not isinstance(method, dict) or not {"rtt", "throughput"} <= set(method):
        raise ProfileError("method 要有 rtt 与 throughput 两项（未测的项写 null）")
    hosts = profile["hosts"]
    if not isinstance(hosts, dict) or len(hosts) < 2:
        raise ProfileError("hosts 至少要有两台主机")
    for name, info in hosts.items():
        if not isinstance(info, dict) or not isinstance(info.get("ip"), str):
            raise ProfileError(f"hosts.{name} 缺少 ip")
    seen = set()
    for i, pair in enumerate(profile["pairs"]):
        where = f"pairs[{i}]"
        src, dst = pair.get("src"), pair.get("dst")
        if src not in hosts or dst not in hosts or src == dst:
            raise ProfileError(f"{where}：src/dst 应为 hosts 中两台不同的主机，收到 {src!r}、{dst!r}")
        if (src, dst) in seen:
            raise ProfileError(f"{where}：{src}→{dst} 重复")
        seen.add((src, dst))
        where = f"pairs[{i}]（{src}→{dst}）"
        for key in ("rtt_ms", "throughput_mbps", "flags"):
            if key not in pair:
                raise ProfileError(f"{where} 缺少 {key}")
        if pair["rtt_ms"] is not None:
            _quantiles(pair["rtt_ms"], f"{where}.rtt_ms")
            _count(pair["rtt_ms"].get("lost"), f"{where}.rtt_ms.lost")
        if pair["throughput_mbps"] is not None:
            _throughput(pair["throughput_mbps"], f"{where}.throughput_mbps")
        for key, method_key in (("rtt_ms", "rtt"), ("throughput_mbps", "throughput")):
            if pair[key] is None and method[method_key] is not None and not pair.get("errors"):
                raise ProfileError(f"{where}.{key} 为 null：测过却没有结果时，要在 errors 里写明原因")
        flags = pair["flags"]
        if not isinstance(flags, list) or not set(flags) <= FLAGS:
            raise ProfileError(f"{where}.flags 只能取 {sorted(FLAGS)}，收到 {flags!r}")
        if "owd_ms" in pair and pair["owd_ms"] is not None:
            _quantiles(pair["owd_ms"], f"{where}.owd_ms")
        for spine, block in (pair.get("by_path") or {}).items():
            _throughput(block, f"{where}.by_path.{spine}")
        curve = pair.get("transfer_curve")
        if curve is not None:
            sizes, seconds = curve.get("sizes_bytes"), curve.get("seconds")
            if not (isinstance(sizes, list) and isinstance(seconds, list) and len(sizes) == len(seconds) >= 2):
                raise ProfileError(f"{where}.transfer_curve 的 sizes_bytes 与 seconds 应等长且至少两点")
            _number(curve.get("rate_mbps"), f"{where}.transfer_curve.rate_mbps")
            _number(curve.get("intercept_s"), f"{where}.transfer_curve.intercept_s", -math.inf)
    return profile


class Profile:
    """读取后的画像。Lab 9 的调度器用 rtt() 与 throughput() 取数，取不到时返回 None。"""

    def __init__(self, data):
        self.data = validate(data)
        self.hosts = data["hosts"]
        self.environment = data["environment"]
        self.pairs = {(p["src"], p["dst"]): p for p in data["pairs"]}

    def rtt(self, src, dst, statistic="p50"):
        block = self.pairs.get((src, dst), {}).get("rtt_ms")
        return None if block is None else block[statistic]

    def throughput(self, src, dst, statistic="median"):
        block = self.pairs.get((src, dst), {}).get("throughput_mbps")
        return None if block is None else block[statistic]

    def flags(self, src, dst):
        return list(self.pairs.get((src, dst), {}).get("flags", []))


def load(path):
    with open(path, encoding="utf-8") as stream:
        return Profile(json.load(stream))
