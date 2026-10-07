# Lab 3　搭一个迷你数据中心

> 对应第 05 讲　｜　建议用时 1 周（基础约 3 小时；进阶任务 5 约 1.5 小时、任务 6 约 2 小时；挑战任务 7、8 各约 1.5 小时）　｜　产出：2 spine × 4 leaf × 8 host 的数据中心实验床——Lab 4 至 Lab 9 都在它上面跑

第 05 讲的课堂观察里，你已经在一张**给定的** leaf-spine 实验床上预测、观察、解释过六组现象。本实验把这张"老师给的实验床"变成"你自己搭的实验床"：把课堂脚本里的拓扑整理成你自己的 `topo.sh`，接入你在 Lab 2 写的路由守护进程，再把课堂上看到的现象亲手做出来、量出来——收敛比、哈希与上联、VXLAN 租户。这张实验床一旦稳定，后续实验都直接复用，**约定比跑通更重要**。

任务分三层：**基础**（任务 1–4）人人完成；**进阶**拉开区分度；**挑战**深入内核实现与测量口径。进阶任务 5 不依赖 overlay；进阶任务 6 与挑战任务 7、8 是同一条 VXLAN 选做链——任务 6 没做，7、8 就没有前提——时间紧可以整条跳过，这也是全课程预留的缓冲点，计分见第八节。

---

## 一、实验目标

1. 把课堂观察用的拓扑整理成自己维护的 `topo.sh`：节点名、接口名、地址、限速与课堂约定完全一致，支持 `up` / `check` / `rate` / `show` / `down`，重复搭建与清理可恢复到明确状态。
2. 接入路由守护进程（首选自己的 `lsrd --ecmp`，也可用参考实现），逐链路验证连通，确认每个 leaf 去往其他机架的路由都有两个下一跳。
3. 按同一方向计算收敛比，结合路径上的共享链路推导吞吐上界与完成时间下界；用 `tc` 计数把首部开销折算进帧级下界，再用测量检查。
4. 量化哈希对完成时间的影响：同路与分路的流传同样的数据量，比较完成时间与理论下界；并搞清"换端口能不能把流搬到另一条上联"。
5. （进阶）在 underlay 上自建双租户 VXLAN，验证隔离性；用测量说明"网络隔离不等于带宽保证"。
6. （挑战）用 `ip route get` 复算 VTEP 的选路，说明外层源端口何时决定出口、何时被路由缓存覆盖；建立"封装开销"的测量口径。

---

## 二、预备知识与工具

**先读**：

- [第 05 讲](../../docs/datacenter_network.md)全文：2.2 节拓扑与地址约定、2.5 节同机架/跨机架抓包、模块三（ECMP）、模块四（收敛比）、模块五（VXLAN）以及 6.6 节"从课堂实践走向 Lab 3"。
- [Lab 2 指导书](../02/README.md)任务 8：`topo.sh` 以 `--ecmp` 启动路由守护进程（并列首跳装成内核 multipath 路由），就绪断言要求跨机架路由有两个下一跳。自己的 `lsrd` 还没实现 ECMP 时，按 3.1 节改用参考实现完成本实验。

**环境**：与课堂观察相同——Linux（`sudo`）、`iproute2`、`iputils-ping`、`traceroute`、`tcpdump`、`ethtool`、`iperf3`、Python 3.12 与 `uv`；内核支持 namespace、veth、bridge、HTB、fq 与 VXLAN。先检查 VXLAN 模块：

```bash
# 1. 内核应能创建 VXLAN 设备；报错则 sudo modprobe vxlan，或安装 linux-modules-extra-$(uname -r)
sudo ip link add vxprobe0 type vxlan id 1 dstport 4789 && sudo ip link del vxprobe0
```

**准备 Python 环境**（路由器复用 Lab 2 的环境，传输工具用本实验的环境）：

```bash
# 1. 按各自锁文件初始化两个实验的独立环境
uv sync --project 2026/experiments/02 --frozen
uv sync --project 2026/experiments/03 --frozen
```

**约定**：以下所有命令**从仓库根目录执行**，需要 root 的步骤显式写了 `sudo`。与 Lab 2 不同，学生拓扑的验收靠 `topo.sh check`、抓包对账和测量记录。任务连续复用同一张拓扑；执行 `down` 后需要重新 `up` 并重建 overlay。`down` 保留结果目录；重启主机可能清除 `/tmp`，需要长期保存时另行复制。

**留意抓包占用的空间**：测量助手保存完整报文，每传 30 MB 约留下 32 MB pcap，做完全部任务约 2 GB。有的系统把 `/tmp` 挂成内存文件系统 tmpfs（本文验证用的 Ubuntu 26.04 虚拟机只有 1.4 GB），写满后测量会失败。开始前先 `df -h /tmp`；空间紧张时，核对完一轮就删除该轮目录里的 `.pcap`，保留 `summary.json` 与 `run.json`。

---

## 三、目录与资源

### 3.1 文件

| 文件 | 说明 |
| :--- | :--- |
| `topo.sh` | **实验床，你要补全**。TODO 1（机架接入）、TODO 2（leaf–spine 上联）、TODO 3（check 自检）。命令面：`up [--reference]` / `check` / `rate 50\|100` / `show` / `down`。幂等。 |
| `classroom.sh` | 第 05 讲的课堂观察脚本，保持原样。它与你自己的 `topo.sh` 是两套独立资源（各自的登记目录），不能混用，也不要同时搭建。 |
| `measure.py` | 重启本轮服务端、等待就绪、并发传输、共同计时、按五元组／VNI 分类抓包；不改变路由与限速。 |
| `overlay_down.sh` | 只清理任务 6 登记的租户资源；`topo.sh down` 自动调用。 |
| `transfer.py` | 定量 TCP 传输：客户端绑定源端口，服务端确认收到全部应用字节后回执。本实验的测量工具。 |
| `pyproject.toml`、`.python-version`、`uv.lock` | 本实验的 uv 环境（只用标准库）。 |
| `MAINTENANCE.md`、`tests/` | 教师维护用：验证记录、测量分类器的离线测试。学生不需要运行。 |
| `/run/lab03/` | `topo.sh` 的资源登记、pid 与控制套接字 |
| `/tmp/lab03-results/` | 路由日志与各任务的测量输出；`down` 之后仍保留 |

**路由实现**：本实验考核拓扑、多路径与测量，不重复考核 Lab 2。首选接入自己的 `lsrd --ecmp`；还没完成 Lab 2 任务 8（ECMP，属进阶）的同学，可以用 `up --reference` 加载 [Lab 2 的参考实现](../02/README.md)完成本实验全部任务，报告注明所用实现。用自己的 `lsrd` 通过 `up` 与 `check` 另记附加分（第八节）。参考实现也适合自查：把"拓扑问题"和"路由问题"分开定位。

### 3.2 实验床与地址约定

```
        ┌─ h1a（10.0.1.11）      每个 leaf 的机架网桥上接两台 host
  机架 1│
        └─ br1 ─ r1（leaf）─┬── 10.1.0.0/30 ── r5（spine）
                             └── 10.1.1.0/30 ── r6（spine）
  机架 2、3、4 与机架 1 同构：r2、r3、r4 各有两条上联，全网共 8 条 leaf–spine 链路。
```

*图 1：源图只画出机架 1——两台 host 接在 r1 的网桥 br1 上，r1 用两条 /30 上联分别连到 spine r5、r6；机架 2–4 同构，全网共八条 leaf–spine 点到点链路。机架内的 bridge 与 leaf 在同一 namespace，主机各自独立。上联双向可切换 100／50 Mbit/s，主机接入双向固定 100 Mbit/s。阅读版画出全部四个机架，用实线、虚线区分连接 r5 与 r6 的上联，交叉处不相连。*

| 项目 | 约定 | 与已有实验的关系 |
| :--- | :--- | :--- |
| leaf / spine | leaf 为 `r1`–`r4`，spine 为 `r5`、`r6`，均为 network namespace | 延续 Lab 1、Lab 2 的路由器命名 |
| 机架网络 | 第 $i$ 个机架用 `10.0.i.0/24`；网关 `br{i}` = `.1`；host `h{i}a`/`h{i}b` = `.11`/`.12`，接口 `eth0` | 延续 Lab 1、Lab 2 的机架地址与主机名 |
| 机架内网桥 | `br1`–`br4`，网关地址放在 bridge 上 | `lsrd` 用 `--passive` 通告它，不在网桥上建邻 |
| 上联 | 每个 leaf 两条，`10.1.0.0/30`–`10.1.7.0/30`；leaf `.1`、spine `.2`，第 $k$ 条链路 $k = 2(\text{leaf}-1) + (\text{spine}-5)$ | 与课堂脚本完全一致 |

| leaf | 到 r5 | 到 r6 |
| :--- | :--- | :--- |
| r1 | `10.1.0.1/30` / `10.1.0.2/30` | `10.1.1.1/30` / `10.1.1.2/30` |
| r2 | `10.1.2.1/30` / `10.1.2.2/30` | `10.1.3.1/30` / `10.1.3.2/30` |
| r3 | `10.1.4.1/30` / `10.1.4.2/30` | `10.1.5.1/30` / `10.1.5.2/30` |
| r4 | `10.1.6.1/30` / `10.1.6.2/30` | `10.1.7.1/30` / `10.1.7.2/30` |

