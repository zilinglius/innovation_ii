"""
邻居状态机与 Hello 处理逻辑。

主要职责：
- 跟踪邻居状态（Down / Init / Two-Way / Full）；
- 处理 Hello 报文，决定是否触发邻接建立；
- 维护超时、DR/BDR 选择等信息（实验中可选）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from ospf import timers


class NeighborState(str, Enum):
  DOWN = "down"
  INIT = "init"
  TWO_WAY = "two-way"
  EXSTART = "exstart"
  EXCHANGE = "exchange"
  LOADING = "loading"
  FULL = "full"


@dataclass
class Adjacency:
  router_id: str
  interface: str
  state: NeighborState = NeighborState.DOWN
  dr: Optional[str] = None
  bdr: Optional[str] = None
  last_hello: float = 0.0
  dead_timer: float = field(default_factory=lambda: timers.DEAD_INTERVAL)
  hello_options: Dict[str, Any] = field(default_factory=dict)

  def process_hello(self, message: Dict[str, Any], now: float) -> bool:
    """
    处理收到的 Hello 报文，并更新本地状态。

    返回值：
      bool: 当状态发生变化或需要触发进一步动作时，返回 True。

    TODO:
      - 校验 area、hello/dead interval、网络掩码等协商字段；
      - 根据邻居列表决定是否进入 Two-Way；
      - 当需要形成邻接时，推进到 ExStart/Exchange；
      - 维护 DR/BDR 字段。
    """
    raise NotImplementedError("TODO: implement Hello handling logic")

  def build_hello(self) -> Dict[str, Any]:
    """
    构造发送给邻居的 Hello 报文字段。

    TODO:
      - 依据本地接口参数填充 network mask、hello interval 等；
      - 加入本地已知邻居列表；
      - 根据 DR/BDR 选举结果设置相应字段。
    """
    raise NotImplementedError("TODO: build Hello message payload")

  def tick(self, now: float) -> None:
    """
    定时器触发时检查邻居是否超时。

    TODO:
      - 若超时则将状态切换为 Down，并清理邻接上下文；
      - 可以返回事件或抛出异常，由上层捕获处理。
    """
    raise NotImplementedError("TODO: handle dead timer expiration")
