"""挑战任务：限制同时在途的请求数，看它能不能缓解 incast（TODO 6）。"""

import asyncio
import time


async def windowed_round(shards, service, policy, counters, limit, call_shard):
    """TODO 6　同一轮最多 limit 个请求同时在途，其余排队，有请求完成才发下一个。

    call_shard(shard, service, policy, counters) 是给定的协程，向一个分片发请求并等它完成。
    返回值要与 runner.one_round 相同：(轮次耗时 ms, [每个分片的结果])。
    提示：asyncio.Semaphore(limit) 配合 asyncio.gather 只需要几行。
    """
    raise NotImplementedError("TODO 6：windowed_round")
