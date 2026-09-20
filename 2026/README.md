# 《云网融合创新实践》2026

本目录存放 2026 学年的讲义与实验。课程共 16 讲、10 个实验加一个综合项目，最终目标是让学生亲手实践**计算与网络的相互融合**：感知网络、感知算力、联合决策，让同样的计算跑得更快。

去年的材料归档在 [`../2025/`](../2025/README.md)，仅作参考；今年的实验是重新设计的。

## 目录

| 路径 | 内容 |
| --- | --- |
| [`docs/`](docs/) | 讲义（每讲一篇） |
| [`experiments/`](experiments/README.md) | 实验设计总览；各实验按 `NN/` 两位编号组织，目录内的 `README.md` 为实验指导书 |

## 课程大纲与进度

> 状态：✅ 已完成 ｜ 📝 撰写中 ｜ ⏳ 未开始

| 讲次 | 主题 | 讲义 | 配套实验 | 状态 |
| --- | --- | --- | --- | --- |
| **一、网络基础与虚拟化** | | | | |
| 01 | 计算机网络基础与 Linux 网络虚拟化 | [`docs/network.md`](docs/network.md) | Lab 1 | 📝 |
| 02 | 二层交换与静态路由：bridge、多跳拓扑、路由表与转发 | — | Lab 1 | ⏳ |
| 03 | 动态路由协议：距离向量、链路状态、路径向量（RIP / OSPF / BGP） | — | Lab 2 | ⏳ |
| 04 | 动手实现一个链路状态路由器：邻居发现、LSA 泛洪、SPF | — | Lab 2 | ⏳ |
| **二、云数据中心网络** | | | | |
| 05 | 数据中心网络架构：Clos / leaf-spine、ECMP、收敛比 | — | Lab 3 | ⏳ |
| 06 | 云网络虚拟化：overlay、VXLAN、容器网络、SDN 思想 | — | Lab 4 | ⏳ |
| 07 | 网络性能测量与流量控制：带宽 / 延迟 / 抖动 / 丢包，`iperf3`、`tc` | — | Lab 5 | ⏳ |
| **三、传输、时间与延迟** | | | | |
| 08 | 传输层与拥塞控制：CUBIC / BBR / DCTCP，incast 问题 | — | Lab 6 | ⏳ |
| 09 | 发送节奏与报文时间戳：pacing、`SO_TXTIME`、ETF qdisc | — | Lab 6 | ⏳ |
| 10 | 长尾延迟：成因、放大效应与缓解手段 | — | Lab 7 | ⏳ |
| **四、网络视角下的分布式计算** | | | | |
| 11 | 分布式计算的通信模式与代价模型：BSP / barrier、shuffle、参数服务器、AllReduce，α-β 模型 | — | Lab 8 | ⏳ |
| 12 | 网络对分布式框架的影响：跨机架瓶颈与 straggler | — | Lab 8；布置综合项目 | ⏳ |
| 13 | 集合通信与 AI 训练网络：Ring / Tree AllReduce、RDMA / RoCE、在网计算 | — | Lab 9 | ⏳ |
| **五、算网融合** | | | | |
| 14 | 拓扑感知调度：让计算“看见”网络 | — | Lab 10 | ⏳ |
| 15 | 算力网络与算网协同：算力度量、算力感知路由（IETF CATS）、云边协同、算力星座 | — | Lab 10 | ⏳ |
| 16 | 综合项目展示与课程总结 | — | 综合项目 | ⏳ |

实验的设计原则、各实验内容与相互依赖见 [`experiments/README.md`](experiments/README.md)。

### 可参考的 2025 材料

撰写今年讲义时可以在去年对应主题的基础上改写（去年以英文为主）：

| 今年讲次 | 2025 讲义 |
| --- | --- |
| 01–02 | [`network.md`](../2025/docs/network.md)、[`route.md`](../2025/docs/route.md) |
| 03–04 | [`routing_protocol.md`](../2025/docs/routing_protocol.md) |
| 09 | [`udp_app_send_timing.md`](../2025/docs/udp_app_send_timing.md)、[`timestamped_packet_transmission.md`](../2025/docs/timestamped_packet_transmission.md) |
| 10 | [`network_latency_long_tail.md`](../2025/docs/network_latency_long_tail.md) |
| 11–12 | [`network_impact_distributed_frameworks.md`](../2025/docs/network_impact_distributed_frameworks.md) |
| 14 | [`topology_aware_distributed_framework.md`](../2025/docs/topology_aware_distributed_framework.md) |
| 15 | [`compute_constellation.md`](../2025/docs/compute_constellation.md) |

第 05、06、07、08、13 讲没有对应的旧材料，需要新写。

## 实验环境

- 一台 Linux 主机或虚拟机即可完成全部实验，不需要 GPU 或多机环境。建议至少 4 核 CPU、4 GB 内存，具备 `sudo` 权限。
- 推荐 Ubuntu 22.04 及以上（Lab 10 需要 cgroup v2，较新的发行版默认启用）。
- 必需：`iproute2`、`iputils-ping`、`tcpdump`、`iperf3`、Python 3 与 [`uv`](https://docs.astral.sh/uv/)。
- macOS / Windows 用户请使用 Linux 虚拟机或云主机；network namespace 是 Linux 内核特性。
- 所有实验命令默认从**仓库根目录**执行。

写作与脚本规范见仓库根目录的 [`AGENTS.md`](../AGENTS.md)。
