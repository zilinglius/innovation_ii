# 计算机网络基础与 Linux 网络虚拟化讲义

> **课程导读**：本讲义专为网络与分布式系统系列实验设计，旨在系统梳理计算机网络核心理论体系，并将其与 Linux 内核级网络虚拟化技术无缝衔接。学完本讲义后，你将能够建立从**物理信号、数据链路层以太网帧、网络层 IP 路由、传输层 TCP/UDP** 到 **Linux Network Namespace / veth 虚拟网络搭建** 的立体认知，为后续深入学习路由协议、流量测量与分布式系统打下坚实基础。

---

## 学习目标

1. **分层体系认知**：理解 OSI 七层模型与 TCP/IP 四层/五层模型的设计哲学、协议分工与解耦思想。
2. **报文结构与机制**：掌握以太网帧（Ethernet II）、IPv4 / IPv6 数据报、TCP 报文段的完整字段结构与关键机制（MTU、IP 分片、TTL、ICMP 差错报告、TCP 三次握手、标志位与窗口）。
3. **端到端传输轨迹**：建立微观视角，清晰追踪一段应用层数据在发送端封装、中间网络设备转发、接收端解封装的完整生命周期。
4. **Linux 网络虚拟化实操**：熟练掌握 Linux Network Namespace 和 `veth pair` 的构建、连通性配置与抓包分析，具备独立搭建网络拓扑的实验能力。

---

## 模块一：网络体系结构与分层模型

### 1.1 为什么需要分层体系？

计算机网络连接着异构的硬件设备、操作系统与应用程序。如果采用单一单体架构实现通信，任何物理介质或上层应用的变更都会导致整个网络协议栈重构。

分层模型遵循**关注点分离**（Separation of Concerns）与**高内聚低耦合**的工程原则：
- **独立性**：每层仅定义对等层之间的通信规范（协议），以及对相邻上层提供的服务接口（API），下层实现细节对上层完全透明。
- **灵活性**：各层技术可独立演进。例如，从有线以太网切换到 Wi-Fi、从铜缆切换到光纤，网络层（IP）及之上的应用均无需修改代码。
- **标准化**：促成不同厂商设备和开源软件之间的互联互通。

各层交换的数据单元通称为 **PDU（Protocol Data Unit，协议数据单元）**：
- **应用层**：报文 / 消息（Message / Data）
- **传输层**：报文段（Segment，针对 TCP）/ 数据报（Datagram，针对 UDP）
- **网络层**：分组 / 数据报 / 包（Packet / Datagram）
- **数据链路层**：帧（Frame）
- **物理层**：比特流（Bits）

---

### 1.2 OSI 七层模型与 TCP/IP 模型映射

国际标准化组织（ISO）提出了理论完备的 **OSI（Open Systems Interconnection）七层参考模型**，而工业界实际部署并主导互联网的则是工程导向的 **TCP/IP 体系**。

```mermaid
graph LR
    subgraph OSI_7_Layers [OSI 七层参考模型]
        O7[7. 应用层 Application]
        O6[6. 表示层 Presentation]
        O5[5. 会话层 Session]
        O4[4. 传输层 Transport]
        O3[3. 网络层 Network]
        O2[2. 数据链路层 Data Link]
        O1[1. 物理层 Physical]
    end

    subgraph TCPIP_5_Layers [TCP/IP 五层教学体系]
        T5[应用层 Application]
        T4[传输层 Transport]
        T3[网络层 Network / Internet]
        T2[数据链路层 Data Link]
        T1[物理层 Physical]
    end

    subgraph TCPIP_4_Layers [TCP/IP 四层工业体系]
        I4[应用层 Application]
        I3[传输层 Host-to-Host Transport]
        I2[网际层 Internet]
        I1[网络接口层 Network Access]
    end

    O7 --> T5 --> I4
    O6 --> T5
    O5 --> T5
    O4 --> T4 --> I3
    O3 --> T3 --> I2
    O2 --> T2 --> I1
    O1 --> T1 --> I1
```

#### OSI 各层核心职责与典型协议

| 层级 | 层名称 | 核心职责 | 典型协议与标准 | 常见网络设备 |
| :--- | :--- | :--- | :--- | :--- |
| **7** | **应用层 (Application)** | 为终端用户的应用程序直接提供网络服务接口。 | HTTP/HTTPS, DNS, SSH, FTP, SMTP, DHCP | 主机终端、应用网关 |
| **6** | **表示层 (Presentation)** | 数据格式转换、加密解密、压缩解压缩，确保异构系统语法可识。 | SSL/TLS, ASCII, UTF-8, JSON, JPEG | 终端操作系统运行库 |
| **5** | **会话层 (Session)** | 建立、管理和终止应用程序之间的通信会话，提供同步检查点。 | RPC, NetBIOS, SIP | 终端会话管理器 |
| **4** | **传输层 (Transport)** | 提供端到端（进程到进程）的逻辑通信、可靠性保证、流量控制与复用。 | TCP, UDP, QUIC, SCTP | 四层负载均衡器 (LVS) |
| **3** | **网络层 (Network)** | 负责逻辑寻址（IP）、数据分片与跨多网段的路径选择（路由转发）。 | IPv4, IPv6, ICMP, OSPF, BGP | 路由器 (Router)、三层交换机 |
| **2** | **数据链路层 (Data Link)** | 负责同一局域网（链路上）相邻节点间的帧封装、介质访问控制与差错检测。 | Ethernet (802.3), Wi-Fi (802.11), ARP, VLAN (802.1Q) | 二层交换机 (Switch)、网桥 (Bridge) |
| **1** | **物理层 (Physical)** | 在物理介质上透明传输无结构的原始比特流（定义电压、时钟、引脚）。 | 1000BASE-T, 光纤规程, RJ45, 曼彻斯特编码 | 中继器 (Repeater)、集线器 (Hub) |

> [!NOTE]
> 在实际生产开发（如 Linux 内核与 Web 开发）中，通常采用 **TCP/IP 四层/五层模型**。OSI 的会话层与表示层功能已全部融入现代应用层（例如 HTTPS 中的 TLS 握手及 Protobuf/JSON 序列化）。
>
> 上表的协议是按**功能**归层的，与“报文封装在谁里面”并不总是一致：OSPF 直接承载于 IP（协议号 89），BGP 则运行在 TCP 179 端口之上，但二者解决的都是网络层的选路问题；ARP 报文直接封装在以太网帧里，服务的却是 IP，通常被看作二、三层之间的“胶水”。

---

## 模块二：数据链路层与以太网帧

数据链路层解决的是局域网（LAN）内“**相邻节点之间如何可靠传输一个数据单元**”的问题。在现代局域网中，以太网（Ethernet）占据绝对统治地位。

### 2.1 MAC 地址体系

每块以太网网络接口卡（NIC）出厂时都烧录了一个设计上全局唯一的物理地址，称为 **MAC（Media Access Control）地址**：
- **长度与表示**：长度为 48 位（6 字节），采用 12 位十六进制数表示，形如 `08:00:27:1a:2b:3c`。
- **地址分配**：
  - 前 24 位（高位）：**OUI（Organizationally Unique Identifier，组织唯一标识符）**，由 IEEE 分配给网卡制造商。
  - 后 24 位（低位）：由厂商自行分配的网卡序列号。
- **三种寻址模式**：
  - **单播（Unicast）**：第一个字节的最低有效位（b0，称 I/G 位）为 `0`，发送给单一特定接口。
  - **组播（Multicast）**：第一个字节的最低有效位（b0）为 `1`，例如 IPv4 组播映射 MAC 地址段 `01:00:5E:xx:xx:xx`。
  - **广播（Broadcast）**：48 位全为 `1`，即 `FF:FF:FF:FF:FF:FF`，同一二层广播域内的所有主机均会接收并处理该帧。
- **全局管理与本地管理（U/L 位）**：第一个字节的次低位（b1）为 `0` 表示厂商烧录的全局唯一地址；为 `1` 表示**本地管理地址（Locally Administered Address）**，由操作系统或管理员自行指定，只要在所在局域网内不冲突即可。虚拟机、容器以及本课程大量使用的 veth 虚拟网卡，MAC 都是内核随机生成的本地管理单播地址，首字节的低两位固定为 `10`。所以你在实验里看到的 MAC，第二个十六进制数字一定是 `2`、`6`、`a`、`e` 之一（如 `ba:d6:9f:0e:7d:da`），也查不到对应的厂商 OUI。

---

### 2.2 以太网帧结构（Ethernet II）

工业界最主流的以太网帧标准为 **Ethernet II（DIX 帧）**：

```
+-------------------+---------------+------------------+------------------+-------------------+----------------------------+-----------------+
| 前导码 Preamble   | 起始符 SFD    | 目的 MAC (DMAC)  | 源 MAC (SMAC)    | 类型 (EtherType)  | 数据载荷 (Data Payload)    | 校验序列 (FCS)  |
| 7 字节            | 1 字节        | 6 字节           | 6 字节           | 2 字节            | 46 ~ 1500 字节             | 4 字节          |
+-------------------+---------------+------------------+------------------+-------------------+----------------------------+-----------------+
|<--- 物理层同步前导码 (8 字节) --->|<--------------------------- 经典以太网帧 (64 ~ 1518 字节) -------------------------->|
```

