"""把作业时间拆成计算、上传、等待、下载（TODO 1、2）。纯计算，可以离线测试。"""

PHASES = ("compute", "upload", "wait", "download")


def round_breakdown(worker, server, barrier_done):
    """TODO 1　拆开一个 worker 的一轮，返回 {"compute":…, "upload":…, "wait":…, "download":…}（秒）。

    worker：该 worker 本轮的记录，含 compute_start、compute_end、model_first、model_last。
    server：PS 对该 worker 本轮的记录，含 grad_first、grad_last。
    barrier_done：PS 收齐全部梯度并聚合完的时刻。

    四段首尾相接，加起来应等于 model_last − compute_start：
        compute  本地计算
        upload   算完到 PS 收齐这个 worker 的梯度（注意不是 sendall 返回的时刻）
        wait     自己的梯度已到，等别人（barrier）
        download barrier 结束到模型收齐
    """
    raise NotImplementedError("TODO 1：round_breakdown")


def job_breakdown(result):
    """TODO 2　汇总整个作业。result 是 jobrun.py 写出的 JSON（已解析成字典）。

    取数：
        result["workers"][name]["rounds"][i]             worker 的记录
        result["server"]["workers"][name][i]             PS 对该 worker 的记录
        result["server"]["aggregates"][i]["barrier_done"] 第 i 轮的 barrier 结束时刻

    返回字典：
        "jct"：最晚的 model_last − 最早的 compute_start（秒）
        "per_worker"：{name: {四段各自的累计秒数, "total": 四段之和}}
        "mean"：四段在全部 worker 上的平均累计秒数，{phase: 秒}
        "share"：mean 中每段占四段之和的比例，{phase: 0–1}
    """
    raise NotImplementedError("TODO 2：job_breakdown")
