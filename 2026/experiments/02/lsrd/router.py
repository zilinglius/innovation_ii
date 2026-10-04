"""
把各部件接起来：事件 → 动作。这个文件是守护进程的“主板”，逻辑都在别处。

时间线上会发生的事：
  定时器  每 hello 秒        → 在每个活动接口广播 Hello（R1）
  定时器  每 0.5 秒          → 邻居表超时检查（R2 的 Dead 定时器）
  定时器  每 1 秒（开了 R9） → 重传未确认的 LSU
  套接字  收到 hello         → neighbors.process_hello → 事件 → 可能 R3 / R4
  套接字  收到 lsu           → flooder.on_lsu → LSDB 变了 → 安排一次 SPF
  套接字  收到 ack           → flooder.on_ack
  ip monitor（进阶 T6）      → 接口失去载波 → 该接口上的邻居立即 Down → R4

SPF 不是收到一条 LSA 就跑一次，而是延迟 spf_delay 秒合并这段时间内的所有变化再跑一次；
跑完把前缀表翻译成 (下一跳地址, 出接口)，与上次安装的做 diff，只 replace / del 有变化的路由（R8）。
"""

from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import spf, sysnet
from .lsdb import Flooder, Lsdb
from .neighbor import Event, NeighborTable
from .transport import Link, Transport

LOG = logging.getLogger("router")

Nexthop = Tuple[str, str]      # (下一跳地址, 出接口)


@dataclass
class Config:
  rid: int
  passive: List[str] = field(default_factory=list)   # 只通告网段、不发 Hello 的接口（机架侧的网桥）
  hello: int = 2
  dead: int = 8
  cost: Dict[str, int] = field(default_factory=dict) # 接口 → cost，缺省 10
  default_cost: int = 10
  spf_delay: float = 0.1
  ecmp: bool = False          # R7：并列时装成多下一跳（进阶 T8）
  ack: bool = False           # R9：可靠泛洪（进阶 T9）
  watch_links: bool = False   # 订阅内核链路事件（进阶 T6）
  install: bool = True        # False = 只算不写内核
  port: int = 5200


