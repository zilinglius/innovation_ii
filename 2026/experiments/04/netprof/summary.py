"""把样本变成统计量与可信度标记（TODO 3、4、6）。纯计算，可以离线测试。"""

import math  # noqa: F401  计算区间时会用到
import statistics  # noqa: F401  中位数、样本标准差可以直接用标准库

# 自由度 1–30 的双侧 95% t 分位数；自由度超过 30 时用最后一个值（偏保守）。
T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
       2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
       2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]

# 任务 4 用数据确定后改写，并在报告中说明依据：某次测量的任一端 CPU 占用达到这个百分比，就标记 cpu_bound。
CPU_LIMIT = 90.0


def nearest_rank(values, p):
    """TODO 3（上）　最近秩法分位数：把样本从小到大排序，取第 ceil(p·n) 个（从 1 计数）。

    p 取 (0, 1]；ceil(p·n) 小于 1 时取第 1 个。values 为空时抛出 ValueError。
    例：values = [5, 1, 4, 2, 3]，p = 0.5 → 第 3 个 → 3；p = 0.9 → 第 5 个 → 5。
    """
    raise NotImplementedError("TODO 3：nearest_rank")


def summarize_rtt(parsed):
    """TODO 3（下）　把 parse_ping 的结果变成画像中的 rtt_ms。

    返回 {"p50": …, "p90": …, "n": 样本数, "lost": 发出数 − 收到数}，分位数用 nearest_rank，保留 3 位小数；
    一个样本都没有时返回 None（调用者会在 errors 里记“全部丢失”，并打上 unreachable 标记）。
    """
    raise NotImplementedError("TODO 3：summarize_rtt")


def summarize_throughput(values):
    """TODO 4　把同一主机对多次吞吐读数（Mbit/s）变成画像中的 throughput_mbps。

    返回 {"median": 中位数, "min": …, "max": …, "n": 次数, "ci95": [下限, 上限] 或 None}，数值保留 2 位小数：
    - median 用 statistics.median（偶数个时取中间两个的平均）；
    - ci95 是均值的 95% t 区间：均值 ± T95[n−2] · s / √n，s 为样本标准差（除以 n−1）；n < 2 时为 None；
    - values 为空时抛出 ValueError。
    第 06 讲 5.2 节的例子：[95.39, 94.9, 94.59, 95.62, 95.22] → median 95.22，ci95 ≈ [94.64, 95.65]。
    """
    raise NotImplementedError("TODO 4：summarize_throughput")


def flags(rtt, runs, sent=None):
    """TODO 6　根据一对主机的测量结果给出可信度标记，返回列表（顺序不限、不重复）。

    rtt：summarize_rtt 的结果或 None；runs：parse_iperf3 结果的列表（可以为空）；
    sent：本次 RTT 测量发出的探测数（rtt 为 None 时用来区分“没测”与“全丢”）。
    - "unreachable"：测过 RTT 却一个回复都没收到（rtt 为 None 且 sent 大于 0），或测过吞吐却全部失败；
    - "lossy"：RTT 测量中有丢失（lost > 0）——只说明这些探测丢了，不代表丢包率的估计值；
    - "cpu_bound"：任一次吞吐测量中，本端或对端的 CPU 占用达到 CPU_LIMIT。
    """
    raise NotImplementedError("TODO 6：flags")
