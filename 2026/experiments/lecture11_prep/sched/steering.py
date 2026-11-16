"""请求分发策略：就近、算力最强、最空闲（给定），联合代价（TODO 4、5）。纯计算，可以离线测试。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Request:
    """一个请求：先上传 input_bytes 字节的输入，再让实例做 work_ms 毫秒（CPU 时间）的计算。"""
    id: int
    input_bytes: int
    work_ms: float


@dataclass(frozen=True)
class Instance:
    """分发器眼里的一个实例，三个数分别来自网络画像与算力画像。"""
    name: str
    mbps: float        # 客户端到这个实例的吞吐，Mbit/s
    rtt_ms: float      # 客户端到这个实例的往返时间，ms
    rate: float        # 算力：每秒墙上时间能完成多少秒的计算（1.0 相当于一个不受限的核）


def nearest(request, instances, outstanding):
    """就近：只看网络，选吞吐最大的实例；吞吐相同时选往返时间小的。"""
    return max(instances, key=lambda item: (item.mbps, -item.rtt_ms)).name


def strongest(request, instances, outstanding):
    """算力最强：只看算力，选 rate 最大的实例。"""
    return max(instances, key=lambda item: item.rate).name


def least(request, instances, outstanding):
    """最空闲：选已发出、还没返回的请求数最少的实例；相同时按给出的顺序取第一个。"""
    return min(instances, key=lambda item: outstanding[item.name]).name


def estimate(request, instance, now, free_at):
    """TODO 4　估计把 request 现在（时刻 now，秒）发给 instance，它什么时候做完。

    返回 {"transfer":…, "wait":…, "compute":…, "finish":…}，前三项是时长（秒），finish 是时刻（秒）。
    - transfer：把输入送到实例的时间 = 一个往返（建连）+ 输入的比特数 ÷ 吞吐。
      注意单位：rtt_ms 是毫秒，mbps 是 10^6 bit/s，input_bytes 是字节；
    - 输入在 now + transfer 到齐；实例先到先算，free_at 是它算完手头所有请求的时刻（秒）。
      到齐时实例还在忙，就要等：wait = max(0, free_at − 到齐时刻)；
    - compute：work_ms 毫秒的计算在这个实例上要多久 = 工作量 ÷ instance.rate；
    - finish = 到齐时刻 + wait + compute。结果很小，返回的时间忽略不计。
    例：输入 1 MB、work_ms=20，实例 mbps=9.4、rtt_ms=0.2、rate=0.6，now=0、free_at=0：
    transfer ≈ 0.851，wait = 0，compute ≈ 0.033，finish ≈ 0.885。
    """
    raise NotImplementedError("TODO 4：estimate")


class Joint:
    """TODO 5　联合代价：每个请求发给“预计最早做完”的实例。

    分发器自己记着每个实例的 free_at（预计算完手头请求的时刻），初始都是 0。
    choose(request, instances, now)：
      1. 用 estimate() 为每个实例算出这个请求的 finish，取最小的；并列时取 instances 里靠前的；
      2. 把选中实例的 free_at 更新为这个 finish（它后面的请求要排在这个请求之后）；
      3. 返回选中实例的名字。
    只用分发器自己的记录，不去问实例：分发器是唯一的客户端时，这份记录就够了。
    """

    def __init__(self):
        self.free_at = {}

    def choose(self, request, instances, now):
        raise NotImplementedError("TODO 5：Joint.choose")
