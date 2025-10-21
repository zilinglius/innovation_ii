"""
路由器主体逻辑。

负责：
- 解析配置并初始化接口；
- 管理邻居与 LSDB；
- 驱动 SPF 与路由安装；
- 与事件循环交互，处理定时器与消息 IO。
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ospf.adjacency import Adjacency, NeighborState
from ospf.events import EventLoop
from ospf.lsdb import LinkStateDatabase
from ospf import message, timers

LOGGER = logging.getLogger(__name__)


@dataclass
class InterfaceConfig:
  name: str
  ip: str
  cost: int
  neighbors: List[Dict[str, str]]
  hello_interval: Optional[int] = None
  dead_interval: Optional[int] = None


@dataclass
class InterfaceState:
  config: InterfaceConfig
  address: ipaddress.IPv4Interface
  socket: Optional[socket.socket] = None
  adjacency: Dict[str, Adjacency] = field(default_factory=dict)


class Router:
  def __init__(
      self,
      router_id: str,
      config: Dict[str, object],
      event_loop: EventLoop,
      dry_run: bool = False,
      single_process: bool = False,
  ) -> None:
    self.router_id = router_id
    self.config = config
    self.loop = event_loop
    self.dry_run = dry_run
    self.single_process = single_process
    self.area_id = str(config.get("defaults", {}).get("area", "0.0.0.0"))
    self.interfaces: Dict[str, InterfaceState] = {}
    self.lsdb = LinkStateDatabase()
    self._sockets: List[socket.socket] = []

  # --- 生命周期 -------------------------------------------------------

  def bootstrap(self) -> None:
    """
    初始化路由器实例。

    TODO:
      - 解析配置文件，填充 InterfaceState；
      - 为每个接口打开 UDP 套接字（建议监听 224.0.0.5 类似组播或直接单播）；
      - 向事件循环注册套接字回调；
      - 调度周期性 Hello、LS Refresh 等任务。
    """
    LOGGER.debug("bootstrap router %s", self.router_id)
    raise NotImplementedError("TODO: bootstrap router")

  def shutdown(self) -> None:
    LOGGER.debug("shutdown router %s", self.router_id)
    for sock in self._sockets:
      with suppress(Exception):
        sock.close()
    self._sockets.clear()

  # --- 消息处理 -------------------------------------------------------

  def _on_socket_readable(self, sock: socket.socket) -> None:
    """
    处理套接字可读事件。

    TODO:
      - 接收数据报并解析；
      - 根据来源匹配接口或邻居；
      - 调用 `process_message`。
    """
    raise NotImplementedError("TODO: handle incoming datagrams")

  def process_message(self, msg: message.Message, src: Tuple[str, int]) -> None:
    """
    根据消息类型分发处理。

    TODO:
      - HELLO → 更新邻居状态；
      - LSU → 调用 LSDB install，并决定是否泛洪；
      - LSR/DD/ACK → 结合实验要求自行补充。
    """
    raise NotImplementedError("TODO: dispatch message to handlers")

  def send_hello(self, iface: InterfaceState) -> None:
    """
    从指定接口发送 Hello。

    TODO:
      - 构建 Hello 报文（调用 adjacency.build_hello 或 message.build_hello）；
      - 选择发送地址（多播或对等体列表）；
      - 发送后更新邻居状态。
    """
    raise NotImplementedError("TODO: send hello on interface")

  # --- SPF 与路由安装 -------------------------------------------------

  def run_spf(self) -> None:
    """
    运行 Dijkstra 计算最短路径树，并更新路由表。

    TODO:
      - 从 self.lsdb.snapshot() 构建图；
      - 执行 SPF 得到到各 LSDB 节点的成本；
      - 生成转发表（可存储在 self.routes 或直接调用 `ip route`）；
      - 日志输出结果供 CLI 使用。
    """
    raise NotImplementedError("TODO: implement SPF")

  # --- 辅助方法 -------------------------------------------------------

  def get_neighbors(self) -> Dict[str, Dict[str, str]]:
    """
    提供给 CLI 的邻居视图。
    """
    snapshot: Dict[str, Dict[str, str]] = {}
    for ifname, state in self.interfaces.items():
      for rid, adj in state.adjacency.items():
        snapshot[f"{ifname}:{rid}"] = {
            "interface": ifname,
            "neighbor": rid,
            "state": adj.state.value,
        }
    return snapshot

  def get_lsdb(self) -> Dict[str, object]:
    """
    提供 LSDB 快照。
    """
    return {
        f"{lsa.header.lsa_type}:{lsa.header.lsa_id}": {
            "adv_router": lsa.header.advertising_router,
            "seq": lsa.header.sequence,
            "age": lsa.header.age,
            "payload": lsa.payload,
        }
        for lsa in self.lsdb.snapshot().values()
    }

  def get_routes(self) -> Dict[str, object]:
    """
    返回当前转发表（由学生在 run_spf 中填充）。
    """
    # TODO: 可以维护 self.routes，在 SPF 中更新。
    raise NotImplementedError("TODO: expose routing table state")


from contextlib import suppress
