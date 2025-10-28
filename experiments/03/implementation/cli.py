"""
Simple interactive CLI used to inspect the running OSPF process during labs.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Iterable

LOGGER = logging.getLogger(__name__)


class CliShell:
  def __init__(self, router: "Router") -> None:
    self.router = router
    self._running = threading.Event()
    self._running.set()
    self._commands = {
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
      except Exception:  # pragma: no cover - interactive diagnostics
        LOGGER.exception("command failed")

  def stop(self) -> None:
    self._running.clear()

  # ----------------------------------------------------------------- commands
  def _cmd_show(self, args: Iterable[str]) -> None:
    sub = list(args)
    if not sub:
      LOGGER.info("usage: show <neighbors|lsdb|routes>")
      return
    topic = sub[0]
    if topic == "neighbors":
      self._show_neighbors()
    elif topic == "lsdb":
      self._show_lsdb()
    elif topic == "routes":
      self._show_routes()
    else:
      LOGGER.warning("unsupported show topic: %s", topic)

  def _cmd_send(self, args: Iterable[str]) -> None:
    sub = list(args)
    if len(sub) != 2 or sub[0] != "hello":
      LOGGER.info("usage: send hello <interface>")
      return
    iface = sub[1]
    iface_state = self.router.interfaces.get(iface)
    if iface_state is None:
      LOGGER.warning("interface not found: %s", iface)
      return
    try:
      self.router.send_hello(iface_state)
    except Exception:  # pragma: no cover - diagnostics
      LOGGER.exception("failed to send hello")
    else:
      LOGGER.info("hello sent on %s", iface)

  def _cmd_quit(self, _: Iterable[str]) -> None:
    LOGGER.info("exiting CLI")
    self.stop()

  def _cmd_help(self, _: Iterable[str]) -> None:
    LOGGER.info("commands: show neighbors|lsdb|routes, send hello <iface>, quit/exit")

  # ------------------------------------------------------------------- views
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
      last = entry.get("last_hello", "?")
      LOGGER.info("%s neighbor=%s state=%s last=%.1f", iface, rid, state, last)

  def _show_lsdb(self) -> None:
    lsdb = self.router.get_lsdb()
    if not lsdb:
      LOGGER.info("lsdb empty")
      return
    for key in sorted(lsdb):
      entry = lsdb[key]
      LOGGER.info(
          "%s adv=%s seq=%s age=%s payload=%r",
          key,
          entry.get("adv_router"),
          entry.get("seq"),
          entry.get("age"),
          entry.get("payload"),
      )

  def _show_routes(self) -> None:
    routes = self.router.get_routes()
    if not routes:
      LOGGER.info("routing table empty")
      return
    for prefix in sorted(routes):
      entry = routes[prefix]
      LOGGER.info(
          "%s -> next-hop %s via %s cost %s",
          prefix,
          entry.get("next_hop", "-"),
          entry.get("interface", "-"),
          entry.get("cost", "?"),
      )


# Avoid circular import
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from .router import Router
