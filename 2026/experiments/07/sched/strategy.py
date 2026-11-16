"""放置策略：随机、同机架优先（给定），按代价模型打分（TODO 2）。纯计算，可以离线测试。"""

import random

from .model import Placement, all_placements  # noqa: F401  TODO 2 会用到 all_placements


def random_placement(table, n, seed):
    """随机：从全部主机里不放回地抽 n + 1 台，第一台作 PS。种子相同，结果相同。"""
    picked = random.Random(seed).sample(sorted(table.hosts), n + 1)
    return Placement(picked[0], tuple(picked[1:]))


def rack_first(table, n, ps="h1a"):
    """同机架优先：只看机架标签。先用与 PS 同机架的主机，再按机架号从小到大取；同一机架内按主机名排序。"""
    home = table.rack[ps]
    others = sorted((name for name in table.hosts if name != ps),
                    key=lambda name: (table.rack[name] != home, table.rack[name], name))
    return Placement(ps, tuple(others[:n]))


def rank_placements(table, job, score):
    """TODO 2　给全部候选放置打分并排序，返回 [(分数, Placement), …]，分数小的在前。

    - 候选来自 all_placements(table.hosts, job.n)；
    - score 是一个函数：score(table, placement, job) 返回预测的 JCT（秒），越小越好；
    - 分数相同时，按 (ps, workers) 的字典序排，保证每次运行的结果相同；
    - 不要修改 table，也不要在这里运行作业。
    排在第一个的就是“按画像打分”选出的放置。
    """
    raise NotImplementedError("TODO 2：rank_placements")
