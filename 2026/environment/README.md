# 备课与实验验证沙箱

本目录供教师与 AI 助手设计讲义、开发实验及进行 Linux 实机验证。学生自行准备 Ubuntu 环境，学生材料以标准 Ubuntu 工具和命令为基准；本目录中的 Lima / Docker 入口属于备课流程。

当前本机沙箱使用 [Lima + Ubuntu 24.04](lima.md)，提供完整、可管理的 Ubuntu 内核，用于验证拥塞控制与 CPU 限额等实验能力。快速入口（从仓库根目录执行）：

```bash
# 1. 创建或启动备课验证 VM，安装环境
bash 2026/environment/lima.sh up

# 2. 实测基础网络与后续内核能力
bash 2026/environment/lima.sh check

# 3. 进入 VM 的独立 Linux 工作副本
bash 2026/environment/lima.sh shell
```

本页保留已有 Docker 镜像的构建与使用说明。Docker Desktop 内核缺少 `fq`、BBR / DCTCP 等能力时，使用上述 Lima 环境；Ubuntu 容器镜像本身不能替换 Docker VM 内核。

## Docker 基础验证沙箱

以 `ubuntu:24.04` 为基础，为备课与基础实验验证提供 Linux 工具环境。所有主机、交换机与路由器的 network namespace 都在**同一个容器**内创建，沿用现有实验脚本。

Docker Desktop 在 macOS / Windows 上通过 Linux 虚拟机提供内核。容器内运行的是真实 Linux 网络栈与进程；所有节点共享虚拟机 CPU，测量吞吐与延迟时仍须考虑资源争用。

## 环境目标与预备条件

- 已安装并启动 Docker Desktop，或 Linux 上的 Docker Engine。
- 为 Docker 虚拟机分配至少 4 核、4 GB 内存。
- 构建时需要访问 Ubuntu 软件仓库与 `ghcr.io`。已有 `ubuntu:24.04` 镜像可直接复用。
- 网络实验容器使用 `--privileged`，以支持 `ip netns` 的挂载操作、网络管理和流量控制；容器内默认使用 root，讲义中的 `sudo` 命令也可直接执行。

| 工具 | 用途 |
| --- | --- |
| `iproute2`（`ip`、`bridge`、`tc`、`ss`） | namespace、veth、bridge、路由与流量控制 |
| `ping`、`traceroute`、`tcpdump`、`iperf3`、`ethtool` | 连通性、路径、抓包与性能测量 |
| `iptables`、`nftables`、`sysctl` | 故障注入、防火墙与内核参数 |
| FRRouting（`zebra`、`ospfd`、`vtysh`） | 第 03 讲的动态路由演示 |
| Python 3.12、`uv` | 按各实验的 `pyproject.toml` 与 `uv.lock` 管理环境 |
| 系统 Python 的 `numpy`、`pyyaml` | 简短交互练习；正式实验仍使用各自的 `uv` 环境 |
| `shellcheck`、`git`、`rsync`、编辑器 | 脚本检查与实验资料维护 |

## 目录与资源

| 文件 | 作用 |
| --- | --- |
| [Dockerfile](Dockerfile) | 安装系统工具与固定版本的 `uv` |
| [entrypoint.sh](entrypoint.sh) | 首次启动时从只读源仓库建立 Linux 工作副本 |
| [check.sh](check.sh) | 镜像内的 `course-check`，检查实际内核功能并自动清理 |
| [.dockerignore](.dockerignore) | 只将环境构建文件发送给 Docker |

镜像本身只包含工具与环境脚本。启动时，将本机仓库只读挂到 `/course-src`；入口脚本会首次复制到 `/workspace`，排除 `.venv`、`.git`、缓存、日志和抓包。容器里的开发修改与 Linux Python 环境留在 `/workspace`，重启不会被源仓库覆盖。

## 构建与使用

以下宿主机命令均从仓库根目录执行。

```bash
# 1. 基于已有 Ubuntu 24.04 构建课程工具镜像
docker build --pull=false -t innovation-ii-lab:2026 2026/environment

# 2. 验证镜像中的 Linux 网络功能；自检容器退出后自动删除
docker run --rm --init --privileged innovation-ii-lab:2026 course-check

# 3. 创建可保留开发修改的交互容器，源仓库以只读方式挂载
docker run --init -it --privileged \
  --name innovation-ii-lab \
  --mount "type=bind,source=$PWD,target=/course-src,readonly" \
  innovation-ii-lab:2026
```

进入容器后，当前目录 `/workspace` 就是仓库根目录，继续执行原实验命令：

```bash
# 1. 初始化 Lab 2 的独立 Linux Python 环境（该实验只依赖标准库，可离线）
uv sync --project 2026/experiments/02 --frozen --offline

# 2. 搭建 Lab 1，验证所有预设的连通性
sudo bash 2026/experiments/01/ns_topo.sh
sudo bash 2026/experiments/01/ns_topo.sh check

# 3. 完成后幂等清理
sudo bash 2026/experiments/01/ns_topo.sh down
```

在宿主机另开终端，可进入正在运行的容器；退出容器的主终端后，可再次启动原容器：

```bash
# 1. 进入正在运行的同一容器
docker exec -it innovation-ii-lab bash

# 2. 主终端退出后，重新启动原容器并进入
docker start -ai innovation-ii-lab
```

若本机仓库更新，需要在容器内主动同步资料。此操作会覆盖容器中同名的源文件，**先将需要保留的开发修改导出**，再执行：

