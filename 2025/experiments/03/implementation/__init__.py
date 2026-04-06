"""
本目录提供 `experiments/03` 实验所需的 OSPF 协议完整实现。

暴露的主要组件：
- `Router`：路由进程核心，负责邻居维护、LSDB 泛洪与 SPF 计算；
- `EventLoop`：轻量级事件循环，实现定时任务与套接字轮询；
- `CliShell`：实验调试时使用的交互式命令行。

模块的职责划分与实验指导书中的描述保持一致，方便学生对照阅读。
"""

from .router import Router  # re-export for convenience
from .events import EventLoop
from .cli import CliShell

__all__ = ["Router", "EventLoop", "CliShell"]
