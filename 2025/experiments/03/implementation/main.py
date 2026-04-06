#!/usr/bin/env python3
"""
教学版 OSPF 协议的可执行入口，便于在 namespace 或单进程模式下运行。
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import sys
import threading
from pathlib import Path
from typing import Any, Dict

try:
  import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - instruct the student
  yaml = None

from .cli import CliShell
from .events import EventLoop
from .router import Router


def parse_args(argv: list[str]) -> argparse.Namespace:
  parser = argparse.ArgumentParser(
      description="experiments/03 完整版 OSPF 实验进程入口。",
  )
  parser.add_argument("--router", required=True, help="Router ID in dotted decimal form, e.g. 1.1.1.1")
  parser.add_argument("--config", default="../topo.sample.yaml", help="Topology definition file (YAML)")
  parser.add_argument("--log-level", default="info", choices=["trace", "debug", "info", "warning", "error"])
  parser.add_argument("--dry-run", action="store_true", help="Skip programming kernel routing tables")
  parser.add_argument("--single-process", action="store_true", help="Run using loopback sockets instead of namespaces")
  return parser.parse_args(argv)


def load_config(path: Path) -> Dict[str, Any]:
  if not path.exists():
    raise FileNotFoundError(f"config file not found: {path}")
  if yaml is None:
    raise RuntimeError("未安装 PyYAML，可执行 `pip install pyyaml` 或改用 JSON 拓扑文件。")
  with path.open("r", encoding="utf-8") as stream:
    data = yaml.safe_load(stream)
  if not isinstance(data, dict):
    raise ValueError("topology file must contain a mapping at the root")
  return data


def setup_logging(level_name: str) -> None:
  level = logging.getLevelName(level_name.upper())
  if isinstance(level, str):
    level = logging.INFO

  logging.basicConfig(
      level=level,
      format="%(asctime)s %(levelname)-5s [%(threadName)s] %(name)s: %(message)s",
  )
  if level_name == "trace":
    logging.getLogger().setLevel(5)
    logging.addLevelName(5, "TRACE")


def main(argv: list[str]) -> int:
  args = parse_args(argv)
  setup_logging(args.log_level)

  config = load_config(Path(args.config))
  loop = EventLoop()
  router = Router(
      router_id=args.router,
      config=config,
      event_loop=loop,
      dry_run=args.dry_run,
      single_process=args.single_process,
  )

  cli = CliShell(router=router)
  cli_thread = threading.Thread(target=cli.run, name="cli", daemon=True)

  logging.info("启动路由器进程 %s", args.router)
  router.bootstrap()
  cli_thread.start()

  try:
    loop.run()
  except KeyboardInterrupt:
    logging.warning("收到中断信号，开始清理")
  finally:
    with contextlib.suppress(Exception):
      loop.stop()
    with contextlib.suppress(Exception):
      router.shutdown()
    cli.stop()
    cli_thread.join(timeout=1)

  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
