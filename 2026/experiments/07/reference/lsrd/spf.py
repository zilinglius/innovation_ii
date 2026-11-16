"""
最短路径计算：从 LSDB 建图、Dijkstra、取首跳、算前缀表。对应规范 R7。

这个文件是纯函数，不碰套接字也不碰内核，可以离线测试：
    uv run python -m unittest tests.test_spf

  build_graph(lsdb)                → {rid: {邻居 rid: cost}}    只保留双向都声明了的边
  dijkstra(graph, root)            → (dist, first_hops)          first_hops[rid] = 到 rid 的所有等价首跳
  compute_routes(lsdb, root, ecmp) → {prefix: (cost, [首跳 rid, ...])}

R7 的三条约定：
  1. 边 A–B 存在，当且仅当 A 的 links 里列了 B **且** B 的 links 里列了 A；两个方向的 cost 可以不同。
     （拔线后 r1 先删掉了 r2，r2 的旧 LSA 还列着 r1——这条“半截边”必须当作不存在。）
  2. 前缀 P 的距离 = 通告它的路由器的距离 + P 自己的 cost；多台路由器通告同一前缀取最小。
  3. 距离并列：基础版取 router id 最小的首跳（结果确定、便于验收）；ecmp=True 时保留全部首跳。
root 自己通告的前缀是直连的，不出现在结果里。
"""

from __future__ import annotations

import heapq
import logging
from typing import Dict, List, Set, Tuple

from .lsdb import Lsdb

LOG = logging.getLogger("spf")

Graph = Dict[int, Dict[int, int]]


def build_graph(lsdb: Lsdb) -> Graph:
  """从 LSDB 建有向图：graph[a][b] = a → b 的 cost，仅当 a 列了 b 且 b 列了 a。"""
  # >>> STUDENT R7
  declared: Dict[int, Dict[int, int]] = {}
  for lsa in lsdb.all():
    declared[lsa.rid] = {}
    for link in lsa.links:
      nbr, cost = link["nbr"], link["cost"]
      if nbr not in declared[lsa.rid] or cost < declared[lsa.rid][nbr]:
        declared[lsa.rid][nbr] = cost
  graph: Graph = {rid: {} for rid in declared}
  for a, links in declared.items():
    for b, cost in links.items():
      if b in declared and a in declared[b]:
        graph[a][b] = cost
  return graph
  # <<< STUDENT


def dijkstra(graph: Graph, root: int) -> Tuple[Dict[int, int], Dict[int, Set[int]]]:
  """
  返回 (dist, first_hops)：
    dist[rid]       root 到 rid 的最短距离（不可达的不出现）
    first_hops[rid] 所有最短路径上紧挨着 root 的那一跳的集合；root 自己是空集
  """
  # >>> STUDENT R7
  dist: Dict[int, int] = {root: 0}
  first_hops: Dict[int, Set[int]] = {root: set()}
  heap: List[Tuple[int, int]] = [(0, root)]
  done: Set[int] = set()
  while heap:
    d, u = heapq.heappop(heap)
    if u in done:
      continue
    done.add(u)
    for v, cost in graph.get(u, {}).items():
      nd = d + cost
      hops = {v} if u == root else set(first_hops[u])
      if v not in dist or nd < dist[v]:
        dist[v] = nd
        first_hops[v] = hops
        heapq.heappush(heap, (nd, v))
      elif nd == dist[v]:
        first_hops[v] |= hops
  return dist, first_hops
  # <<< STUDENT


def compute_routes(lsdb: Lsdb, root: int, ecmp: bool = False) -> Dict[str, Tuple[int, List[int]]]:
  """
  算出 root 的前缀表：{prefix: (总 cost, [首跳 rid, ...])}。
  首跳列表升序；ecmp=False 时只保留第一个（即 rid 最小的）。root 自己通告的前缀不出现。
  """
  # >>> STUDENT R7
  graph = build_graph(lsdb)
  dist, first_hops = dijkstra(graph, root)
  own = lsdb.get(root)
  own_prefixes = {p["p"] for p in own.prefixes} if own else set()
  best: Dict[str, Tuple[int, Set[int]]] = {}
  for lsa in lsdb.all():
    if lsa.rid == root or lsa.rid not in dist:
      continue
    for entry in lsa.prefixes:
      prefix = entry["p"]
      if prefix in own_prefixes:
        continue
      cost = dist[lsa.rid] + entry["cost"]
      hops = first_hops[lsa.rid]
      if prefix not in best or cost < best[prefix][0]:
        best[prefix] = (cost, set(hops))
      elif cost == best[prefix][0]:
        best[prefix][1].update(hops)
  routes: Dict[str, Tuple[int, List[int]]] = {}
  for prefix, (cost, hops) in best.items():
    ordered = sorted(hops)
    routes[prefix] = (cost, ordered if ecmp else ordered[:1])
  return routes
  # <<< STUDENT
