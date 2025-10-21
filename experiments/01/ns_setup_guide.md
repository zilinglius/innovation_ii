# Linux 网络命名空间线性拓扑设置脚本说明

## Linux 环境准备

在开始网络实验之前，需要确保您的 Linux 环境满足以下要求并完成必要的准备工作。

### 系统要求

#### 支持的操作系统
- **Ubuntu**: 18.04+ 
- **CentOS/RHEL**: 7+
- **Debian**: 9+
- **Fedora**: 28+
- **Arch Linux**: 最新版本

#### 内核版本要求
```bash
# 检查内核版本（需要 3.8+ 支持网络命名空间）
uname -r
```
建议使用 4.0+ 内核以获得更好的网络虚拟化支持。

### 必需的软件包

#### Ubuntu/Debian 系统
```bash
# 更新软件包列表
sudo apt update

# 安装必需的网络工具
sudo apt install -y iproute2 iputils-ping net-tools tcpdump iptables

# 可选：安装网络分析工具
sudo apt install -y wireshark-common iperf3 nmap traceroute
```

### 权限配置

#### 用户权限设置
```bash
# 检查当前用户是否在 sudo 组中
groups $USER

# 如果不在 sudo 组中，添加用户到 sudo 组（需要管理员权限）
sudo usermod -aG sudo $USER

# 重新登录或使用以下命令刷新组成员资格
newgrp sudo
```

#### SELinux 配置（CentOS/RHEL）
```bash
# 检查 SELinux 状态
sestatus

# 如果启用了 SELinux，可能需要临时设置为 permissive 模式
sudo setenforce 0

# 或者永久禁用（重启后生效）
sudo sed -i 's/SELINUX=enforcing/SELINUX=disabled/g' /etc/selinux/config
```

### 内核模块检查

#### 验证网络命名空间支持
```bash
# 检查网络命名空间功能是否可用
ls /proc/*/ns/net | head -5

# 检查是否可以创建网络命名空间
sudo ip netns list

# 测试创建临时命名空间
sudo ip netns add test_ns
sudo ip netns del test_ns
```

#### 检查必需的内核模块
```bash
# 检查 veth 模块支持
lsmod | grep veth

# 如果没有加载，手动加载
sudo modprobe veth

# 检查桥接模块
lsmod | grep bridge
sudo modprobe bridge
```

### 网络配置检查

#### 检查现有网络配置
```bash
# 查看现有网络接口
ip addr show

# 查看路由表
ip route show

# 查看网络命名空间列表（应为空或仅有默认命名空间）
sudo ip netns list
```

#### IP 转发配置
```bash
# 检查系统级 IP 转发状态
cat /proc/sys/net/ipv4/ip_forward

# 如果需要全局启用 IP 转发（可选，脚本中会在特定命名空间中启用）
# echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.conf
# sudo sysctl -p
```

### 防火墙配置

#### Ubuntu/Debian (UFW)
```bash
# 检查 UFW 状态
sudo ufw status

# 如果启用了 UFW，可能需要临时禁用或配置规则
# sudo ufw disable  # 谨慎使用
```

#### CentOS/RHEL (firewalld)
```bash
# 检查 firewalld 状态
sudo systemctl status firewalld

# 如果需要，可以临时停止防火墙
# sudo systemctl stop firewalld  # 谨慎使用
```

#### iptables
```bash
# 查看当前 iptables 规则
sudo iptables -L

# 如果有复杂的防火墙规则，可能需要备份现有规则
sudo iptables-save > ~/iptables-backup.txt
```

### 环境验证脚本

创建一个简单的环境检查脚本：

```bash
#!/bin/bash
# env_check.sh - 环境检查脚本

echo "=== Linux 网络实验环境检查 ==="

# 检查内核版本
echo "1. 内核版本检查:"
uname -r

# 检查必需命令
echo -e "\n2. 必需命令检查:"
commands=("ip" "ping" "tcpdump" "iptables")
for cmd in "${commands[@]}"; do
    if command -v "$cmd" &> /dev/null; then
        echo "✓ $cmd: 已安装"
    else
        echo "✗ $cmd: 未安装"
    fi
done

# 检查权限
echo -e "\n3. 权限检查:"
if [ "$EUID" -eq 0 ]; then
    echo "✓ 当前以 root 用户运行"
elif groups | grep -q sudo; then
    echo "✓ 当前用户在 sudo 组中"
else
    echo "✗ 需要 sudo 权限"
fi

# 检查网络命名空间支持
echo -e "\n4. 网络命名空间支持检查:"
if [ -d "/var/run/netns" ] || mkdir -p /var/run/netns 2>/dev/null; then
    echo "✓ 支持网络命名空间"
else
    echo "✗ 不支持网络命名空间"
fi

# 检查 IP 转发
echo -e "\n5. IP 转发状态:"
if [ "$(cat /proc/sys/net/ipv4/ip_forward)" = "1" ]; then
    echo "✓ IP 转发已启用"
else
    echo "! IP 转发未启用（脚本会在特定命名空间中启用）"
fi

echo -e "\n=== 检查完成 ==="
```

