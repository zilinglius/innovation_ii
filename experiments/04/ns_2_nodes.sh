#!/usr/bin/env bash
set -Eeuo pipefail

# 链状拓扑：2个命名空间组成链状网络
# ns1 --(veth12a)-- (veth12b)ns2
# 每个链接使用独立的 /30 子网

NS1=ns1
NS2=ns2

# veth接口对
V12A=veth12a   # in ns1
V12B=veth12b   # in ns2

# IP地址分配 (每个/30网段提供2个可用地址)
IP1A=10.0.12.1/30   # ns1-ns2链接
IP2A=10.0.12.2/30

# 小工具函数
exists_ns () { ip netns list | awk '{print $1}' | grep -qx "$1"; }
exists_link () { ip link show "$1" &>/dev/null; }

cleanup () {
  set +e
  # 尝试删除我们创建的 veth（无论是否在某个 ns 里）
  for L in "$V12A" "$V12B"; do
    if exists_link "$L"; then ip link del "$L" || true; fi
    # 也尝试在各 ns 内删除（避免残留）
    for N in "$NS1" "$NS2"; do
      if exists_ns "$N"; then ip -n "$N" link del "$L" 2>/dev/null || true; fi
    done
  done
  # 删除 netns
  for N in "$NS1" "$NS2"; do
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

echo "[*] 创建 veth 并分配到各 ns..."
# ns1-ns2 链接
ip link add "$V12A" type veth peer name "$V12B"
ip link set "$V12A" netns "$NS1"
ip link set "$V12B" netns "$NS2"


echo "[*] 启动 lo 并配置地址..."
# ns1 (连接到 ns2)
ip -n "$NS1" link set lo up
ip -n "$NS1" addr add "$IP1A" dev "$V12A"
ip -n "$NS1" link set "$V12A" up

# ns2 (连接到 ns1)
ip -n "$NS2" link set lo up
ip -n "$NS2" addr add "$IP2A" dev "$V12B"
ip -n "$NS2" link set "$V12B" up

echo "[*] 在所有命名空间开启 IPv4 转发..."
for N in "$NS1" "$NS2"; do
  ip netns exec "$N" sysctl -w net.ipv4.ip_forward=1 >/dev/null
done

echo "[*] 拓扑就绪。链状网络连通性测试..."
set +e
# 相邻节点直连测试
ip netns exec "$NS1" ping -c 1 -W 1 10.0.12.2 >/dev/null && echo "ns1 → ns2 OK (直连)" || echo "ns1 → ns2 FAIL"
ip netns exec "$NS2" ping -c 1 -W 1 10.0.12.1 >/dev/null && echo "ns2 → ns1 OK (直连)" || echo "ns2 → ns1 FAIL"

set -e

cat <<EOF

[*] 完成！

当前链状拓扑：
  $NS1 -- $NS2

接口配置：
  $NS1: $V12A=10.0.12.1/30
  $NS2: $V12B=10.0.12.2/30

常用查看命令：
  ip netns list
  ip -n $NS1 addr ; ip -n $NS2 addr

链状测试命令：
  ip netns exec $NS1 ping 10.0.12.2  # ns1 → ns2
  ip netns exec $NS2 ping 10.0.12.1  # ns2 → ns1

清理命令：
  sudo bash $(basename "$0") down
EOF