#### 字段详解

| 字段名称 | 字节大小 | 作用说明 |
| :--- | :--- | :--- |
| **Preamble (前导码)** | 7 字节 | 7 个 `10101010` 字节（共 56 位 1、0 交替），供接收方网卡锁定物理时钟频率、实现位同步。 |
| **SFD (帧起始定界符)** | 1 字节 | 二进制固定为 `10101011`，最后两位 `11` 标示前导码结束，下一比特进入真正的帧头。 |
| **Destination MAC** | 6 字节 | 接收端网卡的 MAC 地址。 |
| **Source MAC** | 6 字节 | 发送端网卡的 MAC 地址。 |
| **EtherType (类型)** | 2 字节 | 标识上层协议类型。常用值：<br>• `0x0800`：IPv4 协议<br>• `0x86DD`：IPv6 协议<br>• `0x0806`：ARP 协议<br>• `0x8100`：802.1Q VLAN 标签<br>取值不小于 `0x0600`（1536）才表示“类型”；不大于 1500 时，该字段在 IEEE 802.3 帧格式中表示“长度”。 |
| **Data Payload (载荷)** | 46~1500 字节 | 上层协议传递下来的数据包（如 IP 报文）。标准 MTU 为 1500 字节。如果载荷小于 46 字节，必须填充 Padding 字节至 46 字节。 |
| **FCS (帧校验序列)** | 4 字节 | 采用 CRC-32 循环冗余校验。发送方计算后写入，接收方重新校验，若不匹配则静默丢弃该帧。 |

> [!IMPORTANT]
> **为什么以太网帧的最小长度是 64 字节？（46 字节载荷 + 18 字节首部/尾部）**  
> 早期半双工以太网使用 CSMA/CD（载波侦听多路访问/冲突检测）机制。主机边发边听，为了确保发送方能在**帧发送完毕前**检测到最远距离传输发生的最坏碰撞，帧的**发送时延**必须不小于争用期（即端到端往返传播时延 $2\tau$）。10 Mbps 以太网按最大跨距约 2500 米（计入中继器时延）把争用期定为 51.2 μs，对应 $10\ \text{Mbps} \times 51.2\ \mu\text{s} = 512$ 比特，即 64 字节。虽然现代全双工交换以太网不再发生物理冲突，但为了协议向下兼容，64 字节最小帧长一直沿用至今。

> [!NOTE]
> **为什么抓包时会看到不足 64 字节的帧？**  
> `tcpdump` / Wireshark 显示的帧长不含前导码与 SFD，通常也不含 FCS：FCS 由网卡硬件在发送时追加、接收时校验并剥离，填充（Padding）同样由发送方的网卡或驱动完成，抓包点位于它们之上。而 veth 是纯软件设备，既不填充也不计算 FCS。因此在模块六的实验中，你会看到 ARP 帧只有 **42 字节**（14 字节帧头 + 28 字节 ARP 报文），`ping` 的帧是 **98 字节**（14 + 20 字节 IP 首部 + 8 字节 ICMP 首部 + 56 字节数据）。这不是错误，而是“线路上的帧”与“内核里的帧”之间的差别。

---

### 2.3 MTU 与巨型帧（Jumbo Frames）

- **MTU（Maximum Transmission Unit，最大传输单元）**：
  - 数据链路层对上层数据载荷的最大长度限制。
  - 标准以太网的 MTU 默认为 **1500 字节**。相应地，以太网帧的最大长度为 $1500 + 14 \text{ (帧头)} + 4 \text{ (FCS)} = 1518$ 字节（若带 802.1Q VLAN Tag 则为 1522 字节）。
  - 在 Linux 中，`ip link show` 输出里的 `mtu` 字段即接口 MTU：物理网卡与 veth 默认都是 1500，环回接口 `lo` 为 65536。
- **巨型帧（Jumbo Frames）**：
  - 在现代数据中心、高速局域网（10G/40G/100G）和存储区域网（iSCSI, RDMA）中，频繁处理 1500 字节小帧会给 CPU 带来巨大中断负荷。
  - 巨型帧通常把 MTU 扩大到 **9000 字节**（业界惯例，并非 IEEE 标准，各厂商支持的上限略有差异），显著降低协议开销与内核处理开销，提升吞吐量。**要求传输链路上所有网卡与交换机统一开启 Jumbo Frames 支持**。

---

### 2.4 ARP 协议（地址解析协议）

在局域网内，两台主机即便知道对方的 IP 地址，也无法直接发送二层以太网帧，必须先将 **目标 IP 映射为目标 MAC 地址**。这就是 ARP 协议（RFC 826）的核心作用。ARP 报文直接封装在以太网帧中（EtherType = `0x0806`），不经过 IP 层，因而无法穿越路由器——ARP 只能解析**同一网段内**的地址。

```mermaid
sequenceDiagram
    autonumber
    participant HostA as 主机 A (192.168.1.1)
    participant Switch as 二层交换机
    participant HostB as 主机 B (192.168.1.2)

    Note over HostA: 欲发数据给 192.168.1.2，但本地 ARP 缓存未命中
    HostA->>Switch: 广播 ARP Request: "谁有 192.168.1.2？请告诉 192.168.1.1(MAC_A)"<br/>(DMAC = FF:FF:FF:FF:FF:FF)
    Switch->>HostB: 泛洪该 ARP 请求帧（广播帧送往所有其他端口）
    Note over HostB: 检查发现目标 IP 是自己，记录 HostA 的 ARP 映射
    HostB-->>Switch: 单播 ARP Reply: "192.168.1.2 的 MAC 是 MAC_B"<br/>(DMAC = MAC_A, SMAC = MAC_B)
    Switch-->>HostA: 精准转发给 HostA
    Note over HostA: 更新本地 ARP 缓存表，开始发送数据帧
```

在 Linux 中，可以通过以下命令查看与管理 ARP 缓存：
```bash
# 查看本地邻居/ARP 缓存
ip neigh show
# 或使用经典命令（来自 net-tools 软件包，新版发行版默认不再安装）
arp -n
```

`ip neigh show` 每行末尾是该表项的状态。`REACHABLE` 表示近期确认过对方可达；一段时间（默认约 30 秒）没有新的确认就降为 `STALE`——表项仍然可用，但下次用它发包后会进入 `DELAY` / `PROBE`，由内核发一个**单播** ARP Request 向对方求证，无应答才置为 `FAILED`。所以抓包时偶尔冒出的单播 ARP 是内核在“复查”缓存，并非异常。

---

## 模块三：网络层与 IP 协议体系

网络层的核心目标是解决**异构网络互联与跨网络路由转发**问题，提供“无连接、尽最大努力交付（Best Effort）”的数据报传输服务。

### 3.1 IPv4 协议体系

#### 1. IPv4 地址结构与表示
- **长度**：32 位（4 字节），通常采用**点分十进制**表示，例如 `192.168.1.1`。
- **层次结构**：逻辑上划分为两部分：
  - **网络号（Network ID）**：标识该主机所属的网络段。
  - **主机号（Host ID）**：标识该特定网段内的独立主机接口。

#### 2. 经典分类寻址（Classful Addressing）

早期互联网将 IP 地址划分为五类：

| 类别 | 首字节高位特征 | 地址范围 | 默认子网掩码 | 适用网络类型 |
| :--- | :--- | :--- | :--- | :--- |
| **A 类** | `0...` | `1.0.0.0` ~ `126.255.255.255` | `255.0.0.0` (/8) | 超大型跨国网络（每个网络容纳 1677 万台主机） |
| **B 类** | `10...` | `128.0.0.0` ~ `191.255.255.255` | `255.255.0.0` (/16) | 中型园区网络（每个网络容纳 65534 台主机） |
| **C 类** | `110...` | `192.0.0.0` ~ `223.255.255.255` | `255.255.255.0` (/24) | 小型局域网（每个网络容纳 254 台主机） |
| **D 类** | `1110...` | `224.0.0.0` ~ `239.255.255.255` | 无 | 多播/组播专有地址（Multicast） |
| **E 类** | `1111...` | `240.0.0.0` ~ `255.255.255.255` | 无 | 保留科研实验与未来用途 |

> [!NOTE]
> `127.0.0.0/8` 段被保留用作本机环回接口（Loopback），最常见的是 `127.0.0.1` (`localhost`)。

#### 3. 私网地址与 NAT（网络地址转换）

为了缓解 IPv4 地址耗尽危机，RFC 1918 预留了三段专用私网地址（Private IP），这些地址在公共互联网路由器上不可路由：
- **A 类私网**：`10.0.0.0` ~ `10.255.255.255`（即 `10.0.0.0/8`）
- **B 类私网**：`172.16.0.0` ~ `172.31.255.255`（即 `172.16.0.0/12`）
- **C 类私网**：`192.168.0.0` ~ `192.168.255.255`（即 `192.168.0.0/16`）