### 故障排除

#### 常见问题及解决方案

1. **权限不足**
   ```bash
   # 确保使用 sudo 执行需要管理员权限的命令
   sudo ip netns add test
   ```

2. **命令未找到**
   ```bash
   # 安装缺失的工具包
   sudo apt install iproute2  # Ubuntu/Debian
   sudo yum install iproute   # CentOS/RHEL
   ```

3. **网络命名空间不支持**
   ```bash
   # 检查内核配置
   grep CONFIG_NET_NS /boot/config-$(uname -r)
   # 应该显示 CONFIG_NET_NS=y
   ```

4. **模块加载失败**
   ```bash
   # 手动加载必需模块
   sudo modprobe veth
   sudo modprobe bridge
   ```

### 实验环境隔离建议

1. **使用虚拟机**: 建议在虚拟机中进行实验，避免影响主系统
2. **系统快照**: 实验前创建系统快照，方便快速恢复
3. **资源清理**: 实验后及时清理网络命名空间和虚拟接口
4. **日志记录**: 保留实验日志，便于问题排查和学习回顾

完成以上环境准备后，您就可以开始进行网络命名空间实验了。

## 概述

本脚本 `ns.sh` 创建了一个简单的三节点线性网络拓扑，使用 Linux 网络命名空间（Network Namespaces）和虚拟以太网对（veth pairs）来模拟分布式网络环境。这种设置常用于网络实验、协议测试和分布式系统开发。

## 网络拓扑结构

```
ns1 --(veth12a)-- (veth12b)ns2(veth23a) --(veth23b)-- ns3
10.0.12.1/30  <->  10.0.12.2/30
                   10.0.23.1/30  <->  10.0.23.2/30
```

### 拓扑详细说明

- **三个网络命名空间**: `ns1`, `ns2`, `ns3`
- **两对虚拟以太网接口**:
  - `veth12a` (ns1) ↔ `veth12b` (ns2)
  - `veth23a` (ns2) ↔ `veth23b` (ns3)
- **IP 地址分配**:
  - ns1: `10.0.12.1/30` (网段: 10.0.12.0/30)
  - ns2: `10.0.12.2/30` 和 `10.0.23.1/30`
  - ns3: `10.0.23.2/30` (网段: 10.0.23.0/30)

## 脚本功能详解

### 1. 变量定义

```bash
NS1=ns1     # 第一个命名空间
NS2=ns2     # 第二个命名空间（路由器角色）
NS3=ns3     # 第三个命名空间

V12A=veth12a   # ns1 中的接口
V12B=veth12b   # ns2 中的接口
V23A=veth23a   # ns2 中的接口
V23B=veth23b   # ns3 中的接口
```

### 2. 工具函数

- `exists_ns()`: 检查网络命名空间是否存在
- `exists_link()`: 检查网络接口是否存在
- `cleanup()`: 清理所有创建的资源

### 3. 错误处理

脚本使用 `set -Eeuo pipefail` 确保严格的错误处理，并在出错时自动清理资源：

```bash
trap 'echo "[!] 出错，清理资源..." ; cleanup' ERR
```

### 4. 主要操作步骤

#### 步骤 1: 创建网络命名空间
```bash
ip netns add "$NS1"
ip netns add "$NS2"
ip netns add "$NS3"
```

#### 步骤 2: 创建和配置 veth 对
```bash
# 创建第一对 veth
ip link add "$V12A" type veth peer name "$V12B"
ip link set "$V12A" netns "$NS1"
ip link set "$V12B" netns "$NS2"

# 创建第二对 veth
ip link add "$V23A" type veth peer name "$V23B"
ip link set "$V23A" netns "$NS2"
ip link set "$V23B" netns "$NS3"
```

#### 步骤 3: 配置 IP 地址
每个命名空间中的接口都被分配相应的 IP 地址，并启用接口。

```bash
# ns1 配置
ip -n "$NS1" link set lo up
ip -n "$NS1" addr add "$IP1A" dev "$V12A"     # 添加 10.0.12.1/30
ip -n "$NS1" link set "$V12A" up

# ns2 配置（双接口）
ip -n "$NS2" link set lo up
ip -n "$NS2" addr add "$IP2A" dev "$V12B"     # 添加 10.0.12.2/30
ip -n "$NS2" link set "$V12B" up
ip -n "$NS2" addr add "$IP2B" dev "$V23A"     # 添加 10.0.23.1/30
ip -n "$NS2" link set "$V23A" up

# ns3 配置
ip -n "$NS3" link set lo up
ip -n "$NS3" addr add "$IP3B" dev "$V23B"     # 添加 10.0.23.2/30
ip -n "$NS3" link set "$V23B" up
```

