"""
轻量级事件循环，用于调度定时器与 IO 事件。

为简化实验，本循环仅提供：
- `schedule`：注册一次性/周期性任务；
- `register_socket`：注册套接字读事件（留空实现给学生）；
- `run`：启动主循环；
- `stop`：终止循环。

学生可根据需要扩展 selectors、asyncio 或多线程模型。
"""

from __future__ import annotations

import heapq
import logging
import selectors
import socket
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

LOGGER = logging.getLogger(__name__)


@dataclass(order=True)
class ScheduledTask:
  deadline: float
  priority: int
  callback: Callable[[], None] = field(compare=False)
  interval: Optional[float] = field(default=None, compare=False)
  cancelled: bool = field(default=False, compare=False)


class EventLoop:
  def __init__(self) -> None:
    self._selector = selectors.DefaultSelector()
    self._tasks: list[ScheduledTask] = []
    self._running = False
    self._task_seq = 0

  def schedule(self, delay: float, callback: Callable[[], None], repeat: bool = False) -> ScheduledTask:
    """
    安排一个延迟任务。

    TODO:
      - 根据 repeat 参数决定是否周期性执行；
      - 返回 ScheduledTask，便于取消或调整。
    """
    self._task_seq += 1
    task = ScheduledTask(
        deadline=time.time() + delay,
        priority=self._task_seq,
        callback=callback,
        interval=delay if repeat else None,
    )
    heapq.heappush(self._tasks, task)
    return task

  def cancel(self, task: ScheduledTask) -> None:
    task.cancelled = True

  def register_socket(
      self,
      sock: socket.socket,
      callback: Callable[[socket.socket], None],
  ) -> Callable[[], None]:
    """
    注册套接字读事件。

    TODO:
      - 根据需要设置非阻塞；
      - 调用 selector.register，并在事件触发时执行回调；
      - 设计卸载机制（如返回一个取消函数）。
    """
    sock.setblocking(False)
    self._selector.register(sock, selectors.EVENT_READ, callback)

    def unregister() -> None:
      try:
        self._selector.unregister(sock)
      except KeyError:
        pass

    return unregister

  def run(self) -> None:
    self._running = True
    while self._running:
      self._run_once()

  def stop(self) -> None:
    self._running = False

  def _run_once(self) -> None:
    now = time.time()

    # 执行到期的任务
    while self._tasks and self._tasks[0].deadline <= now:
      task = heapq.heappop(self._tasks)
      if task.cancelled:
        continue
      try:
        task.callback()
      except Exception as exc:  # pragma: no cover - 调试输出
        LOGGER.exception("scheduled task failed: %s", exc)
      if task.interval and not task.cancelled:
        task.deadline = now + task.interval
        heapq.heappush(self._tasks, task)

    # 计算 selector 超时时间
    timeout = None
    if self._tasks:
      timeout = max(0.0, self._tasks[0].deadline - now)

    # 阻塞等待 IO
    events = self._selector.select(timeout)
    for key, _ in events:
      callback = key.data
      try:
        callback(key.fileobj)
      except Exception as exc:  # pragma: no cover
        LOGGER.exception("socket callback failed: %s", exc)
