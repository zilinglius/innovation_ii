"""
简单的交互式 CLI，方便在实验中查询路由器状态。

支持命令（推荐实现）：
- `show neighbors`
- `show lsdb`
- `show routes`
- `send hello <ifname>`
- `quit` / `exit`
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Dict, Iterable

LOGGER = logging.getLogger(__name__)


class CliShell:
  def __init__(self, router: "Router") -> None:
    self.router = router
    self._running = threading.Event()
    self._running.set()
    self._commands: Dict[str, Callable[[Iterable[str]], None]] = {
        "show": self._cmd_show,
        "send": self._cmd_send,
        "quit": self._cmd_quit,
        "exit": self._cmd_quit,
        "help": self._cmd_help,
    }
    self._history: queue.Queue[str] = queue.Queue()

  def run(self) -> None:
    while self._running.is_set():
      try:
        line = input("> ").strip()
      except EOFError:
        break
      if not line:
        continue
      self._history.put(line)
      tokens = line.split()
      command = tokens[0]
      handler = self._commands.get(command)
      if handler is None:
        LOGGER.warning("unknown command: %s", command)
        continue
      try:
        handler(tokens[1:])
      except Exception as exc:  # pragma: no cover - 仅调试用
        LOGGER.exception("command failed: {exc}", exc=exc)

  def stop(self) -> None:
    self._running.clear()

  # --- command handlers -------------------------------------------------

  def _cmd_show(self, args: Iterable[str]) -> None:
    sub = list(args)
    if not sub:
      LOGGER.info("usage: show <neighbors|lsdb|routes>")
      return
    lookup = sub[0]
    if lookup == "neighbors":
      self._show_neighbors()
    elif lookup == "lsdb":
      self._show_lsdb()
    elif lookup == "routes":
      self._show_routes()
    else:
      LOGGER.warning("unsupported show target: %s", lookup)

  def _cmd_send(self, args: Iterable[str]) -> None:
    sub = list(args)
    if len(sub) < 2:
      LOGGER.info("usage: send hello <iface>")
      return
    action, iface = sub[0], sub[1]
    if action != "hello":
      LOGGER.warning("unsupported send action: %s", action)
      return
    iface_state = self.router.interfaces.get(iface)
    if iface_state is None:
      LOGGER.warning("interface not found: %s", iface)
      return
    try:
      self.router.send_hello(iface_state)
    except NotImplementedError:
      LOGGER.warning("router send_hello not implemented")
    except Exception as exc:  # pragma: no cover - 用于调试
      LOGGER.exception("failed to send hello on %s: %s", iface, exc)
    else:
      LOGGER.info("hello sent on %s", iface)

  def _cmd_quit(self, _: Iterable[str]) -> None:
    LOGGER.info("exiting CLI")
    self.stop()

  def _cmd_help(self, _: Iterable[str]) -> None:
    LOGGER.info(
        "commands: show neighbors|lsdb|routes, send hello <iface>, quit/exit"
    )

  # --- helper show methods ---------------------------------------------

  def _show_neighbors(self) -> None:
    neighbors = self.router.get_neighbors()
    if not neighbors:
      LOGGER.info("no neighbors recorded")
      return
    for key in sorted(neighbors):
      entry = neighbors[key]
      iface = entry.get("interface", "?")
      rid = entry.get("neighbor", "?")
      state = entry.get("state", "?")
      LOGGER.info("%s neighbor=%s state=%s (%s)", iface, rid, state, key)

  def _show_lsdb(self) -> None:
    lsdb_view = self.router.get_lsdb()
    if not lsdb_view:
      LOGGER.info("lsdb empty")
      return
    for key in sorted(lsdb_view):
      entry = lsdb_view[key]
      adv = entry.get("adv_router", "?")
      seq = entry.get("seq", "?")
      age = entry.get("age", "?")
      payload = entry.get("payload")
      LOGGER.info("%s adv=%s seq=%s age=%s payload=%r", key, adv, seq, age, payload)

  def _show_routes(self) -> None:
    try:
      routes = self.router.get_routes()
    except NotImplementedError:
      LOGGER.warning("router get_routes not implemented")
      return
    if not routes:
      LOGGER.info("routing table empty")
      return
    for key in sorted(routes):
      LOGGER.info("%s -> %s", key, routes[key])


# 避免循环导入
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from ospf.router import Router
