"""
Link State Database 管理。

职责：
- 存储并检验 LSA；
- 处理序列号、老化、泛洪决策；
- 提供给 SPF 过程的拓扑视图。
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    raise NotImplementedError("TODO: implement LSA installation logic")

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
