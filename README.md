# 云网融合创新实践（Innovation II）

本科生课程 **《云网融合创新实践》** 的讲义与配套实验。课程从计算机网络基础出发，利用 Linux 内核的网络虚拟化能力（network namespace、veth、bridge、`tc netem`）在单机上搭建可复现的网络实验，逐步深入到路由协议、精确定时与延迟测量，以及网络对分布式计算框架的影响。

2026 学期共 **15 讲、9 个实验和一个综合项目**。课程最终目标是让学生实践计算与网络的相互融合，以作业完成时间（Job Completion Time, JCT）衡量后半程的优化效果。

## 仓库结构

| 路径 | 说明 |
| --- | --- |
| [`2026/`](2026/README.md) | **当前学期**：讲义（`docs/`）与实验（`experiments/`），大纲与进度见其中的 README |
| [`2025/`](2025/README.md) | 去年内容的归档：9 篇讲义与 8 个实验，含各实验的快速上手命令 |
| [`AGENTS.md`](AGENTS.md) | 写作、脚本与协作规范（同时供 AI 助手读取） |

## 从哪里开始

- 选课同学：从 [`2026/README.md`](2026/README.md) 的课程大纲进入，第一讲是 [计算机网络基础与 Linux 网络虚拟化](2026/docs/network.md)。
- 想提前动手：按 [2026 的 Lab 1](2026/experiments/01/README.md) 搭建两机架实验床，再进入 [Lab 2](2026/experiments/02/README.md) 实现链路状态路由器。
- 备课与编写资料：先读 [`AGENTS.md`](AGENTS.md)、[课程大纲](2026/README.md) 和 [实验设计总览](2026/experiments/README.md)。已有资料与备课流程见 [2026 学期索引](2026/README.md#备课与维护)。

目前第 01–04 讲、第一讲的回顾与参考答案，以及 Lab 1、Lab 2 已有文件，状态仍为撰写中；后续讲次与实验按大纲逐步编写。Lab 2 提供的是含学生 TODO 的教学骨架，初始离线测试有预期失败，详见指导书。

## 实验环境

- 一台 Linux 主机或虚拟机，推荐 Ubuntu 22.04 及以上、至少 4 核 CPU 和 4 GB 内存，具备 `sudo` 权限；Lab 9 需要 cgroup v2
- 必需：`iproute2`、`iputils-ping`、`tcpdump`、`traceroute`、`iperf3`、`iptables`、Python 3.10 及以上与 [`uv`](https://docs.astral.sh/uv/)
- 个别讲次另需 FRRouting 或特定内核模块，详见 [2026 环境说明](2026/README.md#实验环境) 与各实验指导书；`shellcheck` 用于脚本静态检查
- macOS / Windows 用户请使用 Linux 虚拟机或云主机
- 所有实验命令默认从**仓库根目录**执行

在 Linux 上快速验证环境（搭建并拆除 2026 的两机架实验床）：

```bash
# 1. 搭建实验床，脚本会自动检查同机架与跨机架连通性
sudo bash 2026/experiments/01/ns_topo.sh

# 2. 单独重跑连通性检查
sudo bash 2026/experiments/01/ns_topo.sh check

# 3. 拆除实验床
sudo bash 2026/experiments/01/ns_topo.sh down
```

## 说明

本仓库为教学用途。发现问题欢迎提 issue 或 PR，规范见 [`AGENTS.md`](AGENTS.md)。
