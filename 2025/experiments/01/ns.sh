#!/usr/bin/env bash
set -Eeuo pipefail

# 环型拓扑：5个命名空间组成环形网络
# ns1 --(veth12a)-- (veth12b)ns2 --(veth23a)-- (veth23b)ns3 --(veth34a)-- (veth34b)ns4 --(veth45a)-- (veth45b)ns5 --(veth51a)-- (veth51b)ns1
# 每个链接使用独立的 /30 子网

NS1=ns1
NS2=ns2
NS3=ns3
NS4=ns4
NS5=ns5

# veth接口对
V12A=veth12a   # in ns1
V12B=veth12b   # in ns2
V23A=veth23a   # in ns2
V23B=veth23b   # in ns3
V34A=veth34a   # in ns3
V34B=veth34b   # in ns4
V45A=veth45a   # in ns4
V45B=veth45b   # in ns5
V51A=veth51a   # in ns5
V51B=veth51b   # in ns1

# IP地址分配 (每个/30网段提供2个可用地址)
IP1A=10.0.12.1/30   # ns1-ns2链接
IP2A=10.0.12.2/30

IP2B=10.0.23.1/30   # ns2-ns3链接
IP3A=10.0.23.2/30

IP3B=10.0.34.1/30   # ns3-ns4链接
IP4A=10.0.34.2/30

IP4B=10.0.45.1/30   # ns4-ns5链接
IP5A=10.0.45.2/30

IP5B=10.0.51.1/30   # ns5-ns1链接
IP1B=10.0.51.2/30

# 小工具函数
exists_ns () { ip netns list | awk '{print $1}' | grep -qx "$1"; }
exists_link () { ip link show "$1" &>/dev/null; }

cleanup () {
  set +e
  # 尝试删除我们创建的 veth（无论是否在某个 ns 里）
  for L in "$V12A" "$V12B" "$V23A" "$V23B" "$V34A" "$V34B" "$V45A" "$V45B" "$V51A" "$V51B"; do
    if exists_link "$L"; then ip link del "$L" || true; fi
    # 也尝试在各 ns 内删除（避免残留）
    for N in "$NS1" "$NS2" "$NS3" "$NS4" "$NS5"; do
      if exists_ns "$N"; then ip -n "$N" link del "$L" 2>/dev/null || true; fi
    done
  done
  # 删除 netns
  for N in "$NS1" "$NS2" "$NS3" "$NS4" "$NS5"; do
    if exists_ns "$N"; then ip netns del "$N" || true; fi
  done
}
trap 'echo "[!] 出错，清理资源..." ; cleanup' ERR

if [[ "${1:-}" == "down" ]]; then
  echo "[*] 清理已创建的 namespace 与 veth..."
  cleanup
  echo "[*] 完成清理。"
  exit 0
fi

# 预清理同名资源，确保可重复执行
cleanup || true

echo "[*] 创建 namespaces..."
ip netns add "$NS1"
ip netns add "$NS2"
ip netns add "$NS3"
ip netns add "$NS4"
ip netns add "$NS5"

echo "[*] 创建 veth 并分配到各 ns..."
# ns1-ns2 链接
ip link add "$V12A" type veth peer name "$V12B"
ip link set "$V12A" netns "$NS1"
ip link set "$V12B" netns "$NS2"

# ns2-ns3 链接
ip link add "$V23A" type veth peer name "$V23B"
ip link set "$V23A" netns "$NS2"
ip link set "$V23B" netns "$NS3"

# ns3-ns4 链接
ip link add "$V34A" type veth peer name "$V34B"
ip link set "$V34A" netns "$NS3"
ip link set "$V34B" netns "$NS4"

# ns4-ns5 链接
ip link add "$V45A" type veth peer name "$V45B"
ip link set "$V45A" netns "$NS4"
ip link set "$V45B" netns "$NS5"

# ns5-ns1 链接 (完成环)
ip link add "$V51A" type veth peer name "$V51B"
ip link set "$V51A" netns "$NS5"
ip link set "$V51B" netns "$NS1"

echo "[*] 启动 lo 并配置地址..."
# ns1 (连接到 ns2 和 ns5)
ip -n "$NS1" link set lo up
ip -n "$NS1" addr add "$IP1A" dev "$V12A"
ip -n "$NS1" link set "$V12A" up
ip -n "$NS1" addr add "$IP1B" dev "$V51B"
ip -n "$NS1" link set "$V51B" up

