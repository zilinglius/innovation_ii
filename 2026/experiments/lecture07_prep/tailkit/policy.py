"""对冲策略。runner 对每个主请求调用一次 on_request()、delay_ms()；
主请求超过 delay_ms() 还没回来时问 allow_backup()；分片完成时调用 on_result()。

NoHedge、FixedDelay 是给定的，第 07 讲课上就在用；AdaptiveDelay、BudgetedHedge 是 TODO 4、5。
"""

import collections

from .report import rank


class NoHedge:
    """不对冲。"""

    name = "off"

    def on_request(self):
        pass

    def delay_ms(self):
        return None

    def allow_backup(self):
        return False

    def on_result(self, latency_ms):
        pass


class FixedDelay:
    """固定对冲延迟：主请求超过 delay 还没回来，就向另一副本发一个备份请求。"""

    def __init__(self, delay):
        self.delay = delay
        self.name = f"fixed-{delay:g}ms"

    def on_request(self):
        pass

    def delay_ms(self):
        return self.delay

    def allow_backup(self):
        return True

    def on_result(self, latency_ms):
        pass


class AdaptiveDelay(FixedDelay):
    """TODO 4　用最近的延迟样本决定对冲延迟，而不是事先写死一个数。

    - 保留最近 window 个 on_result() 收到的样本（可以用 collections.deque 的 maxlen）。
    - delay_ms()：样本数少于 min_samples 时返回 initial；否则返回样本的第 q 分位数，用 rank()。
    - allow_backup() 沿用父类。
    """

    def __init__(self, q=0.95, window=500, initial=12.0, min_samples=50):
        super().__init__(initial)
        self.q = q
        self.window = window
        self.initial = initial
        self.min_samples = min_samples
        self.samples = collections.deque(maxlen=window)
        self.name = f"adaptive-p{q * 100:g}"

    def delay_ms(self):
        raise NotImplementedError("TODO 4：AdaptiveDelay.delay_ms")

    def on_result(self, latency_ms):
        raise NotImplementedError("TODO 4：AdaptiveDelay.on_result")


class BudgetedHedge:
    """TODO 5　给对冲加预算：备份请求不超过主请求数的 ratio，防止慢的时候反而把负载放大。

    令牌桶：每个主请求（on_request）增加 ratio 个令牌，上限 burst；初始为 burst。
    allow_backup()：先问被包装的策略 inner；令牌不少于 1 时扣 1 并返回 True，否则返回 False。
    delay_ms()、on_result() 转交给 inner，on_request() 也要转交。
    """

    def __init__(self, inner, ratio=0.05, burst=10.0):
        self.inner = inner
        self.ratio = ratio
        self.burst = burst
        self.tokens = burst
        self.name = f"{inner.name}+budget-{ratio * 100:g}%"

    def on_request(self):
        raise NotImplementedError("TODO 5：BudgetedHedge.on_request")

    def delay_ms(self):
        raise NotImplementedError("TODO 5：BudgetedHedge.delay_ms")

    def allow_backup(self):
        raise NotImplementedError("TODO 5：BudgetedHedge.allow_backup")

    def on_result(self, latency_ms):
        raise NotImplementedError("TODO 5：BudgetedHedge.on_result")
