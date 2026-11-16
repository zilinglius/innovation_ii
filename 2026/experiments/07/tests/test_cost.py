"""TODO 1、3 的离线测试。画像 fixtures 是 2026-11-14 在备课虚拟机上实测的两份快速画像。"""

from pathlib import Path
import unittest

from netprof import schema
from sched.cost import expected_shared_time, predict_jct, predict_round
from sched.model import Job, Placement, Table

FIXTURES = Path(__file__).parent / "fixtures"


def table(name):
    return Table(schema.load(FIXTURES / f"profile-{name}.json"))


class UniformTable:
    """人工构造的均匀网络：任意两台主机之间 100 Mbit/s，两个机架各 3 台。"""

    def __init__(self, slow=()):
        self.hosts = ["a1", "a2", "a3", "b1", "b2", "b3"]
        self.rack = {name: name[0] for name in self.hosts}
        self.tput = {(s, d): 100.0 for s in self.hosts for d in self.hosts if s != d}
        for pair, value in slow:
            self.tput[pair] = value

    def capacity_in(self, host):
        return max(self.tput[(s, host)] for s in self.hosts if s != host)

    def capacity_out(self, host):
        return max(self.tput[(host, d)] for d in self.hosts if d != host)


class RoundCases(unittest.TestCase):
    """TODO 1：三项的代价模型。"""

    def test_uniform_shares_ps_access(self):
        job = Job(n=4, model_bytes=1_000_000, compute_s=0.2)
        result = predict_round(UniformTable(), Placement("a1", ("a2", "a3", "b1", "b2")), job)
        self.assertAlmostEqual(result["compute"], 0.2)
        self.assertAlmostEqual(result["upload"], 8 / 25)          # 4 条流平分 100 Mbit/s
        self.assertAlmostEqual(result["download"], 8 / 25)
        self.assertAlmostEqual(result["round"], 0.2 + 0.32 + 0.32)

    def test_slowest_worker_decides(self):
        slow = [(("b1", "a1"), 10.0)]                             # 只有 b1 → a1 的上传方向慢
        result = predict_round(UniformTable(slow), Placement("a1", ("a2", "a3", "b1", "b2")), Job())
        self.assertAlmostEqual(result["upload"], 0.8)
        self.assertAlmostEqual(result["download"], 0.32)

    def test_directions_use_their_own_numbers(self):
        slow = [(("a1", "b2"), 20.0)]                             # 只有下发方向慢
        result = predict_round(UniformTable(slow), Placement("a1", ("a2", "b1", "b2")), Job(n=3))
        self.assertAlmostEqual(result["upload"], 8 / (100 / 3))
        self.assertAlmostEqual(result["download"], 0.4)

    def test_model_size_and_worker_count(self):
        job = Job(n=2, model_bytes=5_000_000, compute_s=0.05)
        result = predict_round(UniformTable(), Placement("b1", ("a1", "b2")), job)
        self.assertAlmostEqual(result["upload"], 40 / 50)
        self.assertAlmostEqual(result["round"], 0.05 + 0.8 + 0.8)

    def test_measured_profile_rack2_slow(self):
        t = table("rack2-slow")
        fast = predict_round(t, Placement("h1a", ("h1b", "h3a", "h3b", "h4a")), Job())
        slow = predict_round(t, Placement("h1a", ("h1b", "h2a", "h3a", "h4a")), Job())
        self.assertAlmostEqual(fast["round"], 0.870, places=2)    # 实测 JCT 8.939 s，即每轮 0.894 s
        self.assertAlmostEqual(slow["round"], 1.898, places=2)    # 实测 JCT 19.033 s，即每轮 1.903 s

    def test_measured_profile_lecture10(self):
        t = table("lecture10")
        self.assertAlmostEqual(predict_jct(t, Placement("h1a", ("h1b", "h2a", "h2b", "h3a")), Job()), 35.96, places=1)
        self.assertAlmostEqual(predict_jct(t, Placement("h2a", ("h1b", "h2b", "h4a", "h4b")), Job()), 8.67, places=1)

    def test_jct_is_rounds_times_round(self):
        job = Job(rounds=7)
        placement = Placement("a1", ("a2", "a3", "b1", "b2"))
        self.assertAlmostEqual(predict_jct(UniformTable(), placement, job), 7 * predict_round(UniformTable(), placement, job)["round"])


class SharedTimeCases(unittest.TestCase):
    """TODO 3（上）：几条流随机选上联时的期望用时。"""

    def test_single_flow(self):
        self.assertAlmostEqual(expected_shared_time(1, 2, 9.4, 23.85, 8), 8 / 9.4)
        self.assertAlmostEqual(expected_shared_time(1, 2, 95.0, 23.85, 8), 8 / 23.85)

    def test_two_flows_two_uplinks(self):
        expected = 0.5 * (8 / 9.4) + 0.5 * (16 / 9.4)
        self.assertAlmostEqual(expected_shared_time(2, 2, 9.4, 23.85, 8), expected)

    def test_three_flows_two_uplinks(self):
        # 8 种分配：2 种全在一条上联（L=3），6 种是 2 + 1（L=2）
        expected = (2 * 3 + 6 * 2) / 8 * (8 / 9.4)
        self.assertAlmostEqual(expected_shared_time(3, 2, 9.4, 23.85, 8), expected)

    def test_fast_uplink_is_capped_by_share(self):
        # 上联很快时，撞不撞都受 PS 接入份额限制
        self.assertAlmostEqual(expected_shared_time(2, 2, 95.0, 23.85, 8), 8 / 23.85)

    def test_one_uplink_always_collides(self):
        self.assertAlmostEqual(expected_shared_time(3, 1, 10.0, 50.0, 8), 3 * 8 / 10.0)


class SharedRoundCases(unittest.TestCase):
    """TODO 3（下）：predict_round(shared=True)。"""

    def test_two_workers_in_slow_remote_rack(self):
        t = table("rack2-slow")
        placement = Placement("h1a", ("h1b", "h2a", "h2b", "h3a"))
        plain = predict_jct(t, placement, Job())
        shared = predict_jct(t, placement, Job(), shared=True)
        self.assertAlmostEqual(plain, 18.99, places=1)
        self.assertAlmostEqual(shared, 27.49, places=1)           # 五次实测：35.951、35.343、27.472、27.436、19.114 s

    def test_single_remote_worker_unchanged(self):
        t = table("rack2-slow")
        placement = Placement("h1a", ("h1b", "h2a", "h3a", "h4a"))
        self.assertAlmostEqual(predict_jct(t, placement, Job(), shared=True), predict_jct(t, placement, Job()))

    def test_same_rack_as_ps_not_grouped(self):
        slow = [(("a2", "a1"), 10.0), (("a3", "a1"), 10.0)]       # 与 PS 同机架的两个 worker 不经过上联
        placement = Placement("a1", ("a2", "a3", "b1"))
        result = predict_round(UniformTable(slow), placement, Job(n=3), shared=True)
        self.assertAlmostEqual(result["upload"], 0.8)

    def test_fast_remote_rack_unchanged(self):
        placement = Placement("a1", ("a2", "b1", "b2", "b3"))
        self.assertAlmostEqual(predict_round(UniformTable(), placement, Job(), shared=True)["round"],
                               predict_round(UniformTable(), placement, Job())["round"])


if __name__ == "__main__":
    unittest.main()
