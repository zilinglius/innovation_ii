# 《云网融合创新实践》2026

本目录存放 2026 学年的讲义与实验。课程共 15 讲、9 个实验加一个综合项目，最终目标是让学生亲手实践**计算与网络的相互融合**：感知网络、感知算力、联合决策，让同样的计算跑得更快。

去年的材料归档在 [`../2025/`](../2025/README.md)，仅作参考；今年的实验是重新设计的。

## 目录

| 路径 | 内容 |
| --- | --- |
| [`docs/`](docs/) | 讲义（每讲一篇） |
| [`experiments/`](experiments/README.md) | 实验设计总览；各实验按 `NN/` 两位编号组织，目录内的 `README.md` 为实验指导书 |
| [`environment/`](environment/README.md) | 教师与 AI 助手的备课、实验开发及 Linux 验证沙箱 |

## 课程大纲与进度

> 状态：✅ 已完成 ｜ 📝 撰写中 ｜ ⏳ 未开始
>
> 2026-09-27 调整：因假期停课一次，全课由 16 讲压缩为 15 讲——原第 05、06 讲合并为第 05 讲，原 Lab 3、Lab 4 合并为 Lab 3（VXLAN 多租户改为进阶任务），其后的讲次与实验编号依次前移一位。

| 讲次 | 主题 | 讲义 | 配套实验 | 状态 |
| --- | --- | --- | --- | --- |
| **一、网络基础与虚拟化** | | | | |
| 01 | 计算机网络基础与 Linux 网络虚拟化 | [`docs/network.md`](docs/network.md) | [Lab 1](experiments/01/README.md) | 📝 |
| 02 | 二层交换与静态路由：bridge、多跳拓扑、路由表与转发 | [`docs/switching_routing.md`](docs/switching_routing.md) | [Lab 1](experiments/01/README.md) | 📝 |
| 03 | 动态路由协议：距离向量、链路状态、路径向量（RIP / OSPF / BGP） | [`docs/routing_protocol.md`](docs/routing_protocol.md) | [Lab 2](experiments/02/README.md) | 📝 |
| 04 | 动手实现一个链路状态路由器：邻居发现、LSA 泛洪、SPF | [`docs/link_state_router.md`](docs/link_state_router.md) | [Lab 2](experiments/02/README.md) | 📝 |
| **二、云数据中心网络** | | | | |
| 05 | 数据中心网络：Clos / leaf-spine、ECMP、收敛比；overlay 与 VXLAN 多租户，容器网络与 SDN 一瞥 | [`docs/datacenter_network.md`](docs/datacenter_network.md) | [Lab 3](experiments/03/README.md) | 📝 |
| 06 | 网络性能测量与流量控制：带宽 / 延迟 / 抖动 / 丢包，`iperf3`、`tc` | — | Lab 4 | ⏳ |
| **三、传输、时间与延迟** | | | | |
| 07 | 传输层与拥塞控制：CUBIC / BBR / DCTCP，incast 问题 | — | Lab 5 | ⏳ |
| 08 | 发送节奏与报文时间戳：pacing、`SO_TXTIME`、ETF qdisc | — | Lab 5 | ⏳ |
| 09 | 长尾延迟：成因、放大效应与缓解手段 | — | Lab 6 | ⏳ |
| **四、网络视角下的分布式计算** | | | | |
| 10 | 分布式计算的通信模式与代价模型：BSP / barrier、shuffle、参数服务器、AllReduce，α-β 模型 | — | Lab 7 | ⏳ |
| 11 | 网络对分布式框架的影响：跨机架瓶颈与 straggler | — | Lab 7；布置综合项目 | ⏳ |
| 12 | 集合通信与 AI 训练网络：Ring / Tree AllReduce、RDMA / RoCE、在网计算 | — | Lab 8 | ⏳ |
| **五、算网融合** | | | | |
| 13 | 拓扑感知调度：让计算“看见”网络 | — | Lab 9 | ⏳ |
| 14 | 算力网络与算网协同：算力度量、算力感知路由（IETF CATS）、云边协同、算力星座 | — | Lab 9 | ⏳ |
| 15 | 综合项目展示与课程总结 | — | 综合项目 | ⏳ |

实验的设计原则、各实验内容与相互依赖见 [`experiments/README.md`](experiments/README.md)。

### 补充资料

| 对应讲次 | 资料 | 用途 |
| --- | --- | --- |
| 01 | [第一讲回顾](docs/network_review.md) | 围绕实验输出复习，供学生自查与课堂讨论 |
| 01 | [回顾参考答案](docs/network_review_answers.md) | 配合回顾讲义讲评 |

