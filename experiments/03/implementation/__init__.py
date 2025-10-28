"""
Concrete OSPF implementation used by the experiments/03 lab.

The package exposes high level helpers re-used by the CLI entrypoint:

- `Router`: routing process coordinating neighbors, LSDB, and SPF
- `EventLoop`: lightweight scheduler that integrates socket IO and timers
- `CliShell`: tiny interactive shell for inspection during experiments

Modules follow the simplified specification documented in `ospf_lab_guide.md`.
"""

from .router import Router  # re-export for convenience
from .events import EventLoop
from .cli import CliShell

__all__ = ["Router", "EventLoop", "CliShell"]