内网设备访问互联网时，必须通过出口路由器部署的 **NAT（Network Address Translation / NAPT）** 将私网源 IP 转换为公网全局单播 IP。

#### 4. CIDR（无类别域间路由）与子网计算

分类寻址造成了巨大的地址块浪费。现代网络全面采用 **CIDR（Classless Inter-Domain Routing，最初由 RFC 1519 提出，现行规范为 RFC 4632）**，打破了 A/B/C 类刚性界限，使用任意长度的网络前缀（Slash 记法，如 `/24`）划分网络。

**计算实例**：分析 IP 地址 `192.168.1.100/26`
- **子网掩码**：前 26 位为 `1`，后 6 位为 `0` $\rightarrow$ `255.255.255.192`。
- **网络地址（Network ID）**：将 IP 与掩码按位与运算，主机位全置 `0` $\rightarrow$ `192.168.1.64`。
- **广播地址（Broadcast）**：主机位 6 位全置 `1` $\rightarrow$ `192.168.1.127`。
- **可用主机范围**：`192.168.1.65` ~ `192.168.1.126`（共 $2^6 - 2 = 62$ 个可用主机 IP）。

#### 5. 同网段判断：直接交付还是交给网关

主机拿到目的 IP 后要做的第一件事，是判断对方与自己是否在**同一网段**：用**本机接口的掩码**分别与本机 IP、目的 IP 做按位与，结果相同即为同网段。

- **同网段 → 直接交付**：对**目的 IP 本身**做 ARP，把帧直接发给对方。
- **不同网段 → 间接交付**：对**网关（下一跳）的 IP** 做 ARP，把帧发给路由器；IP 首部里的目的 IP 仍然是最终目的地（见 5.2 节）。

沿用上面的例子：对 `192.168.1.100/26` 这台主机来说，`192.168.1.120` 与它同网段（`120 & 192 = 64`），而 `192.168.1.130` 不是（`130 & 192 = 128`）——尽管三个地址的前三个字节一模一样。

Linux 用路由表来落实这个判断。给接口配上 `192.168.1.1/24` 的那一刻，内核会自动生成一条**直连路由**：

```
192.168.1.0/24 dev veth1 proto kernel scope link src 192.168.1.1
```

含义是“去往 `192.168.1.0/24` 的包直接从 `veth1` 发出，不需要网关”。如果路由表里没有任何一条能匹配目的地址，内核会直接报 `Network is unreachable`，连 ARP 都不会发。路由表的完整读法与最长前缀匹配是第 02 讲的主题，这里只需记住：**配 IP 的同时，也就配好了到本网段的路由。**

---

### 3.2 IPv4 报文格式剖析

IPv4 报文由 **IP 首部（20 ~ 60 字节）** 和 **数据载荷（Data Payload）** 组成。

#### IPv4 报头标准位图（按 32 位字长排布）

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|Version|  IHL  |Type of Service|          Total Length         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Identification        |Flags|     Fragment Offset     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Time to Live |    Protocol   |        Header Checksum        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Source IP Address                       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Destination IP Address                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Options                    |    Padding    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

#### IPv4 首部字段详解

| 字段名称 | 比特长度 | 功能与机制说明 |
| :--- | :--- | :--- |
| **Version (版本)** | 4 bits | 协议版本号。IPv4 固定为 `4`（二进制 `0100`）。 |
| **IHL (首部长度)** | 4 bits | Internet Header Length。以 **32 位字（4 字节）** 为计数单位。无选项时最小值为 `5`（即 $5 \times 4 = 20$ 字节），最大值为 `15`（即 60 字节）。 |
| **ToS / DSCP / ECN** | 8 bits | 服务类型/区分服务字段。前 6 位用于 DSCP（QoS 优先级），后 2 位用于 ECN（显式拥塞通知）。 |
| **Total Length (总长度)** | 16 bits | IP 报文整体长度（首部 + 数据载荷），以字节为单位。最大值为 $2^{16}-1 = 65535$ 字节。 |
| **Identification (标识)** | 16 bits | 发送端赋予每个数据包的唯一序列标识。同一数据包分片后，**所有分片拥有相同的标识值**。 |
| **Flags (标志)** | 3 bits | 控制分片行为：<br>• Bit 0：保留（必须置 0）<br>• Bit 1（**DF, Don't Fragment**）：置 1 表示不允许路由器分片，若包超 MTU 则丢弃并回复 ICMP 差错报文（Type 3 / Code 4，见 3.5 节）<br>• Bit 2（**MF, More Fragments**）：置 1 表示后续还有分片，置 0 表示这是最后一个分片 |
| **Fragment Offset (片偏移)** | 13 bits | 标识该分片在原始未分片数据载荷中的相对起始位置。以 **8 字节（64 位）** 为基本度量单位。 |
| **TTL (Time to Live)** | 8 bits | 数据报生存时间（路由器跳数上限）。每经过一个路由器，TTL 递减 1。**若 TTL 归零，路由器丢弃该包并向源地址发送 ICMP Time Exceeded 报文**，有效防止路由环路死循环。Linux 发包的默认初始值为 64（`net.ipv4.ip_default_ttl`），Windows 为 128。 |
| **Protocol (协议号)** | 8 bits | 指示载荷中封装的高层协议类型。常用值：<br>• `1`：ICMP<br>• `6`：TCP<br>• `17`：UDP<br>• `89`：OSPF |
| **Header Checksum (首部校验和)** | 16 bits | 专门校验 IP 首部是否发生比特翻转（不校验载荷数据）。每过一跳路由器，由于 TTL 递减，校验和必须重新计算。 |
| **Source IP Address** | 32 bits | 发送端主机的 IP 地址。 |
| **Destination IP Address** | 32 bits | 目标主机的 IP 地址。 |
| **Options & Padding** | 可变长度 | 可选字段（如安全标签、源路由、时间戳）。若选项长度非 4 字节整数倍，通过 Padding 补零填充对齐。 |

---

### 3.3 IP 分片与重组实战分析

当上层传递给 IP 层的报文总长度超过底层网络接口的 **MTU（通常为 1500 字节）** 时，IP 层必须启动分片（Fragmentation）。

**案例场景**：发送一个总长度为 4000 字节的 IPv4 数据报（20 字节 IP 头部 + 3980 字节数据载荷），通过 MTU = 1500 字节的以太网接口：

```
原始数据包:
[IP头: 20B][Payload: 3980 字节] (ID = 1000, Total Length = 4000)

分片计算过程 (除最后一片外，每个分片的载荷长度必须是 8 字节的整数倍):
• 最大载荷空间 = 1500 - 20 (新IP头) = 1480 字节 (1480 能被 8 整除)
• 分片 1: 载荷 1480 字节 (字节 0 ~ 1479)
• 分片 2: 载荷 1480 字节 (字节 1480 ~ 2959)
• 分片 3: 剩余载荷 3980 - 1480*2 = 1020 字节 (字节 2960 ~ 3979)
```

| 分片编号 | Total Length 字段 | Identification | Flags (DF, MF) | Fragment Offset 字段值 | 对应的载荷字节区间 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **分片 1** | 1500 字节 (20+1480) | 1000 | DF=0, **MF=1** | $0 / 8 = \mathbf{0}$ | 0 ~ 1479 |
| **分片 2** | 1500 字节 (20+1480) | 1000 | DF=0, **MF=1** | $1480 / 8 = \mathbf{185}$ | 1480 ~ 2959 |
| **分片 3** | 1040 字节 (20+1020) | 1000 | DF=0, **MF=0** | $2960 / 8 = \mathbf{370}$ | 2960 ~ 3979 |

> [!WARNING]
> **分片的工程弊端**：
> 1. **脆弱性倍增**：IP 协议本身不具备重传功能。任一分片在传输中丢失，目标端在重组超时后将丢弃全部已收到的分片，迫使上层（如 TCP）重传整个报文段。
> 2. **处理开销与兼容性**：分片与重组要消耗路由器的 CPU 和接收端的重组缓冲区；而且只有第一个分片带有传输层首部（端口号），防火墙、NAT 以及按五元组做负载均衡的设备都难以正确处理后续分片。
> 3. **工程上的对策是“干脆不分片”**：现代主机默认给 TCP 报文置 DF=1，并启用 **Path MTU Discovery（PMTUD，RFC 1191）**——路径上某台路由器发现报文超过下一跳 MTU 时将其丢弃，回送 ICMP “Fragmentation Needed”（Type 3 / Code 4，其中携带下一跳 MTU），源主机据此调小后续报文。TCP 还会在握手时用 MSS 选项告知对方自己能接收的最大报文段（见思考题 2）。IPv6 则更进一步，完全禁止路由器分片。

上面这张分片表不只是纸面推演：模块六的“选做观察 A”会在真实内核上把它原样抓出来。

---

### 3.4 IPv6 协议与下一代互联网

