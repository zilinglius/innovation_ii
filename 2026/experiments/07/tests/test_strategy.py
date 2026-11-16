"""给定策略与 TODO 2 的离线测试。"""

from pathlib import Path
import unittest

from netprof import schema
from sched.model import Job, Placement, Table, all_placements
from sched.strategy import rack_first, random_placement, rank_placements

FIXTURES = Path(__file__).parent / "fixtures"


def table(name):
    return Table(schema.load(FIXTURES / f"profile-{name}.json"))


class GivenCases(unittest.TestCase):
    """给定部分：候选放置与两种不看画像的策略。"""

    def test_candidate_count(self):
        self.assertEqual(sum(1 for _ in all_placements(table("rack2-slow").hosts, 4)), 280)

    def test_rack_first(self):
        t = table("rack2-slow")
        self.assertEqual(rack_first(t, 4), Placement("h1a", ("h1b", "h2a", "h2b", "h3a")))
        self.assertEqual(rack_first(t, 4, ps="h3b"), Placement("h3b", ("h3a", "h1a", "h1b", "h2a")))

    def test_random_is_reproducible(self):
        t = table("rack2-slow")
        self.assertEqual(random_placement(t, 4, 3), random_placement(t, 4, 3))
        self.assertEqual(random_placement(t, 4, 3), Placement("h2b", ("h3a", "h4a", "h1b", "h2a")))


class RankCases(unittest.TestCase):
    """TODO 2：给全部候选打分并排序。"""

    @staticmethod
    def by_name(table, placement, job):
        """一个与网络无关的打分函数：PS 是 h2a 得 1 分，否则 2 分；worker 里有 h1a 再加 1 分。"""
        return (1 if placement.ps == "h2a" else 2) + (1 if "h1a" in placement.workers else 0)

    def test_all_candidates_sorted(self):
        t = table("rack2-slow")
        ranked = rank_placements(t, Job(), self.by_name)
        self.assertEqual(len(ranked), 280)
        scores = [score for score, _ in ranked]
        self.assertEqual(scores, sorted(scores))
        self.assertEqual(len({placement for _, placement in ranked}), 280)

    def test_ties_broken_by_name(self):
        ranked = rank_placements(table("rack2-slow"), Job(), self.by_name)
        self.assertEqual(ranked[0], (1, Placement("h2a", ("h1b", "h2b", "h3a", "h3b"))))
        self.assertEqual(ranked[1], (1, Placement("h2a", ("h1b", "h2b", "h3a", "h4a"))))
        self.assertEqual(ranked[-1][0], 3)

    def test_uses_job_size(self):
        ranked = rank_placements(table("rack2-slow"), Job(n=2), self.by_name)
        self.assertEqual(len(ranked), 8 * 21)
        self.assertEqual(len(ranked[0][1].workers), 2)

    def test_score_receives_table_and_job(self):
        t, job, seen = table("lecture10"), Job(rounds=3), []

        def score(tb, placement, jb):
            seen.append((tb is t, jb is job))
            return 0.0
        rank_placements(t, job, score)
        self.assertEqual(len(seen), 280)
        self.assertTrue(all(a and b for a, b in seen))


if __name__ == "__main__":
    unittest.main()
