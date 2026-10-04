"""
与内核打交道的三件事：读接口、写路由表、听链路事件。全部通过 iproute2 的 `ip` 命令，
守护进程跑在哪个 network namespace 里，`ip` 就作用于哪个 namespace。

  list_interfaces()          `ip -j addr show`      → 有 IPv4 地址的接口列表
  route_replace / route_del  `ip route replace/del` → 写内核 FIB（规范 R8）
  route_flush()              `ip route flush proto 200`
  watch_links()              `ip -o monitor link`   → 接口 up/down 事件（进阶任务 T6）

路由都带 `proto 200 metric 20`：proto 200 是 iproute2 没有占用的协议号，
`ip route show proto 200` 一眼看出哪些路由是本进程写的；metric 20 与 FRR 的 OSPF 一致，
于是第 03 讲思考题 5 的现象（手工静态路由 metric 0 压住动态路由）在这里原样复现。
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

PROTO = 200
METRIC = 20

LOG = logging.getLogger("sysnet")


@dataclass
class Iface:
  name: str
  ifindex: int
  addr: str          # 10.0.12.1
  prefixlen: int     # 30
  network: str       # 10.0.12.0/30
  lower_up: bool     # 接口 UP 且有载波（对端没拔线）


_TODO_SEEN = set()


def _todo(what: str) -> None:
  if what not in _TODO_SEEN:
    _TODO_SEEN.add(what)
    LOG.warning("TODO 尚未实现：%s", what)


def _ip(*args: str) -> subprocess.CompletedProcess:
  return subprocess.run(["ip", *args], capture_output=True, text=True, check=False)


def list_interfaces() -> List[Iface]:
  """所有带 IPv4 地址的接口（不含 lo）。一个接口有多个地址时只取第一个。"""
  result = _ip("-j", "addr", "show")
  if result.returncode != 0:
    raise RuntimeError(f"ip -j addr show failed: {result.stderr.strip()}")
  ifaces: List[Iface] = []
  for entry in json.loads(result.stdout or "[]"):
    if entry.get("ifname") == "lo":
      continue
    inet = [a for a in entry.get("addr_info", []) if a.get("family") == "inet"]
    if not inet:
      continue
    addr, plen = inet[0]["local"], int(inet[0]["prefixlen"])
    network = str(ipaddress.ip_interface(f"{addr}/{plen}").network)
    flags = entry.get("flags", [])
    ifaces.append(Iface(
        name=entry["ifname"], ifindex=int(entry["ifindex"]), addr=addr, prefixlen=plen,
        network=network, lower_up=("UP" in flags and "LOWER_UP" in flags)))
  return ifaces


# ---- 写路由表（R8）------------------------------------------------------------

def route_replace(prefix: str, nexthops: Sequence[Tuple[str, str]]) -> bool:
  """
  安装或替换一条路由。nexthops 是 [(下一跳地址, 出接口), ...]，多于一个时装成 ECMP。
  `ip route replace` 本身是幂等的：已有就改，没有就加。
  """
  args = ["route", "replace", prefix, "proto", str(PROTO), "metric", str(METRIC)]
  if len(nexthops) == 1:
    via, dev = nexthops[0]
    args += ["via", via, "dev", dev]
  else:
    for via, dev in nexthops:
      args += ["nexthop", "via", via, "dev", dev]
  result = _ip(*args)
  if result.returncode != 0:
    LOG.error("ip %s: %s", " ".join(args), result.stderr.strip())
    return False
  return True


def route_del(prefix: str) -> bool:
  result = _ip("route", "del", prefix, "proto", str(PROTO), "metric", str(METRIC))
  if result.returncode != 0:
    LOG.error("ip route del %s: %s", prefix, result.stderr.strip())
    return False
  return True


def route_flush() -> None:
  """删掉本进程写过的全部路由。退出时调用，也可以手工执行 `ip route flush proto 200`。"""
  _ip("route", "flush", "proto", str(PROTO))


def route_list() -> List[Dict[str, Any]]:
  """内核里 proto 200 的路由（`ip -j route show proto 200`），供 CLI 对照 RIB 与 FIB。"""
  result = _ip("-j", "route", "show", "proto", str(PROTO))
  if result.returncode != 0:
    return []
  return json.loads(result.stdout or "[]")


# ---- 听链路事件（进阶任务 T6）-------------------------------------------------

LinkCallback = Callable[[str, bool], None]


def parse_monitor_line(line: str) -> Optional[Tuple[str, bool]]:
  """
  解析 `ip -o monitor link` 的一行，返回 (接口名, 是否 LOWER_UP)；不是链路状态行返回 None。
  典型的行：
    5: r1-r2@if6: <BROADCAST,MULTICAST> mtu 1500 qdisc noqueue state DOWN group default \\    link/ether ...
    6: r2-r1@if5: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state LOWERLAYERDOWN ...
    Deleted 7: r1-r3@if8: <BROADCAST,MULTICAST,UP,LOWER_UP> ...
  """
  parts = line.split()
  if len(parts) < 3:
    return None
  if parts[0] == "Deleted":
    parts = parts[1:]
  if not parts[0].endswith(":") or not parts[1].endswith(":"):
    return None
  name = parts[1][:-1].split("@", 1)[0]
  flags_field = parts[2]
  if not (flags_field.startswith("<") and flags_field.endswith(">")):
    return None
  flags = flags_field[1:-1].split(",")
  return name, ("UP" in flags and "LOWER_UP" in flags)


def watch_links(loop: Any, callback: LinkCallback) -> Optional[subprocess.Popen]:
  """
  订阅内核的链路状态事件：起一个 `ip -o monitor link` 子进程，把它的标准输出
  挂进事件循环；每读到一行完整输出就解析并调用 callback(接口名, 是否 LOWER_UP)。

  这正是 zebra 通过 netlink 做的事——只是我们借 `ip monitor` 之手。
  有了它，拔线这种“响的故障”就不必再等 Dead 定时器。

  实现提示：Popen(["ip", "-o", "monitor", "link"], stdout=PIPE)；把 stdout 的 fd 设成非阻塞，
  loop.add_reader(fd, ...)；回调里 os.read() 一块，按 "\n" 切成行（末尾不完整的半行留到下次），
  每行交给 parse_monitor_line()，解析成功就 callback(name, up)。返回 Popen 对象以便退出时 terminate()。
  """
  # ---- TODO（进阶任务 T6）：把下面的桩换成你的实现 ----
  _todo("sysnet.watch_links（进阶任务 T6）：--watch-links 暂时不起作用")
  return None
