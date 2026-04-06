"""
Link State Database management helpers.

The implementation stores LSAs in-memory and performs the minimum validation
required to support the teaching exercises: sequence handling, checksum
verification, and ageing/refresh logic.
"""

from __future__ import annotations

import json
import time
import zlib
from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, Tuple

from . import timers


@dataclass
class LsaHeader:
  lsa_type: str
  lsa_id: str
  advertising_router: str
  sequence: int
  age: int = 0
  checksum: int = 0


@dataclass
class Lsa:
  header: LsaHeader
  payload: Dict[str, object] = field(default_factory=dict)

  def fingerprint(self) -> Tuple[str, str]:
    return (self.header.lsa_type, self.header.lsa_id)


def _compute_checksum(header: LsaHeader, payload: Dict[str, object]) -> int:
  """
  CRC32 based checksum mirroring the simplified message encoding.
  """
  data = {
      "header": {
          "lsa_type": header.lsa_type,
          "lsa_id": header.lsa_id,
          "advertising_router": header.advertising_router,
          "sequence": header.sequence,
          "age": header.age,
          "checksum": 0,
      },
      "payload": payload,
  }
  encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
  return zlib.crc32(encoded) & 0xFFFFFFFF


class LinkStateDatabase:
  """
  In-memory LSDB following the minimal rules required by the lab exercises.
  """

  def __init__(self) -> None:
    self._lsas: Dict[Tuple[str, str], Lsa] = {}
    self._last_refresh = time.time()

  def install(self, lsa: Lsa) -> bool:
    """
    将 LSA 插入或更新到数据库，当 LSDB 发生变化时返回 True。
    """
    key = lsa.fingerprint()
    current = self._lsas.get(key)

    payload_copy = deepcopy(lsa.payload)
    base_header = replace(lsa.header, age=0, checksum=0)
    checksum = _compute_checksum(base_header, payload_copy)
    candidate = Lsa(
        header=replace(base_header, checksum=checksum),
        payload=payload_copy,
    )

    if current is not None:
      if candidate.header.sequence < current.header.sequence:
        return False
      if candidate.header.sequence == current.header.sequence:
        if candidate.header.checksum == current.header.checksum:
          # LSA identical; nothing to do.
          return False

    self._lsas[key] = candidate
    return True

  def age(self, seconds: int) -> Iterable[Lsa]:
    """
    为每条 LSA 增加 age，超过刷新时间的条目会被删除并返回以供泛洪。
    """
    if seconds <= 0:
      return []

    now = time.time()
    expired: list[Lsa] = []
    refreshed: dict[Tuple[str, str], Lsa] = {}

    for key, lsa in list(self._lsas.items()):
      new_age = lsa.header.age + seconds
      if new_age >= timers.LS_REFRESH_TIME:
        expired.append(self._lsas.pop(key))
        continue
      refreshed[key] = Lsa(
          header=replace(lsa.header, age=new_age),
          payload=lsa.payload,
      )

    self._lsas.update(refreshed)
    self._last_refresh = now
    return expired

  def snapshot(self) -> Dict[Tuple[str, str], Lsa]:
    """
    返回 LSDB 的浅拷贝，避免外部直接修改内部状态。
    """
    return dict(self._lsas)

  def to_message_payload(self, lsa: Lsa) -> Dict[str, object]:
    """
    将内存中的 LSA 转换为 LSU 可携带的 JSON 结构。
    """
    return {
        "header": {
            "lsa_type": lsa.header.lsa_type,
            "lsa_id": lsa.header.lsa_id,
            "advertising_router": lsa.header.advertising_router,
            "sequence": lsa.header.sequence,
            "age": lsa.header.age,
            "checksum": lsa.header.checksum,
        },
        "payload": deepcopy(lsa.payload),
    }

  @staticmethod
  def from_message_payload(payload: Dict[str, object]) -> Lsa:
    """
    将 LSU 报文中的 JSON 字段还原为 Lsa 对象。
    """
    header_dict = dict(payload.get("header") or {})
    return Lsa(
        header=LsaHeader(
            lsa_type=str(header_dict.get("lsa_type")),
            lsa_id=str(header_dict.get("lsa_id")),
            advertising_router=str(header_dict.get("advertising_router")),
            sequence=int(header_dict.get("sequence", 0)),
            age=int(header_dict.get("age", 0)),
            checksum=int(header_dict.get("checksum", 0)),
        ),
        payload=deepcopy(payload.get("payload") or {}),
    )
