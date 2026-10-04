"""
链路状态数据库（LSDB）与泛洪。对应规范 R3、R4、R5、R6，以及进阶任务的 R9。

  Lsa      一条 Router-LSA：{"rid", "seq", "links": [{"nbr", "cost"}], "prefixes": [{"p", "cost"}]}
  Lsdb     每台路由器一条 LSA，按 rid 索引；只认 seq 更大的（R5 前半）
  Flooder  泛洪规则：
             R3  邻居进入 Full → 把整个 LSDB 单播给它（代替 OSPF 的 DBD/LSR/LSU）
             R4  本机邻居集合或前缀集合变化 → seq + 1，重新生成本机 LSA 并泛洪
             R5  收到 LSA：更新则存入、转发给除来源外的所有 Full 邻居；否则丢弃
             R6  收到 rid 是自己、seq 不小于本机当前值的 LSA → seq 跳到它之上，重新生成
             R9  （进阶）每条发出的 LSU 等 Ack，1 秒没等到就重传，直到收到或邻居 Down

Flooder 通过 router 对象访问其余部件：router.rid、router.lsdb、router.neighbors、
router.transport、router.stats、router.loop、router.ack_enabled。
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from .transport import VERSION, Link

if TYPE_CHECKING:            # 只为类型标注，避免循环导入
  from .neighbor import Neighbor
  from .router import Router

LOG = logging.getLogger("lsdb")

RETRANSMIT_INTERVAL = 1.0    # R9：重传间隔（秒）


@dataclass
class Lsa:
  rid: int
  seq: int
  links: List[Dict[str, int]] = field(default_factory=list)       # [{"nbr": 2, "cost": 10}, ...]
  prefixes: List[Dict[str, Any]] = field(default_factory=list)    # [{"p": "10.0.1.0/24", "cost": 10}, ...]

  @classmethod
  def from_dict(cls, d: Dict[str, Any]) -> "Lsa":
    return cls(rid=int(d["rid"]), seq=int(d["seq"]),
               links=[{"nbr": int(l["nbr"]), "cost": int(l["cost"])} for l in d["links"]],
               prefixes=[{"p": str(p["p"]), "cost": int(p["cost"])} for p in d["prefixes"]])

  def to_dict(self) -> Dict[str, Any]:
    return {"rid": self.rid, "seq": self.seq,
            "links": sorted(self.links, key=lambda l: l["nbr"]),
            "prefixes": sorted(self.prefixes, key=lambda p: p["p"])}

  def __str__(self) -> str:
    links = ",".join(f"{l['nbr']}:{l['cost']}" for l in sorted(self.links, key=lambda l: l["nbr"]))
    prefixes = ",".join(f"{p['p']}:{p['cost']}" for p in sorted(self.prefixes, key=lambda p: p["p"]))
    return f"LSA(rid={self.rid} seq={self.seq} links=[{links}] prefixes=[{prefixes}])"


_TODO_SEEN = set()


def _todo(what: str) -> None:
  """还没实现的规则：只在日志里提醒一次，守护进程继续跑。"""
  if what not in _TODO_SEEN:
    _TODO_SEEN.add(what)
    LOG.warning("TODO 尚未实现：%s", what)


class Lsdb:

  def __init__(self) -> None:
    self._db: Dict[int, Lsa] = {}

  def get(self, rid: int) -> Optional[Lsa]:
    return self._db.get(rid)

  def all(self) -> List[Lsa]:
    return [self._db[rid] for rid in sorted(self._db)]

  def __len__(self) -> int:
    return len(self._db)

  def put(self, lsa: Lsa) -> None:
    """无条件存入（不做 seq 比较）。离线测试用它来摆好一张地图，协议代码不要用它。"""
    self._db[lsa.rid] = lsa

  def is_newer(self, lsa: Lsa) -> bool:
    """R5 前半：LSDB 里没有这台路由器的 LSA，或这条的 seq 更大，才算“更新”。"""
    # ---- TODO（规范 R5）：把下面的桩换成你的实现 ----
    _todo("Lsdb.is_newer（R5）")
    return True

  def install(self, lsa: Lsa) -> bool:
    """更新则存入并返回 True；否则不动并返回 False。"""
    # ---- TODO（规范 R5）：把下面的桩换成你的实现 ----
    _todo("Lsdb.install（R5）")
    return False

  def digest(self) -> str:
    """整个 LSDB 的指纹：三台路由器的地图一致，指纹就一致。"""
    canonical = json.dumps([lsa.to_dict() for lsa in self.all()], sort_keys=True,
                           separators=(",", ":"))
    return hashlib.sha1(canonical.encode()).hexdigest()[:10]

  def snapshot(self) -> List[Dict[str, Any]]:
    return [lsa.to_dict() for lsa in self.all()]


class Flooder:
  """泛洪规则 R3–R6、R9。"""

  def __init__(self, router: "Router") -> None:
    self.router = router
    self.seq_floor = 0                                          # R6：本机 seq 至少要超过它
    # R9：等待确认的 LSU。键 (邻居 rid, 接口名, LSA 的 rid) → [seq, Neighbor, 上次发送时刻]
    self.pending: Dict[Tuple[int, str, int], List[Any]] = {}

  # ---- 小工具 --------------------------------------------------------------

  def _lsu(self, lsas: List[Lsa]) -> Dict[str, Any]:
    return {"v": VERSION, "type": "lsu", "rid": self.router.rid,
            "lsas": [lsa.to_dict() for lsa in lsas]}

  def send(self, nbr: "Neighbor", lsas: List[Lsa]) -> None:
    """把若干 LSA 打包成一条 LSU 单播给邻居；开了 R9 就登记等待 Ack。"""
    if not lsas:
      return
    self.router.transport.unicast(nbr.link, nbr.addr, self._lsu(lsas))
    if self.router.ack_enabled:
      now = self.router.loop.now()
      for lsa in lsas:
        self.pending[(nbr.rid, nbr.link.name, lsa.rid)] = [lsa.seq, nbr, now]

  # ---- R4：生成本机 LSA ------------------------------------------------------

  def originate(self, links: List[Dict[str, int]], prefixes: List[Dict[str, Any]]) -> Lsa:
    """
    用当前的 Full 邻居列表与前缀列表生成本机的新 LSA：
    seq = max(本机当前 seq, seq_floor) + 1，存入 LSDB，向所有 Full 邻居泛洪。
    """
    # ---- TODO（规范 R4）：把下面的桩换成你的实现 ----
    _todo("Flooder.originate（R4）")
    return Lsa(rid=self.router.rid, seq=0, links=links, prefixes=prefixes)

  # ---- R5：收 LSU 并转发 -----------------------------------------------------

  def flood(self, lsa: Lsa, exclude: Optional["Neighbor"]) -> None:
    """把一条 LSA 发给所有 Full 邻居，exclude（它的来源）除外。"""
    # ---- TODO（规范 R5）：把下面的桩换成你的实现 ----
    _todo("Flooder.flood（R5）")

  def on_lsu(self, link: Link, src: str, msg: Dict[str, Any]) -> bool:
    """
    处理一条收到的 LSU。返回 LSDB 是否发生了变化（变化则 router 会重跑 SPF）。
      - 来源邻居 = neighbors.get(msg["rid"], link)，可能为 None（不是邻居也照收——协议没有认证）；
      - 对每条 LSA：
          rid 是自己 → 交给 R6（self_originated）；
          否则 lsdb.install()：更新 → 记日志、转发给除来源外的 Full 邻居；不更新 → 丢弃计数；
      - 开了 R9：无论新旧，把收到的每条 (rid, seq) 都 Ack 回去（旧的也要 Ack，否则对方会一直重传）。
    """
    # ---- TODO（规范 R5）：把下面的桩换成你的实现 ----
    _todo("Flooder.on_lsu（R5）")
    return False

  # ---- R6：收到“自己的” LSA ---------------------------------------------------

  def self_originated(self, lsa: Lsa) -> bool:
    """
    收到 rid 等于本机的 LSA（本机重启后网络里还留着旧版本，或者有人伪造）。
    它比本机当前的 LSA “新”（seq 更大，或 seq 相同但内容不同）时：把 seq_floor 抬到它的 seq，
    返回 True——router 随后会以更大的 seq 重新生成本机 LSA，把它盖掉。
    否则（就是本机当前这条被邻居原样送回来了，R3 全量同步时常见）返回 False。
    """
    # ---- TODO（规范 R6）：把下面的桩换成你的实现 ----
    _todo("Flooder.self_originated（R6）")
    return False

  # ---- R3：新邻居全量同步 ----------------------------------------------------

  def on_neighbor_full(self, nbr: "Neighbor") -> None:
    """邻居进入 Full：把本机 LSDB 里的全部 LSA 打包发给它。"""
    # ---- TODO（规范 R3）：把下面的桩换成你的实现 ----
    _todo("Flooder.on_neighbor_full（R3）")

  def on_neighbor_down(self, nbr: "Neighbor") -> None:
    """邻居消失：丢掉发给它的待确认条目（R9）。"""
    for key in [k for k in self.pending if k[0] == nbr.rid and k[1] == nbr.link.name]:
      del self.pending[key]

  # ---- R9：Ack 与重传（进阶任务 T9）------------------------------------------

  def on_ack(self, link: Link, src: str, msg: Dict[str, Any]) -> None:
    """收到 Ack：对每个 {rid, seq}，若待确认表里对应条目的 seq 不大于它，删除该条目。"""
    # ---- TODO（规范 R9）：把下面的桩换成你的实现 ----
    pass                # 进阶任务 T9

  def retransmit(self, now: float) -> None:
    """每秒调用一次：超过 RETRANSMIT_INTERVAL 没被确认的条目，重发 LSDB 里该 rid 的**当前**版本。"""
    # ---- TODO（规范 R9）：把下面的桩换成你的实现 ----
    pass                # 进阶任务 T9
