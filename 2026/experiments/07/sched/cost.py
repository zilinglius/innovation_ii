"""代价模型：用画像预测一种放置的作业完成时间（TODO 1、3）。纯计算，可以离线测试。"""

from itertools import product  # noqa: F401  TODO 3 枚举哈希结果时可以用


def predict_round(table, placement, job, shared=False):
    """TODO 1　预测参数服务器一轮的时间，返回 {"compute":…, "upload":…, "download":…, "round":…}（秒）。

    模型就是第 10 讲 3.1 节的三项：round = compute + upload + download。
    - compute = job.compute_s；
    - upload：最慢的一个 worker 传完一份梯度（job.megabits Mbit）的时间。worker w 的上传速率是
      min(table.tput[(w, ps)], table.capacity_in(ps) / N)，N 是 worker 数；
    - download：最慢的一个 worker 收齐模型的时间，速率是 min(table.tput[(ps, w)], table.capacity_out(ps) / N)。
    单位：吞吐是 Mbit/s，时间是秒。第 10 讲 3.2 节的手算可以用来核对：rack2-slow 的画像里，
    PS h1a、worker h1b,h2a,h3a,h4a 的 round 约 1.90 秒。

    TODO 3（下）　shared=True 时做共享上联修正：与 PS 不同机架、且同一机架里有 k ≥ 2 个 worker 时，
    这 k 条流的用时改用 expected_shared_time(k, 2, b, share, job.megabits)，其中 b 取这 k 个 worker
    该方向吞吐的最小值，share 是上面的 capacity / N。其余 worker 的算法不变。上传、下发两个方向分别修正。
    基础任务只要求 shared=False；没做 TODO 3 时，shared=True 应抛出 NotImplementedError。
    """
    raise NotImplementedError("TODO 1：predict_round")


def expected_shared_time(k, uplinks, pair_mbps, share_mbps, megabits):
    """TODO 3（上）　k 条流要出同一个机架，机架有 uplinks 条上联，每条流各自随机选一条。返回期望用时（秒）。

    - 每条流要传 megabits Mbit；一条上联上只有它自己时速率是 pair_mbps（画像里测到的就是这种情况）；
    - 一条上联上有 L 条流时，它们平分这条上联，L 份数据要 L × megabits / pair_mbps 秒才全部传完；
    - 不管怎么分，每条流的速率都不会超过 share_mbps（PS 接入链路的平分份额），即用时不少于 megabits / share_mbps；
    - 一种分配方式下，这组流的用时 = max(megabits / share_mbps, 最忙那条上联的 L × megabits / pair_mbps)；
    - 每条流独立、等概率地选上联，共有 uplinks ** k 种分配方式，返回这些用时的平均值。
    例：k=2、uplinks=2、pair_mbps=9.4、share_mbps=23.85、megabits=8 → 一半的情况各走一条（0.851 秒），
    一半的情况撞在一起（1.702 秒），期望约 1.277 秒。k=1 时没有共享，结果是 megabits / min(pair_mbps, share_mbps)。
    """
    raise NotImplementedError("TODO 3：expected_shared_time")


def predict_jct(table, placement, job, shared=False):
    """预测作业完成时间（给定）：轮数 × 每轮时间。"""
    return job.rounds * predict_round(table, placement, job, shared=shared)["round"]
