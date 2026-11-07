"""TODO 1–3 的离线测试。"""

import unittest

from tailkit.predict import knee, predict_round, slow_round_probability


class SlowRoundCases(unittest.TestCase):
    def test_one_shard_is_p(self):
        self.assertAlmostEqual(slow_round_probability(0.01, 1), 0.01)

    def test_hundred_shards(self):
        self.assertAlmostEqual(slow_round_probability(0.01, 100), 0.634, places=3)

    def test_never_slow(self):
        self.assertEqual(slow_round_probability(0.0, 50), 0.0)

    def test_always_slow(self):
        self.assertEqual(slow_round_probability(1.0, 3), 1.0)


class KneeCases(unittest.TestCase):
    def test_p90(self):
        self.assertEqual(knee(0.01, 0.9), 11)

    def test_p50(self):
        self.assertEqual(knee(0.01, 0.5), 69)

    def test_p99_needs_more_than_one(self):
        # N=1 时慢轮比例恰为 1%，没有超过 1-q，所以要 2 个分片。
        self.assertEqual(knee(0.01, 0.99), 2)

    def test_never(self):
        self.assertIsNone(knee(0.0, 0.9))


class PredictCases(unittest.TestCase):
    def test_small_fanout(self):
        self.assertEqual(predict_round(0.01, 10, 8.0, 108.0), {0.5: 8.0, 0.9: 8.0, 0.99: 108.0})

    def test_large_fanout(self):
        self.assertEqual(predict_round(0.01, 100, 15.0, 115.0), {0.5: 115.0, 0.9: 115.0, 0.99: 115.0})

    def test_custom_quantiles(self):
        self.assertEqual(predict_round(0.01, 20, 9.0, 109.0, (0.5, 0.9)), {0.5: 9.0, 0.9: 109.0})


if __name__ == "__main__":
    unittest.main()
