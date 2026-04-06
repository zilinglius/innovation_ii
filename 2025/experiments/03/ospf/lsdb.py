"""
Link State Database 管理。

职责：
- 存储并检验 LSA；
- 处理序列号、老化、泛洪决策；
- 提供给 SPF 过程的拓扑视图。
"""

from __future__ import annotations

import json
import zlib
from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, Tuple


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


class LinkStateDatabase:
  def __init__(self) -> None:
    self._lsas: Dict[Tuple[str, str], Lsa] = {}

  def install(self, lsa: Lsa) -> bool:
    """
    将 LSA 插入数据库。

    返回值：
      bool: 是否更新了数据库（True 表示新 LSA 或更“新鲜”的 LSA）。

    TODO:
      - 比较序列号判断是否接受；
      - 更新 age/checksum；
      - 返回布尔值指示是否需要继续泛洪。
    """
    key = lsa.fingerprint()
    current = self._lsas.get(key)

    # 构造待存储的 LSA 副本，归零 age 并重新计算校验和。
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
          # 新的 LSA 与现有完全一致，无需更新。
          return False

    self._lsas[key] = candidate
    return True

  def age(self, seconds: int) -> Iterable[Lsa]:
    """
    老化所有 LSA，当 age 超过 LSRefreshTime 时应触发刷新或移除。

    TODO:
      - 遍历 self._lsas，对 age 做 +seconds；
      - 对超时 LSA 采取相应策略（重发或删除）；
      - 返回处理后的 LSA 列表（可用于泛洪）。
    """
    raise NotImplementedError("TODO: implement LSA aging")

  def snapshot(self) -> Dict[Tuple[str, str], Lsa]:
    """
    提供 LSDB 快照给 SPF 过程或 CLI。
    """
    return dict(self._lsas)


def _compute_checksum(header: LsaHeader, payload: Dict[str, object]) -> int:
  """
  简易校验和，方便在实验中比较 LSA 是否发生变更。
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
