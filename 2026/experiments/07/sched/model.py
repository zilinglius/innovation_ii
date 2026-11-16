"""作业、放置与画像表（给定）。纯数据结构，不运行命令，可以离线测试。"""

from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True)
class Job:
    """参数服务器作业的要求。默认值就是 jobrun.py 的默认值。"""
    n: int = 4                      # worker 数
    model_bytes: int = 1_000_000    # 梯度与模型的大小，字节
    rounds: int = 10
    compute_s: float = 0.2          # 每个 worker 每轮的计算时间，秒

    @property
    def megabits(self):
        """一份梯度或模型有多少 Mbit（10^6 bit）。"""
        return self.model_bytes * 8 / 1e6


@dataclass(frozen=True)
class Placement:
    """一次放置：PS 在哪台主机，worker 用哪几台主机。"""
    ps: str
    workers: tuple

    def args(self):
        """交给 jobrun.py 的参数。"""
        return f"--ps {self.ps} --workers {','.join(self.workers)}"


class ProfileGap(ValueError):
    """画像里缺少调度需要的数（有主机对没测吞吐，或测量失败）。"""


class Table:
    """从画像里取出调度要用的数。

    hosts          主机名列表，按名称排序
    rack[h]        主机 h 的机架号（拓扑标签）
    tput[(s, d)]   s 到 d 的吞吐中位数，Mbit/s（一对主机单独传时测得）
    """

    def __init__(self, profile):
        self.hosts = sorted(profile.hosts)
        self.rack = {name: info.get("rack") for name, info in profile.hosts.items()}
        self.tput = {}
        for src in self.hosts:
            for dst in self.hosts:
                if src == dst:
                    continue
                value = profile.throughput(src, dst)
                if value is None or value <= 0:
                    raise ProfileGap(f"画像里没有 {src} → {dst} 的吞吐；先用 checkup.py 测全部主机对。")
                self.tput[(src, dst)] = value

    def capacity_in(self, host):
        """host 接入链路的入向能力：别的主机向它发送时测到的最大吞吐。"""
        return max(self.tput[(src, host)] for src in self.hosts if src != host)

    def capacity_out(self, host):
        """host 接入链路的出向能力：它向别的主机发送时测到的最大吞吐。"""
        return max(self.tput[(host, dst)] for dst in self.hosts if dst != host)


def all_placements(hosts, n):
    """全部候选放置：每台主机轮流作 PS，其余主机里取 n 台作 worker。按 (ps, workers) 的字典序给出。"""
    hosts = sorted(hosts)
    for ps in hosts:
        for workers in combinations([name for name in hosts if name != ps], n):
            yield Placement(ps, workers)