#### 步骤 4: 启用 IP 转发
在 `ns2` 中启用 IP 转发功能，使其可以作为路由器转发数据包：
```bash
ip netns exec "$NS2" sysctl -w net.ipv4.ip_forward=1
```

#### 步骤 5: 配置静态路由
- ns1 通过 ns2 访问 ns3 的网段
- ns3 通过 ns2 访问 ns1 的网段

```bash
# ns1 访问 10.0.23.0/30（ns2-ns3 链路）走 ns2
ip -n "$NS1" route add 10.0.23.0/30 via 10.0.12.2 dev "$V12A"

# ns3 访问 10.0.12.0/30（ns1-ns2 链路）走 ns2
ip -n "$NS3" route add 10.0.12.0/30 via 10.0.23.1 dev "$V23B"
```

### 5. 连通性测试

脚本自动执行以下测试：
- ns1 → ns2 直连测试
- ns2 → ns3 直连测试
- ns1 → ns3 跨节点测试（通过 ns2 转发）
- ns3 → ns1 跨节点测试（通过 ns2 转发）

```bash
# 连通性测试代码
set +e  # 暂时关闭严格错误处理，允许 ping 失败
ip netns exec "$NS1" ping -c 1 -W 1 10.0.12.2 >/dev/null && echo "ns1 → ns2 OK" || echo "ns1 → ns2 FAIL"
ip netns exec "$NS2" ping -c 1 -W 1 10.0.23.2 >/dev/null && echo "ns2 → ns3 OK" || echo "ns2 → ns3 FAIL"
ip netns exec "$NS1" ping -c 1 -W 1 10.0.23.2 >/dev/null && echo "ns1 → ns3 OK (经 ns2)" || echo "ns1 → ns3 FAIL"
ip netns exec "$NS3" ping -c 1 -W 1 10.0.12.1 >/dev/null && echo "ns3 → ns1 OK (经 ns2)" || echo "ns3 → ns1 FAIL"
set -e  # 重新启用严格错误处理
```

**测试参数说明**：
- `-c 1`: 只发送一个 ping 包
- `-W 1`: 等待响应超时时间为 1 秒
- `>/dev/null`: 隐藏 ping 输出，只显示测试结果

## 使用方法

### 创建拓扑
```bash
sudo bash ns.sh
```

### 清理拓扑
```bash
sudo bash ns.sh down
```

## 实用命令

### 查看命名空间状态
```bash
# 列出所有网络命名空间
ip netns list

# 查看各命名空间的网络接口
ip -n ns1 addr
ip -n ns2 addr
ip -n ns3 addr

# 查看路由表
ip -n ns1 route
ip -n ns2 route
ip -n ns3 route
```

### 在命名空间中执行命令
```bash
# 在 ns1 中执行 ping 命令
ip netns exec ns1 ping 10.0.23.2

# 在 ns2 中查看网络统计
ip netns exec ns2 netstat -i

# 在 ns3 中启动网络服务
ip netns exec ns3 python3 -m http.server 8080
```

## 网络原理说明

### CIDR 表示法
- `/30` 表示前 30 位是网络地址，后 2 位是主机地址
- 每个 /30 网段可容纳 4 个地址（网络地址、广播地址、2个主机地址）

### 路由工作原理
1. **直连路由**: 同一网段内的通信无需额外路由
2. **静态路由**: 不同网段间通过配置的路由表进行转发
3. **IP 转发**: ns2 作为路由器，需要启用 IP 转发功能

## 应用场景

1. **网络协议测试**: 模拟多节点网络环境
2. **分布式系统开发**: 在本地模拟分布式部署
3. **网络安全实验**: 隔离的网络环境进行安全测试
4. **容器网络研究**: 理解容器网络的底层实现
5. **SDN 实验**: 软件定义网络的基础实验平台

## 注意事项

1. **权限要求**: 脚本需要 root 权限执行
2. **资源清理**: 实验完成后记得清理资源
3. **端口冲突**: 确保使用的 IP 地址段不与现有网络冲突
4. **防火墙**: 某些系统可能需要调整防火墙规则

## 故障排除

### 常见问题

1. **权限不足**: 确保使用 `sudo` 执行
2. **资源残留**: 运行清理命令或重启系统
3. **IP 冲突**: 检查现有网络配置，避免地址冲突

### 调试命令

```bash
# 检查接口状态
ip -n ns1 link show
ip -n ns2 link show
ip -n ns3 link show

# 查看 ARP 表
ip -n ns1 neigh
ip -n ns2 neigh
ip -n ns3 neigh

# 抓包分析
ip netns exec ns1 tcpdump -i veth12a icmp
```

## 扩展建议

1. **添加更多节点**: 扩展为星型或网格拓扑
2. **引入动态路由**: 使用 OSPF 或 BGP 协议
3. **网络性能测试**: 使用 iperf3 进行带宽测试
4. **安全增强**: 添加 iptables 规则和网络隔离
5. **监控集成**: 添加网络监控和日志收集