#### 1. IPv6 的演进动因与核心优势
- **巨大地址空间**：采用 **128 位地址**，可提供 $2^{128} \approx 3.4 \times 10^{38}$ 个独立地址，彻底解决地址枯竭问题。
- **定长简化头部**：基本头部固定为 **40 字节**，取消了变长 Options，改为模块化的**扩展首部（Extension Headers）**；同时取消了首部校验和，并禁止路由器分片（只允许源主机分片），大幅提高路由器硬件转发效率。
- **原生取消广播**：以更精准的组播（Multicast）和任播（Anycast）替代广播，彻底避免全网广播风暴。
- **即插即用（SLAAC）**：支持无状态地址自动配置，设备无需 DHCP 服务器即可自动配置网络。
- **免去 NAT**：恢复互联网最初端到端（End-to-End）直接对等通信的架构设计。
- **IPsec 支持**：IPsec 最初随 IPv6 一同设计，早期规范要求所有 IPv6 节点必须实现；自 RFC 6434 起已降为“建议支持”（SHOULD，现行规范为 RFC 8504）。如今 IPsec 在 IPv4 与 IPv6 上同样可用，“IPv6 天生比 IPv4 安全”的说法并不成立。

#### 2. IPv6 地址表示与压缩书写规则

IPv6 采用十六进制表示，分为 8 组，每组 16 位，组间以冒号 `:` 分隔：
- **完整格式**：`2001:0db8:85a3:0000:0000:8a2e:0370:7334`
- **压缩规则 1（前导零省略）**：每组内部的前导 `0` 可省略。例如 `:0000:` $\rightarrow$ `:0:`，`:0370:` $\rightarrow$ `:370:`。
- **压缩规则 2（双冒号压缩）**：连续多组全 `0` 可用双冒号 `::` 替换。**注意：为避免二义性，双冒号在一个地址中仅能出现一次**。
  - 示例 1：`2001:0db8:0000:0000:0000:ff00:0042:8329` $\rightarrow$ `2001:db8::ff00:42:8329`
  - 示例 2（环回地址）：`0000:0000:0000:0000:0000:0000:0000:0001` $\rightarrow$ `::1`
  - 示例 3（未指定地址）：`0000:...:0000` $\rightarrow$ `::`
- **规范写法（RFC 5952）**：十六进制字母一律小写；`::` 必须压缩最长的那一段全 `0`（等长时取第一段），且不用于只有单独一组 `0` 的情形。`ip addr` 等工具的输出都遵循这一写法。

#### 3. IPv6 地址分类

| 地址类型 | 前缀范围 | 作用与特征 | 对应 IPv4 概念 |
| :--- | :--- | :--- | :--- |
| **全球单播地址 (GUA)** | `2000::/3` | 公网全局唯一，互联网全局可路由。 | 公网 IPv4 地址 |
| **链路本地地址 (Link-Local)** | `fe80::/10` | 局域网链路内自动生成，不跨路由器路由。用于邻居发现与局域网引导。 | `169.254.0.0/16` (APIPA) |
| **唯一本地地址 (ULA)** | `fc00::/7` | 专用私网地址，在组织内部跨网段路由，不在公共互联网路由。 | RFC 1918 私网地址 (如 `10.0.0.0/8`) |
| **组播地址 (Multicast)** | `ff00::/8` | 发往特定订阅群组（如 `ff02::1` 为链路所有节点，`ff02::2` 为所有路由器）。 | IPv4 组播与广播 |
| **任播地址 (Anycast)** | 共享单播空间 | 多个接口配置同一任播地址，由路由协议路由至拓扑距离最近的一个节点。 | Anycast DNS / CDN 节点 |

#### 4. 邻居发现协议（NDP，Neighbor Discovery Protocol）

IPv6 完全弃用了 ARP 和广播，转而使用基于 ICMPv6 的 **NDP 协议** 实现链路层通信管理：
- **地址解析（替代 ARP）**：
  - **NS（Neighbor Solicitation，邻居请求）**：向目标地址对应的**被请求节点组播地址**（Solicited-Node Multicast，`ff02::1:ffXX:XXXX`）发送查询，只有极少数节点会被打扰；复查邻居可达性时则用单播。
  - **NA（Neighbor Advertisement，邻居通告）**：回复自身链路层 MAC 地址。
- **路由器发现与无状态自动配置（SLAAC）**：
  - **RS（Router Solicitation，路由器请求）**：主机开机接入网络时主动发送，请求网关信息。
  - **RA（Router Advertisement，路由器通告）**：路由器周期性地向“所有节点”组播地址 `ff02::1` 发送，或针对 RS 应答，携带网络前缀与默认网关信息。主机将该 64 位前缀与自身生成的 64 位接口 ID 组合，再做一次重复地址检测（DAD），即可完成全球单播地址的配置。

#### 5. IPv4 到 IPv6 的过渡演进机制

- **双栈技术（Dual Stack）**：路由器与终端主机同时配置 IPv4 和 IPv6 两种协议栈，自动根据对端能力适配。
- **隧道技术（Tunneling）**：将 IPv6 报文封装在 IPv4 报文中穿透纯 IPv4 骨干网络（如 6to4, GRE 隧道）。
- **网络转换（NAT64 / DNS64）**：在网关处进行协议头与地址翻译，允许纯 IPv6 主机透明访问纯 IPv4 服务器。

> [!NOTE]
> 本课程的实验统一使用 IPv4，但 IPv6 会在实验里“自己冒出来”：只要系统启用了 IPv6（Ubuntu 默认启用），接口一旦 UP，内核就会自动为它生成一个 `fe80::/10` 链路本地地址（`ip addr show` 输出中的 `inet6 fe80::… scope link` 一行），并发出几个 NDP / MLD 组播报文。抓包时看到 `IP6 … ICMP6, router solicitation` 之类的帧不必惊慌，用过滤表达式（如 `arp or icmp`）把它们滤掉即可。

---

### 3.5 ICMP：网络层的差错报告与诊断

IP 只负责“尽力而为”地转发，出了问题并不通知任何人。这个缺口由 **ICMP（Internet Control Message Protocol，RFC 792）** 补上：路由器或目的主机无法继续处理某个数据报时，用 ICMP 向**源主机**报告原因；`ping`、`traceroute` 等诊断工具也建立在它之上。ICMP 报文封装在 IP 数据报中（协议号 `1`），但功能上属于网络层的一部分。

每个 ICMP 报文以 **Type（1 字节）、Code（1 字节）、Checksum（2 字节）** 开头，Type 给出大类，Code 给出细分原因。本课程会反复遇到的只有下面几种：

| Type | Code | 含义 | 你会在哪里遇到它 |
| :--- | :--- | :--- | :--- |
| **8 / 0** | 0 | Echo Request / Echo Reply（回显请求 / 应答） | `ping` |
| **3** | 0 / 1 | Destination Unreachable：网络不可达 / 主机不可达 | 路由器查不到路由；最后一跳 ARP 无应答 |
| **3** | 3 | Destination Unreachable：端口不可达 | 目的主机上没有进程监听该 UDP 端口；`traceroute` 靠它判断“到站了” |
| **3** | 4 | Destination Unreachable：需要分片但 DF=1 | PMTUD（3.3 节） |
| **11** | 0 | Time Exceeded：TTL 减到 0 | `traceroute`（第 02 讲） |

两条设计细节值得留意：ICMP 差错报文会附带**出错数据报的 IP 首部及其后 8 字节**，源主机据此才能把差错对应到具体的连接；为避免雪崩，**不会针对一个 ICMP 差错报文再产生新的 ICMP 差错报文**。IPv6 的对应协议是 ICMPv6（协议号 `58`），它除了差错报告，还承担了 3.4 节的 NDP。

---

## 模块四：传输层与端到端传输

网络层提供的是“主机到主机（Host-to-Host）”的通信服务，而传输层则在套接字层面上实现了“**进程到进程**（Process-to-Process）”的端到端逻辑传输。

### 4.1 端口复用与套接字（Socket）

操作系统上运行着成百上千个并发进程。传输层利用 **16 位端口号（Port Number）** 实现多路复用与多路分用：
- 端口号范围：$0 \sim 65535$。
  - **熟知端口（Well-Known Ports）**：$0 \sim 1023$（系统级关键服务，如 HTTP 80, HTTPS 443, SSH 22, DNS 53）。
  - **注册端口（Registered Ports）**：$1024 \sim 49151$。
  - **动态/私有端口（Ephemeral Ports）**：$49152 \sim 65535$（客户端发起连接时系统临时随机分配）。这是 IANA 的建议范围（RFC 6335）；Linux 实际默认使用 $32768 \sim 60999$（`sysctl net.ipv4.ip_local_port_range`），模块六抓包时看到的客户端端口就落在这个区间。
- **网络通信五元组**：唯一确定一个网络连接的五项元数据：
  $$\text{Connection} = (\text{源 IP}, \text{源端口}, \text{目的 IP}, \text{目的端口}, \text{传输层协议})$$

---

### 4.2 TCP vs UDP 核心机制对比

