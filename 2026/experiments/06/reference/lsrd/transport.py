"""
线上传输：每个活动接口一个 UDP 套接字，JSON 报文。

规范 3.1 节：
  - UDP 端口 5200；
  - 套接字用 SO_BINDTODEVICE 绑到接口上——收到的包一定来自这个接口，
    发出的包一定从这个接口出去；
  - Hello 发往 255.255.255.255（限制广播），其余报文单播给邻居；
  - 报文体是 UTF-8 JSON，公共字段 {"v": 1, "type": ..., "rid": ...}。

为什么每个接口一个套接字，而不是一个套接字听所有接口：
协议要知道“这个 Hello 是从哪个接口进来的”——邻居是接口级的概念。
单套接字也能做（IP_PKTINFO 辅助数据），但每接口一个套接字最直白。

抓包看报文：sudo ip netns exec r1 tcpdump -n -A -i r1-r2 udp port 5200
"""

from __future__ import annotations

import json
import logging
import socket
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

PORT = 5200
BROADCAST = "255.255.255.255"
VERSION = 1
MSG_TYPES = ("hello", "lsu", "ack")

LOG = logging.getLogger("transport")


class MessageError(ValueError):
  """报文格式不符合规范。"""


@dataclass
class Link:
  """一个活动接口及其套接字。"""
  name: str          # 接口名，如 r1-r2
  ifindex: int
  addr: str          # 本端地址，如 10.0.12.1
  prefix: str        # 所在网段，如 10.0.12.0/30
  cost: int          # 接口 cost（规范 3.3 节，默认 10）
  sock: socket.socket = field(repr=False)

  def __str__(self) -> str:
    return f"{self.name}({self.addr})"


# ---- 编解码 -------------------------------------------------------------------

def encode(msg: Dict[str, Any]) -> bytes:
  """字典 → 字节串。键排序、不留空白，同一报文的编码唯一。"""
  return json.dumps(msg, separators=(",", ":"), sort_keys=True).encode("utf-8")


def decode(data: bytes) -> Dict[str, Any]:
  """字节串 → 字典，并按报文类型校验必需字段。不合规范的报文抛 MessageError。"""
  try:
    msg = json.loads(data.decode("utf-8"))
  except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise MessageError(f"not JSON: {exc}") from exc
  if not isinstance(msg, dict):
    raise MessageError("message must be a JSON object")
  if msg.get("v") != VERSION:
    raise MessageError(f"unsupported version {msg.get('v')!r}")
  mtype = msg.get("type")
  if mtype not in MSG_TYPES:
    raise MessageError(f"unknown type {mtype!r}")
  if not isinstance(msg.get("rid"), int):
    raise MessageError("rid must be an integer")

  if mtype == "hello":
    for key in ("hello", "dead"):
      if not isinstance(msg.get(key), int) or msg[key] <= 0:
        raise MessageError(f"hello: {key} must be a positive integer")
    seen = msg.get("seen")
    if not isinstance(seen, list) or not all(isinstance(r, int) for r in seen):
      raise MessageError("hello: seen must be a list of router ids")
  elif mtype == "lsu":
    lsas = msg.get("lsas")
    if not isinstance(lsas, list):
      raise MessageError("lsu: lsas must be a list")
    for lsa in lsas:
      _check_lsa(lsa)
  elif mtype == "ack":
    acks = msg.get("acks")
    if not isinstance(acks, list):
      raise MessageError("ack: acks must be a list")
    for ack in acks:
      if not (isinstance(ack, dict) and isinstance(ack.get("rid"), int)
              and isinstance(ack.get("seq"), int)):
        raise MessageError("ack: each entry needs integer rid and seq")
  return msg


def _check_lsa(lsa: Any) -> None:
  if not isinstance(lsa, dict):
    raise MessageError("lsa must be an object")
  if not isinstance(lsa.get("rid"), int) or not isinstance(lsa.get("seq"), int):
    raise MessageError("lsa: rid and seq must be integers")
  links = lsa.get("links")
  if not isinstance(links, list) or not all(
      isinstance(l, dict) and isinstance(l.get("nbr"), int) and isinstance(l.get("cost"), int)
      for l in links):
    raise MessageError("lsa: links must be a list of {nbr, cost}")
  prefixes = lsa.get("prefixes")
  if not isinstance(prefixes, list) or not all(
      isinstance(p, dict) and isinstance(p.get("p"), str) and isinstance(p.get("cost"), int)
      for p in prefixes):
    raise MessageError("lsa: prefixes must be a list of {p, cost}")


# ---- 套接字 -------------------------------------------------------------------

OnMessage = Callable[[Link, str, Dict[str, Any]], None]


class Transport:
  """管理所有接口套接字。收到合法报文时调用 on_message(link, 源地址, 报文)。"""

  def __init__(self, loop: Any, on_message: OnMessage, stats: Dict[str, int],
               port: int = PORT) -> None:
    self.loop = loop
    self.on_message = on_message
    self.stats = stats
    self.port = port
    self.links: Dict[str, Link] = {}

  def open(self, name: str, ifindex: int, addr: str, prefix: str, cost: int) -> Link:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, name.encode())
    sock.bind(("", self.port))
    sock.setblocking(False)
    link = Link(name=name, ifindex=ifindex, addr=addr, prefix=prefix, cost=cost, sock=sock)
    self.links[name] = link
    self.loop.add_reader(sock.fileno(), lambda _fd, link=link: self._on_readable(link))
    LOG.info("listening on %s udp/%d (prefix %s, cost %d)", link, self.port, prefix, cost)
    return link

  def close_all(self) -> None:
    for link in self.links.values():
      self.loop.remove_reader(link.sock.fileno())
      link.sock.close()
    self.links.clear()

  def broadcast(self, link: Link, msg: Dict[str, Any]) -> None:
    self._send(link, (BROADCAST, self.port), msg)

  def unicast(self, link: Link, addr: str, msg: Dict[str, Any]) -> None:
    self._send(link, (addr, self.port), msg)

  def _send(self, link: Link, dst: Tuple[str, int], msg: Dict[str, Any]) -> None:
    data = encode(msg)
    try:
      link.sock.sendto(data, dst)
      self.stats[f"{msg['type']}_tx"] += 1
      self.stats["bytes_tx"] += len(data)
    except OSError as exc:
      # 接口被拔掉（Network is down）时 sendto 会失败——这不是错误，协议靠定时器发现它
      LOG.debug("send on %s to %s failed: %s", link, dst[0], exc)
      self.stats["send_errors"] += 1

  def _on_readable(self, link: Link) -> None:
    while True:
      try:
        data, (src, _sport) = link.sock.recvfrom(65535)
      except BlockingIOError:
        return
      except OSError as exc:
        LOG.debug("recv on %s failed: %s", link, exc)
        return
      if src == link.addr:
        continue                      # 自己发的广播会被内核回送一份，忽略
      self.stats["bytes_rx"] += len(data)
      try:
        msg = decode(data)
      except MessageError as exc:
        LOG.warning("bad message from %s on %s: %s", src, link.name, exc)
        self.stats["bad_rx"] += 1
        continue
      self.stats[f"{msg['type']}_rx"] += 1
      self.on_message(link, src, msg)