限速：host 接入口两个方向固定 100 Mbit/s；leaf–spine 链路两个方向可切换 100 / 50 Mbit/s（`topo.sh rate`）。**这张表就是 Lab 4–9 依赖的约定**：节点名、接口名、地址与档位都在这里固化。

### 3.3 测量口径

与课堂一致的四个习惯，报告里要一直带着：

- **应用字节与链路字节分开**：`transfer.py` 报告的是应用有效字节；链路上还有 TCP/IP 与封装开销。限速器按以太网帧长计费，两者之比可以由帧长算出（任务 3）。
- **MB 与 Mbit/s 分清**：本实验的"30 MB"是十进制 30 000 000 字节；速率换算用 $8 \times \text{字节} / \text{秒}$。
- **共同窗口**：从启动第一条客户端进程前，到观察到最后一条客户端成功退出；包含进程启动、建连、慢启动、完整回执与退出开销。助手每 5 ms 检查一次退出状态；每流应用速率另用客户端内部计时，二者不可混用。
- **SYN 抓包定路径**：SYN 说明建连时的上联；只有路由、哈希与连接路径稳定时才可代表后续传输。测量助手同时统计目标连接的数据包出口，遇到多个出口不能强行归成一条路径。

本文保留的课堂实测样例来自 2026-10-04 的 Ubuntu 24.04、Linux `6.8.0-142-generic`（ARM64、4 核 4 GB）备课沙箱，任务 3、5、6、8 的修订样例来自 2026-10-05 的同一沙箱；任务 3 的 `tc` 计数观察、附加诊断与任务 7 的样例来自 2026-10-07 的 Ubuntu 26.04、Linux `7.0.0-38-generic`（x86_64、2 核 2.8 GB）虚拟机。验证范围见末尾“维护与验证”。理论下界与预期输出单独标注，不要求复现固定端口、路径比例或用时。

---

## 四、课堂观察回顾（第 05 讲已完成）

课堂上用 `classroom.sh` 完成了六组观察。这里留一张速查表；现象与数据的带读在讲义对应小节，本实验的任务是**在你自己的实验床上重建并扩展它们**。

| 观察 | 命令（课堂脚本） | 现象一句话 | 讲义 |
| :--- | :--- | :--- | :--- |
| locality | `classroom.sh locality` | 同机架帧从网桥端口出，跨机架帧走上联；traceroute 通常四行，含目的 host | 2.5 节 |
| ecmp | `classroom.sh ecmp` | 自然 ECMP 下单流受一条 50 Mbit/s 上联限制；样例八流接收吞吐接近翻倍，不保证流数或吞吐均分 | 3.5 节 |
| matrix | `classroom.sh matrix` | 两流共 60 MB、固定分路；集中接收时共享 100 Mbit/s 接入口，比较共同窗口 | 6.3 节 |
| capacity | `classroom.sh capacity` | 两流共 60 MB、固定分路；全部 fabric 链路双向从 100 降至 50 Mbit/s，样例共同窗口约翻倍 | 6.4 节 |
| vxlan | `classroom.sh vxlan` | 同 VNI 往返、关闭 A 接收端后 B 不替 A 响应；同包内外层关联支持封装解释 | 5.7 节 |
| mtu | `classroom.sh mtu` | ICMP 数据 1422 B 对应内层 IPv4 包 1450 B；数据增至 1423 B 时被源接口拒绝 | 5.8 节 |

> [!NOTE]
> `classroom.sh down` 只清理课堂脚本自己登记的资源。课堂的参考数据同样来自备课沙箱（见讲义"材料状态"），你在自己的实验床上测到的分布可能与它不同——先解释，再决定是否重跑。

---

## 五、实验步骤

### 基础任务

#### 任务 1　补全 topo.sh：机架与上联

`topo.sh` 已经把与教学无关的部分写好了：namespace 登记与幂等清理（`new_ns`/`down`）、HTB+fq 限速封装（`limit_port`/`set_rate`）、路由器 sysctl、`lsrd` 启动、offload 关闭、就绪断言（`ready`）。你补三块：**TODO 1** 机架接入网、**TODO 2** 上联、**任务 2 的 TODO 3** 自检。

先对照阅读 `classroom.sh` 的 `up()`，回答两个检查点（写进报告）：

1. 假如在 TODO 1 里用裸 `ip netns add h1a` 代替 `new_ns`：`down` 之后系统里会留下什么？再次 `up` 时会在哪一步、以什么提示失败？（提示：对照 `down()` 读取的清单与 `up()` 开头的重名检查。）
2. host 的 `eth0` 和 leaf 侧的接入端口**两边都**限速 100 Mbit/s，为什么一边不够？（提示：HTB 限的是 egress，想一想发与收两个方向。）

然后补全 TODO 1 与 TODO 2。地址表见 3.2 节；上联**不在** TODO 里限速——`up()` 结尾的 `set_rate` 会按当前档位统一配置，这是为了任务中能整体切换。

```bash
# 1. 每次改动后先做语法检查，不创建任何网络资源
bash -n 2026/experiments/03/topo.sh
```

```bash
# 2. 搭建实验床（先清理再搭建，幂等），用你自己的 lsrd --ecmp 起路由
sudo bash 2026/experiments/03/topo.sh up
```

```
[*] 全部 leaf–spine 链路两端 egress = 100 Mbit/s；host 接入口保持 100 Mbit/s。
[*] 6 台路由器全部 Full；r1 的跨机架路由有两个下一跳。实验床就绪。
[*] 下一步自检：sudo bash 2026/experiments/03/topo.sh check
```

就绪断言只看三件事：每台路由器的 Full 邻居数（leaf 2 个、spine 4 个）、LSDB 里 6 个节点、`r1` 去往 `10.0.3.0/24` 的路由有两个下一跳。断言不过，看 `/tmp/lab03-results/r*.log`；最常见的原因是 Lab 2 任务 8 的 ECMP 还没实现。

#### 任务 2　连通性自检（TODO 3）与逐链路验证

补全 `check()`：8 条上联两端互 ping、8 台 host ping 网关、注释指定的三项跨机架 ping；再逐一核对 4 个 leaf 去往其他 3 个机架前缀的 12 条路由都有两个下一跳。`ready` 只查了 `r1` 去往机架 3 的一条，后续实验会用到所有方向，单方向的 ECMP 缺陷要在这里暴露。全过后打印约定的两行 `[OK]` 和 `r1` 的路由。

提示：`ip -n r2 route show 10.0.4.0/24` 的输出中，每个下一跳单独占一行 `nexthop via …`；只有一个下一跳时没有这样的行。

```bash
# 3. 数据平面自检
sudo bash 2026/experiments/03/topo.sh check
```

```
[OK] 8 条上联往返、8 台 host 网关可达、跨机架往返。
[OK] 4 个 leaf 去往其他 3 个机架的 12 条路由均有两个下一跳。
10.0.3.0/24 proto 200 metric 20
	nexthop via 10.1.0.2 dev r1-r5 weight 1
	nexthop via 10.1.1.2 dev r1-r6 weight 1
```

```bash
# 4. 全网地址与路由总览
sudo bash 2026/experiments/03/topo.sh show
```

```
== r1 ==
br1              UP             10.0.1.1/24 fe80::44a1:ff:fe26:2d47/64
r1-h1a@if2       UP             fe80::cb3:b0ff:fe2d:4bfd/64
r1-h1b@if2       UP             fe80::70ab:2cff:fe98:520a/64
r1-r5@if2        UP             10.1.0.1/30 fe80::2451:fcff:fed6:28aa/64
r1-r6@if2        UP             10.1.1.1/30 fe80::e080:6ff:feba:3222/64
10.0.1.0/24 dev br1 proto kernel scope link src 10.0.1.1
10.0.2.0/24 proto 200 metric 20
	nexthop via 10.1.0.2 dev r1-r5 weight 1
	nexthop via 10.1.1.2 dev r1-r6 weight 1
...
10.1.0.0/30 dev r1-r5 proto kernel scope link src 10.1.0.1
10.1.2.0/30 via 10.1.0.2 dev r1-r5 proto 200 metric 20
10.1.3.0/30 via 10.1.1.2 dev r1-r6 proto 200 metric 20
...
```

（地址列的 IPv6 链路本地地址每次不同，略。）

**把两行放在一起看**：去往**机架前缀**（`10.0.2.0/24` 等）的路由有两个下一跳——这是 ECMP；去往**上联网段**（`10.1.2.0/30`、`10.1.3.0/30`）的路由只有一个下一跳，而且 r2–r5 的网段经 r5、r2–r6 的网段经 r6。为什么？提示：这两个网段分别挂在哪台 spine 身上，绕另一台 spine 的 cost 是多少。

```bash
# 5. 验证幂等：重复搭建与重复清理都不应报错；结束后重建，继续后面的任务
sudo bash 2026/experiments/03/topo.sh down
sudo bash 2026/experiments/03/topo.sh down
sudo bash 2026/experiments/03/topo.sh up
```

#### 任务 3　收敛比：先分散路径，再改变容量

