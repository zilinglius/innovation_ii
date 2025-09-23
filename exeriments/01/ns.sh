#!/usr/bin/env bash
set -Eeuo pipefail

# 线型拓扑：
# ns1 --(veth12a)-- (veth12b)ns2 (veth23a) --(veth23b)-- ns3
# 10.0.12.1/30 <-> 10.0.12.2/30
# 10.0.23.1/30 <-> 10.0.23.2/30

NS1=ns1
NS2=ns2
NS3=ns3

V12A=veth12a   # in ns1
V12B=veth12b   # in ns2
V23A=veth23a   # in ns2
V23B=veth23b   # in ns3

IP1A=10.0.12.1/30
IP2A=10.0.12.2/30
IP2B=10.0.23.1/30
IP3B=10.0.23.2/30

# 小工具函数
exists_ns () { ip netns list | awk '{print $1}' | grep -qx "$1"; }
exists_link () { ip link show "$1" &>/dev/null; }

cleanup () {
  set +e
  # 尝试删除我们创建的 veth（无论是否在某个 ns 里）
  for L in "$V12A" "$V12B" "$V23A" "$V23B"; do
    if exists_link "$L"; then ip link del "$L" || true; fi
    # 也尝试在各 ns 内删除（避免残留）
    for N in "$NS1" "$NS2" "$NS3"; do
      if exists_ns "$N"; then ip -n "$N" link del "$L" 2>/dev/null || true; fi
    done
  done
  # 删除 netns
  for N in "$NS1" "$NS2" "$NS3"; do
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

echo "[*] 创建 veth 并分配到各 ns..."
ip link add "$V12A" type veth peer name "$V12B"
ip link set "$V12A" netns "$NS1"
ip link set "$V12B" netns "$NS2"

ip link add "$V23A" type veth peer name "$V23B"
ip link set "$V23A" netns "$NS2"
ip link set "$V23B" netns "$NS3"

echo "[*] 启动 lo 并配置地址..."
# ns1
ip -n "$NS1" link set lo up
ip -n "$NS1" addr add "$IP1A" dev "$V12A"
ip -n "$NS1" link set "$V12A" up

# ns2
ip -n "$NS2" link set lo up
ip -n "$NS2" addr add "$IP2A" dev "$V12B"
ip -n "$NS2" link set "$V12B" up
ip -n "$NS2" addr add "$IP2B" dev "$V23A"
ip -n "$NS2" link set "$V23A" up

# ns3
ip -n "$NS3" link set lo up
ip -n "$NS3" addr add "$IP3B" dev "$V23B"
ip -n "$NS3" link set "$V23B" up

echo "[*] 在 ns2 开启 IPv4 转发(仅限该 ns)..."
ip netns exec "$NS2" sysctl -w net.ipv4.ip_forward=1 >/dev/null

echo "[*] 配置静态路由：让 ns1/ns3 通过 ns2 互通..."
# ns1 访问 10.0.23.0/30（ns2-ns3 链路）走 ns2
ip -n "$NS1" route add 10.0.23.0/30 via 10.0.12.2 dev "$V12A"

# ns3 访问 10.0.12.0/30（ns1-ns2 链路）走 ns2
ip -n "$NS3" route add 10.0.12.0/30 via 10.0.23.1 dev "$V23B"

echo "[*] 拓扑就绪。可选连通性测试（3 次 ping）..."
set +e
ip netns exec "$NS1" ping -c 1 -W 1 10.0.12.2 >/dev/null && echo "ns1 → ns2 OK" || echo "ns1 → ns2 FAIL"
ip netns exec "$NS2" ping -c 1 -W 1 10.0.23.2 >/dev/null && echo "ns2 → ns3 OK" || echo "ns2 → ns3 FAIL"
ip netns exec "$NS1" ping -c 1 -W 1 10.0.23.2 >/dev/null && echo "ns1 → ns3 OK (经 ns2)" || echo "ns1 → ns3 FAIL"
ip netns exec "$NS3" ping -c 1 -W 1 10.0.12.1 >/dev/null && echo "ns3 → ns1 OK (经 ns2)" || echo "ns3 → ns1 FAIL"
set -e

cat <<EOF

[*] 完成！

当前拓扑：
  $NS1 ($V12A: 10.0.12.1/30)  <-->  $NS2 ($V12B: 10.0.12.2/30, $V23A: 10.0.23.1/30)  <-->  $NS3 ($V23B: 10.0.23.2/30)

常用查看命令：
  ip netns list
  ip -n $NS1 addr ; ip -n $NS2 addr ; ip -n $NS3 addr
  ip -n $NS1 route ; ip -n $NS2 route ; ip -n $NS3 route

清理命令：
  sudo bash $(basename "$0") down
EOF
