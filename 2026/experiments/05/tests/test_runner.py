"""环回地址上的端到端测试：不需要 root，也不需要实验床。给定部分应当一开始就通过。"""

import asyncio
import unittest

from tailkit import policy, runner
from tailkit.rpc import Service, serve

PORT_A = 17101
PORT_B = 17102


class LoopbackCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.servers = [asyncio.create_task(serve(PORT_A, seed=1)), asyncio.create_task(serve(PORT_B, seed=2))]
        await asyncio.sleep(0.05)

    async def asyncTearDown(self):
        for task in self.servers:
            task.cancel()
        await asyncio.gather(*self.servers, return_exceptions=True)

    async def shard(self, service, chosen):
        primary = runner.RpcClient("a", "127.0.0.1", PORT_A)
        backup = runner.RpcClient("b", "127.0.0.1", PORT_B)
        await primary.connect()
        await backup.connect()
        counters = runner.Counters()
        result = await runner.call_shard(runner.Shard(primary, backup), service, chosen, counters)
        await primary.close()
        await backup.close()
        return result, counters


class GivenCases(LoopbackCase):
    async def test_no_hedge_waits_for_slow_reply(self):
        (elapsed, _, slow, hedged), counters = await self.shard(Service(128, 1, 50, 1.0), policy.NoHedge())
        self.assertTrue(slow)
        self.assertFalse(hedged)
        self.assertGreaterEqual(elapsed, 50)
        self.assertEqual(counters.backups, 0)

    async def test_fixed_hedge_sends_backup_when_late(self):
        (elapsed, _, _, hedged), counters = await self.shard(Service(128, 30, 0, 0.0), policy.FixedDelay(5))
        self.assertTrue(hedged)
        self.assertEqual(counters.backups, 1)
        self.assertGreaterEqual(elapsed, 30)

    async def test_fixed_hedge_quiet_when_fast(self):
        (_, _, _, hedged), counters = await self.shard(Service(128, 1, 0, 0.0), policy.FixedDelay(200))
        self.assertFalse(hedged)
        self.assertEqual(counters.backups, 0)

    async def test_response_size(self):
        client = runner.RpcClient("a", "127.0.0.1", PORT_A)
        await client.connect()
        reply = await client.call(1, Service(100000, 0, 0, 0.0))
        await client.close()
        self.assertEqual(reply.resp_bytes, 100000)


class WindowedCases(LoopbackCase):
    """TODO 6。"""

    async def clients(self, count):
        clients = [runner.RpcClient("a", "127.0.0.1", PORT_A) for _ in range(count)]
        await asyncio.gather(*(c.connect() for c in clients))
        for client in clients:
            self.addAsyncCleanup(client.close)
        return [runner.Shard(c) for c in clients]

    async def test_limit_serializes(self):
        shards = await self.clients(4)
        elapsed, results = await runner.windowed_round(
            shards, Service(128, 20, 0, 0.0), policy.NoHedge(), runner.Counters(), 1, runner.call_shard)
        self.assertEqual(len(results), 4)
        self.assertGreaterEqual(elapsed, 80)

    async def test_limit_allows_parallel(self):
        shards = await self.clients(4)
        elapsed, _ = await runner.windowed_round(
            shards, Service(128, 20, 0, 0.0), policy.NoHedge(), runner.Counters(), 4, runner.call_shard)
        self.assertLess(elapsed, 60)


if __name__ == "__main__":
    unittest.main()