**问题**：当四条流在发送侧与接收侧都不争用同一个上联出口时，上联从 100 降到 50 Mbit/s，通信完成时间怎样变化？

| 要素 | 本任务约定 |
| :--- | :--- |
| 数据量 | 四条流各 30 MB，共 120 MB，十进制应用字节 |
| 接收映射 | `h1a→h3a`、`h1b→h3b`、`h2a→h4a`、`h2b→h4b` |
| 固定路径 | `h1a/h2a` 经 r5，`h1b/h2b` 经 r6；接入均为 100 Mbit/s |
| 唯一改变 | 全部 leaf–spine 链路两端的 egress 从 100 改成 50 Mbit/s |
| 指标 | 每流完成时间、共同窗口、聚合应用有效速率 |

```mermaid
flowchart TB
    %% lab3:capacity
    subgraph A["A：上联 100 Mbit/s"]
        a1["h1a：30 MB"] --> a5["r1 → r5 → r3"] --> aa["h3a"]
        a2["h1b：30 MB"] --> a6["r1 → r6 → r3"] --> ab["h3b"]
        a3["h2a：30 MB"] --> a7["r2 → r5 → r4"] --> ac["h4a"]
        a4["h2b：30 MB"] --> a8["r2 → r6 → r4"] --> ad["h4b"]
    end
    subgraph B["B：同样映射，上联 50 Mbit/s"]
        b1["h1a：30 MB"] --> b5["r1 → r5 → r3"] --> ba["h3a"]
        b2["h1b：30 MB"] --> b6["r1 → r6 → r3"] --> bb["h3b"]
        b3["h2a：30 MB"] --> b7["r2 → r5 → r4"] --> bc["h4a"]
        b4["h2b：30 MB"] --> b8["r2 → r6 → r4"] --> bd["h4b"]
    end
```

*图 2：两场景采用相同的四行路径布局，自上而下为 F1–F4（分别由 h1a、h1b、h2a、h2b 发出），每条各传 30 MB。只有 leaf–spine 链路（阅读版中的蓝色 fabric 区域）从 100 改为 50 Mbit/s，外侧 host 接入口始终为 100 Mbit/s。路径展开中的同名路由器表示同一设备，不是新增节点；四条流分别经过源 leaf r1/r2 与目的 leaf r3/r4。省略 bridge、ACK 回程和未使用的候选路径；A/B 改变全部 fabric 链路两个方向。*

**先预测**：按同一方向（单向）分别算出一个 leaf 的下联与上联总容量，再算全网；全双工不能只在一侧翻倍。写出两档收敛比、每流完成时间下界与四流聚合速率上界，再往下读。

**测量助手怎样工作**：`--flow h1a:h3a:40001:5201` 表示源节点、目的节点、TCP 源端口、服务端端口，IP 从 3.2 节约定表读取。助手在**接收节点**启动一次性 `transfer.py server`，用 `ss -ltn` 确认监听后启动客户端；每轮自动重启服务端。它只等待本轮客户端，在收到完整回执并退出后结束共同窗口，再停止自己的抓包与服务端。失败或 Ctrl+C 会清理本轮进程，但**不会恢复你手工设置的路由和限速**。

`--leaf r1 --leaf r2` 在两个源 leaf 的四个上联出口上用 `tcpdump --immediate-mode -U -s 0 -Q out` 抓取完整 pcap。`-Q out` 限定发送方向，`-s 0` 保留完整报文，`--immediate-mode` 减少交付到抓包进程的缓冲等待。按目标五元组归组，不直接数所有 SYN，也不把多行文本当成多包。原始包、抓包丢失计数、服务端回执、每流 JSON 与 `summary.json` 都在本轮目录；抓包丢失或路径证据不完整时，不能给出确定性路径结论。

```bash
# 6. 设置本次结果根路径；以后重跑需另取名称，助手拒绝覆盖已有轮次
RUN=/tmp/lab03-results/run-$(date +%Y%m%d-%H%M%S)
PY=2026/experiments/03/.venv/bin/python
MEASURE=2026/experiments/03/measure.py
```

这三个变量只在当前终端有效，任务 5–8 继续使用；换终端或隔天继续时重新设置，`RUN` 取新名称。各命令的客户端源端口是固定的：失败后一分钟内重跑同一块，旧连接可能仍处于 TIME_WAIT 而报 `Address already in use`，等一分钟或把块内源端口整体加一个偏移。

下面整个块在子 shell 中执行。正常退出、命令失败与 Ctrl+C 都删除本任务的钉路并恢复 100 档；发生断电等无法捕获的中断时，按第六节清理。

```bash
# 7. 设置临时路径，完成两档对照；只等待测量工具，不等待其他终端的抓包
(
  set -Eeuo pipefail
  restore_t3() {
    for r in r1 r2; do
      for table in 105 106; do
        sudo ip -n "$r" rule del priority "$table" 2>/dev/null || true
        sudo ip -n "$r" route flush table "$table" 2>/dev/null || true
      done
    done
    sudo bash 2026/experiments/03/topo.sh rate 100
  }
  trap restore_t3 EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  for rack in 1 2; do
    k=$((2 * (rack - 1)))
    sudo ip -n r$rack route add table 105 default via 10.1.$k.2 dev r$rack-r5 onlink
    sudo ip -n r$rack route add table 106 default via 10.1.$((k + 1)).2 dev r$rack-r6 onlink
    sudo ip -n r$rack rule add priority 105 from 10.0.$rack.11/32 lookup 105
    sudo ip -n r$rack rule add priority 106 from 10.0.$rack.12/32 lookup 106
  done
  for rate in 100 50; do
    sudo bash 2026/experiments/03/topo.sh rate "$rate"
    base=$((40000 + (100 - rate) * 20))
    sudo "$PY" "$MEASURE" --leaf r1 --leaf r2 --output "$RUN/t3-r$rate" \
      --flow h1a:h3a:$((base+1)):5201 --flow h1b:h3b:$((base+3)):5203 \
      --flow h2a:h4a:$((base+5)):5205 --flow h2b:h4b:$((base+7)):5207
  done
)
```

```bash
# 8. 查配置与真实报文：路径策略已恢复，抓包仍记录刚才的实际路径
sudo ip -n r1 rule show
sudo ip -n r2 rule show
sudo tcpdump -n -r "$RUN/t3-r100/r1-r5.pcap" 'tcp[13] & 0x12 = 0x02'
cat "$RUN/t3-r100/summary.json"
```

**预期字段（结构示意，数值以本轮为准）**：`bytes` 应为 `120000000`；`wall_seconds` 是共同窗口；`shared_window_mbps = 8 × bytes / wall_seconds / 10^6`；各流 `received_bytes` 应为 `30000000`。`capture.syn_paths` 与 `capture.groups` 分别给建连出口与实际数据包统计。例如 `h1a` 应只在 `r1-r5` 留下目标连接，`h1b` 应在 `r1-r6`；也要核对 `r2` 的两条流。

<details>
<summary>核对答案：收敛比与理想下界（写下自己的预测后再展开）</summary>

两档收敛比为 **1:1 / 2:1**，每流下界 **2.4 / 4.8 s**，四流应用速率上界 **400 / 200 Mbit/s**。这是只按应用字节计算的理想值，忽略首部与启动成本。

</details>

**帧级下界：把首部开销算进去**。`limit_port` 用的 HTB 按每个包的以太网帧长（14 B 以太网头加 IP 包，不含 FCS）扣令牌，链路上计费的不是应用字节。本实验床 MTU 为 1500，连接默认带 12 B 的 TCP 时间戳选项：一个满长数据帧 1514 B，只载 1448 B 应用数据。因此 $D$ 字节应用数据在容量 $C$ 上至少需要 $T_{\mathrm{frame}}=\frac{8D}{C}\times\frac{1514}{1448}$，比理想值多约 4.6%：30 MB 在 100 / 50 Mbit/s 上分别为 **2.509 / 5.019 s**。下面用 `tc` 的计数检验这个帧长假设。

**短观察：链路计费的字节是应用字节的多少倍？** 预测：发送端上联的 HTB 类计数应约为应用字节的 $1514/1448\approx1.0456$ 倍，每包约 1514 B。`topo.sh rate` 会重建限速队列，计数随之归零，所以先切一次档，再只发一条流；读计数之前不要再切档。

```bash
# 9. 计数归零后只发一条 30 MB 流（自然 ECMP），再读 r1 两条上联的 HTB 类计数
sudo bash 2026/experiments/03/topo.sh rate 100
sudo "$PY" "$MEASURE" --output "$RUN/t3-tc" --flow h1a:h3a:40101:5201
sudo ip netns exec r1 tc -s class show dev r1-r5
sudo ip netns exec r1 tc -s class show dev r1-r6
```

**实测样例（2026-10-07，x86_64 虚拟机；省略结果路径行与令牌字段）**：

```output
[共同窗口] 30.00 MB，2.590 s，92.67 Mbit/s
[流] h1a → h3a，SYN 出口 ['r1-r5']
class htb 1:10 root leaf 10: prio 0 rate 100Mbit ceil 100Mbit burst 1600b cburst 1600b
 Sent 31367930 bytes 20725 pkt (dropped 0, overlimits 20715 requeues 0)
class htb 1:10 root leaf 10: prio 0 rate 100Mbit ceil 100Mbit burst 1600b cburst 1600b
 Sent 204 bytes 2 pkt (dropped 0, overlimits 0 requeues 0)
```

