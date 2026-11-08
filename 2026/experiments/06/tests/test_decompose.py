"""TODO 1、2 的离线测试。"""

import unittest

from jobkit.decompose import PHASES, job_breakdown, round_breakdown


def record(start, compute, grad_last, barrier, model_last):
    worker = {"compute_start": start, "compute_end": start + compute, "local_send_done": start + compute,
              "model_first": barrier + 0.001, "model_last": model_last}
    server = {"grad_first": grad_last - 0.05, "grad_last": grad_last, "grad_bytes": 1000}
    return worker, server


class RoundCases(unittest.TestCase):
    def test_four_phases(self):
        worker, server = record(10.0, 0.2, 10.5, 10.8, 11.3)
        parts = round_breakdown(worker, server, 10.8)
        self.assertAlmostEqual(parts["compute"], 0.2)
        self.assertAlmostEqual(parts["upload"], 0.3)
        self.assertAlmostEqual(parts["wait"], 0.3)
        self.assertAlmostEqual(parts["download"], 0.5)

    def test_phases_close(self):
        worker, server = record(1.0, 0.1, 1.4, 1.9, 2.5)
        parts = round_breakdown(worker, server, 1.9)
        self.assertAlmostEqual(sum(parts[p] for p in PHASES), 1.5)

    def test_upload_uses_arrival_not_local_send(self):
        # sendall 早就返回了，上传段必须算到 PS 收齐为止。
        worker, server = record(0.0, 0.1, 1.0, 1.0, 1.2)
        worker["local_send_done"] = 0.11
        self.assertAlmostEqual(round_breakdown(worker, server, 1.0)["upload"], 0.9)


def job():
    """两个 worker、两轮。b 第一轮计算慢，a 要等它。"""
    a0, sa0 = record(0.0, 0.1, 0.3, 0.8, 1.0)
    b0, sb0 = record(0.0, 0.6, 0.8, 0.8, 1.1)
    a1, sa1 = record(1.0, 0.1, 1.3, 1.3, 1.6)
    b1, sb1 = record(1.1, 0.1, 1.3, 1.3, 1.7)
    return {"workers": {"a": {"rounds": [a0, a1]}, "b": {"rounds": [b0, b1]}},
            "server": {"workers": {"a": [sa0, sa1], "b": [sb0, sb1]},
                       "aggregates": [{"barrier_done": 0.8}, {"barrier_done": 1.3}]}}


class JobCases(unittest.TestCase):
    def test_jct_is_latest_minus_earliest(self):
        self.assertAlmostEqual(job_breakdown(job())["jct"], 1.7)

    def test_per_worker_sums(self):
        rows = job_breakdown(job())["per_worker"]
        self.assertAlmostEqual(rows["a"]["compute"], 0.2)
        self.assertAlmostEqual(rows["a"]["wait"], 0.5)
        self.assertAlmostEqual(rows["b"]["compute"], 0.7)
        self.assertAlmostEqual(rows["b"]["wait"], 0.0)
        self.assertAlmostEqual(rows["a"]["total"], 1.6)

    def test_mean_and_share(self):
        summary = job_breakdown(job())
        self.assertAlmostEqual(summary["mean"]["compute"], 0.45)
        self.assertAlmostEqual(sum(summary["share"].values()), 1.0)
        whole = sum(summary["mean"].values())
        self.assertAlmostEqual(summary["share"]["wait"], summary["mean"]["wait"] / whole)


if __name__ == "__main__":
    unittest.main()
