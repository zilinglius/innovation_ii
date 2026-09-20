# 云网融合创新实践（Innovation II）

本科生课程 **《云网融合创新实践》** 的讲义与配套实验。课程从计算机网络基础出发，利用 Linux 内核的网络虚拟化能力（network namespace、veth、bridge、`tc netem`）在单机上搭建可复现的网络实验，逐步深入到路由协议、精确定时与延迟测量，以及网络对分布式计算框架的影响。

## 仓库结构

| 路径 | 说明 |
| --- | --- |
| [`2026/`](2026/README.md) | **当前学期**：讲义（`docs/`）与实验（`experiments/`），大纲与进度见其中的 README |
| [`2025/`](2025/README.md) | 去年内容的归档：9 篇讲义与 8 个实验，含各实验的快速上手命令 |
| [`AGENTS.md`](AGENTS.md) | 写作、脚本与协作规范（同时供 AI 助手读取） |

## 从哪里开始

- 选课同学：从 [`2026/README.md`](2026/README.md) 的课程大纲进入，第一讲是 [计算机网络基础与 Linux 网络虚拟化](2026/docs/network.md)。
- 想提前动手：可以先做 [2025 的实验 01](2025/experiments/01/ns_setup_guide.md)（namespace 环形拓扑与网桥）。

## 实验环境

- 任意现代 Linux 主机或虚拟机（内核 ≥ 3.8，推荐 5.x 及以上），具备 `sudo` 权限
- 必需：`iproute2`、`iputils-ping`、`bridge-utils`、`tcpdump`
- 可选：`shellcheck`、`iperf3`、`gcc` + `libpcap-dev`、`python3` / [`uv`](https://docs.astral.sh/uv/)
- macOS / Windows 用户请使用 Linux 虚拟机或云主机
- 所有实验命令默认从**仓库根目录**执行

快速验证环境（搭建并拆除一个五节点环形拓扑）：

```bash
sudo bash 2025/experiments/01/ns.sh
sudo ip netns exec ns1 ping -c1 10.0.23.2
sudo bash 2025/experiments/01/ns.sh down
```

## 说明

本仓库为教学用途。发现问题欢迎提 issue 或 PR，规范见 [`AGENTS.md`](AGENTS.md)。
