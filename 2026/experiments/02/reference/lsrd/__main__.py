"""
守护进程入口。

    sudo ip netns exec r1 .venv/bin/python -m lsrd --id 1 --passive br1

常用选项（完整列表 --help）：
    --hello 2 --dead 8        定时器（规范 3.3 节；三台必须一致，否则 Hello 被丢弃）
    --cost r1-r2=20           某个接口的 cost（缺省 10）
    --watch-links             订阅内核链路事件（进阶 T6）
    --ecmp                    并列路径装成多下一跳（进阶 T8）
    --ack                     可靠泛洪（进阶 T9）
    --no-install              只算路由，不写内核
    --log FILE                日志文件（缺省标准错误）
通常不直接敲这条命令，而是 sudo bash 2026/experiments/02/run.sh start [选项...]。
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from typing import Dict, List

from . import cli
from .loop import EventLoop
from .router import Config, Router

PID_DIR = "/run/lsrd"


def parse_cost(items: List[str]) -> Dict[str, int]:
  cost: Dict[str, int] = {}
  for item in items:
    try:
      name, value = item.split("=", 1)
      cost[name] = int(value)
    except ValueError:
      raise SystemExit(f"--cost expects IFACE=COST, got {item!r}")
    if cost[name] <= 0:
      raise SystemExit(f"--cost {name}: cost must be positive")
  return cost


def parse_args(argv: List[str]) -> argparse.Namespace:
  p = argparse.ArgumentParser(prog="lsrd", description="Lab 2 链路状态路由守护进程（LSR-lite v1）")
  p.add_argument("--id", type=int, required=True, help="router id（小整数）")
  p.add_argument("--passive", action="append", default=[], metavar="IFACE",
                 help="只通告网段、不发 Hello 的接口，可重复")
  p.add_argument("--hello", type=int, default=2, help="Hello 间隔（秒，默认 2）")
  p.add_argument("--dead", type=int, default=8, help="Dead 间隔（秒，默认 8）")
  p.add_argument("--cost", action="append", default=[], metavar="IFACE=COST",
                 help="接口 cost（默认 10），可重复")
  p.add_argument("--spf-delay", type=float, default=0.1, help="SPF 合并延迟（秒，默认 0.1）")
  p.add_argument("--ecmp", action="store_true", help="等价路径装成多下一跳")
  p.add_argument("--ack", action="store_true", help="LSU 需要 Ack，未确认则重传")
  p.add_argument("--watch-links", action="store_true", help="订阅内核链路事件")
  p.add_argument("--no-install", action="store_true", help="不写内核路由表")
  p.add_argument("--port", type=int, default=5200)
  p.add_argument("--log", metavar="FILE", help="日志文件（默认标准错误）")
  p.add_argument("--sock", metavar="PATH", help=f"CLI 套接字（默认 {cli.SOCK_DIR}/<id>.sock）")
  p.add_argument("--pidfile", metavar="PATH", help=f"pid 文件（默认 {PID_DIR}/<id>.pid）")
  p.add_argument("-v", "--verbose", action="store_true", help="DEBUG 级日志（含每条被丢弃的 LSA）")
  return p.parse_args(argv)


def main(argv: List[str]) -> int:
  args = parse_args(argv)
  if args.hello <= 0 or args.dead <= args.hello:
    raise SystemExit("--dead must be larger than --hello, both positive")

  logging.basicConfig(
      level=logging.DEBUG if args.verbose else logging.INFO,
      format="%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s",
      datefmt="%H:%M:%S",
      filename=args.log,
  )
  log = logging.getLogger("lsrd")

  cfg = Config(rid=args.id, passive=args.passive, hello=args.hello, dead=args.dead,
               cost=parse_cost(args.cost), spf_delay=args.spf_delay, ecmp=args.ecmp,
               ack=args.ack, watch_links=args.watch_links, install=not args.no_install,
               port=args.port)
  loop = EventLoop()
  router = Router(cfg, loop)

  pidfile = args.pidfile or os.path.join(PID_DIR, f"{args.id}.pid")
  os.makedirs(os.path.dirname(pidfile), exist_ok=True)
  with open(pidfile, "w", encoding="utf-8") as fh:
    fh.write(str(os.getpid()))

  def on_signal(signum: int, _frame: object) -> None:
    log.info("signal %d, shutting down", signum)
    loop.stop()

  signal.signal(signal.SIGTERM, on_signal)
  signal.signal(signal.SIGINT, on_signal)
  # SIGUSR1：内容不变、seq + 1，重新生成并泛洪一条本机 LSA——用来数泛洪份数（run.sh poke rN）
  signal.signal(signal.SIGUSR1, lambda *_: router.originate())

  log.info("lsrd starting: rid=%d hello=%d dead=%d passive=%s ecmp=%s ack=%s watch_links=%s install=%s",
           cfg.rid, cfg.hello, cfg.dead, cfg.passive, cfg.ecmp, cfg.ack, cfg.watch_links, cfg.install)
  server = cli.serve(loop, router, args.sock or cli.sock_path(args.id))
  status = 0
  try:
    router.start()
    loop.run()
  except Exception:                      # 学生代码抛异常：把栈打进日志，然后清理退出
    log.exception("daemon crashed")
    status = 1
  finally:
    router.shutdown()
    server.close()
    for path in (args.sock or cli.sock_path(args.id), pidfile):
      try:
        os.unlink(path)
      except OSError:
        pass
    log.info("lsrd stopped")
  return status


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
