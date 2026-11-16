"""进阶测量用到的计算。纯计算，可以离线测试。

完整实现（2026-12-07 随第 10 讲与 Lab 7 发布）；Lab 4 里这两个函数是 TODO 7、8。
"""


def is_bimodal(values, ratio=1.5):
    """同一主机对的多次吞吐读数是否分成了两簇。

    建议做法：从小到大排序，看相邻两值之比的最大者；最大比值 ≥ ratio 时判为两簇（分界两侧自然各有至少一个值）。
    少于 3 个读数时返回 False：样本太少，分不清“两簇”与“偶然一次偏低”，在报告中说明。
    读数中有 0 或负数时抛出 ValueError。
    """
    if any(v <= 0 for v in values):
        raise ValueError("吞吐读数应为正数")
    if len(values) < 3:
        return False
    ordered = sorted(values)
    return max(b / a for a, b in zip(ordered, ordered[1:])) >= ratio


def fit_transfer_curve(sizes_bytes, seconds):
    """用最小二乘把完成时间拟合成 T = a + 8·m / (b·10^6)。

    输入：数据量 m（字节）与完成时间 T（秒）两个等长列表，至少两个不同的数据量。
    返回 {"intercept_s": a, "rate_mbps": b, "max_residual_s": 各点拟合残差绝对值的最大者}。
    a 是与数据量无关的固定开销（建连、首个往返、接收回执等），b 是随数据量增长的那部分对应的速率。
    第 08 讲的 α-β 模型写作 T = α + β·m：a 对应 α，8/(b·10^6) 对应每字节的 β。
    斜率不为正（数据越多反而越快）时抛出 ValueError。
    """
    n = len(sizes_bytes)
    if n != len(seconds) or len(set(sizes_bytes)) < 2:
        raise ValueError("至少需要两个不同的数据量，且两个列表等长")
    mean_m, mean_t = sum(sizes_bytes) / n, sum(seconds) / n
    slope = (sum((m - mean_m) * (t - mean_t) for m, t in zip(sizes_bytes, seconds))
             / sum((m - mean_m) ** 2 for m in sizes_bytes))
    if slope <= 0:
        raise ValueError("斜率不为正：数据越多反而越快，检查测量")
    intercept = mean_t - slope * mean_m
    residual = max(abs(t - (intercept + slope * m)) for m, t in zip(sizes_bytes, seconds))
    return {"intercept_s": intercept, "rate_mbps": 8 / (slope * 1e6), "max_residual_s": residual}
