"""画像格式 v1 的校验与读取（给定部分，开箱即通过）。不需要 root，不需要实验床：
    uv run --frozen python -m unittest tests.test_schema -v
"""

import copy
import json
import os
import tempfile
import unittest

from netprof import schema


def sample():
    return {
        "schema": schema.SCHEMA,
        "created": "2026-10-17T20:00:00+08:00",
        "environment": {"kernel": "7.0.0", "cpus": 2, "scenario": "baseline"},
        "method": {"rtt": {"tool": "ping"}, "throughput": {"tool": "iperf3"}},
        "hosts": {"h1a": {"ip": "10.0.1.11", "rack": 1}, "h3a": {"ip": "10.0.3.11", "rack": 3}},
        "pairs": [
            {"src": "h1a", "dst": "h3a", "flags": [],
             "rtt_ms": {"p50": 0.155, "p90": 0.192, "n": 40, "lost": 0},
             "throughput_mbps": {"median": 95.22, "min": 94.59, "max": 95.62, "n": 5, "ci95": [94.64, 95.65]}},
            {"src": "h3a", "dst": "h1a", "flags": ["unreachable"], "errors": ["连接被拒"],
             "rtt_ms": {"p50": 0.155, "p90": 0.192, "n": 40, "lost": 0}, "throughput_mbps": None},
        ],
    }


class SchemaCases(unittest.TestCase):

    def rejects(self, mutate, words):
        data = sample()
        mutate(data)
        with self.assertRaises(schema.ProfileError) as ctx:
            schema.validate(data)
        self.assertIn(words, str(ctx.exception))

    def test_valid_profile(self):
        data = sample()
        self.assertIs(schema.validate(data), data)

    def test_load_and_query(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as stream:
            json.dump(sample(), stream)
        try:
            profile = schema.load(stream.name)
        finally:
            os.unlink(stream.name)
        self.assertEqual(profile.rtt("h1a", "h3a"), 0.155)
        self.assertEqual(profile.throughput("h1a", "h3a"), 95.22)
        self.assertIsNone(profile.throughput("h3a", "h1a"))
        self.assertEqual(profile.flags("h3a", "h1a"), ["unreachable"])
        self.assertIsNone(profile.rtt("h1a", "h1a"))

    def test_wrong_schema(self):
        self.rejects(lambda d: d.update(schema="v0"), "schema")

    def test_quantile_order(self):
        self.rejects(lambda d: d["pairs"][0]["rtt_ms"].update(p50=0.3), "p50")

    def test_interval_needs_two_samples(self):
        def mutate(d):
            d["pairs"][0]["throughput_mbps"].update(n=1)
        self.rejects(mutate, "ci95")

    def test_duplicate_pair(self):
        self.rejects(lambda d: d["pairs"].append(copy.deepcopy(d["pairs"][0])), "重复")

    def test_unknown_flag(self):
        self.rejects(lambda d: d["pairs"][0].update(flags=["slow"]), "flags")

    def test_missing_result_needs_reason(self):
        self.rejects(lambda d: d["pairs"][1].pop("errors"), "errors")


if __name__ == "__main__":
    unittest.main()
