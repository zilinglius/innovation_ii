"""
离线测试 R7：把 tests/graphs/*.json 里的 LSDB 喂给 spf.compute_routes，对照期望的前缀表。
不需要 root，不需要实验床：
    uv run python -m unittest tests.test_spf -v
"""

import json
import pathlib
import unittest

from lsrd.lsdb import Lsa, Lsdb
from lsrd import spf

GRAPHS = pathlib.Path(__file__).parent / "graphs"


def load(name):
  data = json.loads((GRAPHS / f"{name}.json").read_text(encoding="utf-8"))
  lsdb = Lsdb()
  for d in data["lsdb"]:
    lsdb.put(Lsa.from_dict(d))          # put 不做 seq 比较，测试不依赖 R5
  return data, lsdb


def normalise(routes):
  return {prefix: [cost, list(hops)] for prefix, (cost, hops) in routes.items()}


class GraphCases(unittest.TestCase):

  def check(self, name, ecmp=False):
    data, lsdb = load(name)
    key = "expected_ecmp" if ecmp else "expected"
    for root, expected in data[key].items():
      self.assertEqual(normalise(spf.compute_routes(lsdb, int(root), ecmp=ecmp)), expected,
                       f"graph={name} root={root} ecmp={ecmp}")

  def test_triangle(self):
    self.check("triangle")

  def test_triangle_ecmp(self):
    self.check("triangle", ecmp=True)

  def test_cost20(self):
    self.check("cost20")

  def test_cost20_ecmp(self):
    self.check("cost20", ecmp=True)

  def test_halflink_is_not_an_edge(self):
    self.check("halflink")

  def test_five_routers(self):
    self.check("five")


class GraphBuilding(unittest.TestCase):

  def test_two_way_check(self):
    _, lsdb = load("halflink")
    graph = spf.build_graph(lsdb)
    self.assertNotIn(2, graph[1])
    self.assertNotIn(1, graph[2])
    self.assertEqual(graph[1], {3: 10})
    self.assertEqual(graph[3], {1: 10, 2: 10})

  def test_dijkstra_first_hops(self):
    _, lsdb = load("triangle")
    dist, hops = spf.dijkstra(spf.build_graph(lsdb), 1)
    self.assertEqual(dist, {1: 0, 2: 10, 3: 10})
    self.assertEqual(hops[1], set())
    self.assertEqual(hops[2], {2})
    self.assertEqual(hops[3], {3})

  def test_unreachable_router_has_no_routes(self):
    _, lsdb = load("five")
    routes = spf.compute_routes(lsdb, 5)
    self.assertEqual(routes, {})


if __name__ == "__main__":
  unittest.main()
