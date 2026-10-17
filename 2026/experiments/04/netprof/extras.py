"""进阶任务用到的计算（TODO 7、8）。纯计算，可以离线测试。基础任务不需要它们。"""


def is_bimodal(values, ratio=1.5):
    """TODO 7（进阶任务 5）　同一主机对的多次吞吐读数是否分成了两簇。

    建议做法：从小到大排序，看相邻两值之比的最大者；最大比值 ≥ ratio 时判为两簇（分界两侧自然各有至少一个值）。
    少于 3 个读数时返回 False：样本太少，分不清“两簇”与“偶然一次偏低”，在报告中说明。
    读数中有 0 或负数时抛出 ValueError。
    """
    raise NotImplementedError("TODO 7：is_bimodal")


def fit_transfer_curve(sizes_bytes, seconds):
    """TODO 8（进阶任务 6）　用最小二乘把完成时间拟合成 T = a + 8·m / (b·10^6)。

    输入：数据量 m（字节）与完成时间 T（秒）两个等长列表，至少两个不同的数据量。
    返回 {"intercept_s": a, "rate_mbps": b, "max_residual_s": 各点拟合残差绝对值的最大者}。
    a 是与数据量无关的固定开销（建连、首个往返、接收回执等），b 是随数据量增长的那部分对应的速率。
    第 10 讲的 α-β 模型写作 T = α + β·m：a 对应 α，8/(b·10^6) 对应每字节的 β。
    斜率不为正（数据越多反而越快）时抛出 ValueError。
    """
    raise NotImplementedError("TODO 8：fit_transfer_curve")
