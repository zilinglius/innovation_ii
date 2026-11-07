"""TODO 4、5 的离线测试：只检查策略的决策，不发请求。"""

import unittest

from tailkit.policy import AdaptiveDelay, BudgetedHedge, FixedDelay


class AdaptiveCases(unittest.TestCase):
    def test_initial_until_enough_samples(self):
        policy = AdaptiveDelay(q=0.95, window=100, initial=12.0, min_samples=5)
        for value in (1.0, 2.0, 3.0, 4.0):
            policy.on_result(value)
            self.assertEqual(policy.delay_ms(), 12.0)

    def test_nearest_rank(self):
        policy = AdaptiveDelay(q=0.95, window=100, initial=12.0, min_samples=5)
        for value in range(1, 21):
            policy.on_result(float(value))
        self.assertEqual(policy.delay_ms(), 19.0)

    def test_window_forgets_old_samples(self):
        policy = AdaptiveDelay(q=0.5, window=10, initial=12.0, min_samples=5)
        for _ in range(10):
            policy.on_result(100.0)
        for _ in range(10):
            policy.on_result(5.0)
        self.assertEqual(policy.delay_ms(), 5.0)


class BudgetCases(unittest.TestCase):
    def test_burst_then_refuse(self):
        policy = BudgetedHedge(FixedDelay(10.0), ratio=0.1, burst=2.0)
        self.assertTrue(policy.allow_backup())
        self.assertTrue(policy.allow_backup())
        self.assertFalse(policy.allow_backup())

    def test_refill_rate(self):
        policy = BudgetedHedge(FixedDelay(10.0), ratio=0.25, burst=1.0)
        self.assertTrue(policy.allow_backup())
        for _ in range(3):
            policy.on_request()
        self.assertFalse(policy.allow_backup())
        policy.on_request()
        self.assertTrue(policy.allow_backup())

    def test_tokens_capped_at_burst(self):
        policy = BudgetedHedge(FixedDelay(10.0), ratio=1.0, burst=2.0)
        for _ in range(100):
            policy.on_request()
        self.assertEqual(sum(policy.allow_backup() for _ in range(5)), 2)

    def test_delegates_delay(self):
        self.assertEqual(BudgetedHedge(FixedDelay(7.0), ratio=0.1).delay_ms(), 7.0)

    def test_long_run_ratio(self):
        policy = BudgetedHedge(FixedDelay(10.0), ratio=0.05, burst=1.0)
        policy.tokens = 0.0
        allowed = 0
        for _ in range(1000):
            policy.on_request()
            allowed += policy.allow_backup()
        self.assertIn(allowed, (49, 50))


if __name__ == "__main__":
    unittest.main()