```bash
# 1. 同步源仓库，同时保留容器内的 Linux 虚拟环境
rsync -a \
  --exclude='.git/' --exclude='.venv/' --exclude='__pycache__/' \
  --exclude='.DS_Store' --exclude='.env' --exclude='*.pcap' --exclude='*.log' \
  /course-src/ /workspace/
```

## 验证范围

`sudo course-check` 会创建三个临时 namespace，验证以下功能，并在成功或失败退出时自动清理：

1. namespace、veth、bridge 和双向 `ping`。
2. IP 转发、`proto 200` 的 ECMP 路由安装、五元组哈希开关。
3. `tc netem`、`htb` 的安装；另外探测可选的 `fq` 队列调度器。
4. `tcpdump` 抓取真实 ICMP 往返、`iperf3` 传输真实 TCP 流量。
5. namespace 内的 `iptables` 规则操作；另外探测可选的 VXLAN 设备创建。

自检还会显示 cgroup v2 与当前 TCP 拥塞控制算法。缺少 `fq` 或 VXLAN 时会明确提示；这些可选能力的缺失不影响基础检查的退出状态。**ECMP 分流比例、完整 VXLAN overlay、FRR 路由收敛、DCTCP / BBR 行为、Lab 9 的 CPU 控制器委派与限额需要按各实验另行验证**，不因基础环境自检通过而自动视为这些实验完成。

只检查工具安装时可执行 `course-check tools`，不需要特权容器。发生异常中断后，可用 `sudo course-check down` 清理自检 namespace；它只处理 `course-check-a`、`course-check-b`、`course-check-s`。

Lab 2 的学生骨架保留 TODO。其初始离线测试出现 5 项通过、9 项失败、3 项错误是预期教学状态。`2026/experiments/02/run.sh` 默认启动学生版；教师验证参考实现时须另行选择 `reference/lsrd`，不能把参考文件覆盖到学生目录。

### 本次构建与实测记录

2026-10-04，在 Apple Silicon Mac 的 Docker Desktop 4.93.0 中构建 `innovation-ii-lab:2026`，平台为 `linux/arm64`，内核为 `7.0.14-linuxkit`。以下记录属于本机备课沙箱的验证结果；学生环境按各实验指导书独立检查。

| 层次 | 实测结果 |
| --- | --- |
| 文件与工具 | 构建成功；环境脚本通过 `bash -n` 与 `shellcheck`；Python 3.12.3、uv 0.12.23、FRR 8.4.4、iperf3 3.16 |
| 基础内核功能 | namespace、veth、bridge、双向 ping、IP 转发、ECMP 安装、netem、htb、抓包、真实 TCP 传输、VXLAN 设备和 iptables 均通过；退出后无自检 namespace 残留，重复 `down` 通过 |
| Lab 1 | 按现有脚本搭建，所有连通性检查通过；重复清理通过 |
| Lab 2 参考实现 | 单独加载 `reference/lsrd`，17 项离线测试通过；在三角形拓扑上启用 ECMP、Ack 和链路监测，Full 邻接、LSDB 一致、跨机架往返与双下一跳路由通过。此次未覆盖全部故障注入与收敛时间测量 |
| 后续实验限制 | `fq` 安装报 `Specified qdisc kind is unknown`；当前可用 TCP 拥塞算法显示 `reno cubic`。cgroup v2 存在且列出 `cpu`，但 CPU 控制器委派与限额未验证 |

以上测试使用只读源仓库和容器内的独立 Linux 工作副本；未修改学生 TODO。Lab 3–9 的状态仍以 [实验总览](../experiments/README.md) 为准。

## 故障排查

| 现象 | 检查方法 |
| --- | --- |
| 无法连接 Docker 服务 | 确认 Docker Desktop 已启动，宿主机 `docker version` 能显示 Server |
| `ip netns add` 报 `Operation not permitted` | 按上面的 `--privileged` 启动；受组织隔离策略限制时，用独立 Linux 虚拟机 |
| `tc` 或 VXLAN 报不支持 | 容器共享 Docker 虚拟机的内核；安装 Ubuntu 工具包不能补齐 VM 内核功能，可升级 Docker 或换完整 Linux VM |
| Python 无法执行、虚拟环境路径错误 | 使用 `/workspace` 内新建的 Linux `.venv`；不要直接运行 `/course-src` 中的 Mac `.venv` |
| 源仓库修改没有反映到容器 | `/workspace` 是独立副本，按上面的同步步骤更新或重新创建容器 |
| FRR 的 `systemctl` 报错 | 容器没有运行 systemd；沿用讲义中的 `/usr/lib/frr/frrinit.sh` 和 pathspace 启动方式 |
| Lab 9 找不到可用 CPU 控制器 | cgroup v2 存在不等于已委派控制器；按 Lab 9 单独准备可写的 cgroup 层级 |

## 导出成果与清理

在宿主机执行以下命令；删除容器会删除其工作副本，先导出要保留的成果：

```bash
# 1. 示例：导出修改过的实验脚本，目标路径按需调整
docker cp innovation-ii-lab:/workspace/2026/experiments/01/ns_topo.sh ./ns_topo.saved.sh

# 2. 停止并删除课程容器（镜像仍保留，下次可重新创建）
docker stop innovation-ii-lab
docker rm innovation-ii-lab
```

环境基础资料：[Docker 权限](https://docs.docker.com/engine/containers/run/#runtime-privilege-and-linux-capabilities)、[Docker Desktop 的 Linux VM](https://docs.docker.com/desktop/setup/install/mac-permission-requirements/#containers-running-as-root-within-the-linux-vm)、[`uv` 的 Docker 集成](https://docs.astral.sh/uv/guides/integration/docker/)。实验内容与进度见 [实验总览](../experiments/README.md)。
