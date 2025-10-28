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


@dataclass
class Message:
  msg_type: MessageType
  router_id: str
  area_id: str
  payload: Dict[str, Any] = field(default_factory=dict)

  PROTOCOL_VERSION = 1

  def dumps(self) -> bytes:
    """
    编码为字节串以便通过 UDP 发送。

    TODO:
      - 校验必要字段；
      - 根据 msg_type 限制 payload 内容；
      - 支持版本号或校验字段（可选）。
    """
    _ensure_non_empty("router_id", self.router_id)
    _ensure_non_empty("area_id", self.area_id)
    if not isinstance(self.payload, dict):
      raise MessageValidationError("payload must be a dict")

    _validate_payload(self.msg_type, self.payload)

    envelope = {
        "version": self.PROTOCOL_VERSION,
        "type": self.msg_type.value,
        "router_id": self.router_id,
        "area_id": self.area_id,
        "payload": self.payload,
    }

    try:
      checksum = _compute_checksum(envelope)
    except (TypeError, ValueError) as exc:
      raise MessageValidationError(f"message payload is not JSON serialisable: {exc}") from exc
    envelope["checksum"] = checksum

    try:
      return json.dumps(
          envelope,
          sort_keys=True,
          separators=(",", ":"),
      ).encode("utf-8")
    except (TypeError, ValueError) as exc:
      raise MessageValidationError(f"failed to encode message: {exc}") from exc

  @classmethod
  def loads(cls, data: bytes) -> "Message":
    """
    从字节串恢复消息实例。

    TODO:
      - 校验 JSON 结构；
      - 根据 msg_type 验证必需字段；
      - 处理 decode 异常并抛出自定义错误。
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
      raise MessageDecodeError("data must be bytes-like")

    try:
      text = bytes(data).decode("utf-8")
    except UnicodeDecodeError as exc:
      raise MessageDecodeError("message is not valid UTF-8") from exc

    try:
      envelope = json.loads(text)
    except json.JSONDecodeError as exc:
      raise MessageDecodeError("message is not valid JSON") from exc

    if not isinstance(envelope, dict):
      raise MessageDecodeError("message envelope must be a JSON object")

    version = envelope.get("version", cls.PROTOCOL_VERSION)
    if not isinstance(version, int):
      raise MessageDecodeError("version must be an integer")
    if version != cls.PROTOCOL_VERSION:
      raise MessageDecodeError(f"unsupported message version: {version}")

    try:
      msg_type = MessageType(envelope["type"])
    except KeyError as exc:
      raise MessageDecodeError("message type missing") from exc
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
    try:
      expected_checksum = _compute_checksum(
          {
              key: value
              for key, value in envelope.items()
              if key != "checksum"
          }
      )
    except (TypeError, ValueError) as exc:
      raise MessageDecodeError(f"message contents not JSON serialisable: {exc}") from exc

    if checksum is not None:
      if not isinstance(checksum, int):
        raise MessageDecodeError("checksum must be an integer")
      if checksum != expected_checksum:
        raise MessageDecodeError("checksum mismatch")

    try:
      _validate_payload(msg_type, payload)
    except MessageValidationError as exc:
      raise MessageDecodeError(str(exc)) from exc

    return cls(
        msg_type=msg_type,
        router_id=str(router_id),
        area_id=str(area_id),
        payload=dict(payload),
    )


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


class MessageError(ValueError):
  """Base class for message related errors."""


class MessageValidationError(MessageError):
  """Raised when message validation fails."""


class MessageDecodeError(MessageError):
  """Raised when decoding bytes into a message fails."""


def _ensure_non_empty(field: str, value: Any, *, error_cls: type[MessageError] = MessageValidationError) -> None:
  if not isinstance(value, str) or not value:
    raise error_cls(f"{field} must be a non-empty string")


def _compute_checksum(envelope: Dict[str, Any]) -> int:
  encoded = json.dumps(
      envelope,
      sort_keys=True,
      separators=(",", ":"),
  ).encode("utf-8")
  return zlib.crc32(encoded) & 0xFFFFFFFF


def _validate_payload(msg_type: MessageType, payload: Dict[str, Any]) -> None:
  if not isinstance(payload, dict):
    raise MessageValidationError("payload must be a dict")

  validator = _PAYLOAD_VALIDATORS.get(msg_type)
  if validator is None:
    return
  validator(payload)


def _validate_hello(payload: Dict[str, Any]) -> None:
  neighbors = payload.get("neighbors")
  if neighbors is None:
    raise MessageValidationError("hello payload missing 'neighbors'")
  _ensure_list_of("neighbors", neighbors, str)

  allowed_keys = {
      "neighbors",
      "hello_interval",
      "dead_interval",
      "network_mask",
      "priority",
      "dr",
      "bdr",
      "options",
  }
  _ensure_known_fields(payload, allowed_keys)

  _ensure_optional_type(payload, "hello_interval", int)
  _ensure_optional_type(payload, "dead_interval", int)
  _ensure_optional_type(payload, "network_mask", str)
  _ensure_optional_type(payload, "priority", int)
  _ensure_optional_type(payload, "dr", str)
  _ensure_optional_type(payload, "bdr", str)
  _ensure_optional_type(payload, "options", dict)


def _validate_dd(payload: Dict[str, Any]) -> None:
  headers = payload.get("lsa_headers")
  if headers is None:
    raise MessageValidationError("dd payload missing 'lsa_headers'")
  _ensure_list_of("lsa_headers", headers, dict)

  allowed_keys = {
      "lsa_headers",
      "flags",
      "options",
      "mtu",
      "sequence",
      "more",
  }
  _ensure_known_fields(payload, allowed_keys)

  _ensure_optional_type(payload, "flags", (int, str))
  _ensure_optional_type(payload, "options", dict)
  _ensure_optional_type(payload, "mtu", int)
  _ensure_optional_type(payload, "sequence", int)
  _ensure_optional_type(payload, "more", bool)


def _validate_lsr(payload: Dict[str, Any]) -> None:
  requests = payload.get("requests")
  if requests is None:
    raise MessageValidationError("lsr payload missing 'requests'")
  _ensure_list_of("requests", requests, dict)
  _ensure_known_fields(payload, {"requests"})


def _validate_lsu(payload: Dict[str, Any]) -> None:
  lsas = payload.get("lsas")
  if lsas is None:
    raise MessageValidationError("lsu payload missing 'lsas'")
  _ensure_list_of("lsas", lsas, dict)

  allowed_keys = {"lsas", "more"}
  _ensure_known_fields(payload, allowed_keys)
  _ensure_optional_type(payload, "more", bool)


def _validate_ack(payload: Dict[str, Any]) -> None:
  acks = payload.get("acks")
  if acks is None:
    raise MessageValidationError("ack payload missing 'acks'")
  _ensure_list_of("acks", acks, dict)
  _ensure_known_fields(payload, {"acks"})


def _ensure_optional_type(payload: Dict[str, Any], field: str, expected: Any) -> None:
  if field not in payload:
    return
  value = payload[field]
  if not isinstance(value, expected if isinstance(expected, tuple) else (expected,)):
    raise MessageValidationError(f"{field} has invalid type: expected {expected}, got {type(value).__name__}")


def _ensure_list_of(field: str, value: Any, element_type: type) -> None:
  if not isinstance(value, list):
    raise MessageValidationError(f"{field} must be a list")
  for index, item in enumerate(value):
    if not isinstance(item, element_type):
      raise MessageValidationError(f"{field}[{index}] must be {element_type.__name__}")


def _ensure_known_fields(payload: Dict[str, Any], allowed_keys: Iterable[str]) -> None:
  allowed = set(allowed_keys)
  unknown = set(payload) - allowed
  if unknown:
    raise MessageValidationError(f"payload contains unsupported fields: {', '.join(sorted(unknown))}")


_PAYLOAD_VALIDATORS = {
    MessageType.HELLO: _validate_hello,
    MessageType.DATABASE_DESCRIPTION: _validate_dd,
    MessageType.LINK_STATE_REQUEST: _validate_lsr,
    MessageType.LINK_STATE_UPDATE: _validate_lsu,
    MessageType.LINK_STATE_ACK: _validate_ack,
}