class Router:

  def __init__(self, cfg: Config, loop: Any) -> None:
    self.cfg = cfg
    self.rid = cfg.rid
    self.loop = loop
    self.stats: Dict[str, int] = collections.Counter()
    self.transport = Transport(loop, self.on_message, self.stats, port=cfg.port)
    self.neighbors = NeighborTable(cfg.rid, cfg.hello, cfg.dead)
    self.lsdb = Lsdb()
    self.flooder = Flooder(self)
    self.rib: Dict[str, Tuple[int, List[Nexthop]]] = {}   # SPF 的结果：prefix → (cost, 下一跳列表)
    self.installed: Dict[str, List[Nexthop]] = {}          # 已写进内核的
    self._spf_timer = None
    self._originate_timer = None
    self._monitor = None
    self.started_at = time.time()

  @property
  def ack_enabled(self) -> bool:
    return self.cfg.ack

  # ---- 启动 / 停止 ---------------------------------------------------------

  def start(self) -> None:
    for iface in sysnet.list_interfaces():
      if iface.name in self.cfg.passive:
        LOG.info("passive interface %s (%s): advertised, no Hello", iface.name, iface.network)
        continue
      if not iface.lower_up:
        LOG.warning("interface %s is not LOWER_UP, skipping", iface.name)
        continue
      self.transport.open(iface.name, iface.ifindex, iface.addr, iface.network,
                          self.cfg.cost.get(iface.name, self.cfg.default_cost))
    if not self.transport.links:
      LOG.warning("no active interface: nothing to say Hello on")
    for name in self.cfg.cost:
      if name not in self.transport.links and name not in self.cfg.passive:
        LOG.warning("--cost %s: no such interface here, ignored", name)

    self.loop.call_every(self.cfg.hello, self._send_hellos)
    self.loop.call_every(0.5, self._tick)
    if self.cfg.ack:
      self.loop.call_every(1.0, lambda: self.flooder.retransmit(self.loop.now()))
    if self.cfg.watch_links:
      self._monitor = sysnet.watch_links(self.loop, self.on_link_change)

    self.originate()          # 第一条 LSA：还没有邻居，只有自己的前缀
    self._send_hellos()       # 不等第一个周期，立刻打招呼

  def shutdown(self) -> None:
    if self._monitor is not None:
      self._monitor.terminate()
    self.transport.close_all()
    if self.cfg.install:
      sysnet.route_flush()
      LOG.info("flushed proto %d routes", sysnet.PROTO)

  # ---- 定时器 --------------------------------------------------------------

  def _send_hellos(self) -> None:
    for link in self.transport.links.values():
      self.transport.broadcast(link, self.neighbors.build_hello(link))

  def _tick(self) -> None:
    self._handle_events(self.neighbors.expire(self.loop.now()))

  # ---- 报文 ----------------------------------------------------------------

  def on_message(self, link: Link, src: str, msg: Dict[str, Any]) -> None:
    mtype = msg["type"]
    if mtype == "hello":
      self._handle_events(self.neighbors.process_hello(link, src, msg, self.loop.now()))
    elif mtype == "lsu":
      if self.flooder.on_lsu(link, src, msg):
        self.schedule_spf()
    elif mtype == "ack":
      self.flooder.on_ack(link, src, msg)

  # ---- 邻居事件 → R3 / R4 ------------------------------------------------------

  def _handle_events(self, events: Sequence[Event]) -> bool:
    """返回是否因此需要重新生成本机 LSA（并已安排）。"""
    changed = False
    for kind, nbr in events:
      if kind == "init":
        LOG.info("neighbor %s: Init", nbr)
      elif kind == "full":
        LOG.info("neighbor %s: Full", nbr)
        self.stats["neighbor_full"] += 1
        self.flooder.on_neighbor_full(nbr)        # R3
        changed = True
      elif kind == "down":
        LOG.info("neighbor %s: Down", nbr)
        self.stats["neighbor_down"] += 1
        self.flooder.on_neighbor_down(nbr)
        changed = True
      elif kind == "lost":
        LOG.info("neighbor %s: gone before Full", nbr)
    if changed:
      self.originate()                            # R4
    return changed

  # ---- R4：本机 LSA ------------------------------------------------------------

  def originate(self, only_if_changed: bool = False) -> None:
    """
    用当前的 Full 邻居与 LOWER_UP 接口的网段生成本机 LSA，然后安排一次 SPF。
    only_if_changed=True 时，链路与前缀都没变就什么也不做（链路事件常常一次来两条）。
    """
    self.loop.cancel(self._originate_timer)
    self._originate_timer = None
    links: Dict[int, int] = {}
    for nbr in self.neighbors.full():
      links[nbr.rid] = min(nbr.cost, links.get(nbr.rid, nbr.cost))
    link_list = [{"nbr": rid, "cost": cost} for rid, cost in sorted(links.items())]
    prefixes = [{"p": iface.network, "cost": self.cfg.cost.get(iface.name, self.cfg.default_cost)}
                for iface in sysnet.list_interfaces() if iface.lower_up]
    own = self.lsdb.get(self.rid)
    if only_if_changed and own is not None and own.links == link_list and \
        sorted(own.prefixes, key=lambda p: p["p"]) == sorted(prefixes, key=lambda p: p["p"]):
      return
    lsa = self.flooder.originate(link_list, prefixes)
    LOG.info("originated %s", lsa)
    self.schedule_spf()

  def schedule_originate(self) -> None:
    """R6 用：稍后重新生成（合并同一时刻的多次触发）。"""
    if self._originate_timer is None:
      self._originate_timer = self.loop.call_later(0.05, self.originate)

  # ---- 链路事件（进阶 T6）-------------------------------------------------------

  def on_link_change(self, name: str, up: bool) -> None:
    link = self.transport.links.get(name)
    LOG.info("link %s: %s", name, "LOWER_UP" if up else "down")
    handled = False
    if link is not None and not up:
      handled = self._handle_events(self.neighbors.link_down(link))
    if not handled:
      self.originate(only_if_changed=True)        # 前缀集合可能变了（LOWER_UP 过滤）

  # ---- R7 + R8：SPF 与安装 ------------------------------------------------------

  def schedule_spf(self) -> None:
    if self._spf_timer is None:
      self._spf_timer = self.loop.call_later(self.cfg.spf_delay, self.run_spf)

  def run_spf(self) -> None:
    self._spf_timer = None
    t0 = time.perf_counter()
    routes = spf.compute_routes(self.lsdb, self.rid, ecmp=self.cfg.ecmp)
    connected = {iface.network for iface in sysnet.list_interfaces()}
    desired: Dict[str, Tuple[int, List[Nexthop]]] = {}
    for prefix, (cost, hops) in routes.items():
      if prefix in connected:
        continue                                  # 直连网段绝不安装（R8）
      nexthops = sorted({(nbr.addr, nbr.link.name)
                         for rid in hops for nbr in self.neighbors.full_by_rid(rid)})
      if nexthops:
        desired[prefix] = (cost, nexthops)
    self.rib = desired
    self.stats["spf_runs"] += 1
    t1 = time.perf_counter()
    replaced, deleted = (self._install({p: nhs for p, (_, nhs) in desired.items()})
                         if self.cfg.install else (0, 0))
    t2 = time.perf_counter()
    LOG.info("spf: %d prefixes (%.1f ms), installed %d, deleted %d (%.1f ms)",
             len(desired), (t1 - t0) * 1000, replaced, deleted, (t2 - t1) * 1000)

  def _install(self, desired: Dict[str, List[Nexthop]]) -> Tuple[int, int]:
    """与上次安装的做 diff：变了的 replace，没了的 del。返回 (replace 数, del 数)。"""
    replaced = deleted = 0
    for prefix, nexthops in desired.items():
      if self.installed.get(prefix) != nexthops:
        if sysnet.route_replace(prefix, nexthops):
          self.installed[prefix] = nexthops
          replaced += 1
          self.stats["route_replaced"] += 1
          LOG.info("route replace %s via %s", prefix,
                   " + ".join(f"{via} dev {dev}" for via, dev in nexthops))
    for prefix in [p for p in self.installed if p not in desired]:
      if sysnet.route_del(prefix):
        deleted += 1
        self.stats["route_deleted"] += 1
        LOG.info("route del %s", prefix)
      del self.installed[prefix]
    return replaced, deleted

  # ---- 给 CLI 的快照 --------------------------------------------------------------

  def snapshot(self) -> Dict[str, Any]:
    now = self.loop.now()
    return {
        "rid": self.rid,
        "uptime": round(time.time() - self.started_at, 1),
        "config": {"hello": self.cfg.hello, "dead": self.cfg.dead, "passive": self.cfg.passive,
                   "ecmp": self.cfg.ecmp, "ack": self.cfg.ack, "watch_links": self.cfg.watch_links,
                   "install": self.cfg.install},
        "links": [{"name": l.name, "addr": l.addr, "prefix": l.prefix, "cost": l.cost}
                  for l in self.transport.links.values()],
        "neighbors": self.neighbors.snapshot(now),
        "lsdb": self.lsdb.snapshot(),
        "digest": self.lsdb.digest(),
        "rib": {p: {"cost": c, "nexthops": [{"via": v, "dev": d} for v, d in nhs]}
                for p, (c, nhs) in sorted(self.rib.items())},
        "fib": sysnet.route_list() if self.cfg.install else [],
        "pending_acks": len(self.flooder.pending),
        "stats": dict(sorted(self.stats.items())),
    }
