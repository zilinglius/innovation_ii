"""TODO 1、2：解析 ping 与 iperf3 的真实输出（tests/fixtures 中的文件来自备课实验床）。
    uv run --frozen python -m unittest tests.test_parse -v
"""

import json
import pathlib
import unittest

from netprof import parse

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def text(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class PingCases(unittest.TestCase):

    def test_all_received(self):
        got = parse.parse_ping(text("ping_ok.txt"))
        self.assertEqual((got["sent"], got["received"], len(got["samples"])), (20, 20, 20))
        self.assertEqual(got["samples"][0], 0.096)
        self.assertEqual(got["samples"][-1], 0.169)
        self.assertAlmostEqual(sum(got["samples"]), 3.143, places=6)

    def test_losses_keep_sequence_order(self):
        got = parse.parse_ping(text("ping_loss.txt"))
        self.assertEqual((got["sent"], got["received"], len(got["samples"])), (20, 15, 15))
        self.assertAlmostEqual(sum(got["samples"]), 2.623, places=6)

    def test_duplicates_are_not_new_samples(self):
        got = parse.parse_ping(text("ping_dup.txt"))
        self.assertEqual((got["sent"], got["received"], len(got["samples"])), (10, 10, 10))
        # ping 摘要中的 max 0.242 来自一个 (DUP!) 回复，不应进入样本
        self.assertEqual(max(got["samples"]), 0.237)

    def test_everything_lost(self):
        got = parse.parse_ping(text("ping_all_lost.txt"))
        self.assertEqual(got, {"samples": [], "sent": 5, "received": 0})

    def test_truncated_output(self):
        truncated = "\n".join(text("ping_ok.txt").splitlines()[:5])
        with self.assertRaises(ValueError):
            parse.parse_ping(truncated)


class Iperf3Cases(unittest.TestCase):

    def test_reads_receiver_not_sender(self):
        got = parse.parse_iperf3(json.loads(text("iperf3_ok.json")))
        self.assertAlmostEqual(got["mbps"], 95.341295, places=4)
        self.assertAlmostEqual(got["sender_mbps"], 96.414759, places=4)
        self.assertEqual(got["retransmits"], 0)
        self.assertAlmostEqual(got["cpu_host"], 0.772, places=2)
        self.assertAlmostEqual(got["cpu_remote"], 10.193, places=2)

    def test_error_report(self):
        with self.assertRaises(ValueError) as ctx:
            parse.parse_iperf3(json.loads(text("iperf3_refused.json")))
        self.assertIn("Connection refused", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
