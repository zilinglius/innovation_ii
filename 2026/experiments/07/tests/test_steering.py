"""给定的三种分发策略与 TODO 4、5 的离线测试。实例的数字取自 2026-11-15 备课虚拟机上的两张画像。"""

import unittest

from sched.steering import Instance, Joint, Request, estimate, least, nearest, strongest

NEAR = Instance("h1b", mbps=95.2, rtt_ms=0.090, rate=0.152)      # 离客户端最近，算力最弱
MID = Instance("h3a", mbps=28.3, rtt_ms=0.133, rate=0.305)
FAR = Instance("h4a", mbps=9.4, rtt_ms=0.141, rate=0.634)        # 最远，算力最强
ALL = [NEAR, MID, FAR]
UPLOAD = Request(0, 1_000_000, 20.0)        # 大输入、轻计算
COMPUTE = Request(1, 10_000, 150.0)         # 小输入、重计算


class GivenPolicyCases(unittest.TestCase):
    """给定部分。"""

    def test_single_criterion_policies(self):
        idle = {"h1b": 0, "h3a": 0, "h4a": 0}
        self.assertEqual(nearest(UPLOAD, ALL, idle), "h1b")
        self.assertEqual(strongest(UPLOAD, ALL, idle), "h4a")
        self.assertEqual(least(UPLOAD, ALL, {"h1b": 2, "h3a": 1, "h4a": 1}), "h3a")


class EstimateCases(unittest.TestCase):
    """TODO 4：传输 + 排队 + 计算。"""

    def test_idle_instance(self):
        parts = estimate(UPLOAD, FAR, 0.0, 0.0)
        self.assertAlmostEqual(parts["transfer"], 0.000141 + 8 / 9.4, places=6)
        self.assertAlmostEqual(parts["wait"], 0.0)
        self.assertAlmostEqual(parts["compute"], 0.020 / 0.634, places=6)
        self.assertAlmostEqual(parts["finish"], parts["transfer"] + parts["compute"], places=9)

    def test_units(self):
        parts = estimate(COMPUTE, NEAR, 0.0, 0.0)
        self.assertAlmostEqual(parts["transfer"], 0.00009 + 0.08 / 95.2, places=7)       # 10 kB = 0.08 Mbit
        self.assertAlmostEqual(parts["compute"], 0.150 / 0.152, places=6)

    def test_waits_for_busy_instance(self):
        parts = estimate(COMPUTE, MID, 2.0, 3.5)
        arrive = 2.0 + parts["transfer"]
        self.assertAlmostEqual(parts["wait"], 3.5 - arrive, places=9)
        self.assertAlmostEqual(parts["finish"], 3.5 + 0.150 / 0.305, places=6)

    def test_no_wait_when_instance_frees_during_upload(self):
        parts = estimate(UPLOAD, FAR, 1.0, 1.2)            # 上传要 0.85 秒，到齐时实例早已空闲
        self.assertAlmostEqual(parts["wait"], 0.0)
        self.assertAlmostEqual(parts["finish"], 1.0 + parts["transfer"] + parts["compute"], places=9)

    def test_finish_is_absolute_time(self):
        early, late = estimate(COMPUTE, FAR, 0.0, 0.0), estimate(COMPUTE, FAR, 10.0, 0.0)
        self.assertAlmostEqual(late["finish"] - early["finish"], 10.0, places=9)

    def test_best_instance_depends_on_request(self):
        best = lambda request: min(ALL, key=lambda item: estimate(request, item, 0.0, 0.0)["finish"]).name   # noqa: E731
        self.assertEqual(best(UPLOAD), "h1b")          # 大输入：网络说了算
        self.assertEqual(best(COMPUTE), "h4a")         # 重计算：算力说了算


class JointCases(unittest.TestCase):
    """TODO 5：每个请求发给预计最早做完的实例，并记住它变忙了。"""

    def test_first_choice_follows_request_type(self):
        self.assertEqual(Joint().choose(UPLOAD, ALL, 0.0), "h1b")
        self.assertEqual(Joint().choose(COMPUTE, ALL, 0.0), "h4a")

    def test_records_free_at(self):
        joint = Joint()
        joint.choose(COMPUTE, ALL, 0.0)
        self.assertAlmostEqual(joint.free_at["h4a"], estimate(COMPUTE, FAR, 0.0, 0.0)["finish"], places=9)

    def test_spreads_when_best_is_busy(self):
        joint = Joint()
        picks = [joint.choose(Request(i, 10_000, 150.0), ALL, 0.0) for i in range(4)]
        # 同一时刻来 4 个重计算请求：h4a 每个约 0.24 秒，h3a 约 0.49 秒，h1b 约 0.99 秒
        self.assertEqual(picks, ["h4a", "h4a", "h3a", "h4a"])

    def test_time_passing_frees_instances(self):
        joint = Joint()
        self.assertEqual(joint.choose(COMPUTE, ALL, 0.0), "h4a")
        self.assertEqual(joint.choose(COMPUTE, ALL, 5.0), "h4a")      # 5 秒后 h4a 早已算完
        self.assertAlmostEqual(joint.free_at["h4a"], estimate(COMPUTE, FAR, 5.0, 0.0)["finish"], places=9)

    def test_ties_take_first(self):
        twins = [Instance("a", 50.0, 0.1, 0.5), Instance("b", 50.0, 0.1, 0.5)]
        joint = Joint()
        self.assertEqual(joint.choose(COMPUTE, twins, 0.0), "a")
        self.assertEqual(joint.choose(COMPUTE, twins, 0.0), "b")

    def test_does_not_touch_other_instances(self):
        joint = Joint()
        joint.choose(COMPUTE, ALL, 0.0)
        self.assertEqual(joint.free_at.get("h1b", 0.0), 0.0)
        self.assertEqual(joint.free_at.get("h3a", 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