# ns2 (连接到 ns1 和 ns3)
ip -n "$NS2" link set lo up
ip -n "$NS2" addr add "$IP2A" dev "$V12B"
ip -n "$NS2" link set "$V12B" up
ip -n "$NS2" addr add "$IP2B" dev "$V23A"
ip -n "$NS2" link set "$V23A" up

# ns3 (连接到 ns2 和 ns4)
ip -n "$NS3" link set lo up
ip -n "$NS3" addr add "$IP3A" dev "$V23B"
ip -n "$NS3" link set "$V23B" up
ip -n "$NS3" addr add "$IP3B" dev "$V34A"
ip -n "$NS3" link set "$V34A" up

# ns4 (连接到 ns3 和 ns5)
ip -n "$NS4" link set lo up
ip -n "$NS4" addr add "$IP4A" dev "$V34B"
ip -n "$NS4" link set "$V34B" up
ip -n "$NS4" addr add "$IP4B" dev "$V45A"
ip -n "$NS4" link set "$V45A" up

# ns5 (连接到 ns4 和 ns1)
ip -n "$NS5" link set lo up
ip -n "$NS5" addr add "$IP5A" dev "$V45B"
ip -n "$NS5" link set "$V45B" up
ip -n "$NS5" addr add "$IP5B" dev "$V51A"
ip -n "$NS5" link set "$V51A" up

echo "[*] 在所有命名空间开启 IPv4 转发..."
for N in "$NS1" "$NS2" "$NS3" "$NS4" "$NS5"; do
  ip netns exec "$N" sysctl -w net.ipv4.ip_forward=1 >/dev/null
done

echo "[*] 配置静态路由：构建完整的环型路由表..."
# ns1 的路由配置
ip -n "$NS1" route add 10.0.23.0/30 via 10.0.12.2 dev "$V12A"    # 通过 ns2 到达 ns2-ns3 链路
ip -n "$NS1" route add 10.0.34.0/30 via 10.0.12.2 dev "$V12A"    # 通过 ns2 到达 ns3-ns4 链路
ip -n "$NS1" route add 10.0.45.0/30 via 10.0.51.1 dev "$V51B"    # 通过 ns5 到达 ns4-ns5 链路

# ns2 的路由配置
ip -n "$NS2" route add 10.0.34.0/30 via 10.0.23.2 dev "$V23A"    # 通过 ns3 到达 ns3-ns4 链路
ip -n "$NS2" route add 10.0.45.0/30 via 10.0.23.2 dev "$V23A"    # 通过 ns3 到达 ns4-ns5 链路
ip -n "$NS2" route add 10.0.51.0/30 via 10.0.12.1 dev "$V12B"    # 通过 ns1 到达 ns5-ns1 链路

# ns3 的路由配置
ip -n "$NS3" route add 10.0.45.0/30 via 10.0.34.2 dev "$V34A"    # 通过 ns4 到达 ns4-ns5 链路
ip -n "$NS3" route add 10.0.51.0/30 via 10.0.34.2 dev "$V34A"    # 通过 ns4 到达 ns5-ns1 链路
ip -n "$NS3" route add 10.0.12.0/30 via 10.0.23.1 dev "$V23B"    # 通过 ns2 到达 ns1-ns2 链路

# ns4 的路由配置
ip -n "$NS4" route add 10.0.51.0/30 via 10.0.45.2 dev "$V45A"    # 通过 ns5 到达 ns5-ns1 链路
ip -n "$NS4" route add 10.0.12.0/30 via 10.0.45.2 dev "$V45A"    # 通过 ns5 到达 ns1-ns2 链路
ip -n "$NS4" route add 10.0.23.0/30 via 10.0.34.1 dev "$V34B"    # 通过 ns3 到达 ns2-ns3 链路

# ns5 的路由配置
ip -n "$NS5" route add 10.0.12.0/30 via 10.0.51.2 dev "$V51A"    # 通过 ns1 到达 ns1-ns2 链路
ip -n "$NS5" route add 10.0.23.0/30 via 10.0.51.2 dev "$V51A"    # 通过 ns1 到达 ns2-ns3 链路
ip -n "$NS5" route add 10.0.34.0/30 via 10.0.45.1 dev "$V45B"    # 通过 ns4 到达 ns3-ns4 链路

