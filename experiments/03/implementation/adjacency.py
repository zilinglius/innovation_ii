"""
教学版 OSPF 的邻接状态管理。

状态机做了适度简化，但保留了 OSPF 的关键阶段命名。通过 Hello
报文驱动 Down→Init→Two-Way→Full 的转换，并将 ExStart/Exchange/
Loading 合并为一次跃迁，方便学生把精力放在 LSA 泛洪与 SPF 上。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Optional


class NeighborState(str, Enum):
  DOWN = "down"
  INIT = "init"
  TWO_WAY = "two-way"
  FULL = "full"  # combined ExStart/Exchange/Loading


@dataclass
class Adjacency:
  router_id: str
  interface: str
  state: NeighborState = NeighborState.DOWN
  dr: Optional[str] = None
  bdr: Optional[str] = None
  last_hello: float = 0.0
  dead_timer: float = 0.0
  hello_options: Dict[str, Any] = field(default_factory=dict)

  def process_hello(
      self,
      message: Dict[str, Any],
      now: float,
      *,
      local_router_id: str,
      hello_interval: float,
      dead_interval: float,
  ) -> bool:
    """
    处理收到的 Hello 报文，根据对端携带的参数更新邻接状态。

    返回值:
      bool: 若状态发生变化，返回 True 以提示上层采取后续动作。
    """
    changed = False
    neighbors: Iterable[str] = message.get("neighbors", [])

    # 同步对端的 Dead Interval，并记录最近一次 Hello 的时间戳。
    remote_dead = message.get("dead_interval")
    self.dead_timer = float(remote_dead) if isinstance(remote_dead, (int, float)) and remote_dead > 0 else float(dead_interval)
    self.last_hello = now
    self.hello_options = dict(message.get("options") or {})

    # 按 RFC 2328 的流程推进状态。初次收到报文时从 Down → Init。
    if self.state == NeighborState.DOWN:
      self.state = NeighborState.INIT
      changed = True

    if local_router_id in neighbors:
      # 出现在对端邻居列表里，说明链路已实现双向通信。
      if self.state in {NeighborState.DOWN, NeighborState.INIT}:
        self.state = NeighborState.TWO_WAY
        changed = True

    # 本实验仅关注点到点拓扑，可直接升至 Full。
    if self.state == NeighborState.TWO_WAY:
      if (message.get("options") or {}).get("p2p", True):
        self.state = NeighborState.FULL
        changed = True

    # 记录对端的 DR/BDR 信息，便于在广播网络实验中扩展。
    dr = message.get("dr")
    if dr != self.dr:
      self.dr = dr
      changed = True
    bdr = message.get("bdr")
    if bdr != self.bdr:
      self.bdr = bdr
      changed = True

    return changed

  def build_hello(
      self,
      *,
      router_id: str,
      network_mask: str,
      hello_interval: int,
      dead_interval: int,
      known_neighbors: Iterable[str],
      priority: int = 1,
      options: Optional[Dict[str, Any]] = None,
  ) -> Dict[str, Any]:
    """
    构造发送给邻居的 Hello 报文负载，包含必须协商字段与邻居列表。
    """
    payload = {
        "network_mask": network_mask,
        "hello_interval": int(hello_interval),
        "dead_interval": int(dead_interval),
        "priority": int(priority),
        "neighbors": list(known_neighbors),
        "options": dict(options or {"p2p": True}),
    }
    if self.dr:
      payload["dr"] = self.dr
    if self.bdr:
      payload["bdr"] = self.bdr
    return payload

  def tick(self, now: float) -> bool:
    """
    周期性检测邻居是否超时。若超过 Dead Interval，则将状态切回 Down。
    """
    if self.state == NeighborState.DOWN:
      return False
    if self.dead_timer <= 0:
      return False
    if now - self.last_hello <= self.dead_timer:
      return False
    self.state = NeighborState.DOWN
    self.dr = None
    self.bdr = None
    self.hello_options.clear()
    return True