| 对比维度 | TCP (Transmission Control Protocol) | UDP (User Datagram Protocol) |
| :--- | :--- | :--- |
| **连接状态** | **面向连接**（需经过三次握手建立连接，四次挥手拆除） | **无连接**（无需建链，随时直接发送数据） |
| **传输可靠性** | **可靠交付**（确认 ACK、超时重传、数据校验、按序重排；连接中断时向应用报错，而不是悄悄丢数据） | **尽力而为**（不保证递达、不保证有序、无重传机制） |
| **数据流形态** | **面向字节流（Byte Stream）**（应用层无边界，需自行分包） | **面向报文（Datagram）**（保留应用层报文边界） |
| **头部开销** | 基础首部 **20 字节**（带有选项最大可达 60 字节） | 基础首部仅 **8 字节** |
| **传输开销与时延** | 包含流控与拥塞控制算法，建链有 RTT 握手时延 | 无连接时延，即刻发送，实时性极高 |
| **典型应用场景** | Web 浏览 (HTTP/HTTPS)、文件传输 (FTP)、远程终端 (SSH)、数据库交互 | 实时音视频通话 (WebRTC)、DNS 查询、网络对战游戏、广播/多播 |

---

### 4.3 TCP 报文段结构深度解析

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Source Port          |       Destination Port        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Sequence Number                        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Acknowledgment Number                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Data |       |C|E|U|A|P|R|S|F|                               |
| Offset| Rsrvd |W|C|R|C|S|S|Y|I|            Window             |
|       |       |R|E|G|K|H|T|N|N|                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           Checksum            |        Urgent Pointer         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Options                    |    Padding    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                             data                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

上图依据现行 TCP 规范 **RFC 9293**（2022 年发布，取代了 1981 年的 RFC 793）绘制。RFC 793 的原图中保留位为 6 位、标志位只有 6 个，不少教材仍沿用旧图；多出来的 CWR、ECE 两个标志是 RFC 3168 为显式拥塞通知（ECN）新增的。

#### 关键字段剖析

| 字段名称 | 比特长度 | 详细功能说明 |
| :--- | :--- | :--- |
| **Source Port (源端口)** | 16 bits | 发送端应用程序的端口号。 |
| **Destination Port (目的端口)** | 16 bits | 接收端目标应用程序的端口号。 |
| **Sequence Number (序列号, Seq)** | 32 bits | 标识本报文段所发送数据载荷的**第一个字节的顺序编号**。在建立连接（SYN）时用来同步 Initial Sequence Number (ISN)。用于接收端按序拼接重组数据流。 |
| **Acknowledgment Number (确认号, Ack)** | 32 bits | 期望收到对方下一个报文段的第一个数据字节序号。**采用累积确认机制**，表示此序号之前的所有字节均已完整无误接收。 |
| **Data Offset (数据偏移)** | 4 bits | 标明 TCP 首部的长度（以 4 字节为单位）。标准 20 字节首部此字段为 `5`。 |
| **Reserved (保留位)** | 4 bits | 预留未来扩展，目前全部置 0。 |
| **Flags (控制标志位)** | 8 bits | 驱动 TCP 状态机转换的关键标志：<br>• **CWR / ECE**：与 IP 首部的 ECN 字段配合实现显式拥塞通知——接收方用 ECE 把“路上有设备打了拥塞标记”回传给发送方，发送方降速后用 CWR 告知对方（第 07 讲的 DCTCP 依赖这一机制）<br>• **URG**：紧急指针字段有效<br>• **ACK**：确认号字段有效（连接建立后所有报文该位均为 1）<br>• **PSH**：指示接收方尽快将缓冲区数据向上投递给应用程序<br>• **RST**：连接复位（遇到严重错误或连接非法时强制切断）<br>• **SYN**：同步序列号，在发起连接的三次握手阶段使用<br>• **FIN**：发送方完成数据发送，请求释放连接 |
| **Window Size (窗口大小)** | 16 bits | 流量控制核心指标。接收方向发送方通告当前允许对方连续发送的最大字节数（基于自身当前空闲接收缓冲区）。 |
| **Checksum (校验和)** | 16 bits | 包含伪首部（Pseudo Header）、TCP 首部和应用载荷的全量端到端数据完整性校验。 |
| **Urgent Pointer (紧急指针)** | 16 bits | 当 URG 标志置位时有效，指向紧急数据在载荷中的偏移末端。 |
| **Options (选项)** | 可变长度 | 协商高级特性：**MSS（最大报文段长度）**、SACK（选择性确认）、Window Scale（窗口扩大因子，突破 64KB 限制）、Timestamps（时间戳防回绕与精准 RTT 估算）。 |

---

### 4.4 TCP 连接管理：三次握手与四次挥手

“面向连接”的含义是：传数据之前，双方要先各自准备好一份连接状态（序号、窗口、选项），传完之后再有序地拆掉。下图是一次完整的短连接，客户端发送的正是模块五要追踪的那 10 个字节：

```mermaid
sequenceDiagram
    participant C as 客户端（主动打开）
    participant S as 服务端（LISTEN）

    Note over C,S: 三次握手：同步双方的初始序号
    C->>S: SYN, seq = x
    S->>C: SYN + ACK, seq = y, ack = x + 1
    C->>S: ACK, ack = y + 1
    Note over C,S: ESTABLISHED：传输数据
    C->>S: PSH + ACK, seq = x + 1, 数据 10 字节
    S->>C: ACK, ack = x + 11
    Note over C,S: 四次挥手：两个方向各自关闭
    C->>S: FIN + ACK, seq = x + 11
    S->>C: ACK, ack = x + 12
    S->>C: FIN + ACK, seq = y + 1
    C->>S: ACK, ack = y + 2
```

- **三次握手（Three-Way Handshake）**：双方各自随机选取一个初始序号（ISN，即图中的 `x` 与 `y`），并确认对方已经收到。SYN 虽然不携带数据，却要**占用一个序号**，所以对 `seq = x` 的确认号是 `x + 1`。MSS、SACK、Window Scale 等选项只能在带 SYN 的报文里协商。
- **为什么不是两次**：如果服务端一收到 SYN 就认定连接建立，那么一个在网络中滞留许久的**旧 SYN** 也会让它白白分配资源；第三次握手让服务端得以确认“客户端此刻确实想建立这条连接，并且收到了我的 ISN”。
- **四次挥手**：TCP 是全双工的，两个方向要各自关闭，FIN 同样占用一个序号。被动关闭的一方如果恰好也没有数据要发了，常把中间的 ACK 与自己的 FIN 合并成一个报文，所以抓包时往往只看到**三个**报文。主动关闭的一方最后要在 `TIME_WAIT` 状态停留一段时间（Linux 为 60 秒），以确保最后一个 ACK 丢失时还能重发，并让属于旧连接的报文在网络中自然消失。
- **可靠传输与窗口**：序号、累积确认加超时重传，保证字节流不丢、不重、不乱序。发送方同时受两个窗口约束：对方通告的**接收窗口**（流量控制，保护接收方的缓冲区）与自己维护的**拥塞窗口**（拥塞控制，保护网络）。后者是第 07 讲的主题，本讲不展开。

---

## 模块五：数据端到端传输全景剖析

为了将各层理论融会贯通，我们以最经典的教学案例进行端到端追踪：  
**“主机 A 向 主机 B 发送 10 字节字符串 `'Hello TCP!'`”**

这里假设 TCP 连接已按 4.4 节建立完毕；为了便于计算，还假设 TCP 首部不带任何选项（20 字节）。真实的 Linux 内核默认会带上 12 字节的时间戳选项，模块六的“选做观察 B”会让你亲眼看到这个差别。

### 5.1 数据逐层封装过程（Encapsulation）

在主机 A（发送端）的操作系统内核中，数据自顶向下经历层层封装：

```
[应用层 Application]       用户生成原始数据: "Hello TCP!" (10 字节)
                                       │
                                       ▼
[传输层 Transport]        +-------------+------------------+
                         | TCP 头 (20B)| "Hello TCP!"(10B)|  -> TCP Segment (共 30 字节)
                         +-------------+------------------+
                                       │
                                       ▼
[网络层 Network]   +-------------+-------------+------------------+
                   | IP 头 (20B) | TCP 头 (20B)| "Hello TCP!"(10B)|  -> IP Packet (共 50 字节)
                   +-------------+-------------+------------------+
                                       │
                                       ▼
[数据链路层 Data Link]
+-------------+-------------+-------------+------------------+-------------+
| 以太头 (14B)| IP 头 (20B) | TCP 头 (20B)| "Hello TCP!"(10B)| FCS 尾 (4B) | -> Ethernet Frame (共 68 字节)
+-------------+-------------+-------------+------------------+-------------+
                                       │
                                       ▼
[物理层 Physical]         网卡将 68 字节帧转换为物理高低电平或光脉冲信号编码发出
```

