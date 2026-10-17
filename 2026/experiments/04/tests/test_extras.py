"""TODO 7、8（进阶）：双峰判断与传输时间曲线拟合。基础任务不要求这两项通过。
    uv run --frozen python -m unittest tests.test_extras -v
"""

import unittest

from netprof import extras


class BimodalCases(unittest.TestCase):

    def test_two_clusters(self):
        self.assertTrue(extras.is_bimodal([19.1, 95.3, 19.0, 95.1, 19.2]))

    def test_one_cluster(self):
        self.assertFalse(extras.is_bimodal([95.1, 95.3, 94.9, 95.6]))

    def test_too_few(self):
        self.assertFalse(extras.is_bimodal([19.1, 95.3]))

    def test_bad_value(self):
        with self.assertRaises(ValueError):
            extras.is_bimodal([0, 95.3, 95.1])


class CurveCases(unittest.TestCase):

    def test_exact_line(self):
        # a = 2 ms，b = 80 Mbit/s：T = 0.002 + 8·m / 80e6
        sizes = [100_000, 1_000_000, 10_000_000]
        seconds = [0.002 + 8 * m / 80e6 for m in sizes]
        got = extras.fit_transfer_curve(sizes, seconds)
        self.assertAlmostEqual(got["intercept_s"], 0.002, places=9)
        self.assertAlmostEqual(got["rate_mbps"], 80, places=6)
        self.assertAlmostEqual(got["max_residual_s"], 0, places=9)

    def test_negative_slope(self):
        with self.assertRaises(ValueError):
            extras.fit_transfer_curve([100_000, 1_000_000], [0.5, 0.1])


if __name__ == "__main__":
    unittest.main()
