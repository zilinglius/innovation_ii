#!/usr/bin/env python3
"""
精简版 OSPF 协议实验入口。

该脚本负责：
1. 解析命令行参数；
2. 加载拓扑配置并创建 Router 对象；
3. 启动事件循环与 CLI；
4. 在退出时执行清理。

核心协议逻辑位于 `ospf/` 包中，由学生补齐 TODO。
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
except ModuleNotFoundError:  # pragma: no cover - 提示学生安装依赖
  yaml = None

from ospf.cli import CliShell
from ospf.events import EventLoop
from ospf.router import Router


def parse_args(argv: list[str]) -> argparse.Namespace:
  parser = argparse.ArgumentParser(
      description="Mini OSPF-like routing process for teaching purposes."
  )
  parser.add_argument(
      "--router",
      required=True,
      help="Router ID in dotted decimal, e.g. 1.1.1.1",
  )
  parser.add_argument(
      "--config",
      default="topo.sample.yaml",
      help="Topology definition file (YAML).",
  )
  parser.add_argument(
      "--log-level",
      default="info",
      choices=["trace", "debug", "info", "warning", "error"],
      help="Set the logging verbosity.",
  )
  parser.add_argument(
      "--state-dir",
      default="./state",
      help="Directory to persist debug artifacts (pcap, logs, etc.).",
  )
  parser.add_argument(
      "--dry-run",
      action="store_true",
      help="Initialize components without touching kernel routing table.",
  )
  parser.add_argument(
      "--single-process",
      action="store_true",
      help="Run all router instances in one process using loopback sockets.",
  )
  return parser.parse_args(argv)


def load_config(path: Path) -> Dict[str, Any]:
  if not path.exists():
    raise FileNotFoundError(f"config file not found: {path}")
  if yaml is None:
    raise RuntimeError(
        "PyYAML 未安装。请运行 `pip install pyyaml` 后重试，"
        "或将拓扑文件改为 JSON 并自行解析。"
    )
  with path.open("r", encoding="utf-8") as stream:
    data = yaml.safe_load(stream)
  if not isinstance(data, dict):
    raise ValueError("配置文件根节点必须是 mapping")
  return data


def setup_logging(level_name: str) -> None:
  level = logging.getLevelName(level_name.upper())
  if isinstance(level, str):
    level = logging.INFO

  logging.basicConfig(
      level=level,
      format="%(asctime)s %(levelname)-5s [%(threadName)s] %(name)s: %(message)s",
  )

  # 自定义 TRACE 等级，方便细粒度调试。
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

  # CLI 在单独线程运行，避免阻塞事件循环。
  cli = CliShell(router=router)
  cli_thread = threading.Thread(target=cli.run, name="cli", daemon=True)

  logging.info("starting router %s", args.router)
  router.bootstrap()
  cli_thread.start()

  try:
    loop.run()
  except KeyboardInterrupt:
    logging.warning("interrupt received, shutting down...")
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
