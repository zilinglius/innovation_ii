"""
协议报文的编码与解码。

消息类型（建议）：
- HELLO
- DATABASE_DESCRIPTION
- LINK_STATE_REQUEST
- LINK_STATE_UPDATE
- LINK_STATE_ACK

为便于实验，此处使用 JSON/UDP 或其他简单封装。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class MessageType(str, Enum):
  HELLO = "hello"
  DATABASE_DESCRIPTION = "dd"
  LINK_STATE_REQUEST = "lsr"
  LINK_STATE_UPDATE = "lsu"
  LINK_STATE_ACK = "ack"


@dataclass
class Message:
  msg_type: MessageType
  router_id: str
  area_id: str
  payload: Dict[str, Any] = field(default_factory=dict)

  def dumps(self) -> bytes:
    """
    编码为字节串以便通过 UDP 发送。

    TODO:
      - 校验必要字段；
      - 根据 msg_type 限制 payload 内容；
      - 支持版本号或校验字段（可选）。
    """
    raise NotImplementedError("TODO: serialize message to bytes")

  @classmethod
  def loads(cls, data: bytes) -> "Message":
    """
    从字节串恢复消息实例。

    TODO:
      - 校验 JSON 结构；
      - 根据 msg_type 验证必需字段；
      - 处理 decode 异常并抛出自定义错误。
    """
    raise NotImplementedError("TODO: deserialize message from bytes")


def build_hello(router_id: str, area_id: str, **kwargs: Any) -> Message:
  """
  辅助函数：构造 Hello 消息。
  """
  payload = dict(kwargs)
  payload.setdefault("neighbors", [])
  return Message(
      msg_type=MessageType.HELLO,
      router_id=router_id,
      area_id=area_id,
      payload=payload,
  )