echo "[*] 拓扑就绪。环型网络连通性测试..."
set +e
# 相邻节点直连测试
ip netns exec "$NS1" ping -c 1 -W 1 10.0.12.2 >/dev/null && echo "ns1 → ns2 OK (直连)" || echo "ns1 → ns2 FAIL"
ip netns exec "$NS2" ping -c 1 -W 1 10.0.23.2 >/dev/null && echo "ns2 → ns3 OK (直连)" || echo "ns2 → ns3 FAIL"
ip netns exec "$NS3" ping -c 1 -W 1 10.0.34.2 >/dev/null && echo "ns3 → ns4 OK (直连)" || echo "ns3 → ns4 FAIL"
ip netns exec "$NS4" ping -c 1 -W 1 10.0.45.2 >/dev/null && echo "ns4 → ns5 OK (直连)" || echo "ns4 → ns5 FAIL"
ip netns exec "$NS5" ping -c 1 -W 1 10.0.51.2 >/dev/null && echo "ns5 → ns1 OK (直连)" || echo "ns5 → ns1 FAIL"

# 跨节点测试（顺时针方向）
ip netns exec "$NS1" ping -c 1 -W 1 10.0.23.2 >/dev/null && echo "ns1 → ns3 OK (经 ns2)" || echo "ns1 → ns3 FAIL"
ip netns exec "$NS1" ping -c 1 -W 1 10.0.34.2 >/dev/null && echo "ns1 → ns4 OK (经 ns2,ns3)" || echo "ns1 → ns4 FAIL"
ip netns exec "$NS1" ping -c 1 -W 1 10.0.45.2 >/dev/null && echo "ns1 → ns5 OK (经 ns2,ns3,ns4)" || echo "ns1 → ns5 FAIL"

# 跨节点测试（逆时针方向）
ip netns exec "$NS3" ping -c 1 -W 1 10.0.51.2 >/dev/null && echo "ns3 → ns5 OK (经 ns4,ns5)" || echo "ns3 → ns5 FAIL"
ip netns exec "$NS4" ping -c 1 -W 1 10.0.12.2 >/dev/null && echo "ns4 → ns2 OK (经 ns5,ns1)" || echo "ns4 → ns2 FAIL"

# 最远节点测试（对角线）
ip netns exec "$NS1" ping -c 1 -W 1 10.0.34.2 >/dev/null && echo "ns1 → ns4 OK (最远节点)" || echo "ns1 → ns4 FAIL"
ip netns exec "$NS2" ping -c 1 -W 1 10.0.45.2 >/dev/null && echo "ns2 → ns5 OK (最远节点)" || echo "ns2 → ns5 FAIL"

set -e

cat <<EOF

[*] 完成！

当前环型拓扑：
  $NS1 -- $NS2 -- $NS3 -- $NS4 -- $NS5 -- $NS1

接口配置：
  $NS1: $V12A=10.0.12.1/30, $V51B=10.0.51.2/30
  $NS2: $V12B=10.0.12.2/30, $V23A=10.0.23.1/30
  $NS3: $V23B=10.0.23.2/30, $V34A=10.0.34.1/30
  $NS4: $V34B=10.0.34.2/30, $V45A=10.0.45.1/30
  $NS5: $V45B=10.0.45.2/30, $V51A=10.0.51.1/30

常用查看命令：
  ip netns list
  ip -n $NS1 addr ; ip -n $NS2 addr ; ip -n $NS3 addr ; ip -n $NS4 addr ; ip -n $NS5 addr
  ip -n $NS1 route ; ip -n $NS2 route ; ip -n $NS3 route ; ip -n $NS4 route ; ip -n $NS5 route

环型测试命令：
  ip netns exec $NS1 ping 10.0.34.2  # ns1 → ns4 (最远节点)
  ip netns exec $NS2 ping 10.0.45.2  # ns2 → ns5 (最远节点)
  ip netns exec $NS3 ping 10.0.51.2  # ns3 → ns1 (逆时针)

清理命令：
  sudo bash $(basename "$0") down
EOF
