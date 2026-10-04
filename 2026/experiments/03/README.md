# Lab 3 课堂观察：看见路径、容量与虚拟网络

本目录提供[第 05 讲](../../docs/datacenter_network.md)穿插使用的课堂观察脚本。它把 Lab 2 的 `lsrd` 放到 2 spine × 4 leaf × 8 host 拓扑上，让学生先预测、再观察、最后解释。**当前交付的是课堂演示与拓扑原型；完整 Lab 3 的分层作业、验收与后续接口仍待完善。**

## 实验目标

1. 从真实抓包区分同机架交换和跨机架路由。
2. 区分 ECMP 的下一跳集合、实际连接分布和接收端吞吐。
3. 保持数据量不变，分别改变接收端分布或上联容量，观察完成时间变化。
4. 对照租户侧与 underlay 抓包识别 VXLAN；用正反例理解 VNI 隔离与 MTU 边界。

## 预备知识与工具

学生自行准备 Ubuntu Linux，具有 `sudo` 权限；至少 4 核、4 GB。需要 `iproute2`、`ping`、`traceroute`、`tcpdump`、`iperf3`、`ethtool`、Python 3.12 和 `uv`；内核支持 namespace、veth、bridge、HTB、fq 与 VXLAN。

学生跟做时，先完成 Lab 2 的路由实现与 `--ecmp` 进阶任务。默认 `up` 加载学生的 `02/lsrd`，原始骨架的 TODO 会阻止路由就绪。教师演示和备课验证可显式执行 `up --reference`，单独加载 `02/reference/lsrd`；它不会覆盖学生文件。教师也可先搭好网络，让学生只做观察与预测。

## 目录与资源

| 资源 | 说明 |
| --- | --- |
| [classroom.sh](classroom.sh) | 拓扑、路由器启动、课堂观察和幂等清理 |
| [transfer.py](transfer.py) | 定量 TCP 传输；接收端读到 EOF 后回执，确认每流 30 MB 全部到达 |
| `pyproject.toml` / `uv.lock` | 本实验的独立 Python 环境，只用标准库 |
| [Lab 2](../02/README.md) | 路由守护进程、Python 锁文件及参考实现 |
| `/run/course05/` | 本脚本的资源登记、PID 与控制套接字 |
| `/tmp/course05-results/` | iperf3 JSON、SYN 路径证据、抓包文本与路由日志；清理拓扑后仍保留 |

leaf 为 `r1`–`r4`，spine 为 `r5`、`r6`；机架 $i$ 使用 `10.0.i.0/24`，bridge `bri` 地址 `.1`，`hia` / `hib` 为 `.11` / `.12`，host 接口为 `eth0`。leaf 侧 host 端口名如 `r1-h1a`。上联端口名如 `r1-r5` 与 `r5-r1`。

| leaf | 到 r5：leaf / spine 地址 | 到 r6：leaf / spine 地址 |
| --- | --- | --- |
| r1 | `10.1.0.1/30` / `10.1.0.2/30` | `10.1.1.1/30` / `10.1.1.2/30` |
| r2 | `10.1.2.1/30` / `10.1.2.2/30` | `10.1.3.1/30` / `10.1.3.2/30` |
| r3 | `10.1.4.1/30` / `10.1.4.2/30` | `10.1.5.1/30` / `10.1.5.2/30` |
| r4 | `10.1.6.1/30` / `10.1.6.2/30` | `10.1.7.1/30` / `10.1.7.2/30` |

host 接入口的两个方向限 100 Mbit/s；leaf–spine 链路的两个方向可切换为 100 或 50 Mbit/s。只修改实验 namespace 的 sysctl、offload 与队列，不改变 Ubuntu 主机的外部网卡。

## 实验步骤与预期输出

以下命令全部从仓库根目录执行；先结束并清理 Lab 1/2。遇到其他实验占用同名 namespace，本脚本会拒绝搭建。

```bash
# 1. 按锁文件准备路由器与课堂传输的独立 Python 环境
uv sync --project 2026/experiments/02 --frozen
uv sync --project 2026/experiments/03 --frozen

# 2. 使用自己完成的 lsrd 搭建课堂拓扑
sudo bash 2026/experiments/03/classroom.sh up

# 3. 检查每条上联、机架接入和跨机架的往返连通性
sudo bash 2026/experiments/03/classroom.sh check
```

教师明确选择参考实现时，将第 2 步替换为：

```bash
# 1. 教师演示：单独加载参考实现，学生 TODO 保持原样
sudo bash 2026/experiments/03/classroom.sh up --reference
```

就绪时 6 台路由器均形成 Full 邻接；`r1` 到 `10.0.3.0/24` 的内核路由包含两个下一跳：

```text
10.0.3.0/24 proto 200 metric 20
    nexthop via 10.1.0.2 dev r1-r5 weight 1
    nexthop via 10.1.1.2 dev r1-r6 weight 1
```

按讲义所在位置运行对应观察：

