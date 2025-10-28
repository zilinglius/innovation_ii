"""
基于 `selectors` 的迷你事件循环，供教学版 OSPF 协议使用。

仅实现实验所需的最核心能力：
- ``schedule``：注册一次性/周期性定时任务；
- ``register_socket``：监听套接字可读事件；
- ``run`` / ``stop``：驱动与终止主循环。

事件循环是单线程模型，回调中应避免阻塞操作，以免影响定时器精度。
"""

from __future__ import annotations

import heapq
import logging
import selectors
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

LOGGER = logging.getLogger(__name__)


@dataclass(order=True)
class _ScheduledTask:
  deadline: float
  priority: int
  callback: Callable[[], None] = field(compare=False)
  interval: Optional[float] = field(default=None, compare=False)
  cancelled: bool = field(default=False, compare=False)


class EventLoop:
  """
  轻量级调度器，用于复用定时器与套接字读事件。
  """

  def __init__(self) -> None:
    self._selector = selectors.DefaultSelector()
    self._tasks: list[_ScheduledTask] = []
    self._task_seq = 0
    self._running = False
    self._lock = threading.Lock()

  # ------------------------------------------------------------------ timers
  def schedule(self, delay: float, callback: Callable[[], None], *, repeat: bool = False) -> _ScheduledTask:
    """
    Schedule ``callback`` to be executed after ``delay`` seconds.

    When ``repeat`` is true the callback is rescheduled using the same interval
    until :meth:`cancel` is invoked.
    """
    if delay < 0:
      raise ValueError("delay must be non-negative")
    if not callable(callback):
      raise TypeError("callback must be callable")

    with self._lock:
      self._task_seq += 1
      task = _ScheduledTask(
          deadline=time.time() + delay,
          priority=self._task_seq,
          callback=callback,
          interval=delay if repeat else None,
      )
      heapq.heappush(self._tasks, task)
    return task

  def cancel(self, task: _ScheduledTask) -> None:
    """
    Mark a scheduled task as cancelled.  The callback will no longer run.
    """
    task.cancelled = True

  # ---------------------------------------------------------------- sockets
  def register_socket(
      self,
      sock: socket.socket,
      callback: Callable[[socket.socket], None],
  ) -> Callable[[], None]:
    """
    Register ``callback`` to run when ``sock`` becomes readable.
    """
    if not isinstance(sock, socket.socket):
      raise TypeError("sock must be a socket")
    if not callable(callback):
      raise TypeError("callback must be callable")

    sock.setblocking(False)
    self._selector.register(sock, selectors.EVENT_READ, callback)

    def unregister() -> None:
      try:
        self._selector.unregister(sock)
      except KeyError:
        pass

    return unregister

  # ------------------------------------------------------------------- loop
  def run(self) -> None:
    """
    Run the event loop until :meth:`stop` is called.
    """
    self._running = True
    while self._running:
      self._run_once()

  def stop(self) -> None:
    """
    Request loop termination.  The loop exits after the current iteration.
    """
    self._running = False

  # ------------------------------------------------------------ internals
  def _run_once(self) -> None:
    now = time.time()

    # Execute due tasks
    while True:
      with self._lock:
        if not self._tasks or self._tasks[0].deadline > now:
          break
        task = heapq.heappop(self._tasks)
      if task.cancelled:
        continue
      try:
        task.callback()
      except Exception:  # pragma: no cover - diagnostics
        LOGGER.exception("scheduled task failed")
      if task.interval and not task.cancelled:
        task.deadline = now + task.interval
        with self._lock:
          heapq.heappush(self._tasks, task)

    # Compute selector timeout based on next scheduled task
    timeout: Optional[float] = None
    with self._lock:
      if self._tasks:
        timeout = max(0.0, self._tasks[0].deadline - time.time())

    events = self._selector.select(timeout)
    for key, _ in events:
      callback = key.data
      try:
        callback(key.fileobj)  # type: ignore[arg-type]
      except Exception:  # pragma: no cover - diagnostics
        LOGGER.exception("socket callback failed")