1. **应用层**：用户进程调用 `send()` 系统调用，写入 10 字节数据。
2. **传输层**：TCP 模块分配序号 `Seq`，填充源端口与目的端口，构造 20 字节 TCP 首部，组合成 30 字节的 TCP Segment。
3. **网络层**：IP 模块为报文装配 20 字节 IPv4 首部，写入主机 A 的源 IP 与主机 B 的目的 IP，TTL 设为 64，协议号置为 6（TCP），生成 50 字节 IP Packet；同时查路由表确定**下一跳**——B 与 A 同网段时下一跳就是 B 本身，否则是网关（3.1 节）。
4. **数据链路层**：查询本地 ARP 缓存表确定下一跳的 MAC 地址（未命中则先发起 2.4 节的 ARP 请求），装配 14 字节以太网帧头（目的 MAC、源 MAC、EtherType=`0x0800`），并计算追加 4 字节的 CRC-32 尾部校验和（FCS）。此时载荷 50 字节已大于 46 字节，无需额外 Padding，生成 68 字节的标准以太网帧。
5. **物理层**：网卡控制器在前追加 7 字节前导码与 1 字节 SFD，串行转化为物理电信号通过网线发射。

---

### 5.2 跨网段转发中的路由器行为

如果主机 A 与主机 B 处于不同子网，数据包必须经过中间路由器（Router）：

```mermaid
sequenceDiagram
    participant A as 主机 A
    participant R as 路由器 Router
    participant B as 主机 B

    Note over A,R: 局域网 1 (二层)
    A->>R: 帧 1: [DMAC=MAC_Router_In, SMAC=MAC_A | IP: A -> B | TCP | Data]

    Note over R: 1. 网卡收到帧，FCS 校验通过<br/>2. 检查 DMAC 匹配自身接口，剥除二层以太网头<br/>3. 网络层提取 IP 包，查路由表匹配下一跳<br/>4. TTL 递减 1，更新 IP Header Checksum<br/>5. 查 ARP 表获得主机 B 的 MAC 地址<br/>6. 重新封装新的二层帧头

    Note over R,B: 局域网 2 (二层)
    R->>B: 帧 2: [DMAC=MAC_B, SMAC=MAC_Router_Out | IP: A -> B | TCP | Data]
```

> [!IMPORTANT]
> **在传统无 NAT 的路由转发过程中**：
> - **IP 首部的源 IP 和目的 IP 始终保持不变**（全程指向端到端两端主机）；
> - **每跨越一跳路由器，二层帧头的源 MAC 与目的 MAC 都会被彻底刷新**（始终只标示当前一跳链路的发送者与接收者）；
> - **IP 首部并非一字不变**：每经过一跳，TTL 减 1，首部校验和随之重算。

---

### 5.3 接收端逐层解封装（De-encapsulation）

在主机 B 侧，硬件网卡到操作系统的解封装步骤严格逆向执行：
1. **物理层**：网卡物理层芯片同步时钟，识别帧定界符，将信号还原为比特流。
2. **数据链路层**：
   - 校验 FCS：网卡硬件重新计算 CRC，若有误码则直接丢弃；
   - 匹配目的 MAC：确认是送往自身的单播帧、广播帧，或本机已加入的组播组的帧；
   - 剥除以太网头尾，根据 EtherType = `0x0800`，将 50 字节的 IP 包分发给内核网络层处理。
3. **网络层**：
   - 校验 IP 头部校验和；
   - 检查目的 IP 确实是本机接口 IP；
   - 剥除 IP 头部，根据 Protocol = 6，将 30 字节的 TCP Segment 递交传输层。
4. **传输层**：
   - 校验 TCP 首部与数据校验和；
   - 校验序列号 `Seq`，确认数据有序；
   - 向主机 A 构造并回送确认报文（ACK）；
   - 根据目的端口号定位对应的监听 Socket，将 10 字节数据放入该 Socket 的接收缓冲区。
5. **应用层**：目标应用程序通过 `recv()` 或 `read()` 从缓冲区读取 `"Hello TCP!"`。

---

## 模块六：Linux 网络命名空间与虚拟化实操

在云计算与容器技术（如 Docker、Kubernetes）中，隔离不同租户的网络环境并不需要物理网卡，而是依赖 Linux 内核提供的 **Network Namespace（网络命名空间）**。

### 6.1 什么是 Network Namespace？

**Network Namespace（netns）** 是 Linux 内核提供的网络协议栈级逻辑隔离机制。当创建一个独立的 netns 时，它拥有完全私有且隔离的：
- **网络设备（Network Interfaces）**：拥有独立的网卡（如虚拟的 `veth`、`eth0`、`lo` 回环设备）。
- **IP 协议栈与地址**：可配置独立的 IPv4/IPv6 地址。
- **路由表（Routing Tables）**：各 namespace 间路由互不相干。
- **端口空间（Socket Ports）**：不同 namespace 内的进程可以同时监听同一个端口（如 `0.0.0.0:80`）而毫无冲突。
- **ARP/邻居表（Neighbor Table）**。
- **防火墙规则（iptables / nftables）**。
- **大部分内核网络参数（`sysctl net.*`）**：例如决定“本机是否转发 IP 包”的 `net.ipv4.ip_forward` 就是每个 namespace 各有一份，第 02 讲会用它把一个 namespace 变成路由器。

```mermaid
graph TD
    subgraph Host_Root_NS [Host 根网络命名空间 Default NS]
        eth0[物理网卡 eth0]
        lo0[回环 lo]
        rt0[宿主机路由表]
    end

    subgraph Netns_1 [命名空间 ns1]
        veth1[虚拟网卡 veth1: 192.168.1.1/24]
        lo1[回环 lo]
        rt1[ns1 私有路由表]
    end

    subgraph Netns_2 [命名空间 ns2]
        veth2[虚拟网卡 veth2: 192.168.1.2/24]
        lo2[回环 lo]
        rt2[ns2 私有路由表]
    end

    veth1 <== "veth pair：一根虚拟网线" ==> veth2
```

---

### 6.2 虚拟线缆：veth pair 工作原理

两个隔离的 namespace 之间无法直接通信，正如两台断网的物理机。Linux 提供了 **veth（Virtual Ethernet）网卡对**：
- `veth` 设备总是**成对创建**（Peer）。
- 可以把 `veth pair` 形象地理解为**一根虚拟的双绞线（网线）**：从一端输入的所有数据包，都会直接从另一端被内核原封不动地送出。
- 将 `veth` 对的两端分别置入不同的 namespace 中，便建立了一条直连的点对点链路。

---

### 6.3 常用 `ip netns` 命令集

在现代 Linux 系统中，使用 `iproute2` 工具集的 `ip` 命令进行管理：

```bash
# 1. 创建命名空间
sudo ip netns add <ns_name>

# 2. 列出系统当前所有命名空间
ip netns list

# 3. 在指定命名空间内部执行命令
sudo ip netns exec <ns_name> <command>

# 4. 删除指定命名空间 (其中的虚拟网卡会自动被清理或回退到根命名空间)
sudo ip netns del <ns_name>

# 5. 简写: ip 自身的子命令可以用 -n 指定命名空间, 下面两条完全等价
sudo ip netns exec <ns_name> ip addr show
sudo ip -n <ns_name> addr show
```

`ping`、`tcpdump` 等其他命令没有这个简写，仍需写成 `ip netns exec <ns_name> <command>`。本讲为了让“命令在哪个 namespace 里执行”一目了然，统一使用完整写法；第 02 讲起会大量使用 `ip -n`。

---

### 6.4 动手实验：搭建双节点隔离互通环境

下面我们将使用标准的 `iproute2` 命令从零搭建两个互通的 Namespace，并使用 `ping` 与 `tcpdump` 验证网络层与链路层行为。

> [!NOTE]
> **实验环境**：一台 Linux 主机或虚拟机（要求见 [`2026/README.md`](../README.md) 的“实验环境”一节），需要 `iproute2`、`iputils-ping`、`tcpdump`；选做观察 B 另需 `nc`（Ubuntu 自带的 `netcat-openbsd` 即可）。Network Namespace 是 Linux 内核特性，macOS / Windows 用户请在 Linux 虚拟机中操作。下文的输出均为实测结果，其中 MAC 地址、接口编号、端口号、序号与时间戳每次运行都不同，以你自己看到的为准。

#### 步骤一：创建拓扑与虚拟网卡

```bash
# 1. 创建两个独立的网络命名空间 ns1 与 ns2
sudo ip netns add ns1
sudo ip netns add ns2

# 2. 创建一对 veth 设备: 一端命名为 veth1，另一端命名为 veth2
sudo ip link add veth1 type veth peer name veth2

# 3. 将 veth1 塞入 ns1，将 veth2 塞入 ns2
sudo ip link set veth1 netns ns1
sudo ip link set veth2 netns ns2
```

#### 步骤二：配置 IP 地址并激活接口

