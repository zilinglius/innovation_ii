"""扇出与对冲的执行（给定）。一轮：同时向 N 个分片发请求，等全部分片都回来，才算这一轮完成。"""

import asyncio
import itertools
import time

from .rpc import RpcClient
from .windowed import windowed_round

IDS = itertools.count(1)


class Shard:
    """一个分片：主副本一条连接；对冲时另有一个备份副本。"""

    def __init__(self, primary, backup=None):
        self.primary = primary
        self.backup = backup


class Counters:
    def __init__(self):
        self.requests = 0
        self.backups = 0
        self.backup_wins = 0


async def call_shard(shard, service, policy, counters):
    """向一个分片发请求，必要时对冲，返回 (完成耗时 ms, 主副本名, 是否慢, 是否发了备份)。"""
    started = time.perf_counter()
    primary_id = next(IDS)
    primary = shard.primary.call(primary_id, service)
    counters.requests += 1
    policy.on_request()
    delay = policy.delay_ms()
    backup = None
    backup_id = None
    if delay is not None and shard.backup is not None:
        done, _ = await asyncio.wait({primary}, timeout=delay / 1000)
        if not done and policy.allow_backup():
            backup_id = next(IDS)
            backup = shard.backup.call(backup_id, service)
            counters.backups += 1
    if backup is None:
        reply = await primary
    else:
        done, _ = await asyncio.wait({primary, backup}, return_when=asyncio.FIRST_COMPLETED)
        if primary in done:
            reply = primary.result()
            shard.backup.cancel(backup_id)
        else:
            reply = backup.result()
            shard.primary.cancel(primary_id)
            counters.backup_wins += 1
    elapsed = (time.perf_counter() - started) * 1000
    policy.on_result(elapsed)
    return elapsed, shard.primary.host, reply.slow, backup is not None


async def one_round(shards, service, policy, counters):
    """同时扇出到全部分片，返回 (轮次耗时 ms, 每个分片的结果)。"""
    started = time.perf_counter()
    results = await asyncio.gather(*(call_shard(s, service, policy, counters) for s in shards))
    return (time.perf_counter() - started) * 1000, results


async def build_shards(fanout, primaries, backups, addresses, port, cc):
    """分片轮流落在主副本主机上；每个分片一条连接。backups 为空时不建备份连接。"""
    shards = []
    for index in range(fanout):
        primary = RpcClient(primaries[index % len(primaries)], addresses[primaries[index % len(primaries)]], port, cc)
        backup = None
        if backups:
            name = backups[index % len(backups)]
            backup = RpcClient(name, addresses[name], port, cc)
        shards.append(Shard(primary, backup))
    await asyncio.gather(*(c.connect() for s in shards for c in (s.primary, s.backup) if c))
    return shards


async def run(fanout, rounds, service, policy, primaries, backups, addresses, port, cc, warmup=5, gap_ms=0.0,
              max_inflight=None):
    """跑 warmup + rounds 轮，丢弃预热轮；返回结果字典。max_inflight 给出时用 windowed_round（TODO 6）。"""
    shards = await build_shards(fanout, primaries, backups, addresses, port, cc)
    counters = Counters()
    round_ms, request_ms, per_host, slow_requests = [], [], {}, 0
    backed_up = 0
    wall = time.perf_counter()
    for index in range(warmup + rounds):
        if index == warmup:
            counters = Counters()
            wall = time.perf_counter()
        if max_inflight:
            elapsed, results = await windowed_round(shards, service, policy, counters, max_inflight, call_shard)
        else:
            elapsed, results = await one_round(shards, service, policy, counters)
        if gap_ms:
            await asyncio.sleep(gap_ms / 1000)
        if index < warmup:
            continue
        round_ms.append(elapsed)
        for latency, host, slow, hedged in results:
            request_ms.append(latency)
            per_host.setdefault(host, []).append(latency)
            slow_requests += slow
            backed_up += hedged
    wall = time.perf_counter() - wall
    await asyncio.gather(*(c.close() for s in shards for c in (s.primary, s.backup) if c))
    return {
        "round_ms": round_ms,
        "request_ms": request_ms,
        "per_host_ms": per_host,
        "requests": counters.requests,
        "backups": counters.backups,
        "backup_wins": counters.backup_wins,
        "slow_replies": slow_requests,
        "wall_seconds": wall,
    }
