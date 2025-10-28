"""
Routing process implementation for the simplified OSPF lab.

The process reads topology definitions from the YAML file used by the teaching
material, discovers neighbours through Hello exchanges, maintains a Link State
Database, floods LSAs, and runs SPF to derive a forwarding table.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import time
from dataclasses import dataclass, field
from heapq import heappop, heappush
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .adjacency import Adjacency, NeighborState
from .events import EventLoop
from .lsdb import Lsa, LsaHeader, LinkStateDatabase
from . import message, timers

LOGGER = logging.getLogger(__name__)

DEFAULT_OSPF_PORT = 5000
_SINGLE_PROCESS_BASE_PORT = 55000


@dataclass
class NeighborConfig:
  router_id: str
  addr: str


@dataclass
class InterfaceConfig:
  name: str
  ip: str
  cost: int
  neighbors: List[NeighborConfig]
  hello_interval: Optional[int] = None
  dead_interval: Optional[int] = None
  priority: int = 1


@dataclass
class InterfaceState:
  config: InterfaceConfig
  address: ipaddress.IPv4Interface
  adjacency: Dict[str, Adjacency] = field(default_factory=dict)
  neighbors: Dict[str, NeighborConfig] = field(default_factory=dict)


class Router:
  """
  Main OSPF-like routing process used in the lab environment.
  """

  def __init__(
      self,
      router_id: str,
      config: Dict[str, object],
      event_loop: EventLoop,
      *,
      dry_run: bool = False,
      single_process: bool = False,
  ) -> None:
    self.router_id = router_id
    self.config = config
    self.loop = event_loop
    self.dry_run = dry_run
    self.single_process = single_process

    defaults = config.get("defaults", {}) if isinstance(config.get("defaults"), dict) else {}
    self.area_id = str(defaults.get("area", "0.0.0.0"))
    self._default_hello = int(defaults.get("hello_interval", timers.HELLO_INTERVAL))
    self._default_dead = int(defaults.get("dead_interval", timers.DEAD_INTERVAL))

    self.interfaces: Dict[str, InterfaceState] = {}
    self._neighbor_index: Dict[str, List[Tuple[InterfaceState, NeighborConfig]]] = {}
    self.lsdb = LinkStateDatabase()
    self.routes: Dict[str, Dict[str, object]] = {}

    self._socket: Optional[socket.socket] = None
    self._socket_unregister: Optional[Callable[[], None]] = None
    self._local_port: int = DEFAULT_OSPF_PORT
    self._spf_scheduled = False
    self._spf_task = None
    self._self_sequence = 0x80000000
    self._loopback: Optional[ipaddress.IPv4Interface] = None

  # ---------------------------------------------------------------- lifecycle
  def bootstrap(self) -> None:
    LOGGER.debug("bootstrap router %s", self.router_id)
    self._bind_socket()
    self._load_interfaces()
    self._originate_router_lsa()
    self.run_spf()
    self.loop.schedule(timers.NEIGHBOR_TICK, self._tick_neighbors, repeat=True)

  def shutdown(self) -> None:
    LOGGER.debug("shutdown router %s", self.router_id)
    if self._socket_unregister:
      try:
        self._socket_unregister()
      except Exception:
        LOGGER.exception("failed to unregister socket")
      self._socket_unregister = None
    if self._socket:
      try:
        self._socket.close()
      except Exception:
        LOGGER.exception("failed to close socket")
      self._socket = None

  # ------------------------------------------------------------------- setup
  def _bind_socket(self) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
      sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
      pass

    if self.single_process:
      bind_ip = "127.0.0.1"
      self._local_port = self._port_for_router(self.router_id)
    else:
      bind_ip = "0.0.0.0"
      self._local_port = DEFAULT_OSPF_PORT

    sock.bind((bind_ip, self._local_port))
    self._socket = sock
    self._socket_unregister = self.loop.register_socket(sock, self._on_socket_readable)
    LOGGER.info("router %s listening on %s:%s", self.router_id, bind_ip, self._local_port)

  def _load_interfaces(self) -> None:
    routers_cfg = self.config.get("routers")
    if not isinstance(routers_cfg, dict):
      raise ValueError("config missing 'routers' mapping")
    router_cfg = routers_cfg.get(self.router_id)
    if not isinstance(router_cfg, dict):
      raise ValueError(f"config missing definition for router {self.router_id}")

    loopback = router_cfg.get("loopback")
    if loopback:
      self._loopback = ipaddress.ip_interface(loopback)

    interfaces_cfg = router_cfg.get("interfaces")
    if not isinstance(interfaces_cfg, list):
      raise ValueError(f"router {self.router_id} config missing interfaces list")

    for iface_entry in interfaces_cfg:
      if not isinstance(iface_entry, dict):
        raise ValueError("interface entry must be a mapping")
      neighbors_cfg = iface_entry.get("neighbors", [])
      neighbors: List[NeighborConfig] = []
      for neighbor in neighbors_cfg:
        if not isinstance(neighbor, dict):
          raise ValueError("neighbor entry must be a mapping")
        rid = str(neighbor.get("router_id"))
        addr = str(neighbor.get("addr"))
        if not rid or not addr:
          raise ValueError("neighbor entry requires router_id and addr")
        neighbors.append(NeighborConfig(router_id=rid, addr=addr))

      iface_cfg = InterfaceConfig(
          name=str(iface_entry.get("name")),
          ip=str(iface_entry.get("ip")),
          cost=int(iface_entry.get("cost", 1)),
          neighbors=neighbors,
          hello_interval=iface_entry.get("hello_interval"),
          dead_interval=iface_entry.get("dead_interval"),
          priority=int(iface_entry.get("priority", 1)),
      )
      iface_address = ipaddress.ip_interface(iface_cfg.ip)
      iface_state = InterfaceState(config=iface_cfg, address=iface_address)
      for neighbor in neighbors:
        adjacency = Adjacency(
            router_id=neighbor.router_id,
            interface=iface_cfg.name,
            dead_timer=float(iface_cfg.dead_interval or self._default_dead),
        )
        iface_state.adjacency[neighbor.router_id] = adjacency
        iface_state.neighbors[neighbor.router_id] = neighbor
        self._neighbor_index.setdefault(neighbor.router_id, []).append((iface_state, neighbor))

      self.interfaces[iface_cfg.name] = iface_state

      hello_interval = iface_cfg.hello_interval or self._default_hello
      self.loop.schedule(
          float(hello_interval),
          lambda state=iface_state: self.send_hello(state),
          repeat=True,
      )

      LOGGER.info(
          "interface %s configured ip=%s cost=%s neighbors=%s",
          iface_cfg.name,
          iface_cfg.ip,
          iface_cfg.cost,
          [n.router_id for n in neighbors],
      )

  # ------------------------------------------------------------------ timers
  def _tick_neighbors(self) -> None:
    now = time.time()
    any_down = False
    for iface_state in self.interfaces.values():
      for adjacency in iface_state.adjacency.values():
        if adjacency.tick(now):
          LOGGER.warning(
              "neighbor %s on %s timed out",
              adjacency.router_id,
              iface_state.config.name,
          )
          any_down = True
    if any_down:
      self._schedule_spf()
      self._originate_router_lsa()

    expired = list(self.lsdb.age(int(timers.NEIGHBOR_TICK)))
    if expired:
      LOGGER.debug("lsdb aged %d lsas", len(expired))
      self._schedule_spf()

  # --------------------------------------------------------------- messaging
  def _on_socket_readable(self, sock: socket.socket) -> None:
    try:
      data, addr = sock.recvfrom(65535)
    except OSError as exc:
      LOGGER.error("recv failed: %s", exc)
      return
    try:
      msg = message.Message.loads(data)
    except message.MessageError as exc:
      LOGGER.warning("discarding invalid message: %s", exc)
      return

    if msg.area_id != self.area_id:
      LOGGER.debug("ignoring message from different area %s", msg.area_id)
      return

    if msg.router_id == self.router_id:
      LOGGER.debug("ignoring self-originated message")
      return

    self.process_message(msg, src=(addr[0], addr[1]))

  def process_message(self, msg: message.Message, src: Tuple[str, int]) -> None:
    iface_state = self._resolve_interface_for_neighbor(msg.router_id, src[0])
    if iface_state is None:
      LOGGER.warning("received message from unknown neighbor %s (%s)", msg.router_id, src)
      return

    LOGGER.debug("received %s from %s via %s", msg.msg_type.value, msg.router_id, iface_state.config.name)

    if msg.msg_type == message.MessageType.HELLO:
      self._handle_hello(iface_state, msg, src_ip=src[0])
    elif msg.msg_type == message.MessageType.LINK_STATE_UPDATE:
      self._handle_lsu(msg)
    else:
      LOGGER.info("message type %s not implemented in simplified stack", msg.msg_type.value)

  def _handle_hello(self, iface_state: InterfaceState, msg: message.Message, src_ip: str) -> None:
    adjacency = iface_state.adjacency.get(msg.router_id)
    if adjacency is None:
      adjacency = Adjacency(
          router_id=msg.router_id,
          interface=iface_state.config.name,
          dead_timer=float(iface_state.config.dead_interval or self._default_dead),
      )
      iface_state.adjacency[msg.router_id] = adjacency
      neighbor_cfg = NeighborConfig(router_id=msg.router_id, addr=src_ip)
      iface_state.neighbors[msg.router_id] = neighbor_cfg
      self._neighbor_index.setdefault(msg.router_id, []).append((iface_state, neighbor_cfg))
    else:
      neighbor_cfg = iface_state.neighbors.get(msg.router_id)
      if neighbor_cfg and neighbor_cfg.addr != src_ip and not self.single_process:
        LOGGER.debug(
            "updating neighbor %s address on %s to %s",
            msg.router_id,
            iface_state.config.name,
            src_ip,
        )
        neighbor_cfg.addr = src_ip

    prev_state = adjacency.state
    changed = adjacency.process_hello(
        msg.payload,
        time.time(),
        local_router_id=self.router_id,
        hello_interval=float(iface_state.config.hello_interval or self._default_hello),
        dead_interval=float(iface_state.config.dead_interval or self._default_dead),
    )
    if changed:
      LOGGER.info(
          "neighbor %s on %s transitioned %s -> %s",
          adjacency.router_id,
          iface_state.config.name,
          prev_state.value,
          adjacency.state.value,
      )
      if adjacency.state == NeighborState.FULL:
        self._send_full_lsdb(adjacency.router_id)
      self._schedule_spf()
      self._originate_router_lsa()

  def _handle_lsu(self, msg: message.Message) -> None:
    lsas_raw = msg.payload.get("lsas", [])
    if not isinstance(lsas_raw, list):
      LOGGER.warning("malformed LSU payload from %s", msg.router_id)
      return
    installed: List[Lsa] = []
    for raw in lsas_raw:
      if not isinstance(raw, dict):
        continue
      try:
        lsa = LinkStateDatabase.from_message_payload(raw)
      except Exception:
        LOGGER.exception("failed to decode LSA from %s", msg.router_id)
        continue
      if self.lsdb.install(lsa):
        installed.append(lsa)

    if installed:
      LOGGER.info("installed %d lsas from %s", len(installed), msg.router_id)
      self._flood_lsas(installed, exclude=msg.router_id)
      self._schedule_spf()

  def send_hello(self, iface_state: InterfaceState) -> None:
    hello_interval = int(iface_state.config.hello_interval or self._default_hello)
    dead_interval = int(iface_state.config.dead_interval or self._default_dead)
    known_neighbors = [
        rid for rid, adj in iface_state.adjacency.items()
        if adj.state != NeighborState.DOWN
    ]
    payload = {
        "network_mask": str(iface_state.address.network.netmask),
        "hello_interval": hello_interval,
        "dead_interval": dead_interval,
        "priority": iface_state.config.priority,
        "neighbors": known_neighbors,
        "options": {"p2p": True},
    }
    msg = message.build_hello(
        router_id=self.router_id,
        area_id=self.area_id,
        **payload,
    )
    for neighbor in iface_state.neighbors.values():
      self._send_message(neighbor, msg)

  def _send_message(self, neighbor: NeighborConfig, msg: message.Message) -> None:
    if self._socket is None:
      LOGGER.warning("socket not initialised, drop message")
      return
    data = msg.dumps()
    dest_ip = neighbor.addr
    dest_port = self._local_port
    if self.single_process:
      dest_ip = "127.0.0.1"
      dest_port = self._port_for_router(neighbor.router_id)
    try:
      self._socket.sendto(data, (dest_ip, dest_port))
    except OSError as exc:
      LOGGER.error("failed to send %s to %s:%s - %s", msg.msg_type.value, dest_ip, dest_port, exc)

  def _flood_lsas(self, lsas: Iterable[Lsa], *, exclude: Optional[str] = None) -> None:
    payload_lsas = [self.lsdb.to_message_payload(lsa) for lsa in lsas]
    if not payload_lsas:
      return
    msg = message.Message(
        msg_type=message.MessageType.LINK_STATE_UPDATE,
        router_id=self.router_id,
        area_id=self.area_id,
        payload={
            "lsas": payload_lsas,
            "more": False,
        },
    )
    for iface_state in self.interfaces.values():
      for neighbor in iface_state.neighbors.values():
        if neighbor.router_id == exclude:
          continue
        adjacency = iface_state.adjacency.get(neighbor.router_id)
        if adjacency is None or adjacency.state == NeighborState.DOWN:
          continue
        self._send_message(neighbor, msg)

  def _send_full_lsdb(self, neighbor_id: str) -> None:
    snapshot = self.lsdb.snapshot().values()
    if not snapshot:
      return
    entries = self._neighbor_index.get(neighbor_id, [])
    if not entries:
      return
    msg = message.Message(
        msg_type=message.MessageType.LINK_STATE_UPDATE,
        router_id=self.router_id,
        area_id=self.area_id,
        payload={
            "lsas": [self.lsdb.to_message_payload(lsa) for lsa in snapshot],
            "more": False,
        },
    )
    for _, neighbor in entries:
      self._send_message(neighbor, msg)

  # ------------------------------------------------------------------- LSDB
  def _originate_router_lsa(self) -> None:
    links = []
    networks = []
    for iface_state in self.interfaces.values():
      networks.append(
          {
              "prefix": str(iface_state.address.network.with_prefixlen),
              "metric": iface_state.config.cost,
              "interface": iface_state.config.name,
          }
      )
      for neighbor in iface_state.neighbors.values():
        links.append(
            {
                "router_id": neighbor.router_id,
                "cost": iface_state.config.cost,
                "interface": iface_state.config.name,
            }
        )
    payload = {
        "router_id": self.router_id,
        "links": links,
        "networks": networks,
    }
    if self._loopback:
      payload["loopback"] = str(self._loopback.with_prefixlen)
      payload["loopback_cost"] = 0

    self._self_sequence += 1
    lsa = Lsa(
        header=LsaHeader(
            lsa_type="router",
            lsa_id=self.router_id,
            advertising_router=self.router_id,
            sequence=self._self_sequence,
        ),
        payload=payload,
    )
    if self.lsdb.install(lsa):
      LOGGER.debug("originated router lsa seq=%s", self._self_sequence)
      self._flood_lsas([lsa])
      self._schedule_spf()

  # -------------------------------------------------------------------- SPF
  def _schedule_spf(self) -> None:
    if self._spf_scheduled:
      return
    delay = timers.SPF_INITIAL_DELAY

    def run() -> None:
      self._spf_scheduled = False
      self.run_spf()

    self._spf_scheduled = True
    self.loop.schedule(delay, run)

  def run_spf(self) -> None:
    snapshot = self.lsdb.snapshot()
    graph: Dict[str, Dict[str, int]] = {}
    net_records: List[Tuple[str, str, int]] = []

    for lsa in snapshot.values():
      if lsa.header.lsa_type != "router":
        continue
      adv = lsa.header.advertising_router
      graph.setdefault(adv, {})
      for link in lsa.payload.get("links", []):
        router_id = str(link.get("router_id"))
        cost = int(link.get("cost", 1))
        graph.setdefault(adv, {})
        prev = graph[adv].get(router_id)
        if prev is None or cost < prev:
          graph[adv][router_id] = cost
      loopback = lsa.payload.get("loopback")
      if loopback:
        net_records.append((str(loopback), adv, int(lsa.payload.get("loopback_cost", 0))))
      for net in lsa.payload.get("networks", []):
        prefix = str(net.get("prefix"))
        metric = int(net.get("metric", 0))
        net_records.append((prefix, adv, metric))

    dist: Dict[str, float] = {self.router_id: 0}
    first_hop: Dict[str, Optional[str]] = {self.router_id: None}
    heap: List[Tuple[float, str]] = [(0, self.router_id)]

    while heap:
      cost, vertex = heappop(heap)
      if cost > dist.get(vertex, float("inf")):
        continue
      for neighbor, weight in graph.get(vertex, {}).items():
        new_cost = cost + weight
        if new_cost < dist.get(neighbor, float("inf")):
          dist[neighbor] = new_cost
          if vertex == self.router_id:
            first_hop[neighbor] = neighbor
          else:
            first_hop[neighbor] = first_hop.get(vertex)
          heappush(heap, (new_cost, neighbor))

    routes: Dict[str, Dict[str, object]] = {}

    # Local routes (connected)
    for iface_state in self.interfaces.values():
      routes[str(iface_state.address.network.with_prefixlen)] = {
          "cost": 0,
          "interface": iface_state.config.name,
          "next_hop": None,
      }
    if self._loopback:
      routes[str(self._loopback.with_prefixlen)] = {
          "cost": 0,
          "interface": "lo",
          "next_hop": None,
      }

    for prefix, adv_router, metric in net_records:
      if adv_router == self.router_id:
        continue
      base_cost = dist.get(adv_router)
      if base_cost is None:
        continue
      total_cost = base_cost + metric
      hop = first_hop.get(adv_router)
      iface_state, neighbor_cfg = self._resolve_first_hop(hop)
      routes[prefix] = {
          "cost": total_cost,
          "interface": iface_state.config.name if iface_state else None,
          "next_hop": neighbor_cfg.addr if neighbor_cfg else None,
          "next_hop_router": hop,
      }

    self.routes = routes
    LOGGER.info("spf computed %d routes", len(routes))

  # --------------------------------------------------------------- utilities
  def get_neighbors(self) -> Dict[str, Dict[str, object]]:
    snapshot: Dict[str, Dict[str, object]] = {}
    for ifname, state in self.interfaces.items():
      for rid, adj in state.adjacency.items():
        snapshot[f"{ifname}:{rid}"] = {
            "interface": ifname,
            "neighbor": rid,
            "state": adj.state.value,
            "last_hello": adj.last_hello,
        }
    return snapshot

  def get_lsdb(self) -> Dict[str, object]:
    view: Dict[str, object] = {}
    for key, lsa in self.lsdb.snapshot().items():
      view[f"{key[0]}:{key[1]}"] = {
          "adv_router": lsa.header.advertising_router,
          "seq": lsa.header.sequence,
          "age": lsa.header.age,
          "payload": lsa.payload,
      }
    return view

  def get_routes(self) -> Dict[str, object]:
    return dict(self.routes)

  def _resolve_interface_for_neighbor(self, router_id: str, src_ip: Optional[str]) -> Optional[InterfaceState]:
    entries = self._neighbor_index.get(router_id)
    if entries:
      return entries[0][0]
    if src_ip:
      for iface_state in self.interfaces.values():
        for neighbor in iface_state.neighbors.values():
          if neighbor.addr == src_ip:
            return iface_state
    return None

  def _resolve_first_hop(self, hop: Optional[str]) -> Tuple[Optional[InterfaceState], Optional[NeighborConfig]]:
    if hop is None:
      return None, None
    entries = self._neighbor_index.get(hop)
    if not entries:
      return None, None
    return entries[0]

  @staticmethod
  def _port_for_router(router_id: str) -> int:
    return _SINGLE_PROCESS_BASE_PORT + (abs(hash(router_id)) % 10000)