```bash
# 4. 激活 ns1 和 ns2 内部的本地回环接口 (lo)
sudo ip netns exec ns1 ip link set lo up
sudo ip netns exec ns2 ip link set lo up

# 5. 为 ns1 的 veth1 配置 IP: 192.168.1.1/24 并启动
sudo ip netns exec ns1 ip addr add 192.168.1.1/24 dev veth1
sudo ip netns exec ns1 ip link set veth1 up

# 6. 为 ns2 的 veth2 配置 IP: 192.168.1.2/24 并启动
sudo ip netns exec ns2 ip addr add 192.168.1.2/24 dev veth2
sudo ip netns exec ns2 ip link set veth2 up
```

#### 步骤三：验证连通性

```bash
# 7. 在 ns1 内部查看当前网络接口状态
sudo ip netns exec ns1 ip addr show
```

```
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
10: veth1@if9: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default qlen 1000
    link/ether ba:d6:9f:0e:7d:da brd ff:ff:ff:ff:ff:ff link-netns ns2
    inet 192.168.1.1/24 scope global veth1
       valid_lft forever preferred_lft forever
```

几处值得细看：`veth1@if9` 与行尾的 `link-netns ns2` 说明这块网卡的对端是 ns2 里编号为 9 的接口，这是 veth 成对存在的直接证据；`link/ether` 后面是内核随机生成的 MAC，第二个十六进制数字是 `a`，符合 2.1 节本地管理地址的规律；`mtu 1500` 与 2.3 节一致。如果系统启用了 IPv6，`veth1` 下还会多出一行 `inet6 fe80::…/64 scope link`，即 3.4 节的链路本地地址。

**预测一下再往下看**：我们只配了 IP 地址，没有加过任何路由。此时 ns1 的路由表是空的吗？

```bash
# 8. 查看 ns1 的路由表
sudo ip netns exec ns1 ip route show
```

```
192.168.1.0/24 dev veth1 proto kernel scope link src 192.168.1.1
```

这就是 3.1 节所说的直连路由，`proto kernel` 表明它是第 5 步配 IP 时由内核自动添加的。有了它，去往 `192.168.1.2` 的包才知道应该从 `veth1` 发出。

```bash
# 9. 连通性测试: 从 ns1 发送 ICMP 请求到 ns2
sudo ip netns exec ns1 ping -c 3 192.168.1.2
```

```
PING 192.168.1.2 (192.168.1.2) 56(84) bytes of data.
64 bytes from 192.168.1.2: icmp_seq=1 ttl=64 time=0.030 ms
64 bytes from 192.168.1.2: icmp_seq=2 ttl=64 time=0.038 ms
64 bytes from 192.168.1.2: icmp_seq=3 ttl=64 time=0.036 ms

--- 192.168.1.2 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss, time 2048ms
```

读懂这几行：`56(84) bytes of data` 指 56 字节 ICMP 数据，加上 8 字节 ICMP 首部与 20 字节 IP 首部共 84 字节；每行回复里的 `64 bytes` 是 ICMP 首部加数据的长度；`ttl=64` 是**对方的回复包**到达本机时的 TTL，直连链路上没有经过任何路由器，所以仍是初始值 64（第 02 讲里每多一跳它就少 1）；`time` 是往返时延（RTT），在同一个内核里转一圈只需要几十微秒。

```bash
# 10. 查看 ns1 内部自动学习到的 ARP 邻居表
sudo ip netns exec ns1 ip neigh show
```

```
192.168.1.2 dev veth1 lladdr 3e:fb:bd:fb:27:d2 REACHABLE
```

#### 步骤四：抓包观察 ARP 与逐层封装

刚才的 `ping` 已经让双方的 ARP 缓存里有了对方，这时再抓包是看不到 ARP 广播的。先把缓存清空，让整个过程从头发生一遍。

**预测一下再往下看**：清空缓存后只 `ping` 一次，链路上一共会出现几个帧？先后顺序如何？每个帧的目的 MAC 分别是什么？

```bash
# 11. 清空两侧的 ARP 缓存
sudo ip netns exec ns1 ip neigh flush all
sudo ip netns exec ns2 ip neigh flush all

# 12. 终端 1: 在 ns2 内抓包 (-n 不做域名解析, -e 显示以太网帧头; 过滤表达式只保留 ARP 与 ICMP)
sudo ip netns exec ns2 tcpdump -n -e -i veth2 arp or icmp

# 13. 终端 2: 在 ns1 内 ping 一次; 然后回到终端 1 等待约 10 秒, 再按 Ctrl+C 结束抓包
sudo ip netns exec ns1 ping -c 1 192.168.1.2
```

终端 1 的实测输出：

```
01:42:00.065004 ba:d6:9f:0e:7d:da > ff:ff:ff:ff:ff:ff, ethertype ARP (0x0806), length 42: Request who-has 192.168.1.2 tell 192.168.1.1, length 28
01:42:00.065012 3e:fb:bd:fb:27:d2 > ba:d6:9f:0e:7d:da, ethertype ARP (0x0806), length 42: Reply 192.168.1.2 is-at 3e:fb:bd:fb:27:d2, length 28
01:42:00.065014 ba:d6:9f:0e:7d:da > 3e:fb:bd:fb:27:d2, ethertype IPv4 (0x0800), length 98: 192.168.1.1 > 192.168.1.2: ICMP echo request, id 1270, seq 1, length 64
01:42:00.065021 3e:fb:bd:fb:27:d2 > ba:d6:9f:0e:7d:da, ethertype IPv4 (0x0800), length 98: 192.168.1.2 > 192.168.1.1: ICMP echo reply, id 1270, seq 1, length 64
01:42:05.268871 3e:fb:bd:fb:27:d2 > ba:d6:9f:0e:7d:da, ethertype ARP (0x0806), length 42: Request who-has 192.168.1.1 tell 192.168.1.2, length 28
01:42:05.268890 ba:d6:9f:0e:7d:da > 3e:fb:bd:fb:27:d2, ethertype ARP (0x0806), length 42: Reply 192.168.1.1 is-at ba:d6:9f:0e:7d:da, length 28
```

对照前面各模块来读这六行：

1. **第 1 帧**：ns1 广播 ARP Request（目的 MAC 为 `ff:ff:ff:ff:ff:ff`），询问谁是 `192.168.1.2`；
2. **第 2 帧**：ns2 **单播** ARP Reply，给出 `veth2` 的 MAC；
3. **第 3、4 帧**：ICMP Echo Request 与 Echo Reply。EtherType 从 `0x0806` 变成了 `0x0800`，帧头里的源、目的 MAC 正是刚刚解析出来的那一对；
4. **第 5、6 帧**（约 5 秒之后）：ns2 向 ns1 发了一个**单播** ARP Request。ns2 是从第 1 帧里“顺便”记下 ns1 的 MAC 的，这条表项从未经过确认；用它回复了 ICMP 之后，内核便按 2.4 节的状态机主动复查一次；
5. **帧长**：ARP 帧 42 字节、ICMP 帧 98 字节，都不含 FCS，ARP 帧也没有被填充到 64 字节，原因见 2.2 节。

#### 步骤五：选做观察——让纸面算例在内核里重演

下面两个观察分别把 3.3 节与模块五的算例搬到真实内核上，做法都是“先预测、再测量、最后解释差异”。课堂时间不够可以留到课后。

**选做观察 A：亲手抓到 IP 分片。** 3.3 节的算例是一个 4000 字节的 IP 数据报通过 MTU 为 1500 的链路。`ping -s 3972` 恰好能造出这样一个数据报：3972 字节数据 + 8 字节 ICMP 首部 + 20 字节 IP 首部 = 4000 字节。

**预测一下再往下看**：抓包会看到几个分片？各自的总长度、偏移量与 MF 标志是什么？

```bash
# 14. 终端 1: 在 ns2 内抓包 (-v 显示 IP 首部细节; 只看 ns1 发来的方向)
sudo ip netns exec ns2 tcpdump -n -v -i veth2 'ip and src 192.168.1.1'

# 15. 终端 2: 发送一个总长 4000 字节的 IP 数据报
sudo ip netns exec ns1 ping -c 1 -s 3972 192.168.1.2
```

```
01:42:11.573167 IP (tos 0x0, ttl 64, id 35846, offset 0, flags [+], proto ICMP (1), length 1500)
    192.168.1.1 > 192.168.1.2: ICMP echo request, id 1276, seq 1, length 1480
01:42:11.573176 IP (tos 0x0, ttl 64, id 35846, offset 1480, flags [+], proto ICMP (1), length 1500)
    192.168.1.1 > 192.168.1.2: ip-proto-1
01:42:11.573177 IP (tos 0x0, ttl 64, id 35846, offset 2960, flags [none], proto ICMP (1), length 1040)
    192.168.1.1 > 192.168.1.2: ip-proto-1
```

与 3.3 节的表逐项对照：三个分片的 `id` 相同；`length` 依次为 1500 / 1500 / 1040；`flags [+]` 即 MF=1，最后一片是 `[none]`；`offset` 为 0 / 1480 / 2960——`tcpdump` 已经替你换算成了字节，首部里实际存放的值要除以 8，即 0 / 185 / 370。后两片显示为 `ip-proto-1` 而不是 `ICMP echo request`，是因为 ICMP 首部只存在于第一片，`tcpdump` 无从解析，这正是 3.3 节所说“后续分片不带上层首部”的直观体现。

