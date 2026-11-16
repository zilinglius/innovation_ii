"""主机表与主机对。默认是 Lab 3 指导书 3.2 节约定的 8 台主机；换拓扑时用 --hosts 读 JSON。"""

import json

# 名称 → 地址与机架；与 topo.sh 的地址规划一致
HOSTS = {
    f"h{rack}{side}": {"ip": f"10.0.{rack}.{11 if side == 'a' else 12}", "rack": rack}
    for rack in range(1, 5) for side in "ab"
}


def load_hosts(path=None):
    """读主机表。文件格式与 HOSTS 相同：{"h1a": {"ip": "10.0.1.11", "rack": 1}, ...}。"""
    if path is None:
        return dict(HOSTS)
    with open(path, encoding="utf-8") as stream:
        hosts = json.load(stream)
    for name, info in hosts.items():
        if not isinstance(info, dict) or "ip" not in info:
            raise ValueError(f"主机 {name} 缺少 ip 字段")
    return hosts


def ordered_pairs(hosts, sources=None, destinations=None):
    """有向主机对 (src, dst)，src ≠ dst；按主机表顺序排列，结果可复现。"""
    names = list(hosts)
    sources = [n for n in names if sources is None or n in sources]
    destinations = [n for n in names if destinations is None or n in destinations]
    return [(s, d) for s in sources for d in destinations if s != d]


def unordered_pairs(pairs, hosts):
    """把有向对折成无序对：往返时间对两个方向是同一个量，每个无序对只测一次。"""
    order = {name: i for i, name in enumerate(hosts)}
    seen = []
    for src, dst in pairs:
        pair = tuple(sorted((src, dst), key=order.get))
        if pair not in seen:
            seen.append(pair)
    return seen


def same_rack(hosts, src, dst):
    return hosts[src].get("rack") is not None and hosts[src].get("rack") == hosts[dst].get("rack")


def parse_pair_list(text):
    """把 "h1a:h3a,h1b:h3b" 解析成 [("h1a", "h3a"), ("h1b", "h3b")]。"""
    pairs = []
    for item in filter(None, (part.strip() for part in text.split(","))):
        src, sep, dst = item.partition(":")
        if not sep or not src or not dst:
            raise ValueError(f"主机对应写成 src:dst，收到 {item!r}")
        pairs.append((src, dst))
    return pairs

