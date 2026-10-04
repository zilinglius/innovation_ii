# Lima 备课与实验验证沙箱

教师与 AI 助手在 Apple Silicon Mac 上使用 **Lima + Ubuntu 24.04 虚拟机**设计讲义、开发实验和验证真实 Linux 网络行为。VM 有独立且可管理的 Ubuntu 内核；已有 [Docker 镜像](README.md#构建与使用)保留作基础验证用途。

学生自行准备 Ubuntu 主机或虚拟机。学生讲义与实验指导书以标准 Ubuntu 环境为基准，Lima 的启动、挂载与同步属于本机备课流程。

## 环境目标与预备条件

- macOS 13.5 及以上、Apple Silicon，已安装 Lima 2.0 及以上。本模板使用 `vz` 和 `virtiofs`。
- VM 默认分配 4 核、4 GB 内存、30 GB 磁盘；磁盘按实际写入占用宿主机空间。
- 首次安装需要下载 Ubuntu 云镜像、Ubuntu 软件包和固定版本 `uv`。
- 网络节点均在**同一 VM 内**创建，无须宿主机桥接网络或嵌套虚拟化。
- 宿主仓库仅只读挂载，VM 内 `/workspace` 是独立 Linux 工作副本。Mac `.venv`、Git 元数据、日志和抓包不复制。

## 目录与资源

| 文件 | 作用 |
| --- | --- |
| [lima.yaml](lima.yaml) | Ubuntu 24.04、VZ、CPU / 内存 / 磁盘配置 |
| [lima.sh](lima.sh) | 宿主机统一入口，管理 `innovation-ii` 实例 |
| [provision.sh](provision.sh) | VM 内安装工具、匹配的内核模块、uv 与自检脚本 |
| [check.sh](check.sh) | 基础网络、ECMP 路由安装与真实流量检查 |
| [kernel_check.sh](kernel_check.sh) | `fq` / RED / ETF、BBR / DCTCP 套接字选择、实际 CPU 限流检查 |

安装工具与 [Docker 环境](README.md#环境目标与预备条件)一致，另补充运行内核对应的 `linux-modules-extra`（软件仓库提供时）。安装程序加载 `sch_fq`、`tcp_bbr`、`tcp_dctcp`、`sch_red`、`sch_etf` 等模块并设置开机加载，保持 VM 默认 TCP 算法不变。

## 沙箱使用步骤

以下宿主机命令均从仓库根目录执行：

```bash
# 1. 创建或启动 VM，安装环境；已有 /workspace 开发修改不会自动覆盖
bash 2026/environment/lima.sh up

# 2. 检查基础网络与后续实验内核能力，临时网络和 CPU 单元自动清理
bash 2026/environment/lima.sh check

# 3. 进入 VM 的仓库根目录 /workspace
bash 2026/environment/lima.sh shell
```

进入后使用原讲义中的 Linux 命令，`sudo` 由 VM 提供：

```bash
# 1. 搭建并检查 Lab 1
sudo bash 2026/experiments/01/ns_topo.sh
sudo bash 2026/experiments/01/ns_topo.sh check

# 2. 完成后清理
sudo bash 2026/experiments/01/ns_topo.sh down

# 3. 检查 Lab 2 的独立 Linux Python 环境
uv sync --project 2026/experiments/02 --frozen --offline
```

Lab 2 学生骨架的 TODO 保持原样，初始离线测试的失败是预期教学状态；参考实现仅供教师验证，不能覆盖学生源码。

### 更新、导出与停机

修改宿主仓库后，先保存 VM 中需要保留的开发修改，再主动同步；`sync` 会覆盖同名源码，保留 Linux `.venv`，不删除额外文件。

```bash
# 1. 示例：导出 VM 中修改的脚本，目标路径按需调整
limactl copy innovation-ii:/workspace/2026/experiments/01/ns_topo.sh ./ns_topo.saved.sh

# 2. 同步宿主仓库的最新源码
bash 2026/environment/lima.sh sync

# 3. 更新 VM 内安装的自检脚本与工具，再检查
bash 2026/environment/lima.sh up
bash 2026/environment/lima.sh check

# 4. 停机，保留 VM 磁盘和开发修改；下次 up 即可继续
bash 2026/environment/lima.sh down
```

删除 VM 会删除其工作副本，必须先导出成果；需要彻底移除时在停机后执行 `limactl delete innovation-ii`。不要将 `delete` 当作日常实验的清理命令。

## 验证范围

- `course-check` 验证 namespace、veth、bridge、双向 ping、转发、ECMP 路由安装、netem / HTB、抓包、真实 TCP 流量、iptables，并探测 VXLAN。
- `course-kernel-check` 在临时 veth 上实际安装 `fq`、支持 ECN 的 RED 和软件 ETF；创建 TCP 套接字选择 CUBIC、BBR、DCTCP；通过临时 systemd 单元设置 `CPUQuota=50%`，运行忙循环并核对 `cpu.max` 与实际限流计数。
- 内核能力通过不等于实验效果已验证。ECMP 分流比例、完整 VXLAN overlay、DCTCP 的 ECN 标记与吞吐、BBR 行为、发送时间精度、CPU 控制器委派仍按各实验另行验证。Lab 3–9 的状态以 [实验总览](../experiments/README.md)为准。

### 本机实测记录

2026-10-04，使用 Lima 2.2.1 在 Apple Silicon Mac 上创建 `innovation-ii`（VZ，4 核、4 GB、30 GB），运行 Ubuntu 24.04、`6.8.0-142-generic` 内核，安装匹配的 extra 模块。

| 层次 | 实测结果 |
| --- | --- |
| 文件与工具 | 配置通过 `limactl validate`；全部环境脚本通过 `bash -n` 与 VM 内的 `shellcheck`；Python 3.12.3、uv 0.12.23 |
| 基础网络 | namespace、veth、bridge、往返 ping、转发、ECMP 路由安装、netem / HTB、fq、抓包、真实 TCP 传输、VXLAN 设备和 iptables 通过；可选能力提示 0 项 |
| 后续内核能力 | fq、RED / ECN、软件 ETF 安装通过；套接字可选择 CUBIC / BBR / DCTCP；cgroup v2 的 50% CPU 限额与实际限流通过 |
| Lab 1 | 原脚本的全部连通性检查通过，重复清理通过 |
| Lab 2 参考实现 | 明确加载 `reference/lsrd`，17 项离线测试通过；三路由器 Full 邻接、LSDB 一致、跨机架往返和双下一跳 ECMP 通过；未覆盖全部故障与收敛时间测量 |
| 持久性与清理 | 重启后模块、工作副本与 Linux `.venv` 保留；源仓库只读；自检 CPU 单元和 namespace 无残留；重复停机入口通过 |

所有测试均在备课 VM 内完成，结果对应上述内核和资源配置；学生环境仍需独立检查。临时 namespace、路由器进程与自检 CPU 单元结束后清理；学生 TODO 保持原样。

## 故障排查

| 现象 | 处理 |
| --- | --- |
| 初次启动下载失败 | 检查访问 Ubuntu 镜像站与 GitHub 的网络，重新执行 `up` |
| 缺少 `sch_fq` / `tcp_bbr` 等模块 | 核对 `uname -r` 与 `/lib/modules`；安装对应 `linux-modules-extra-$(uname -r)`。若仓库已不提供当前版本，安装 `linux-generic` 并重启 VM，再重新安装环境 |
| 已有 VM 未挂载当前仓库 | 本入口复用原实例配置；仓库搬家后用 `limactl edit innovation-ii` 更新只读挂载位置并重启 |
| 宿主改动未进入 /workspace | 按“更新、导出与停机”主动同步 |
| `uv` 使用 Mac 虚拟环境 | 从 `/workspace` 运行，删除误复制的 `.venv` 后重新 `uv sync` |
| 自检 namespace 因强制中断残留 | VM 内执行 `sudo course-check down` 与 `sudo course-kernel-check down` |
| VM 内存不足或测量波动 | 停止其他 VM / Docker 工作负载；用 `limactl edit innovation-ii` 调整资源并重启，测量仍需预热与重复 |

## 为什么本机验证沙箱暂不采用 mvm

2026-10-04 检查了 [tinylabscom/mvm](https://github.com/tinylabscom/mvm) 的源码与配套 `mvm-images` 内核配置。它支持 macOS 26+ Apple Silicon，能直接从 OCI 镜像启动具有独立 Linux 内核的 microVM，启动入口简洁。

但当前标准内核配置显式关闭 `NETDEVICES`、`VETH`、`BRIDGE`、`NET_SCHED` 和 `MODULES`；默认 workload 内核还关闭 `NAMESPACES` 与 `CGROUPS`。rootless 变体提供部分 namespace 与 cgroup v2，仍明确排除 `NET_NS`。因此现有 namespace、veth、bridge、`tc` 实验无法直接运行，也不能靠安装工具或 `modprobe` 补齐。[基础内核配置](https://github.com/tinylabscom/mvm-images/blob/b455ca71fe6d780b244da20ce09187ed47d0fb02/kernel/base.nix)、[workload 配置](https://github.com/tinylabscom/mvm-images/blob/b455ca71fe6d780b244da20ce09187ed47d0fb02/kernel/workload.nix)、[rootless 配置](https://github.com/tinylabscom/mvm-images/blob/b455ca71fe6d780b244da20ce09187ed47d0fb02/kernel/rootless.nix)。

此外，标准 workload 启动路径清空 capability bounding set 并设置 `NoNewPrivs`，现有依赖 VM 内 root 网络管理权限的实验脚本也无法直接使用。[启动代码](https://github.com/tinylabscom/mvm/blob/67f620f9f7476687169befe26508401eaefdd7e7/crates/mvm-agentd/src/entrypoint.rs#L865)、[权限处理](https://github.com/tinylabscom/mvm/blob/67f620f9f7476687169befe26508401eaefdd7e7/crates/mvm-agentd/src/guest_mount.rs#L929)。

这是源码与文档评估，未安装或实际启动 mvm。根据这些限制推断，用它验证本课程实验需要改内核配置、重建镜像并调整运行权限，维护成本超过使用完整 Ubuntu VM；本机备课验证沙箱采用 Lima。

环境基础资料：[Lima VZ](https://lima-vm.io/docs/config/vmtype/vz/)、[共享目录](https://lima-vm.io/docs/config/mount/)、[Lima 使用说明](https://lima-vm.io/docs/usage/)。
