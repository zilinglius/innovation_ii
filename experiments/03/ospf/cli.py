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
    # TODO: 触发指定接口的 Hello 发送，可调用 router API。
    raise NotImplementedError("TODO: implement manual hello trigger")

  def _cmd_quit(self, _: Iterable[str]) -> None:
    LOGGER.info("exiting CLI")
    self.stop()

  def _cmd_help(self, _: Iterable[str]) -> None:
    LOGGER.info(
        "commands: show neighbors|lsdb|routes, send hello <iface>, quit/exit"
    )

  # --- helper show methods ---------------------------------------------

  def _show_neighbors(self) -> None:
    # TODO: 从 router 获取邻居表并格式化输出。
    raise NotImplementedError("TODO: dump neighbor table via router API")

  def _show_lsdb(self) -> None:
    # TODO: 显示 LSDB 内容，便于比对 LSA。
    raise NotImplementedError("TODO: dump LSDB entries")

  def _show_routes(self) -> None:
    # TODO: 输出当前转发表，可选择调用 `ip route` 或内部结构。
    raise NotImplementedError("TODO: dump routing table")


# 避免循环导入
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from ospf.router import Router