前五讲、上述补充资料与 Lab 1、Lab 2、Lab 3 指导书均有同目录、同名的 `.html` 阅读版。编写时以 `.md` 为源文件，修改后应同步检查对应阅读版。第 05 讲仍为讲义草稿；Lab 3 已交付修订指导书、学生拓扑骨架、测量助手与清理工具；2026-10-05 已按修订命令在备课沙箱中验证主要对照，具体范围见 [Lab 3 维护与验证](experiments/03/README.md#维护与验证)。学生 TODO 保持留白，学生实现仍须独立验收。

### 可参考的 2025 材料

撰写今年讲义时可以在去年对应主题的基础上改写（去年以英文为主）：

| 今年讲次 | 2025 讲义 |
| --- | --- |
| 01–02 | [`network.md`](../2025/docs/network.md)、[`route.md`](../2025/docs/route.md) |
| 03–04 | [`routing_protocol.md`](../2025/docs/routing_protocol.md) |
| 08 | [`udp_app_send_timing.md`](../2025/docs/udp_app_send_timing.md)、[`timestamped_packet_transmission.md`](../2025/docs/timestamped_packet_transmission.md) |
| 09 | [`network_latency_long_tail.md`](../2025/docs/network_latency_long_tail.md) |
| 10–11 | [`network_impact_distributed_frameworks.md`](../2025/docs/network_impact_distributed_frameworks.md) |
| 13 | [`topology_aware_distributed_framework.md`](../2025/docs/topology_aware_distributed_framework.md) |
| 14 | [`compute_constellation.md`](../2025/docs/compute_constellation.md) |

第 05、06、07、12 讲没有完整对应的旧讲义，需要新写；第 05 讲可参考去年 `network_impact_distributed_frameworks.md` 中的拓扑讨论。

## 备课与维护

1. **确认进度与边界**：先读 [`AGENTS.md`](../AGENTS.md)、本页大纲和 [实验设计总览](experiments/README.md)，再查看工作区已有修改。`2025/` 保持归档只读，新增内容放在 `2026/`。
2. **准备一讲**：参考上表的旧材料与 [`network.md`](docs/network.md) 的结构，围绕配套实验写学习目标、理论、动手模块和思考题。已有教师讲义正文的修改须先取得同意。
3. **准备一个实验**：明确它复用哪些上游产出、交付哪些下游接口；按基础、进阶、挑战组织“预测、测量、解释”，并给出连通性验证和资源清理步骤。
4. **核验并更新索引**：检查本地链接、脚本语法、阅读版和对应实验；同步更新本页与实验总览的状态。文件存在不等于实验已经验证通过。
5. **在沙箱中实机验证**：教师与 AI 助手使用 [`environment/`](environment/README.md) 中的 Linux 沙箱运行拓扑和真实流量，记录实际环境与验证范围。学生自行准备 Ubuntu，讲义和实验指导书以学生的独立 Ubuntu 环境为基准。

Python 环境按实验分别管理。目前 Lab 2 与 Lab 3 使用 Python 3.12、只依赖标准库，可以在 macOS 上做离线准备；拓扑、真实流量和路由安装必须在 Linux 上验证。以下命令均从仓库根目录执行：

```bash
# 1. 按各自锁文件初始化 Lab 2 与 Lab 3 的独立 Python 环境
uv sync --project 2026/experiments/02 --frozen
uv sync --project 2026/experiments/03 --frozen

# 2. 检查现有实验脚本的语法（不创建网络资源）
(
  for script in 2026/experiments/01/*.sh 2026/experiments/02/*.sh 2026/experiments/03/*.sh; do
    bash -n "$script" || exit 1
  done
)

# 3. 运行 Lab 2 已有的离线测试（不需要 root）
(cd 2026/experiments/02 && uv run --frozen python -m unittest -v)
```

Lab 2 骨架初始结果为 **17 项测试中 5 项通过、9 项失败、3 项错误**，与 [指导书任务 1](experiments/02/README.md) 一致；学生实现 R5、R7 后才应全部通过。邻居发现、泛洪和链路监测等 TODO 也属于教学任务，不应在日常维护中自动补成参考答案。Linux 实机验证步骤按各实验指导书执行，结束后调用对应的 `down` 子命令。

## 实验环境

- 学生自行准备 Ubuntu Linux 主机或虚拟机，并按各实验指导书安装工具、检查内核能力。仓库中的 `environment/` 是教师与 AI 助手的备课验证沙箱。
- 一台 Linux 主机或虚拟机即可完成全部实验，不需要 GPU 或多机环境。建议至少 4 核 CPU、4 GB 内存，具备 `sudo` 权限。
- 推荐 Ubuntu 22.04 及以上（Lab 9 需要 cgroup v2，较新的发行版默认启用）。
- 必需：`iproute2`、`iputils-ping`、`tcpdump`、`traceroute`（Ubuntu 默认不带）、`iperf3`、`iptables`、Python 3（3.10 及以上）与 [`uv`](https://docs.astral.sh/uv/)。一次装齐：`sudo apt install -y iproute2 iputils-ping tcpdump traceroute iperf3 iptables`。
- 部分讲次另需：第 03 讲动手模块用 FRRouting（`sudo apt install -y frr`，Ubuntu 22.04 为 8.1、24.04 为 8.4）；第 05 讲课堂观察用 `ethtool`（`sudo apt install -y ethtool`），需内核支持 HTB、fq 和 VXLAN；Lab 1 任务 4 需要内核带 `sch_netem`（部分精简内核没有，检查方法见 Lab 1 指导书第二节）。
- macOS / Windows 用户请使用 Linux 虚拟机或云主机；network namespace 是 Linux 内核特性。
- 所有实验命令默认从**仓库根目录**执行。

写作与脚本规范见仓库根目录的 [`AGENTS.md`](../AGENTS.md)。
