"""
Neighbor state handling for the teaching OSPF implementation.

The state machine is intentionally simplified while keeping terminology close
to OSPF.  Hello exchanges transition peers through the usual phases and we
collapse the database exchange steps (ExStart/Exchange/Loading) into a direct
promotion to Full once bidirectional connectivity is confirmed.  This keeps the
lab focused on the link state flooding and SPF logic.
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
    Update state based on the fields contained in a received Hello packet.

    Returns ``True`` when the adjacency state changed and callers should trigger
    further actions (e.g. LSDB synchronisation).
    """
    changed = False
    neighbors: Iterable[str] = message.get("neighbors", [])

    # Refresh timers according to peer settings.
    remote_dead = message.get("dead_interval")
    self.dead_timer = float(remote_dead) if isinstance(remote_dead, (int, float)) and remote_dead > 0 else float(dead_interval)
    self.last_hello = now
    self.hello_options = dict(message.get("options") or {})

    # Transition sequence roughly following RFC 2328 section 10.
    if self.state == NeighborState.DOWN:
      self.state = NeighborState.INIT
      changed = True

    if local_router_id in neighbors:
      # Bidirectional communication established.
      if self.state in {NeighborState.DOWN, NeighborState.INIT}:
        self.state = NeighborState.TWO_WAY
        changed = True

    # On point-to-point links we can directly advance to Full.
    if self.state == NeighborState.TWO_WAY:
      if (message.get("options") or {}).get("p2p", True):
        self.state = NeighborState.FULL
        changed = True

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
    Compose the payload for a Hello message sent over this adjacency.
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
    Periodic maintenance – declare the neighbor down when the Dead timer expires.

    Returns ``True`` when the state transitioned to Down.
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
