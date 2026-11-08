"""TODO 3、4 的离线测试。"""

import unittest

from jobkit.alphabeta import fit_alpha_beta, predict_ps_round


class FitCases(unittest.TestCase):
    def test_exact_line(self):
        sizes = [1000, 100000, 1000000]
        seconds = [0.002 + 8e-8 * m for m in sizes]
        alpha, beta = fit_alpha_beta(sizes, seconds)
        self.assertAlmostEqual(alpha, 0.002, places=9)
        self.assertAlmostEqual(beta, 8e-8, places=14)

    def test_least_squares_not_endpoints(self):
        alpha, beta = fit_alpha_beta([0, 1, 2], [0.0, 2.0, 2.0])
        self.assertAlmostEqual(beta, 1.0)
        self.assertAlmostEqual(alpha, 1.0 / 3)

    def test_needs_two_sizes(self):
        with self.assertRaises(ValueError):
            fit_alpha_beta([1000, 1000], [0.1, 0.2])


class PredictCases(unittest.TestCase):
    def test_round(self):
        result = predict_ps_round(0.001, 1e-7, 1_000_000, 4, 0.2)
        self.assertAlmostEqual(result["compute"], 0.2)
        self.assertAlmostEqual(result["upload"], 0.401)
        self.assertAlmostEqual(result["download"], 0.401)
        self.assertAlmostEqual(result["round"], 1.002)

    def test_communication_grows_with_workers(self):
        small = predict_ps_round(0.0, 1e-7, 1_000_000, 1, 0.2)
        large = predict_ps_round(0.0, 1e-7, 1_000_000, 7, 0.2)
        self.assertAlmostEqual(large["upload"] / small["upload"], 7.0)


if __name__ == "__main__":
    unittest.main()
