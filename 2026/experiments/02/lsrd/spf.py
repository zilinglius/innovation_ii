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


_TODO_SEEN = set()


def _todo(what: str) -> None:
  """还没实现的规则：只在日志里提醒一次。"""
  if what not in _TODO_SEEN:
    _TODO_SEEN.add(what)
    LOG.warning("TODO 尚未实现：%s", what)


def build_graph(lsdb: Lsdb) -> Graph:
  """从 LSDB 建有向图：graph[a][b] = a → b 的 cost，仅当 a 列了 b 且 b 列了 a。"""
  # ---- TODO（规范 R7）：把下面的桩换成你的实现 ----
  raise NotImplementedError("spf.build_graph：规范 R7")


def dijkstra(graph: Graph, root: int) -> Tuple[Dict[int, int], Dict[int, Set[int]]]:
  """
  返回 (dist, first_hops)：
    dist[rid]       root 到 rid 的最短距离（不可达的不出现）
    first_hops[rid] 所有最短路径上紧挨着 root 的那一跳的集合；root 自己是空集
  """
  # ---- TODO（规范 R7）：把下面的桩换成你的实现 ----
  raise NotImplementedError("spf.dijkstra：规范 R7")


def compute_routes(lsdb: Lsdb, root: int, ecmp: bool = False) -> Dict[str, Tuple[int, List[int]]]:
  """
  算出 root 的前缀表：{prefix: (总 cost, [首跳 rid, ...])}。
  首跳列表升序；ecmp=False 时只保留第一个（即 rid 最小的）。root 自己通告的前缀不出现。
  """
  # ---- TODO（规范 R7）：把下面的桩换成你的实现 ----
  _todo("spf.compute_routes（R7）")
  return {}
