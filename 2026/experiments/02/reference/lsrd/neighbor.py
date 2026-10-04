"""
邻居发现：Hello 的生成与处理、邻居表与状态机。对应规范 R1、R2。

  R1  每 hello 秒在每个活动接口广播一次 Hello（周期由 router.py 的定时器驱动，
      这里负责“造”出 Hello：build_hello）。
  R2  邻居状态：收到对方 Hello → Init；对方 seen 里有我 → Full；
      dead 秒没收到 → Down 并删除。hello / dead 与本端不一致的 Hello 丢弃。

邻居是**接口级**的：同一个 router id 从两个接口都能听到时，是两个邻居条目
（键是 (rid, 接口名)）。三角形实验床上不会出现这种情况，但规范不排除。

process_hello / expire / link_down 返回“事件列表”，由 router.py 决定做什么：
  ("init", nbr)   新邻居出现（还没双向确认）
  ("full", nbr)   邻居进入 Full —— router 会把 LSDB 全量发给它（R3）并重新生成本机 LSA（R4）
  ("down", nbr)   一个 Full 邻居消失或退回 Init —— router 会重新生成本机 LSA（R4）
  ("lost", nbr)   一个从未到过 Full 的邻居超时消失（只记日志）
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .transport import VERSION, Link

Event = Tuple[str, "Neighbor"]


class State(enum.Enum):
  INIT = "Init"      # 听到了对方，对方还没听到我（或还没告诉我它听到了）
  FULL = "Full"      # 双向可达：对方的 Hello 里 seen 包含我


@dataclass
class Neighbor:
  rid: int
  link: Link
  addr: str                  # 对方在这条链路上的地址 = 它 Hello 的源地址；R8 的下一跳就是它
  state: State
  last_seen: float           # 最近一次收到它 Hello 的时刻（loop.now()）
  since: float               # 进入当前状态的时刻

  @property
  def cost(self) -> int:
    return self.link.cost

  def __str__(self) -> str:
    return f"rid={self.rid} via {self.link.name} ({self.addr})"


class NeighborTable:

  def __init__(self, rid: int, hello: int, dead: int) -> None:
    self.rid = rid
    self.hello = hello
    self.dead = dead
    self._table: Dict[Tuple[int, str], Neighbor] = {}     # (rid, 接口名) → Neighbor

  # ---- 查询 ---------------------------------------------------------------

  def all(self) -> List[Neighbor]:
    return sorted(self._table.values(), key=lambda n: (n.rid, n.link.name))

  def on_link(self, link: Link) -> List[Neighbor]:
    return [n for n in self.all() if n.link is link]

  def full(self) -> List[Neighbor]:
    return [n for n in self.all() if n.state is State.FULL]

  def full_by_rid(self, rid: int) -> List[Neighbor]:
    return [n for n in self.full() if n.rid == rid]

  def get(self, rid: int, link: Link) -> Optional[Neighbor]:
    return self._table.get((rid, link.name))

  # ---- R1：造 Hello ---------------------------------------------------------

  def build_hello(self, link: Link) -> Dict[str, Any]:
    """
    为某个接口生成一条 Hello（规范 3.2 节）：
      {"v": 1, "type": "hello", "rid": 本机 id, "hello": ..., "dead": ...,
       "seen": [在这个接口上听到过的 router id ...]}
    seen 里放的是本接口上**所有**邻居（Init 与 Full 都算）——它的作用就是告诉对方“我听到你了”。
    """
    # >>> STUDENT R1
    return {
        "v": VERSION,
        "type": "hello",
        "rid": self.rid,
        "hello": self.hello,
        "dead": self.dead,
        "seen": sorted(n.rid for n in self.on_link(link)),
    }
    # <<< STUDENT

  # ---- R2：处理 Hello 与超时 ------------------------------------------------

  def process_hello(self, link: Link, src: str, msg: Dict[str, Any], now: float) -> List[Event]:
    """
    处理从 link 收到的、源地址为 src 的 Hello。返回事件列表（见文件头）。
      1. hello / dead 与本端不一致 → 丢弃，返回 []；
      2. 没见过这个 (rid, 接口) → 新建条目，状态 Init，产生 ("init", nbr)；
      3. 刷新 last_seen 与 addr；
      4. 对方的 seen 里有我 → 若尚未 Full，转 Full，产生 ("full", nbr)；
         对方的 seen 里没有我 → 若已 Full（对方重启过），退回 Init，产生 ("down", nbr)。
    """
    # >>> STUDENT R2
    events: List[Event] = []
    if msg["hello"] != self.hello or msg["dead"] != self.dead:
      return events
    key = (msg["rid"], link.name)
    nbr = self._table.get(key)
    if nbr is None:
      nbr = Neighbor(rid=msg["rid"], link=link, addr=src, state=State.INIT,
                     last_seen=now, since=now)
      self._table[key] = nbr
      events.append(("init", nbr))
    nbr.last_seen = now
    nbr.addr = src
    two_way = self.rid in msg["seen"]
    if two_way and nbr.state is State.INIT:
      nbr.state = State.FULL
      nbr.since = now
      events.append(("full", nbr))
    elif not two_way and nbr.state is State.FULL:
      nbr.state = State.INIT
      nbr.since = now
      events.append(("down", nbr))
    return events
    # <<< STUDENT

  def expire(self, now: float) -> List[Event]:
    """
    Dead 定时器：删掉所有 now - last_seen > dead 的邻居。
    曾经 Full 的产生 ("down", nbr)，从没到过 Full 的产生 ("lost", nbr)。
    """
    # >>> STUDENT R2
    events: List[Event] = []
    for key, nbr in list(self._table.items()):
      if now - nbr.last_seen > self.dead:
        del self._table[key]
        events.append(("down" if nbr.state is State.FULL else "lost", nbr))
    return events
    # <<< STUDENT

  def link_down(self, link: Link) -> List[Event]:
    """
    某个接口失去载波（进阶任务 T6，由 sysnet.watch_links 触发）：
    立刻删掉这个接口上的全部邻居，不等 Dead 定时器。事件语义与 expire 相同。
    """
    # >>> STUDENT R2
    events: List[Event] = []
    for nbr in self.on_link(link):
      del self._table[(nbr.rid, link.name)]
      events.append(("down" if nbr.state is State.FULL else "lost", nbr))
    return events
    # <<< STUDENT

  # ---- 给 CLI 看的快照 --------------------------------------------------------

  def snapshot(self, now: float) -> List[Dict[str, Any]]:
    return [{
        "rid": n.rid, "iface": n.link.name, "addr": n.addr, "state": n.state.value,
        "cost": n.cost, "since": round(now - n.since, 1), "last_hello": round(now - n.last_seen, 1),
    } for n in self.all()]
