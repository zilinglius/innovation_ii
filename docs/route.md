# 路由与实验讲解

## 一、路由的基本概念与原理

### 1. 什么是路由？
- **路由（Routing）** 是指数据包从源主机到目标主机，在多个网络之间选择合适的路径并转发的过程。
- 如果两个主机在同一个局域网内，它们通过 **ARP 解析 + 直接二层通信** 就能完成数据传输，不需要路由。
- 当目标不在本地子网时，操作系统会查找 **路由表（Routing Table）**，决定将数据包交给哪个“下一跳（Next Hop）”。

### 2. 路由表的结构
路由表是一张规则表，每一条规则包含以下主要字段：
- **目标网络（Destination Network）**：例如 `10.0.23.0/24`。
- **子网掩码（Netmask）**：用于判断某个 IP 是否属于该网络。
- **下一跳（Next Hop）**：数据包应当转发到哪个路由器/网关。
- **出接口（Interface）**：通过哪个网卡发出。
- **优先级（Metric）**：当有多条可用路径时，选择代价最低的一条。

例子（Linux `ip route show` 输出）：
```
default via 192.168.1.1 dev eth0
192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.100
10.0.0.0/8 via 192.168.1.254 dev eth0
```

解释：
- 到未知网络的流量，默认交给网关 `192.168.1.1`。
- 本机 `192.168.1.100` 所在的子网，直接从 `eth0` 发出。
- 到达 `10.0.0.0/8` 网络时，转发到 `192.168.1.254`。

### 3. 最长前缀匹配原则（Longest Prefix Match）
- 当有多条路由规则可以匹配目标 IP 时，系统会选择 **网络掩码最长**（也就是更具体）的那条。
- 例如：
  ```
  0.0.0.0/0         → 默认路由
  10.0.0.0/8        → 大范围路由
  10.1.0.0/16       → 更具体
  10.1.1.0/24       → 最具体
  ```
  目的 IP 为 `10.1.1.5` 时，将选择 `10.1.1.0/24` 这一条。

### 4. 主机路由与网络路由
- **主机路由（Host Route）**：掩码为 `/32`，表示只匹配某个特定 IP。例如 `10.0.0.5/32`。
- **网络路由（Network Route）**：匹配一整个子网，例如 `10.0.0.0/24`。
- **默认路由（Default Route）**：`0.0.0.0/0`，匹配所有未被明确指定的目的网络。

### 5. 路由转发过程
一次数据转发的流程：
1. 主机生成数据包，检查目的 IP。
2. 操作系统查找路由表，寻找匹配规则（最长前缀匹配）。
3. 确定下一跳地址和出接口。
4. 如果下一跳在同一局域网，发送 ARP 请求获得其 MAC 地址。
5. 数据包封装到二层帧，通过网卡发出。
6. 下一跳路由器收到后，重复相同过程，直到数据包到达目的主机。

### 6. 路由分类
- **静态路由（Static Routing）**
  - 由管理员手动配置。
  - 简单、可控，但无法适应网络拓扑变化。
- **动态路由（Dynamic Routing）**
  - 由路由协议自动学习和更新，如 RIP、OSPF、BGP。
  - 能够适应网络变化，适合大规模网络。
- **策略路由（Policy Routing）**
  - 不仅基于目的 IP，还可以基于源地址、端口号、协议等条件选择路径。

---

## 二、实验目标
通过 **Linux network namespace**，搭建一个简单的三节点网络拓扑，配置路由规则，让三个节点互通：

```
ns1 --- ns2 --- ns3
```

- 每个节点是一个独立的 network namespace。
- 使用 veth pair 作为链路。
- 配置 IP 地址和路由表，验证连通性。

---

## 三、实验环境准备

### 1. 创建命名空间
```bash
ip netns add ns1
ip netns add ns2
ip netns add ns3
```

### 2. 创建 veth pair 并连接命名空间
```bash
# ns1 <-> ns2
ip link add veth-ns1 type veth peer name veth-ns2-1
ip link set veth-ns1 netns ns1
ip link set veth-ns2-1 netns ns2

# ns2 <-> ns3
ip link add veth-ns2-2 type veth peer name veth-ns3
ip link set veth-ns2-2 netns ns2
ip link set veth-ns3 netns ns3
```

### 3. 分配 IP 地址
```bash
# ns1
ip netns exec ns1 ip addr add 10.0.12.1/24 dev veth-ns1
ip netns exec ns1 ip link set veth-ns1 up
ip netns exec ns1 ip link set lo up

# ns2
ip netns exec ns2 ip addr add 10.0.12.2/24 dev veth-ns2-1
ip netns exec ns2 ip addr add 10.0.23.2/24 dev veth-ns2-2
ip netns exec ns2 ip link set veth-ns2-1 up
ip netns exec ns2 ip link set veth-ns2-2 up
ip netns exec ns2 ip link set lo up

# ns3
ip netns exec ns3 ip addr add 10.0.23.3/24 dev veth-ns3
ip netns exec ns3 ip link set veth-ns3 up
ip netns exec ns3 ip link set lo up
```

---

## 四、路由配置

### 1. 配置默认路由
```bash
# 在 ns1 中，配置到 ns3 的路由，下一跳为 ns2
ip netns exec ns1 ip route add 10.0.23.0/24 via 10.0.12.2

# 在 ns3 中，配置到 ns1 的路由，下一跳为 ns2
ip netns exec ns3 ip route add 10.0.12.0/24 via 10.0.23.2
```

### 2. 验证路由表
```bash
ip netns exec ns1 ip route show
ip netns exec ns2 ip route show
ip netns exec ns3 ip route show
```

---

## 五、实验验证

### 1. 连通性测试
```bash
# ns1 ping ns2
ip netns exec ns1 ping -c 3 10.0.12.2

# ns1 ping ns3 （经过 ns2 转发）
ip netns exec ns1 ping -c 3 10.0.23.3
```

### 2. 抓包验证
```bash
# 在 ns2 上抓包，观察转发的数据包
ip netns exec ns2 tcpdump -i veth-ns2-1 icmp
```

---

## 六、思考题
1. 如果没有配置路由，ns1 能否 ping 通 ns3？为什么？
2. 如何扩展拓扑，加入第四个节点 ns4？
3. 如果想让 ns2 不转发数据包，应该修改什么参数？

---

## 七、总结
- 本实验展示了 **路由表在数据转发中的作用**。
- 通过 network namespace 搭建了最小实验环境。
- 掌握了 **IP 地址分配、路由配置和验证方法**。