```bash
# 16. 置 DF=1 (-M do) 再试: 1472 + 8 + 20 = 1500 恰好等于 MTU, 1473 则超出 1 字节
sudo ip netns exec ns1 ping -c 1 -M do -s 1472 192.168.1.2
sudo ip netns exec ns1 ping -c 1 -M do -s 1473 192.168.1.2
```

第一条正常收到回复；第二条在本机就被拒绝，报文根本没有发出去：

```
ping: local error: message too long, mtu=1500
```

**选做观察 B：把 “Hello TCP!” 真的发一遍。** 按 5.1 节的计算，承载 “Hello TCP!” 的以太网帧是 68 字节，去掉抓包时看不到的 4 字节 FCS，应为 64 字节。

**预测一下再往下看**：实测的帧长会是 64 字节吗？在这个数据帧之前和之后，链路上还会出现哪些报文？

```bash
# 17. 终端 1: 在 ns2 内抓 TCP 报文
sudo ip netns exec ns2 tcpdump -n -e -i veth2 tcp

# 18. 终端 2: 在 ns2 内启动一个监听 9000 端口的 TCP 服务端
sudo ip netns exec ns2 nc -l 9000

# 19. 终端 3: 从 ns1 连接并发送 10 个字节 (printf 不追加换行; -N 表示输入结束后关闭连接)
printf 'Hello TCP!' | sudo ip netns exec ns1 nc -N 192.168.1.2 9000
```

终端 2 会打印出 `Hello TCP!` 然后退出。终端 1 的实测输出如下（为便于阅读，删去了每行开头的时间戳、MAC 地址与 EtherType，时间戳选项的具体数值以 `…` 代替）：

```
length 74: 192.168.1.1.43404 > 192.168.1.2.9000: Flags [S], seq 1087888725, win 64240, options [mss 1460,sackOK,TS val … ecr 0,nop,wscale 10], length 0
length 74: 192.168.1.2.9000 > 192.168.1.1.43404: Flags [S.], seq 2663815566, ack 1087888726, win 65160, options [mss 1460,sackOK,TS val … ecr …,nop,wscale 10], length 0
length 66: 192.168.1.1.43404 > 192.168.1.2.9000: Flags [.], ack 1, win 63, options [nop,nop,TS val … ecr …], length 0
length 76: 192.168.1.1.43404 > 192.168.1.2.9000: Flags [P.], seq 1:11, ack 1, win 63, options [nop,nop,TS val … ecr …], length 10
length 66: 192.168.1.2.9000 > 192.168.1.1.43404: Flags [.], ack 11, win 64, options [nop,nop,TS val … ecr …], length 0
length 66: 192.168.1.1.43404 > 192.168.1.2.9000: Flags [F.], seq 11, ack 1, win 63, options [nop,nop,TS val … ecr …], length 0
length 66: 192.168.1.2.9000 > 192.168.1.1.43404: Flags [F.], seq 1, ack 12, win 64, options [nop,nop,TS val … ecr …], length 0
length 66: 192.168.1.1.43404 > 192.168.1.2.9000: Flags [.], ack 2, win 63, options [nop,nop,TS val … ecr …], length 0
```

- **握手**：前三行依次是 `[S]`、`[S.]`、`[.]`（`tcpdump` 用 `.` 表示 ACK），即 SYN、SYN + ACK、ACK。第二行的 `ack 1087888726` 恰好是第一行的 `seq` 加 1。握手完成后 `tcpdump` 改为显示相对序号，所以数据报文是 `seq 1:11`，即第 1 到第 10 个字节。双方在 SYN 里通告的 `mss 1460` 正是思考题 2 的答案。
- **帧长**：数据帧是 **76 字节**，不是 64 字节。多出来的 12 字节是 TCP 首部里的时间戳选项（`nop,nop,TS val … ecr …`，共 1 + 1 + 10 字节），真实的 TCP 首部是 32 字节而非 20 字节：$14 + 20 + 32 + 10 = 76$。SYN 报文携带的选项更多，首部达到 40 字节，所以帧长是 74 字节。
- **端口**：客户端端口 `43404` 由内核临时分配，落在 4.1 节所说的 32768–60999 区间内。
- **挥手**：最后三行是 `[F.]`、`[F.]`、`[.]`。服务端把“对客户端 FIN 的确认”与“自己的 FIN”合并成了一个报文，四次挥手在这里只用了三个报文（4.4 节）。

#### 步骤六：环境清理（Teardown）

```bash
# 20. 只需删除 namespace，附着在其上的 veth 设备会被 Linux 自动回收销毁
sudo ip netns del ns1
sudo ip netns del ns2

# 21. 确认已清理干净 (应当没有任何输出)
ip netns list
```

---

## 模块七：课后思考与拓展

通过理论与动手实验，请尝试回答以下深度思考题：

1. **MAC 与 IP 的双重必要性**：
   - 既然以太网帧通过 MAC 地址寻址，为什么通信还需要 IP 地址？如果全球所有设备只使用 MAC 地址，路由器能否正常工作？
   - *思考提示：MAC 地址是扁平非层次化的，无法实现跨大洲、跨网络的高效聚合路由（路由表将无限膨胀爆炸）。*
2. **MTU 与 TCP MSS 的联动**：
   - 当我们在以太网中传输数据（MTU = 1500 字节）时，TCP 的最大报文段大小（MSS, Maximum Segment Size）在不带可选头部时推荐配置为多少字节？为什么？
   - *思考提示：$1500 - 20 \text{ (IP Header)} - 20 \text{ (TCP Header)} = 1460$ 字节。*
3. **veth pair 跨网段路由思考**：
   - 若将 `veth1` 配置为 `192.168.1.1/24`，`veth2` 配置为 `10.0.0.1/24`，直接执行 `ping 10.0.0.1` 能否成功？如果失败，除了配置 IP 外，操作系统还需要什么规则（路由表、ARP 响应）？
   - *思考提示：在模块六的拓扑上改一下地址，亲手试一试，先看 `ip route show`。ns1 的路由表里只有 `192.168.1.0/24` 这一条直连路由，没有任何条目能匹配 `10.0.0.1`，内核会直接报 `Network is unreachable`，一个帧都不会发出去。给 ns1 补一条 `ip route add 10.0.0.0/24 dev veth1` 之后，抓包能看到 ARP 与 ICMP 请求都到达了 ns2，却仍然收不到回复——想一想 ns2 的路由表里缺了什么。“去程通了还不够，回程也要有路”正是第 02 讲的核心。*
4. **命名空间与容器云**：
   - Docker 容器中的 `-p 8080:80` 端口映射本质上利用了 Linux 内核的哪两项核心特性？
   - *思考提示：Network Namespace（网络隔离）与 iptables / NAT（宿主机端口流量重定向）。*
5. **一根网线的极限**：
   - veth 总是成对出现，一根“线”只能连接两个 namespace。如果要让 ns1、ns2、ns3 三个 namespace 处在同一个网段 `192.168.1.0/24` 里两两互通，只靠 veth 能做到吗？还缺一个什么样的设备？
   - *思考提示：回想 1.2 节表格里数据链路层的“常见网络设备”一栏。Linux 内核自带这种设备的软件实现，它是第 02 讲的第一个主角。*

---

### 拓展学习资料与后续实验

- **下一讲**：二层交换与静态路由——同一个网段里的多台主机靠什么连在一起，不同网段之间的包又是怎样被一跳一跳送到目的地的。
- **后续衔接实验**：
  - Lab 1：从一根虚拟网线到多跳网络（本讲与下一讲的配套实验）
- **核心网络规范 (RFCs)**：
  - **IEEE 802.3**: *Ethernet*（帧格式与最小 / 最大帧长；非 RFC）
  - RFC 826: *An Ethernet Address Resolution Protocol*（ARP）
  - RFC 894: *A Standard for the Transmission of IP Datagrams over Ethernet Networks*（IP 数据报如何封装进以太网帧）
  - RFC 791: *Internet Protocol (IPv4)*
  - RFC 792: *Internet Control Message Protocol*（ICMP）
  - RFC 1191: *Path MTU Discovery*
  - RFC 1918: *Address Allocation for Private Internets*（私网地址）
  - RFC 4632: *Classless Inter-domain Routing (CIDR)*（取代 RFC 1519）
  - RFC 8200: *Internet Protocol, Version 6 (IPv6) Specification*
  - RFC 4291: *IP Version 6 Addressing Architecture*；RFC 5952: *A Recommendation for IPv6 Address Text Representation*
  - RFC 4861: *Neighbor Discovery for IP version 6 (IPv6)*；RFC 4862: *IPv6 Stateless Address Autoconfiguration*
  - RFC 9293: *Transmission Control Protocol (TCP)*（取代 RFC 793）
  - RFC 768: *User Datagram Protocol*
  - RFC 3168: *The Addition of Explicit Congestion Notification (ECN) to IP*