带读：

- 本轮连接从 `r1-r5` 发出（`[流]` 行；你的可能是 `r1-r6`，读对应的类）。`r1-r6` 只有 2 个包、204 B，是 `lsrd` 的控制报文。
- `r1-r5`：$31\,367\,930/20\,725\approx1513.5$ B/包；链路字节与应用字节之比 $31\,367\,930/(30\times10^6)\approx1.0456$，与 $1514/1448$ 一致。
- 逐项对账：`summary.json` 中这条连接在 `r1-r5` 有 20 723 个包，其中 20 719 个携带数据——20 718 个满长帧 $20\,718\times1514=31\,367\,052$ B，加最后一个 336 B 载荷的 402 B 帧；其余 4 个无数据包（SYN 74 B，3 个 ACK/FIN 各 66 B）共 272 B；另 2 个控制报文 204 B。合计 31 367 930 B，与计数完全一致。
- 时间：`summary.json` 的客户端计时 `completion_seconds` 为 2.518 s，只比帧级下界 2.509 s 多 9 ms；共同窗口 2.590 s 再多出的约 72 ms 在客户端计时之外，即进程启动、退出与 5 ms 轮询。
- 边界：这里只核对了一条流的一个方向。若每包字节明显小于 1514，先查连接的 TCP 选项、接口 MTU 与 offload 状态，不要直接调整模型。

**修订后实测样例（2026-10-05，4 核沙箱）**：

| 档位 | 共同窗口 | 四流聚合应用速率 | 实际出口 |
| :--- | ---: | ---: | :--- |
| 100 Mbit/s | 2.543 s | 377.53 Mbit/s | r1-r5、r1-r6、r2-r5、r2-r6，各一流 |
| 50 Mbit/s | 5.051 s | 190.07 Mbit/s | 与上一轮相同 |

例如 $8\times120/2.543\approx377.5$ Mbit/s；样例用原始精度计算，表内时间已四舍五入。两轮都收到 120 MB，路径保持分散，支持容量约束的解释。与帧级下界 2.509 / 5.019 s 相比，共同窗口只多 34 / 32 ms：首部开销已由帧长解释，余下的几十毫秒落在启动、建连、慢启动与回执这些环节，单次数据不再细分。启动时间随机器而变：同一块命令在上述 2 核虚拟机上的共同窗口为 2.700 / 5.188 s，各流客户端计时却仍为 2.511–2.522 / 5.020–5.025 s。

**附加诊断（选做）**：保持相同钉路与 100 档，只把映射改为 `h1a→h3a`、`h1b→h4a`、`h2a→h3b`、`h2b→h4b`。两条 a 流会汇合于 `r5→r3`，两条 b 流汇合于 `r6→r4`；每个共享出口承载 60 MB，理想下界升到 4.8 s（帧级 5.019 s），而收敛比仍是 1:1。

```bash
# 10. 选做：同样钉路、同样 100 档，只改变接收映射；结束时删除钉路并恢复 100 档
(
  set -Eeuo pipefail
  restore_t3() {
    for r in r1 r2; do
      for table in 105 106; do
        sudo ip -n "$r" rule del priority "$table" 2>/dev/null || true
        sudo ip -n "$r" route flush table "$table" 2>/dev/null || true
      done
    done
    sudo bash 2026/experiments/03/topo.sh rate 100
  }
  trap restore_t3 EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  for rack in 1 2; do
    k=$((2 * (rack - 1)))
    sudo ip -n r$rack route add table 105 default via 10.1.$k.2 dev r$rack-r5 onlink
    sudo ip -n r$rack route add table 106 default via 10.1.$((k + 1)).2 dev r$rack-r6 onlink
    sudo ip -n r$rack rule add priority 105 from 10.0.$rack.11/32 lookup 105
    sudo ip -n r$rack rule add priority 106 from 10.0.$rack.12/32 lookup 106
  done
  sudo bash 2026/experiments/03/topo.sh rate 100
  sudo "$PY" "$MEASURE" --leaf r1 --leaf r2 --output "$RUN/t3-shared" \
    --flow h1a:h3a:40201:5201 --flow h1b:h4a:40203:5203 \
    --flow h2a:h3b:40205:5205 --flow h2b:h4b:40207:5207
)
```

在 2 核虚拟机上（2026-10-07），四条流仍按钉路分别从 `r1-r5`、`r1-r6`、`r2-r5`、`r2-r6` 发出，共同窗口为 5.175 s，约为分散映射的两倍。容量比必须与流量和实际路径一起读。

#### 任务 4　复现课堂对照：交换与路由的边界

在自己的实验床上手敲 locality 观察。终端 1 先运行抓包，它最多等待 8 秒；终端 2 再产生请求。命令需要 root 写结果时用 `tee`，避免普通 shell 向 root 创建的目录重定向失败。

```bash
# 11. 终端 1：同机架观察，收到一包就退出；无包时 timeout 返回 124
sudo ip netns exec r1 timeout 8 tcpdump -n -l -i any -Q out -c 1 \
  'icmp and src host 10.0.1.11 and dst host 10.0.1.12'
```

```bash
# 12. 终端 2：同机架请求
sudo ip netns exec h1a ping -c 1 -W 2 10.0.1.12
```

**课堂实测节选**：

```output
r1-h1b Out IP 10.0.1.11 > 10.0.1.12: ICMP echo request, id 3870, seq 1, length 64
```

```bash
# 13. 终端 1：跨机架观察
sudo ip netns exec r1 timeout 8 tcpdump -n -l -i any -Q out -c 1 \
  'icmp and src host 10.0.1.11 and dst host 10.0.3.11'
```

```bash
# 14. 终端 2：跨机架请求与逐跳追踪
sudo ip netns exec h1a ping -c 1 -W 2 10.0.3.11
sudo ip netns exec h1a traceroute -n -I -q 1 -w 1 10.0.3.11
```

预期出口为 `r1-r5` 或 `r1-r6`；通常看到 `r1 → spine → r3 → h3a` 四行，最后一行是目的 host，bridge 不是 IP 跳。把两次出口、对应设备和 traceroute 中的地址写进报告。不同探测可走不同分支，不能要求 traceroute 与之前的 ping 同路，更不能由 RTT 推断带宽。

---

### 进阶任务

#### 任务 5　哈希碰撞：同路与分路

**5.1 先预测，再观察端口与路径**

改变端口会改变部分哈希输入，但两个不同输入仍可能落到同一条路径；“换端口必换路”不是 ECMP 的保证。本机 namespace/veth 还可能携带内核已有的流哈希，不能直接将结果推广到独立物理交换机。

```bash
# 15. 终端 1：自然 ECMP 的 SYN，观察源端口与 seq；等待 20 秒后自动停止
sudo ip netns exec r1 timeout 20 tcpdump -n -l -S -i any -Q out \
  'tcp dst port 5299 and tcp[13] & 0x12 = 0x02'
```

```bash
# 16. 终端 2：同一五元组的十次新建连尝试；不设服务端，预期 Connection refused
for i in $(seq 1 10); do
  sudo ip netns exec h1a python3 - <<'PY'
import socket
with socket.socket() as s:
    s.settimeout(0.4)
    s.bind(("10.0.1.11", 46001))
    try:
        s.connect(("10.0.3.11", 5299))
    except OSError as error:
        print(type(error).__name__, error)
PY
  sleep 0.3
done
```

另开一次 20 秒窗口，终端 1 将过滤式改为 `'udp dst port 5299'`，终端 2 运行下列命令。相同五元组发十个，再改一个端口；即使两组走同路，也应保留结果。

```bash
# 17. 两组 UDP 探针；无 UDP 服务端，发送成功不代表应用收到
for port in 46001 46002; do
  sudo ip netns exec h1a python3 - "$port" <<'PY'
import socket, sys, time
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    s.bind(("10.0.1.11", int(sys.argv[1])))
    for i in range(10):
        s.sendto(f"probe-{i}".encode(), ("10.0.3.11", 5299))
        time.sleep(0.2)
PY
done
```

