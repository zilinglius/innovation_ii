"""TODO 3、4、6：分位数、吞吐区间与可信度标记。纯计算：
    uv run --frozen python -m unittest tests.test_summary -v
"""

import unittest

from netprof import summary


class RankCases(unittest.TestCase):

    def test_nearest_rank(self):
        values = [5, 1, 4, 2, 3]
        self.assertEqual(summary.nearest_rank(values, 0.5), 3)
        self.assertEqual(summary.nearest_rank(values, 0.9), 5)
        self.assertEqual(summary.nearest_rank(values, 0.01), 1)
        # 40 个样本的 p90 是第 36 个（第 06 讲 1.4 节）
        self.assertEqual(summary.nearest_rank(list(range(1, 41)), 0.9), 36)
        self.assertEqual(summary.nearest_rank(list(range(1, 41)), 0.5), 20)

    def test_empty(self):
        with self.assertRaises(ValueError):
            summary.nearest_rank([], 0.5)


class RttCases(unittest.TestCase):

    def test_summary(self):
        parsed = {"samples": [0.2, 0.1, 0.4, 0.3], "sent": 5, "received": 4}
        self.assertEqual(summary.summarize_rtt(parsed), {"p50": 0.2, "p90": 0.4, "n": 4, "lost": 1})

    def test_all_lost(self):
        self.assertIsNone(summary.summarize_rtt({"samples": [], "sent": 5, "received": 0}))


class ThroughputCases(unittest.TestCase):

    def test_lecture_example(self):
        got = summary.summarize_throughput([95.39, 94.9, 94.59, 95.62, 95.22])
        self.assertEqual((got["median"], got["min"], got["max"], got["n"]), (95.22, 94.59, 95.62, 5))
        self.assertAlmostEqual(got["ci95"][0], 94.64, places=2)
        self.assertAlmostEqual(got["ci95"][1], 95.65, places=2)

    def test_even_count_median(self):
        self.assertEqual(summary.summarize_throughput([10, 20, 30, 40])["median"], 25)

    def test_single_run_has_no_interval(self):
        got = summary.summarize_throughput([47.4])
        self.assertEqual((got["median"], got["n"], got["ci95"]), (47.4, 1, None))

    def test_empty(self):
        with self.assertRaises(ValueError):
            summary.summarize_throughput([])


class FlagCases(unittest.TestCase):

    RUN = {"mbps": 95.3, "sender_mbps": 96.4, "retransmits": 0, "cpu_host": 0.8, "cpu_remote": 10.2}
    RTT = {"p50": 0.155, "p90": 0.192, "n": 20, "lost": 0}

    def test_clean(self):
        self.assertEqual(summary.flags(self.RTT, [self.RUN], sent=20), [])

    def test_lossy(self):
        self.assertEqual(summary.flags(dict(self.RTT, lost=2), [self.RUN], sent=20), ["lossy"])

    def test_unreachable(self):
        self.assertIn("unreachable", summary.flags(None, [], sent=20))

    def test_not_measured_is_not_unreachable(self):
        self.assertNotIn("unreachable", summary.flags(None, [self.RUN], sent=0))

    def test_cpu_bound(self):
        busy = dict(self.RUN, cpu_host=summary.CPU_LIMIT + 5)
        self.assertEqual(summary.flags(self.RTT, [self.RUN, busy], sent=20), ["cpu_bound"])


if __name__ == "__main__":
    unittest.main()