```bash
# 1. 流量矩阵：两流各 30 MB，分散接收与集中接收
sudo bash 2026/experiments/03/classroom.sh matrix

# 2. 拓扑与路径：同机架、跨机架抓包，再追踪跨机架跳数
sudo bash 2026/experiments/03/classroom.sh locality

# 3. ECMP：每条上联 50 Mbit/s，比较 1 条与 8 条数据连接
sudo bash 2026/experiments/03/classroom.sh ecmp

# 4. 收敛比：相同两流、相同数据量，上联从 100 降为 50 Mbit/s
sudo bash 2026/experiments/03/classroom.sh capacity

# 5. VXLAN：同 VNI 往返、内外层抓包、相同 IP 的隔离反例
sudo bash 2026/experiments/03/classroom.sh vxlan

# 6. MTU：1422 B 的 ICMP 数据可发送，1423 B 超过租户接口边界
sudo bash 2026/experiments/03/classroom.sh mtu
```

- `locality` 应看到同机架请求从 `r1-h1b` 发出，跨机架请求从 `r1-r5` 或 `r1-r6` 发出；跨机架 traceroute 依次经过源 leaf、一个 spine、目的 leaf、目的 host。
- `ecmp` 用 iperf3 JSON 中的数据连接端口筛选 SYN 抓包，排除控制连接，输出每条连接的路径及各组收到的应用字节。观察期间路由与哈希策略保持稳定；一次 8 条流不保证 4:4，若未用到两条路径，应重跑并记录这一结果。
- `matrix` 与 `capacity` 用临时策略路由固定 `h1a` 经 `r5`、`h1b` 经 `r6`，排除 ECMP 碰撞这一变量；抓包核对实际业务路径，结束后删除临时策略。`ecmp` 观察不固定路径。两流各传十进制 30 MB，合计 60 MB；`transfer.py` 在接收端确认全部数据到达后才结束客户端。共同计时窗口用单调时钟，从并发启动客户端到两客户端结束，包含建连与结束开销。
- `vxlan` 为 A / B 分别建 VNI 100 / 200，租户端点为 `t1a` / `t3a`、`t1b` / `t3b`，两租户都用 `192.168.10.11` 与 `.12`。关闭 A 的远端接口后，A 应无法 ping `.12`，B 仍能 ping 相同地址；脚本随后恢复 A。
- `mtu` 的第二次 ping 预期报 `message too long, mtu=1450`。报错发生在源租户接口，不能把它记录成远端丢包。

每组观察都先写预测，再记录路径和测量口径；参考数据与验证范围见[第五讲](../../docs/datacenter_network.md)。链路速率是教学限速，应用有效速率受协议开销、启动和共享 CPU 影响。

2026-10-04 已在 Ubuntu 24.04、Linux 6.8 ARM64、4 核／4 GB 的备课沙箱中显式使用参考路由实现验证全部六组观察：各上联往返、8 台 host 接入与跨机架往返，SYN 数据路径，60 MB 接收确认，两个 VNI 的正反例，以及 MTU 边界。Bash 语法与 ShellCheck 通过，重复搭建和重复清理通过；学生自行完成的路由实现仍需按同一检查入口验证。

```bash
# 1. 完成所有观察后，统一清理拓扑、路由器、抓包和业务进程
sudo bash 2026/experiments/03/classroom.sh down

# 2. 重复清理应成功；检查没有课堂 namespace 残留
sudo bash 2026/experiments/03/classroom.sh down
ip netns list
```

## 故障排查

| 现象 | 检查 |
| --- | --- |
| 提示 `r1` 等名称已被占用 | 先按 Lab 1/2 指导书结束原任务并清理；本脚本不会自动删除其他实验资源 |
| 路由未就绪 | 查看 `/tmp/course05-results/r*.log`；检查是否仍是学生 TODO、ECMP 是否完成、模块是否从正确目录加载 |
| `fq` 或 VXLAN 不支持 | 安装当前 Ubuntu 内核匹配的模块；不能只安装用户态工具 |
| 单流与多流吞吐接近 | 查实际路径分布、host 接入口限速、CPU 负载和重传；先解释证据，再决定是否重跑 |
| 两流完成时间与理论下界不同 | 区分应用字节与链路字节；共同窗口还包含建连、队列和结束开销 |
| 强制中断后有业务进程 | 使用 `down` 清理，再 `up` 重建；结果文件仍保留 |

## 思考题

1. 总数据量相同，为什么接收端从两台变一台之后会变慢？
2. 两条上联都存在，为什么一条连接仍只使用一条？流数相近是否代表字节数相近？
3. VNI 不同的两个租户能够使用相同 IP，是否也各自拥有独立的物理带宽？

## 提交要求与后续衔接

课堂提交一张“预测、证据、解释”记录表，至少包含一个反直觉现象。完整 Lab 3 的作业要求仍以[实验设计总览](../README.md#lab-3搭一个迷你数据中心)后续交付为准；本脚本的存在不代表 Lab 3 已完成。后续拓扑接口固化时继续复用 Lab 2 的路由守护进程。
