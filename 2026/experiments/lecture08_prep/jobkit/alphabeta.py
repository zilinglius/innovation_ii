"""α-β 模型：拟合点对点传输时间，并预测参数服务器与 Ring AllReduce 作业（TODO 3、4、6）。纯计算，可以离线测试。"""


def fit_alpha_beta(sizes_bytes, seconds):
    """TODO 3　用最小二乘把传输时间拟合成 T(m) = α + β·m，返回 (α 秒, β 秒/字节)。

    只能用标准库。至少需要两种不同的大小，否则抛 ValueError。
    提示：β = Σ(m−m̄)(T−T̄) / Σ(m−m̄)²，α = T̄ − β·m̄。
    """
    raise NotImplementedError("TODO 3：fit_alpha_beta")


def predict_ps_round(alpha, beta, model_bytes, workers, compute_seconds):
    """TODO 4　预测参数服务器一轮的时间，返回 {"compute":…, "upload":…, "download":…, "round":…}（秒）。

    假设 N 个 worker 的数据都要挤过 PS 的接入链路，并且这条链路是唯一瓶颈：
        上传阶段把 N·S 字节送到 PS：α + β·N·S
        下载阶段把 N·S 字节从 PS 送出：α + β·N·S
    "round" 是计算、上传、下载之和。
    """
    raise NotImplementedError("TODO 4：predict_ps_round")


def predict_ring_round(alpha, beta, model_bytes, workers, compute_seconds):
    """TODO 6　预测 Ring AllReduce 一轮的时间，返回 {"compute":…, "communicate":…, "round":…}（秒）。

    N 个节点走 2(N−1) 步，每步每个节点传 S/N 字节，并且假设每一步都互不争用同一条链路：
        通信 = 2(N−1) · (α + β·S/N)
    N 为 1 时通信为 0。"round" 是计算与通信之和。
    """
    raise NotImplementedError("TODO 6：predict_ring_round")