填写 `协议 / 五元组 / 尝试次数 / r5 与 r6 的观测 / 边界`。TCP SYN 重传不能当作新连接，结合源端口、绝对初始序号 `seq` 和尝试次数核对；不要直接把原始行数当连接数。若 TCP 相同五元组的新连接选路不同，说明本实验的哈希输入不止你看到的报文字段；这不证明单条连接在逐包轮流转发。Linux 6.8 的 [`fib_multipath_hash`](https://github.com/torvalds/linux/blob/v6.8/net/ipv4/route.c) 会复用已有 L4 哈希，[socket 哈希代码](https://github.com/torvalds/linux/blob/v6.8/include/net/sock.h)提供实现线索，作为拓展而非基础实现要求。

对后续实验的含义：在这张实验床上，转发 TCP 时复用的是发送端 socket 的随机哈希，连接超时重传后这个哈希还可能重选。自然 ECMP 因而近似"按连接随机"，换端口不能把流稳定地放到指定上联。Lab 4–9 需要可重复的路径时，应像任务 3 那样显式钉路，并在报告中写明。

**5.2 并发测量，当场分类**

| 条件 | 保持相同 | 实际比较 |
| :--- | :--- | :--- |
| 同路 / 分路 | `h1a→h3a`、`h1b→h3b` 各 30 MB；上联 50、接入 100 Mbit/s；无钉路 | 当轮连接的实际出口与共同窗口 |

```mermaid
flowchart TB
    %% lab3:collision
    subgraph A["同路：两条流在同一条 50 Mbit/s 上联共享容量"]
        a1["h1a：30 MB"] --> a5["r1 → r5 → r3"] --> a3["h3a"]
        a2["h1b：30 MB"] --> a5 --> a4["h3b"]
    end
    subgraph B["分路：两条 50 Mbit/s 上联各承载一条流"]
        b1["h1a：30 MB"] --> b5["r1 → r5 → r3"] --> b3["h3a"]
        b2["h1b：30 MB"] --> b6["r1 → r6 → r3"] --> b4["h3b"]
    end
```

*图 3：两场景保持相同节点位置；F1 为 h1a→h3a，F2 为 h1b→h3b，各 30 MB（阅读版中实线为 F1、虚线为 F2，细线为候选路径）。同路时，两条流共用一条上联的 50 Mbit/s，并非各有 50 Mbit/s。同路也可能经 r6，分路也可交换 r5/r6。省略网桥、ACK 回程及其他节点；每台 host 接入为 100 Mbit/s。图示是分类条件，不预先指定自然哈希结果。*

先预测：同路与分路下界分别是多少？然后固定做六轮，不以“必须出现某种分组”作为结束条件。

```bash
# 18. 检查自然选路、设置 50 档，并完成六轮；每轮自动重启服务端、使用新源端口
sudo ip -n r1 rule show
sudo bash 2026/experiments/03/topo.sh rate 50
for trial in $(seq 1 6); do
  sudo "$PY" "$MEASURE" --output "$RUN/t5-$trial" \
    --flow h1a:h3a:$((42000+trial)):5201 --flow h1b:h3b:$((43000+trial)):5203
done
sudo bash 2026/experiments/03/topo.sh rate 100
```

先读每轮 `summary.json` 中每流的 SYN 出口，再看 `capture.groups` 中**有数据载荷**的出口是否一致；路由变化、多出口或抓包丢失时标为“路径变化／证据不足”，不要硬分组。按分组报告样本数、各轮值和中位数；某组没有样本就写“本轮未观察到”，可以另加固定数量的补充轮次并全部保留。

<details>
<summary>核对答案：同路与分路的下界</summary>

理想下界为同路 **9.6 s**、分路 **4.8 s**；按任务 3 的帧长折算为 10.04 / 5.02 s。实测不要求精确两倍。

</details>

修订后实测六轮（2026-10-05，4 核沙箱）：分路四轮窗口为 5.039、5.044、5.038、5.044 s；同路两轮为 10.070、10.064 s。对应分路约 95.2、同路约 47.7 Mbit/s。这是本轮分布，不能据六次样本估计稳定的碰撞概率。

#### 任务 6　双租户 VXLAN（选做）

**6.1 自建 overlay 并登记生命周期**

保留自己的 underlay。以下给出关键搭建命令；运行前先画出 `t1a → br100 → vx100 → underlay → vx100 → br100 → t3a`，说明 VNI 100 与 200 的网桥为什么必须分开。租户 bridge 不配 IP，避免将重叠租户前缀通告进 underlay。

下面是一个完整 Bash 块，使用 root 写清理清单；失败会调用清理工具。运行前检查所有同名资源，不会先删除其他实验。重复搭建前显式调用 `overlay_down.sh`。

```bash
# 19. 创建租户 namespace、无 IP 的 bridge、静态 remote VTEP 和接入口
sudo bash <<'BASH'
set -Eeuo pipefail
state=/run/lab03/overlay-resources
[[ -f /run/lab03/namespaces ]] || { echo '先搭好自己的 topo.sh'; exit 1; }
[[ ! -e "$state" ]] || { echo '先执行 overlay_down.sh'; exit 1; }
for ns in t1a t3a t1b t3b; do
  [[ ! -e /run/netns/$ns ]] || { echo "$ns 已占用"; exit 1; }
done
for rack in 1 3; do
  for dev in br100 br200 vx100 vx200 r$rack-t${rack}a r$rack-t${rack}b; do
    if ip -n r$rack link show "$dev" >/dev/null 2>&1; then
      echo "r$rack/$dev 已占用"; exit 1
    fi
  done
done
: >"$state"
trap 'status=$?; if [[ $status -ne 0 ]]; then bash 2026/experiments/03/overlay_down.sh; fi' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
for ns in t1a t3a t1b t3b; do
  ip netns add "$ns"
  echo "ns $ns -" >>"$state"
  ip -n "$ns" link set lo up
done
for rack in 1 3; do
  peer=3; [[ "$rack" == 3 ]] && peer=1
  for tenant in a b; do
    vni=100; [[ "$tenant" == b ]] && vni=200
    ns=t$rack$tenant
    for dev in br$vni vx$vni; do
      if [[ "$dev" == br* ]]; then
        ip -n r$rack link add "$dev" type bridge
      else
        ip -n r$rack link add "$dev" type vxlan id "$vni" \
          local 10.0.$rack.1 remote 10.0.$peer.1 dstport 4789
      fi
      echo "link r$rack $dev" >>"$state"
    done
    ip -n r$rack link add r$rack-$ns type veth peer name eth0 netns "$ns"
    echo "link r$rack r$rack-$ns" >>"$state"
    for dev in r$rack-$ns vx$vni; do
      ip -n r$rack link set "$dev" mtu 1450 master br$vni up
      ip netns exec r$rack ethtool -K "$dev" gro off gso off tso off
    done
    ip -n r$rack link set br$vni mtu 1450 up
    ip -n "$ns" link set eth0 mtu 1450 up
    ip netns exec "$ns" ethtool -K eth0 gro off gso off tso off
    octet=11; [[ "$rack" == 3 ]] && octet=12
    ip -n "$ns" addr add 192.168.10.$octet/24 dev eth0
  done
done
trap - EXIT INT TERM
BASH
```

```bash
# 20. 核对 offload 的实际状态，保留输出；不能用“忽略报错”代替验证
sudo ip netns exec t1a ethtool -k eth0
sudo ip netns exec r1 ethtool -k vx100
sudo ip -n r1 -d link show vx100

# 21. 同 VNI 的两个方向都要验证；两个租户使用相同的 IP
for tenant in a b; do
  sudo ip netns exec t1$tenant ping -c 1 -W 2 192.168.10.12
  sudo ip netns exec t3$tenant ping -c 1 -W 2 192.168.10.11
done
```

应看到租户侧 `generic-receive-offload`、`generic-segmentation-offload`、`tcp-segmentation-offload` 为 off；设备固定不支持的特性以实际 `[fixed]` 状态记录。本任务关闭这三个分段／聚合特性，不声称关闭所有 checksum offload。

**6.2 同一包的内外层证据与隔离反例**

分别在两个终端启动以下抓包，再在第三个终端运行一次 `ping -s 32`。这次比较的是**同一次请求**：核对 ICMP `id/seq`，不能拿不同时间的两个 ping 当同包。

```bash
# 22. 终端 1：租户侧；终端 2 单独执行下一条 underlay 抓包
sudo ip netns exec t1a timeout 10 tcpdump -n -vv -i eth0 -c 1 'icmp[0] = 8'
```

```bash
# 23. 终端 2：VNI 100 内的 IPv4 ICMP 请求（无 VLAN，内层 IPv4 无选项）
sudo ip netns exec r1 timeout 10 tcpdump -n -vv -i any -Q out -c 1 \
  'udp dst port 4789 and udp[12:4] = 0x00006400 and udp[28:2] = 0x0800 and udp[39] = 1 and udp[50] = 8'
```

```bash
# 24. 终端 3：只发一次请求
sudo ip netns exec t1a ping -c 1 -W 2 -s 32 192.168.10.12
```

读偏移：UDP 起点后 12–14 是 VNI，15 是 **VXLAN 保留字节**，所以 `udp[12:4]` 包含三字节 VNI 和一字节保留值；28–29 是内层 EtherType；39 是内层 IP 协议；50 是无选项 IPv4 后的 ICMP 类型。这些固定偏移只适用于上述封装条件。

请求内层 IP 总长应为 $20+8+32=60$ B，外层 IP 总长应为 $20+8+8+14+60=110$ B。记录外层地址、源端口、4789 与 VNI，并用同一 ICMP 标识关联两处观察。

```bash
# 25. A 目的口关闭后应失败；B 仍可达；退出时总是恢复 A
(
  trap 'sudo ip -n t3a link set eth0 up' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  sudo ip -n t3a link set eth0 down
  if sudo ip netns exec t1a ping -c 1 -W 1 192.168.10.12; then
    echo '隔离反例不成立，先排查桥接关系'; exit 1
  fi
  sudo ip netns exec t1b ping -c 1 -W 2 192.168.10.12
)
```

这验证给定配置中的同 VNI 可达与 A/B 分离，不代表 VNI 提供加密或覆盖所有安全威胁。

**6.3 隔离不等于带宽保证**

先预测 A 单独运行与 A+B 同时运行的差别。为消除自然 ECMP 的变化，两种条件都把**外层目的地址**固定经 r5；固定源 leaf 上联 50 Mbit/s，A 始终两条 30 MB。改变的只是 B 是否同时发送两条 30 MB。

```mermaid
flowchart TB
    %% lab3:tenants
    subgraph A["基线：仅 A，合计 60 MB"]
        a1["t1a：VNI 100"] --> a5["r1 → r5 → r3：50 Mbit/s"] --> a3["t3a"]
        a2["t1b：空闲"]
        a4["t3b：空闲"]
    end
    subgraph B["并发：A+B，合计 120 MB"]
        b1["t1a：VNI 100，60 MB"] --> b5["同一条 r1 → r5 → r3：50 Mbit/s"] --> b3["t3a"]
        b2["t1b：VNI 200，60 MB"] --> b5 --> b4["t3b"]
    end
```

*图 4：两场景保留相同节点位置。租户 A（VNI 100）在 t1a→t3a 上发两条 30 MB 流；租户 B（VNI 200）在 t1b→t3b 上发两条 30 MB 流，基线时空闲（阅读版中实线为 A、虚线为 B，均为逻辑流量标记）。共同的 underlay 是 r1→r5→r3；并行画出的租户流量不代表独立的上联容量。只画正向实际路径，省略独立租户 bridge/VTEP、ACK 回程与 r6 候选分支。租户接入口未单独限速，underlay 两端的 50 Mbit/s 出口共享。A、B 虚拟地址重叠，但 VNI 与网桥分开。*

```bash
# 26. 三次交替测基线与并发；每轮源端口换新，结束恢复路由和 100 档
(
  set -Eeuo pipefail
  restore_t6() {
    sudo ip -n r1 route del 10.0.3.1/32 via 10.1.0.2 dev r1-r5 2>/dev/null || true
    sudo bash 2026/experiments/03/topo.sh rate 100
  }
  trap restore_t6 EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  sudo ip -n r1 route add 10.0.3.1/32 via 10.1.0.2 dev r1-r5
  sudo bash 2026/experiments/03/topo.sh rate 50
  for trial in 1 2 3; do
    base=$((44000 + trial * 10))
    sudo "$PY" "$MEASURE" --capture vxlan --output "$RUN/t6-base-$trial" \
      --flow t1a:t3a:$((base+1)):5201 --flow t1a:t3a:$((base+2)):5202
    sudo "$PY" "$MEASURE" --capture vxlan --output "$RUN/t6-both-$trial" \
      --flow t1a:t3a:$((base+3)):5201 --flow t1a:t3a:$((base+4)):5202 \
      --flow t1b:t3b:$((base+5)):5203 --flow t1b:t3b:$((base+6)):5204
  done
)
```

每组列出 A 的每流速率、A 从本轮共同起点到两个 A 客户端都完成的时间、全体共同窗口、A+B 聚合速率和实际出口。助手为每流记录相对本轮起点的 `launch_offset_seconds` 与 `finish_offset_seconds`；取两个 A 的完成偏移最大值就是 A 的子组共同窗口，按 $8\times60\times10^6/T_A$ 算 A 的同窗口速率。完成时刻由 5 ms 轮询观察，包含启动和收尾；两条流各自的速率不能直接相加。

<details>
<summary>核对答案：基线与并发的下界</summary>

忽略开销时，固定路径的下界为基线 **9.6 s**、并发 **19.2 s**。overlay 满长帧同样是 1514 B，但只载 1398 B 应用数据（见任务 8），按帧长折算为 10.40 / 20.79 s。TCP 不保证各流均分，也不要求 A 恰好减半。

</details>

修订后实测样例（2026-10-05，4 核沙箱，三轮中位数）：仅 A 时，共同窗口 10.431 s、A 同窗口速率 46.02 Mbit/s；A+B 时，全体窗口 20.835 s、总速率 46.08 Mbit/s，A 子组窗口 20.799 s、A 同窗口速率 23.08 Mbit/s。两种条件的目标数据都经过 r1-r5，A/B 均有完整字节回执。这里支持的是共享容量导致相互影响，不是 TCP 保证公平分配。

如果 A 没明显变慢，检查 B 是否真的收到 60 MB、两租户是否确实共享 r1-r5、背景负载和抓包丢失。结论应来自 VNI、字节回执、出口与时间的关联，不能只看一张吞吐表。

**此时保留 overlay 继续任务 7、8。** 若跳过后续，执行任务 8 末尾的统一清理。需要重建 overlay 时先执行 `sudo bash 2026/experiments/03/overlay_down.sh`；它同时回收 bridge/VTEP 和租户进程，重复执行不报错。

---

### 挑战任务

#### 任务 7　VTEP 的外层源端口与路由缓存

[RFC 7348 第 5 节](https://www.rfc-editor.org/rfc/rfc7348#section-5)建议由内层报文字段生成外层 UDP 源端口，让 underlay 上按五元组哈希的路由器能区分不同的内层流；它没有要求每个包选择不同路径。外层源端口能否决定路径，取决于做 ECMP 选择的那一跳怎样查路由。本实验床里，唯一的选择点恰好是 VTEP 所在的 r1 本身：r5、r6 去往 r3 都只有一条路。外层源端口由 Linux 的 [`udp_flow_src_port`](https://github.com/torvalds/linux/blob/v6.8/include/net/udp.h) 根据内层报文的哈希（[`skb_get_hash`](https://github.com/torvalds/linux/blob/v6.8/include/linux/skbuff.h)，可能复用发送端 socket 已有的哈希）算出，所以同一连接的外层端口通常保持不变。

Linux 6.8 的 [`vxlan_xmit_one`](https://github.com/torvalds/linux/blob/v6.8/drivers/net/vxlan/vxlan_core.c) 给配置了固定 remote 的 VXLAN 设备启用路由缓存（`dst_cache`）。[`udp_tunnel_dst_lookup`](https://github.com/torvalds/linux/blob/v6.8/net/ipv4/udp_tunnel_core.c) 先查缓存，命中就直接使用；只有未命中时，才用本包的外层源端口去查 multipath 路由。缓存按 CPU 分别保存（[`dst_cache.c`](https://github.com/torvalds/linux/blob/v6.8/net/core/dst_cache.c)），本 namespace 的 IPv4 路由一有增删就整体失效。由此可以预测：

- 缓存刚失效时，连接按自己的外层源端口选出口，可以用 `ip route get … sport 端口` 复算；
- 缓存未失效时，新连接沿用缓存里的出口，与自己的外层源端口无关；
- 不同 CPU 缓存了不同出口时，同一连接、同一外层端口的数据会分到两条上联。

`ip route get` 使用同一套 multipath 哈希（`topo.sh` 设置的 `fib_multipath_hash_policy=1`，输入为外层源／目的地址、协议与端口），但不读写 VXLAN 设备的缓存，正好给出"如果按端口选路，应走哪条"的对照。

| 组 | 条件 | 要回答的问题 |
| :--- | :--- | :--- |
| 每条前失效 | 每条连接前增删一条无关路由，使缓存失效；自然 ECMP | 每条连接用了几个外层源端口、几个出口？出口与复算结果是否一致？ |
| 只失效一次 | 失效一次后连续三条连接，中间不改路由 | 第 2、3 条连接跟随自己的复算结果，还是沿用第 1 条的出口？ |
| 钉路 | 外层 `/32` 固定经 r5 | 不论端口和复算结果，目标数据是否都经过 r1-r5？ |

前两组只差"每条连接前是否使缓存失效"。增删的是 RFC 5737 文档用途前缀 `198.51.100.0/24`，不承载任何流量。每组开始前路由都会变化一次（钉路组添加 `/32` 本身就是路由变化），结果不依赖前面任务留下的缓存。先写下你对每组的预测。

```bash
# 27. 定义"使 r1 的路由缓存失效"；确认没有任务 6 留下的 /32 钉路（最后一条应无输出）
flush_r1() {
  sudo ip -n r1 route add 198.51.100.0/24 via 10.1.0.2 dev r1-r5
  sudo ip -n r1 route del 198.51.100.0/24
}
sudo bash 2026/experiments/03/topo.sh rate 100
sudo ip -n r1 route show 10.0.3.1/32
```

```bash
# 28. 每条前失效组：三条独立的 30 MB 连接
for trial in 1 2 3; do
  flush_r1
  sudo "$PY" "$MEASURE" --capture vxlan --output "$RUN/t7-each-$trial" \
    --flow t1a:t3a:$((47000+trial)):5201
done
```

```bash
# 29. 只失效一次组：失效后连续三条连接，中间不改路由
flush_r1
for trial in 1 2 3; do
  sudo "$PY" "$MEASURE" --capture vxlan --output "$RUN/t7-once-$trial" \
    --flow t1a:t3a:$((47100+trial)):5201
done
```

```bash
# 30. 钉路组：结束后自动移除 /32；不改内层连接数据量
(
  set -Eeuo pipefail
  trap 'sudo ip -n r1 route del 10.0.3.1/32 via 10.1.0.2 dev r1-r5 2>/dev/null || true' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  sudo ip -n r1 route add 10.0.3.1/32 via 10.1.0.2 dev r1-r5
  for trial in 1 2; do
    sudo "$PY" "$MEASURE" --capture vxlan --output "$RUN/t7-pinned-$trial" \
      --flow t1a:t3a:$((47200+trial)):5201
  done
)
```

```bash
# 31. 对每个外层源端口用 ip route get 复算出口，与实际出口并列；此时不能有 /32 钉路
sudo python3 - "$RUN" <<'PY'
import json, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
print("轮次 内层源端口 外层源端口 实际出口 数据包数 复算出口")
for group in ("each", "once", "pinned"):
    for run in sorted(root.glob(f"t7-{group}-*")):
        flow = json.loads((run / "summary.json").read_text())["flows"][0]
        for row in flow["capture"]["groups"]:
            port = str(row["outer_source_port"])
            words = subprocess.run(
                ["ip", "-n", "r1", "route", "get", "10.0.3.1", "from", "10.0.1.1",
                 "ipproto", "udp", "sport", port, "dport", "4789"],
                capture_output=True, text=True, check=True).stdout.split()
            print(run.name, flow["source_port"], port, row["interface"],
                  row["data_packets"], words[words.index("dev") + 1])
PY
```

```bash
# 32. 将汇总对回原始报文：读两条上联抓包的前几个包，核对外层源端口（目录换成要核对的轮次）
cat "$RUN/t7-once-2/summary.json"
sudo tcpdump -n -v -c 4 -r "$RUN/t7-once-2/r1-r5.pcap"
sudo tcpdump -n -v -c 4 -r "$RUN/t7-once-2/r1-r6.pcap"
```

`capture.groups` 按 **VNI + 内层源/目的 IP、TCP 端口**筛选本轮发送连接，再按出口和外层源端口计数。`data_packets` 才是携带目标 TCP 数据的包；`tcp_payload_bytes_with_retransmissions` 包括重传，不能冒充应用有效字节。未匹配的 ARP、IPv6、其他租户与反向业务记在 `unmatched_packets`；同一 VXLAN 包会被 tcpdump 输出为多行，**禁止用 `wc -l` 当包数**。

**实测样例（2026-10-07，x86_64 虚拟机；步骤 31 的输出）**：

```output
轮次 内层源端口 外层源端口 实际出口 数据包数 复算出口
t7-each-1 47001 47162 r1-r5 21465 r1-r5
t7-each-2 47002 60591 r1-r6 21464 r1-r6
t7-each-3 47003 60676 r1-r5 21463 r1-r5
t7-once-1 47101 48221 r1-r5 21467 r1-r5
t7-once-2 47102 45219 r1-r5 21461 r1-r5
t7-once-3 47103 51754 r1-r5 21466 r1-r6
t7-pinned-1 47201 41852 r1-r5 21463 r1-r5
t7-pinned-2 47202 35496 r1-r5 21463 r1-r5
```

带读：

- 每轮只有一行：每条连接只用了一个外层源端口、一个出口；8 轮的抓包丢失计数均为 0。数据包数含重传，21 461 与 21 467 的差别不代表应用多发了数据。
- 每条前失效组：3 条连接的实际出口都与复算一致，第 2 条走了 `r1-r6`。缓存刚失效时，外层源端口经 multipath 哈希决定出口。
- 只失效一次组：第 1、2 条与复算一致；第 3 条的外层端口 51754 复算应走 `r1-r6`，实际仍走 `r1-r5`，沿用了第 1 条连接填入的缓存。第 2 条的复算恰好与第 1 条相同，单看它区分不了两种解释。
- 钉路组：两条都经 `r1-r5`。本轮两条的复算恰好也是 `r1-r5`，这组单独不能说明钉路覆盖了哈希；同一台机器上此前一次探索性测量中，复算指向 `r1-r6` 的连接（外层端口 56924）在钉路下仍经 `r1-r5`。

提交 `组别 / 内层源端口 / 外层源端口 / 各出口数据包数 / 复算出口 / 是否一致 / 抓包丢失`，并用缓存机制逐行解释不一致。若"只失效一次"组后两条连接的复算结果恰好都与第 1 条相同，这组区分不了两种解释——如实写明，可以换一批源端口再做一组，全部保留。

**可能出现的分流**：在上述 2 核虚拟机上，建好 overlay 后不做失效、直接连续测六条连接，每条连接都只有一个外层源端口，数据却都分到了两条上联；例如外层端口 49995 的连接在 `r1-r5`、`r1-r6` 上分别有 4 830 与 16 641 个数据包。按上面的源码，这对应两个 CPU 缓存了不同出口：从哪个 CPU 发包，就走那个 CPU 缓存的上联，切换时段两条路径交错，可能带来乱序。是否出现取决于此前哪些报文先在各 CPU 上填充了缓存，所以不列为必做组；遇到时按本任务的方法记录，不要写成"逐包负载均衡"。

**结论边界**：这些观察说明，本实验床中 VTEP 自己的选路受路由缓存支配。外层源端口为下游按五元组哈希的路由器提供区分信息，要在 VTEP 之后还有 ECMP 选择点时才能观察到。缓存是否在 CPU 之间分歧，随内核版本、CPU 数和此前流量而变，不要把一次结果推广到所有 Linux、网卡或交换机。

#### 任务 8　封装开销：近似模型与实测边界

**先算 MTU**：外层 IPv4 无选项、内层 Ethernet 无 VLAN 时，1450 B 内层 IP + 14 B 内层 Ethernet + 8 B VXLAN + 8 B UDP + 20 B 外层 IPv4 = 1500 B 外层 IP。下面验证源租户接口边界；第二条命令预期失败，失败位置是本地，不是远端丢包。

```bash
# 33. IP 头 20 + ICMP 头 8 + 数据 1422 = 1450；再多一个字节应被本地拒绝
sudo ip netns exec t1a ping -M do -c 1 -W 2 -s 1422 192.168.10.12
sudo ip netns exec t1a ping -M do -c 1 -W 2 -s 1423 192.168.10.12
```

忽略 TCP 选项时，MSS 预算为 overlay 1410、underlay 1460 B，应用效率比近似 $1410/1460\approx0.966$。若连接使用 12 B TCP 时间戳等选项，满长数据段载荷可能是 1398 与 1448 B，应再核对 $1398/1448\approx0.9655$。SYN 的 MSS 声明与数据包实际载荷不是同一个量；用 `tcpdump -vv` 的 options 和数据 `length` 读实际情况，不预先假定没有选项。

再用任务 3 的帧级口径：两种满长数据帧在限速器看来都是 1514 B，overlay 帧多出外层以太网、IP、UDP、VXLAN 与内层以太网头，每帧比 underlay 少载 50 B。100 Mbit/s 上联上的单流速率上界因此分别为 $100\times1448/1514\approx95.64$ 与 $100\times1398/1514\approx92.34$ Mbit/s，比值仍是 $1398/1448$。

**公平对照**：上联 100 档；两种传输各 30 MB，均显式钉到 r5；overlay 为 `t1a→t3a`，underlay 为 `h1a→h3a`。租户接入未限速，underlay host 接入口为 100 Mbit/s，这是仍存在的结构差异，报告要说明；网络整体空闲时二者目标瓶颈都是同一条 100 Mbit/s 上联。交替做五次，报告所有值与中位数。

```bash
# 34. 分别固定 VTEP 与 underlay host 的 /32 路径；退出时移除两条临时路由
(
  set -Eeuo pipefail
  restore_t8() {
    for addr in 10.0.3.1 10.0.3.11; do
      sudo ip -n r1 route del "$addr/32" via 10.1.0.2 dev r1-r5 2>/dev/null || true
    done
  }
  trap restore_t8 EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  sudo bash 2026/experiments/03/topo.sh rate 100
  for addr in 10.0.3.1 10.0.3.11; do
    sudo ip -n r1 route add "$addr/32" via 10.1.0.2 dev r1-r5
  done
  for trial in 1 2 3 4 5; do
    sudo "$PY" "$MEASURE" --output "$RUN/t8-underlay-$trial" \
      --flow h1a:h3a:$((48000+trial)):5201
    sudo "$PY" "$MEASURE" --capture vxlan --output "$RUN/t8-overlay-$trial" \
      --flow t1a:t3a:$((48100+trial)):5201
  done
)
```

```bash
# 35. 汇总每流应用速率，打印全部值与中位数；比值不是因果分解
python3 - "$RUN" <<'PY'
import json, pathlib, statistics, sys
root = pathlib.Path(sys.argv[1])
medians = {}
for kind in ("underlay", "overlay"):
    values = [json.loads((root / f"t8-{kind}-{n}/summary.json").read_text())["flows"][0]["application_mbps"] for n in range(1, 6)]
    medians[kind] = statistics.median(values)
    print(kind, [round(v, 2) for v in values], "中位数", round(medians[kind], 2))
print("overlay/underlay", medians["overlay"] / medians["underlay"])
PY
```

修订后实测样例（2026-10-05，4 核沙箱，五轮客户端应用速率）：underlay 为 95.60、95.63、95.63、95.59、95.63 Mbit/s，overlay 为 92.28、92.33、92.33、92.33、92.33 Mbit/s；中位数比值用原始精度计算为 0.9655。抓包可见 TCP 时间戳选项，与实际段长预算一致。这是每流客户端计时口径，不要与含进程启动的 `shared_window_mbps` 混用。

帧级模型同时给出了绝对值与比值：underlay 中位数 95.63 对上界 95.64，overlay 92.33 对 92.34 Mbit/s，差距不到 0.1%。这支持如下解释：本轮速率由限速器按帧计费决定，封装的代价就是每帧少载的 50 B。要让这个解释成立，还需核对实际段长与 TCP 选项（`tcpdump -vv`）、重传（`tcp_payload_bytes_with_retransmissions` 是否多于应用字节），以及 `tc -s class show` 的每包字节。结论只对这组条件成立；五次稳定值不能说明其他机器上 CPU 也不会成为瓶颈。

**offload 拓展（不计基础验收）**：先保存 `ethtool -k` 输出，再只改租户接入口与 VTEP 的 GRO/GSO/TSO 状态，重复同一套固定路径对照。记录哪些特性真正变了、捕获长度如何变化；结束恢复原状态。不要同时改变速率、路径或流数，也不要把未出现巨型报文当成 offload 一定未生效。

```bash
# 36. 完成或异常中断后的统一清理；结果目录保留，可先复制到长期保存位置
sudo bash 2026/experiments/03/overlay_down.sh
sudo bash 2026/experiments/03/overlay_down.sh
sudo bash 2026/experiments/03/topo.sh down
sudo bash 2026/experiments/03/topo.sh down
ip netns list
```

---

## 六、故障排查

| 现象 | 先查什么 |
| :--- | :--- |
| `topo.sh` 报 TODO 未完成 | 按注释完成学生代码；语法检查通过不等于拓扑正确 |
| `up` 报某个 namespace 已存在 | 多半是第 05 讲的课堂拓扑还在：先 `sudo bash 2026/experiments/03/classroom.sh down`；否则按 Lab 1/2 指导书清理 |
| 路由未就绪或单下一跳 | 路由日志、Lab 2 ECMP 与实际 FIB；可用 `up --reference` 分离问题。就绪失败时拓扑保留，可直接 `show` 检查 |
| 结果目录已存在 | 保存旧轮次，换 `RUN` 或轮次名；不覆盖失败记录 |
| `Address already in use` | 源端口是否仍在 TIME_WAIT；换新端口；服务端端口是否被其他进程占用 |
| 客户端 `Connection refused` | 服务端是否在正确的接收 namespace；核对 `ss -ltn` 和本轮 stderr |
| 没有 `summary.json` | 本轮失败或中断；不能将残留客户端 JSON 当作完整对照 |
| 没有路径证据或存在多个出口 | `--leaf`、五元组、VNI、路由变化和 `capture_stats` 丢失计数；不强行分类 |
| VXLAN 同一外层端口出现在两个出口，或出口与 `ip route get` 复算不一致 | 见任务 7：VTEP 的路由缓存按 CPU 保存；先增删一条无关路由使缓存失效再测 |
| overlay 重建 `File exists` | 先用 `overlay_down.sh` 清理本次登记的租户与 router 侧资源 |
| `ethtool` 失败 | 应为 `ip netns exec ... ethtool`；保留报错，查实际 `-k` 状态 |
| 正常传输已结束，手工 `wait` 不返回 | 不带 PID 的 `wait` 可能在等待抓包；只等待自己的客户端 PID |
| 中断后路径或容量异常 | 重新 `topo.sh down`、`up`、`check`；overlay 重新搭建，结果保留 |

辅助工具只结束自己创建的子进程；不要使用全局 `pkill -f tcpdump`。若要从某个中间任务继续，先确认上一任务的策略路由、`/32`、限速档位和 overlay 状态，不能只检查 ping 通不通。

---

## 七、思考题

1. **1:1 为什么仍可能慢？** 任务 3 的附加映射没有改变容量比，却让流共享接收侧出口。用链路负载下界解释，不把无量纲比值本身叫作吞吐上界。
   *思考提示：逐链路求数据量，再找最大的 $8D_e/C_e$。*
2. **换端口为什么不保证换路？** 比较哈希输入、有限数量的下一跳、内核已有流哈希与五元组。
   *思考提示：不同输入可以碰撞；新建连接与迁移已有连接不是同一件事。*
3. **外层端口与出口为什么可能对不上？** 任务 7 中哪些观察说明 VTEP 不是逐包按外层源端口选路？在真实数据中心里，外层源端口的区分信息在哪一跳起作用？
   *思考提示：区分 VTEP 本机的路由查找与下游路由器的转发哈希；考虑缓存、CPU 与路由变化。*
4. **隔离与保证有什么不同？** 给 A 保证带宽时，在哪里分类、预留或调度？只有限制 A 的最大发送速率，能否保证它的最小速率？
   *思考提示：限速、共享链路容量与最低保障不是同一概念。*
5. **哪些约定供 Lab 4–9 复用？** 列出节点、接口、地址、限速档位与测量指标；为什么通信完成时间还不是完整 JCT？需要可重复的路径时，用什么方式固定？
6. **为什么继续使用 lsrd？** 区分教学复用与生产网络协议选择；不同控制协议能否安装相同的内核 multipath FIB？

---

## 八、提交要求

| 层次 | 提交内容 | 分值 |
| :--- | :--- | :--- |
| 基础任务 1–4，人人完成 | 完整 `topo.sh`（含 12 条路由的 ECMP 自检）；任务 1 检查点；自检与路由；任务 3 预测、两档结果、帧级下界与 `tc` 计数、路径证据；任务 4 出口与跳数解释 | 60 |
| 进阶任务 5 | 探针记录、固定轮数的全部结果、同路／分路分类及证据边界；没有某类样本也可据实分析 | 15 |
| 选做链：进阶任务 6 | 双向连通、同包内外层对照、隔离反例、三轮租户共享对照 | 10 |
| 选做链：挑战任务 7 | 三组的外层源端口、实际出口与 `ip route get` 复算对照表，用缓存机制解释不一致 | 8 |
| 选做链：挑战任务 8 | MTU 账目、实际 TCP 选项与段长、五轮数据及帧级模型分析 | 7 |
| 附加分 | 用自己的 `lsrd --ecmp`（不带 `--reference`）通过 `up` 与 `check` | +5 |

基础报告建议 3–5 页，完成选做可增至 4–8 页；不要求为了页数重复截图。每项有预测、证据、解释：预测被支持或被推翻都正常，评分看证据是否充分。任务 6–8 是一条选做链，跳过不扣基础与任务 5 的得分，也不获得该链的 25 分；若课程因进度宣布全班跳过这条链，则按基础与任务 5 共 75 分折算为百分制。附加分计入后总分不超过 100。

拓扑验收：`up` 成功返回后 `check` 全部通过（两行 `[OK]`）；`up` 的就绪检查约 15 秒后放弃，整个 `up` 约 20 秒内返回；未就绪时会提示并保留拓扑，查日志后再重跑；重复 `up/down` 不遗留资源，`rate` 两档确实可切换。默认启动入口等同 `up`。拓扑 TODO 必须自己完成；路由实现按 3.1 节选择，并在报告中注明。

提交脚本与报告，以及各轮结果目录中的 `summary.json` 与 `run.json`：它们体积很小，用于核对报告中的数字、路径与内核版本。报告附精简汇总表与关键输出；原始 pcap、stderr 和日志在本机留存备查，不提交 `.venv/`、`__pycache__/`、完整抓包和日志。

```bash
# 37. 只打包各轮的 summary.json 与 run.json，随报告提交
(cd /tmp/lab03-results && find . \( -name summary.json -o -name run.json \) -print | tar -czf "$HOME/lab03-summaries.tgz" -T -)
tar -tzf "$HOME/lab03-summaries.tgz" | head
```

### 维护与验证

本文样例的来源与验证范围：

| 日期与环境 | 覆盖内容 |
| :--- | :--- |
| 2026-10-05，Ubuntu 24.04 / Linux `6.8.0-142-generic` ARM64、4 核 4 GB 沙箱 | 任务 3 两档、任务 5 六轮、任务 6 三组交替、任务 8 五组交替的样例；各项观察、清理与重建 |
| 2026-10-07，Ubuntu 26.04 / Linux `7.0.0-38-generic` x86_64、2 核 2.8 GB 虚拟机 | 任务 2 的 12 条路由自检、任务 3 两档复测、`tc` 计数观察与附加诊断、重新设计的任务 7，以及统一清理与结果打包 |

两次验证都使用 Lab 2 参考路由实现与临时补全的拓扑副本，仓库中的学生 TODO 保持未完成。结果只覆盖上述环境，不代表所有学生 Linux 环境或学生实现都已验证；学生应保存自己的数据，不以样例端口、路径比例或用时作为验收标准。完整验证记录、离线检查入口与阅读版生成方法见 [MAINTENANCE.md](MAINTENANCE.md)。
