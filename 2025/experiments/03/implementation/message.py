"""
教学版 OSPF 协议的报文编解码工具。

正式协议使用裸 IP 封装，本实验为方便调试改用 UDP + JSON：既能
直观观测内容，又能在保持结构化约束的同时快速实现校验逻辑。
"""

from __future__ import annotations

import json
import zlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable


class MessageType(str, Enum):
  HELLO = "hello"
  DATABASE_DESCRIPTION = "dd"
  LINK_STATE_REQUEST = "lsr"
  LINK_STATE_UPDATE = "lsu"
  LINK_STATE_ACK = "ack"


class MessageError(ValueError):
  """协议报文相关错误的基类。"""


class MessageValidationError(MessageError):
  """消息违反格式约束时抛出，用于提示编码方修复。"""


class MessageDecodeError(MessageError):
  """外部数据无法成功解析为 Message 实例时抛出的异常。"""


@dataclass
class Message:
  msg_type: MessageType
  router_id: str
  area_id: str
  payload: Dict[str, Any] = field(default_factory=dict)

  PROTOCOL_VERSION = 1

  def dumps(self) -> bytes:
    """
    将消息编码为 UTF-8 JSON，便于通过 UDP 发送。
    """
    _ensure_non_empty("router_id", self.router_id)
    _ensure_non_empty("area_id", self.area_id)
    if not isinstance(self.msg_type, MessageType):
      raise MessageValidationError(f"invalid message type: {self.msg_type!r}")
    if not isinstance(self.payload, dict):
      raise MessageValidationError("payload must be a dictionary")

    _validate_payload(self.msg_type, self.payload)

    envelope = {
        "version": self.PROTOCOL_VERSION,
        "type": self.msg_type.value,
        "router_id": self.router_id,
        "area_id": self.area_id,
        "payload": self.payload,
    }

    checksum = _compute_checksum(envelope)
    envelope["checksum"] = checksum

    try:
      return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
      raise MessageValidationError(f"failed to encode message: {exc}") from exc

  @classmethod
  def loads(cls, data: bytes) -> "Message":
    """
    从 UDP 载荷中恢复 Message 实例，包含基本的结构与校验检查。
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
      raise MessageDecodeError("data must be bytes-like")
    try:
      text = bytes(data).decode("utf-8")
    except UnicodeDecodeError as exc:
      raise MessageDecodeError("payload is not valid UTF-8") from exc

    try:
      envelope = json.loads(text)
    except json.JSONDecodeError as exc:
      raise MessageDecodeError("payload is not valid JSON") from exc
    if not isinstance(envelope, dict):
      raise MessageDecodeError("message must decode into a JSON object")

    version = envelope.get("version", cls.PROTOCOL_VERSION)
    if not isinstance(version, int):
      raise MessageDecodeError("version field must be an integer")
    if version != cls.PROTOCOL_VERSION:
      raise MessageDecodeError(f"unsupported protocol version: {version}")

    try:
      msg_type = MessageType(envelope["type"])
    except KeyError as exc:
      raise MessageDecodeError("message missing type field") from exc
    except ValueError as exc:
      raise MessageDecodeError(f"unknown message type: {envelope.get('type')!r}") from exc

    router_id = envelope.get("router_id")
    _ensure_non_empty("router_id", router_id, error_cls=MessageDecodeError)
    area_id = envelope.get("area_id")
    _ensure_non_empty("area_id", area_id, error_cls=MessageDecodeError)

    payload = envelope.get("payload", {})
    if not isinstance(payload, dict):
      raise MessageDecodeError("payload must be a JSON object")

    checksum = envelope.get("checksum")
    if checksum is not None and not isinstance(checksum, int):
      raise MessageDecodeError("checksum must be an integer")

    expected = _compute_checksum(
        {
            key: value
            for key, value in envelope.items()
            if key != "checksum"
        }
    )
    if checksum is not None and checksum != expected:
      raise MessageDecodeError("checksum mismatch")

    _validate_payload(msg_type, payload)

    return cls(
        msg_type=msg_type,
        router_id=str(router_id),
        area_id=str(area_id),
        payload=dict(payload),
    )


def build_hello(router_id: str, area_id: str, **kwargs: Any) -> Message:
  """
  构造 Hello 消息的辅助函数，自动填充基础字段。
  """
  payload = dict(kwargs)
  payload.setdefault("neighbors", [])
  return Message(
      msg_type=MessageType.HELLO,
      router_id=router_id,
      area_id=area_id,
      payload=payload,
  )


# ------------------------------------------------------------------ helpers

def _ensure_non_empty(field: str, value: Any, *, error_cls: type[MessageError] = MessageValidationError) -> None:
  if not isinstance(value, str) or not value:
    raise error_cls(f"{field} must be a non-empty string")


def _compute_checksum(envelope: Dict[str, Any]) -> int:
  encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
  return zlib.crc32(encoded) & 0xFFFFFFFF


def _validate_payload(msg_type: MessageType, payload: Dict[str, Any]) -> None:
  validator = _PAYLOAD_VALIDATORS.get(msg_type)
  if validator is None:
    return
  validator(payload)


def _ensure_optional(payload: Dict[str, Any], field: str, expected: Any) -> None:
  if field not in payload:
    return
  value = payload[field]
  if not isinstance(value, expected if isinstance(expected, tuple) else (expected,)):
    raise MessageValidationError(f"{field} has invalid type: expected {expected}, got {type(value).__name__}")


def _ensure_list(field: str, value: Any, element_type: type) -> None:
  if not isinstance(value, list):
    raise MessageValidationError(f"{field} must be a list")
  for idx, item in enumerate(value):
    if not isinstance(item, element_type):
      raise MessageValidationError(f"{field}[{idx}] must be {element_type.__name__}")


def _ensure_known(payload: Dict[str, Any], allowed: Iterable[str]) -> None:
  allowed_set = set(allowed)
  unknown = set(payload) - allowed_set
  if unknown:
    raise MessageValidationError(f"payload contains unsupported fields: {', '.join(sorted(unknown))}")


def _validate_hello(payload: Dict[str, Any]) -> None:
  _ensure_list("neighbors", payload.get("neighbors"), str)
  _ensure_known(payload, {"neighbors", "network_mask", "hello_interval", "dead_interval", "priority", "dr", "bdr", "options"})
  _ensure_optional(payload, "network_mask", str)
  _ensure_optional(payload, "hello_interval", int)
  _ensure_optional(payload, "dead_interval", int)
  _ensure_optional(payload, "priority", int)
  _ensure_optional(payload, "dr", str)
  _ensure_optional(payload, "bdr", str)
  _ensure_optional(payload, "options", dict)


def _validate_dd(payload: Dict[str, Any]) -> None:
  _ensure_list("lsa_headers", payload.get("lsa_headers"), dict)
  _ensure_known(payload, {"lsa_headers", "flags", "options", "mtu", "sequence", "more"})
  _ensure_optional(payload, "flags", (int, str))
  _ensure_optional(payload, "options", dict)
  _ensure_optional(payload, "mtu", int)
  _ensure_optional(payload, "sequence", int)
  _ensure_optional(payload, "more", bool)


def _validate_lsr(payload: Dict[str, Any]) -> None:
  _ensure_list("requests", payload.get("requests"), dict)
  _ensure_known(payload, {"requests"})


def _validate_lsu(payload: Dict[str, Any]) -> None:
  _ensure_list("lsas", payload.get("lsas"), dict)
  _ensure_known(payload, {"lsas", "more"})
  _ensure_optional(payload, "more", bool)


def _validate_ack(payload: Dict[str, Any]) -> None:
  _ensure_list("acks", payload.get("acks"), dict)
  _ensure_known(payload, {"acks"})


_PAYLOAD_VALIDATORS = {
    MessageType.HELLO: _validate_hello,
    MessageType.DATABASE_DESCRIPTION: _validate_dd,
    MessageType.LINK_STATE_REQUEST: _validate_lsr,
    MessageType.LINK_STATE_UPDATE: _validate_lsu,
    MessageType.LINK_STATE_ACK: _validate_ack,
}
