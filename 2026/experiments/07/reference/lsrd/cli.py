"""
查看守护进程的内部状态。

守护进程一侧：在事件循环里监听一个 unix socket（默认 /run/lsrd/<id>.sock），
收到一行命令就把 router.snapshot() 以 JSON 回过去。unix socket 不受 network namespace
隔离，所以从宿主 shell 就能查看跑在 r1 里的进程。

客户端一侧：
    sudo python3 -m lsrd.cli <id> neighbors | lsdb | routes | stats | digest | json
通常经由 run.sh：sudo bash 2026/experiments/02/run.sh show r1 neighbors
"""

from __future__ import annotations

import json
import os
import socket
import sys
from typing import Any, Dict

SOCK_DIR = "/run/lsrd"


def sock_path(rid: int) -> str:
  return os.path.join(SOCK_DIR, f"{rid}.sock")


# ---- 守护进程一侧 ---------------------------------------------------------------

def serve(loop: Any, router: Any, path: str) -> socket.socket:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  if os.path.exists(path):
    os.unlink(path)
  server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  server.bind(path)
  server.listen(4)
  server.setblocking(False)

  def on_connection(_fd: int) -> None:
    try:
      conn, _ = server.accept()
    except OSError:
      return
    try:
      conn.settimeout(0.5)
      conn.recv(256)                       # 命令内容不重要：快照一次给全
      conn.sendall(json.dumps(router.snapshot()).encode("utf-8"))
    except OSError:
      pass
    finally:
      conn.close()

  loop.add_reader(server.fileno(), on_connection)
  return server


# ---- 客户端一侧 -----------------------------------------------------------------

def fetch(rid: int) -> Dict[str, Any]:
  client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  client.settimeout(2.0)
  client.connect(sock_path(rid))
  client.sendall(b"snapshot\n")
  chunks = []
  while True:
    chunk = client.recv(65536)
    if not chunk:
      break
    chunks.append(chunk)
  client.close()
  return json.loads(b"".join(chunks).decode("utf-8"))


def fmt_neighbors(snap: Dict[str, Any]) -> str:
  rows = [f"{'RID':>4}  {'IFACE':<8} {'ADDR':<12} {'STATE':<5} {'COST':>4} {'UP-FOR':>7} {'LAST-HELLO':>10}"]
  for n in snap["neighbors"]:
    rows.append(f"{n['rid']:>4}  {n['iface']:<8} {n['addr']:<12} {n['state']:<5} {n['cost']:>4} "
                f"{n['since']:>6}s {n['last_hello']:>9}s")
  if len(rows) == 1:
    rows.append("(no neighbors)")
  return "\n".join(rows)


def fmt_lsdb(snap: Dict[str, Any]) -> str:
  rows = []
  for lsa in snap["lsdb"]:
    links = ", ".join(f"{l['nbr']}:{l['cost']}" for l in lsa["links"]) or "-"
    prefixes = ", ".join(f"{p['p']}:{p['cost']}" for p in lsa["prefixes"]) or "-"
    rows.append(f"rid={lsa['rid']} seq={lsa['seq']}\n    links     {links}\n    prefixes  {prefixes}")
  rows.append(f"digest {snap['digest']}  ({len(snap['lsdb'])} LSAs)")
  return "\n".join(rows)


def fmt_routes(snap: Dict[str, Any]) -> str:
  fib = {}
  for r in snap["fib"]:
    if "nexthops" in r:
      fib[r["dst"]] = [(nh["gateway"], nh["dev"]) for nh in r["nexthops"]]
    else:
      fib[r["dst"]] = [(r.get("gateway", "-"), r.get("dev", "-"))]
  rows = [f"{'PREFIX':<16} {'COST':>4}  {'NEXTHOP(S)':<36} KERNEL"]
  for prefix, entry in snap["rib"].items():
    nhs = " + ".join(f"{nh['via']} dev {nh['dev']}" for nh in entry["nexthops"])
    wanted = [(nh["via"], nh["dev"]) for nh in entry["nexthops"]]
    kernel = "installed" if fib.get(prefix) == wanted else ("DIFFERS" if prefix in fib else "MISSING")
    if not snap["config"]["install"]:
      kernel = "(--no-install)"
    rows.append(f"{prefix:<16} {entry['cost']:>4}  {nhs:<36} {kernel}")
  for prefix in fib:
    if prefix not in snap["rib"]:
      rows.append(f"{prefix:<16} {'':>4}  {'':<36} kernel has it, RIB does not")
  if len(rows) == 1:
    rows.append("(no routes)")
  return "\n".join(rows)


def fmt_stats(snap: Dict[str, Any]) -> str:
  cfg = snap["config"]
  head = (f"rid {snap['rid']}  uptime {snap['uptime']}s  hello/dead {cfg['hello']}/{cfg['dead']}s  "
          f"ecmp={cfg['ecmp']} ack={cfg['ack']} watch_links={cfg['watch_links']} install={cfg['install']}\n"
          f"links: " + ", ".join(f"{l['name']}={l['addr']} cost {l['cost']}" for l in snap["links"]) +
          f"\npending acks: {snap['pending_acks']}")
  rows = [head] + [f"  {k:<20} {v}" for k, v in snap["stats"].items()]
  return "\n".join(rows)


def main(argv: list) -> int:
  if len(argv) < 1:
    print("usage: python3 -m lsrd.cli <id> [neighbors|lsdb|routes|stats|digest|json]", file=sys.stderr)
    return 2
  rid = int(argv[0])
  what = argv[1] if len(argv) > 1 else "neighbors"
  try:
    snap = fetch(rid)
  except OSError as exc:
    print(f"cannot reach lsrd {rid} at {sock_path(rid)}: {exc}", file=sys.stderr)
    return 1
  if what == "neighbors":
    print(fmt_neighbors(snap))
  elif what == "lsdb":
    print(fmt_lsdb(snap))
  elif what == "routes":
    print(fmt_routes(snap))
  elif what == "stats":
    print(fmt_stats(snap))
  elif what == "digest":
    print(snap["digest"])
  elif what == "json":
    print(json.dumps(snap, indent=1, sort_keys=True))
  else:
    print(f"unknown command {what!r}", file=sys.stderr)
    return 2
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
