"""
事件循环：单线程，一个 select() 同时等待“套接字可读”与“定时器到期”。

为什么不用线程：守护进程的全部逻辑都在回调里顺序执行，没有锁、没有竞态，
出了问题按日志时间顺序读一遍就能复现。协议本身的时间尺度是秒级，
一个 select() 绰绰有余。

用法：
    loop = EventLoop()
    loop.add_reader(sock.fileno(), on_readable)       # 套接字可读时调用 on_readable(fd)
    loop.call_every(2.0, send_hello)                  # 每 2 秒调用一次
    t = loop.call_later(0.1, run_spf)                 # 0.1 秒后调用一次
    loop.cancel(t)                                    # 取消一个定时器
    loop.run()                                        # 直到 loop.stop()
"""

from __future__ import annotations

import heapq
import itertools
import select
import time
from typing import Any, Callable, Dict, List, Optional, Tuple


class Timer:
  """call_later / call_every 返回的句柄。"""

  __slots__ = ("when", "callback", "args", "interval", "cancelled")

  def __init__(self, when: float, callback: Callable[..., Any], args: tuple,
               interval: Optional[float]) -> None:
    self.when = when
    self.callback = callback
    self.args = args
    self.interval = interval      # None = 一次性
    self.cancelled = False


class EventLoop:

  def __init__(self) -> None:
    self._readers: Dict[int, Callable[[int], Any]] = {}
    self._timers: List[Tuple[float, int, Timer]] = []   # 小顶堆：(到期时刻, 序号, Timer)
    self._seq = itertools.count()
    self._running = False

  # ---- 时间 ----------------------------------------------------------------

  @staticmethod
  def now() -> float:
    """单调时钟，单位秒。协议里所有“多久没收到”都用它，不受系统时间调整影响。"""
    return time.monotonic()

  # ---- 套接字 --------------------------------------------------------------

  def add_reader(self, fd: int, callback: Callable[[int], Any]) -> None:
    self._readers[fd] = callback

  def remove_reader(self, fd: int) -> None:
    self._readers.pop(fd, None)

  # ---- 定时器 --------------------------------------------------------------

  def call_later(self, delay: float, callback: Callable[..., Any], *args: Any) -> Timer:
    timer = Timer(self.now() + delay, callback, args, None)
    heapq.heappush(self._timers, (timer.when, next(self._seq), timer))
    return timer

  def call_every(self, interval: float, callback: Callable[..., Any], *args: Any) -> Timer:
    timer = Timer(self.now() + interval, callback, args, interval)
    heapq.heappush(self._timers, (timer.when, next(self._seq), timer))
    return timer

  @staticmethod
  def cancel(timer: Optional[Timer]) -> None:
    if timer is not None:
      timer.cancelled = True

  # ---- 主循环 --------------------------------------------------------------

  def run(self) -> None:
    self._running = True
    while self._running:
      timeout = self._next_timeout()
      readable, _, _ = select.select(list(self._readers), [], [], timeout)
      for fd in readable:
        callback = self._readers.get(fd)
        if callback is not None:
          callback(fd)
      self._fire_due_timers()

  def stop(self) -> None:
    self._running = False

  def _next_timeout(self) -> Optional[float]:
    while self._timers and self._timers[0][2].cancelled:
      heapq.heappop(self._timers)
    if not self._timers:
      return None
    return max(0.0, self._timers[0][0] - self.now())

  def _fire_due_timers(self) -> None:
    now = self.now()
    while self._timers and self._timers[0][0] <= now:
      _, _, timer = heapq.heappop(self._timers)
      if timer.cancelled:
        continue
      timer.callback(*timer.args)
      if timer.interval is not None and not timer.cancelled:
        timer.when = now + timer.interval
        heapq.heappush(self._timers, (timer.when, next(self._seq), timer))
