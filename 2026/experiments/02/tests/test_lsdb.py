"""
离线测试 R5 的前半（LSDB 只认更大的 seq）与几件给定的小事（编解码、ip monitor 的解析）。
    uv run python -m unittest tests.test_lsdb -v
"""

import unittest

from lsrd import sysnet, transport
from lsrd.lsdb import Lsa, Lsdb


def lsa(rid, seq, links=(), prefixes=()):
  return Lsa(rid=rid, seq=seq, links=[{"nbr": n, "cost": c} for n, c in links],
             prefixes=[{"p": p, "cost": c} for p, c in prefixes])


class LsdbRules(unittest.TestCase):

  def test_unknown_router_is_newer(self):
    db = Lsdb()
    self.assertTrue(db.is_newer(lsa(1, 1)))
    self.assertTrue(db.install(lsa(1, 1)))
    self.assertEqual(len(db), 1)

  def test_larger_seq_replaces(self):
    db = Lsdb()
    db.install(lsa(1, 3, links=[(2, 10)]))
    self.assertTrue(db.install(lsa(1, 4, links=[(3, 10)])))
    self.assertEqual(db.get(1).seq, 4)
    self.assertEqual(db.get(1).links, [{"nbr": 3, "cost": 10}])

  def test_equal_or_smaller_seq_is_dropped(self):
    db = Lsdb()
    db.install(lsa(1, 3, links=[(2, 10)]))
    self.assertFalse(db.install(lsa(1, 3, links=[(9, 10)])))
    self.assertFalse(db.install(lsa(1, 2)))
    self.assertEqual(db.get(1).links, [{"nbr": 2, "cost": 10}])

  def test_digest_ignores_insertion_order(self):
    a, b = Lsdb(), Lsdb()
    a.install(lsa(1, 1, prefixes=[("10.0.1.0/24", 10)]))
    a.install(lsa(2, 5, links=[(1, 10)]))
    b.install(lsa(2, 5, links=[(1, 10)]))
    b.install(lsa(1, 1, prefixes=[("10.0.1.0/24", 10)]))
    self.assertEqual(a.digest(), b.digest())
    b.install(lsa(2, 6, links=[(1, 10)]))
    self.assertNotEqual(a.digest(), b.digest())


class Encoding(unittest.TestCase):

  def test_roundtrip(self):
    msg = {"v": 1, "type": "hello", "rid": 1, "hello": 2, "dead": 8, "seen": [2, 3]}
    self.assertEqual(transport.decode(transport.encode(msg)), msg)

  def test_rejects_bad_messages(self):
    for bad in (b"not json", b'{"v":2,"type":"hello","rid":1}', b'{"v":1,"type":"nope","rid":1}',
                b'{"v":1,"type":"hello","rid":"1"}', b'{"v":1,"type":"lsu","rid":1,"lsas":[{"rid":1}]}'):
      with self.assertRaises(transport.MessageError, msg=bad):
        transport.decode(bad)

  def test_lsa_roundtrip(self):
    original = lsa(1, 7, links=[(3, 10), (2, 10)], prefixes=[("10.0.1.0/24", 10)])
    self.assertEqual(Lsa.from_dict(original.to_dict()).to_dict(), original.to_dict())


class MonitorParsing(unittest.TestCase):

  def test_parse_lines(self):
    down = ("5: r1-r2@if6: <BROADCAST,MULTICAST> mtu 1500 qdisc noqueue state DOWN group default "
            "\\    link/ether 3e:76:a7:3f:4b:4e brd ff:ff:ff:ff:ff:ff link-netns r2")
    nocarrier = ("6: r2-r1@if5: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue "
                 "state LOWERLAYERDOWN group default \\    link/ether aa:bb brd ff:ff:ff:ff:ff:ff")
    up = "5: r1-r2@if6: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default"
    deleted = "Deleted 7: r1-r3@if8: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP"
    self.assertEqual(sysnet.parse_monitor_line(down), ("r1-r2", False))
    self.assertEqual(sysnet.parse_monitor_line(nocarrier), ("r2-r1", False))
    self.assertEqual(sysnet.parse_monitor_line(up), ("r1-r2", True))
    self.assertEqual(sysnet.parse_monitor_line(deleted), ("r1-r3", True))
    self.assertIsNone(sysnet.parse_monitor_line("10.0.2.0/24 via 10.0.13.2 dev r1-r3 proto 200 metric 20"))


if __name__ == "__main__":
  unittest.main()
