"""把“每个请求以概率 p 变慢”变成对轮次延迟的预测（TODO 1–3）。纯计算，可以离线测试。

模型只有两档：一轮要等全部 N 个分片，任何一个慢，这一轮就慢。各请求是否变慢相互独立。
"""


def slow_round_probability(p, n):
    """TODO 1　一轮里至少有一个请求变慢的概率。

    p：单个请求变慢的概率，0 ≤ p ≤ 1；n：分片数，n ≥ 1。
    例：p=0.01、n=100 时约为 0.634。
    """
    raise NotImplementedError("TODO 1：slow_round_probability")


def knee(p, q):
    """TODO 2　轮次延迟的第 q 分位数从“快”变成“慢”所需的最小分片数 N。

    第 q 分位数落入慢的一档，等价于慢轮比例超过 1-q。返回使
    slow_round_probability(p, N) > 1-q 成立的最小正整数 N。
    例：p=0.01 时，q=0.9 返回 11，q=0.5 返回 69。p=0 时永远不会变慢，返回 None。
    """
    raise NotImplementedError("TODO 2：knee")


def predict_round(p, n, fast_ms, slow_ms, quantiles=(0.5, 0.9, 0.99)):
    """TODO 3　预测轮次延迟的各分位数，返回 {q: 预测值}。

    fast_ms：一轮没有慢请求时的延迟（用自己测的噪声底）；slow_ms：一轮有慢请求时的延迟。
    某个 q 的预测值：慢轮比例超过 1-q 取 slow_ms，否则取 fast_ms。
    """
    raise NotImplementedError("TODO 3：predict_round")
