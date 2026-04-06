#!/usr/bin/env bash
set -Eeuo pipefail

# 需要 root。支持：sudo bash experiments/08/ns_topology_aware.sh down
#
# 拓扑：两机架（L/R）+ 两个 ToR 路由器（torL/torR）+ 一条跨机架互联
#
#   l1    l2                 r1    r2    r3    r4
#    \    /                   \     |     |     /
#     \  /                     \    |     |    /
#     torL ----(inter-rack)---- torR
#
# 设计目的：
# - “机架内”通信：leaf <-> 本机架 ToR（近：低延迟/高带宽）
# - “跨机架”通信：leaf(L) <-> leaf(R) 经过 torL<->torR（远：可在 inter-rack 链路注入瓶颈）

TOR_L=torL
TOR_R=torR

LNS=(l1 l2)
RNS=(r1 r2 r3 r4)

# inter-rack veth
VLR_A=vethLRa  # in torL
VLR_B=vethLRb  # in torR
TOR_L_INTER=10.0.100.1/30
TOR_R_INTER=10.0.100.2/30

# leaf <-> tor veth name plan
LV_TOR=(vl1_tor vl2_tor)
LV_NS=(vl1_ns vl2_ns)
RV_TOR=(vr1_tor vr2_tor vr3_tor vr4_tor)
RV_NS=(vr1_ns vr2_ns vr3_ns vr4_ns)

# left leaf p2p subnets (10.0.1.0/24 carved into /30)
L_TOR_IPS=(10.0.1.1/30 10.0.1.5/30)
L_NS_IPS=(10.0.1.2/30 10.0.1.6/30)
L_TOR_GW=(10.0.1.1 10.0.1.5)

# right leaf p2p subnets (10.0.3.0/24 carved into /30)
R_TOR_IPS=(10.0.3.1/30 10.0.3.5/30 10.0.3.9/30 10.0.3.13/30)
R_NS_IPS=(10.0.3.2/30 10.0.3.6/30 10.0.3.10/30 10.0.3.14/30)
R_TOR_GW=(10.0.3.1 10.0.3.5 10.0.3.9 10.0.3.13)

exists_ns(){ ip netns list | awk '{print $1}' | grep -qx "$1"; }
exists_link(){ ip link show "$1" &>/dev/null; }

cleanup(){
  set +e
  # 删除 root 侧残留 veth（异常中断时可能存在）
  for l in "$VLR_A" "$VLR_B" "${LV_TOR[@]}" "${LV_NS[@]}" "${RV_TOR[@]}" "${RV_NS[@]}"; do
    exists_link "$l" && ip link del "$l" 2>/dev/null || true
  done
  # 直接删除 ns（ns 内接口会随之删除，并连带删除其 veth peer）
  for ns in "${RNS[@]}" "${LNS[@]}" "$TOR_R" "$TOR_L"; do
    exists_ns "$ns" && ip netns del "$ns" 2>/dev/null || true
  done
}

trap 'echo "[!] 出错，清理中..."; cleanup' ERR

if [[ "${1:-}" == "down" ]]; then
  echo "[*] 清理资源..."
  cleanup
  echo "[*] 完成清理。"
  exit 0
fi

echo "[*] 预清理..."
cleanup || true

echo "[*] 创建 namespaces..."
ip netns add "$TOR_L"
ip netns add "$TOR_R"
for ns in "${LNS[@]}" "${RNS[@]}"; do
  ip netns add "$ns"
done

echo "[*] 启动 lo..."
for ns in "$TOR_L" "$TOR_R" "${LNS[@]}" "${RNS[@]}"; do
  ip -n "$ns" link set lo up
done

echo "[*] 创建 torL <-> torR inter-rack 链路..."
ip link add "$VLR_A" type veth peer name "$VLR_B"
ip link set "$VLR_A" netns "$TOR_L"
ip link set "$VLR_B" netns "$TOR_R"
ip -n "$TOR_L" addr add "$TOR_L_INTER" dev "$VLR_A"
ip -n "$TOR_R" addr add "$TOR_R_INTER" dev "$VLR_B"
ip -n "$TOR_L" link set "$VLR_A" up
ip -n "$TOR_R" link set "$VLR_B" up

echo "[*] 创建左侧 leaf <-> torL 链路并配置地址..."
for i in 0 1; do
  ip link add "${LV_TOR[$i]}" type veth peer name "${LV_NS[$i]}"
  ip link set "${LV_TOR[$i]}" netns "$TOR_L"
  ip link set "${LV_NS[$i]}" netns "${LNS[$i]}"

  ip -n "$TOR_L" addr add "${L_TOR_IPS[$i]}" dev "${LV_TOR[$i]}"
  ip -n "${LNS[$i]}" addr add "${L_NS_IPS[$i]}" dev "${LV_NS[$i]}"

  ip -n "$TOR_L" link set "${LV_TOR[$i]}" up
  ip -n "${LNS[$i]}" link set "${LV_NS[$i]}" up
  ip -n "${LNS[$i]}" route add default via "${L_TOR_GW[$i]}" || true
done

echo "[*] 创建右侧 leaf <-> torR 链路并配置地址..."
for i in 0 1 2 3; do
  ip link add "${RV_TOR[$i]}" type veth peer name "${RV_NS[$i]}"
  ip link set "${RV_TOR[$i]}" netns "$TOR_R"
  ip link set "${RV_NS[$i]}" netns "${RNS[$i]}"

  ip -n "$TOR_R" addr add "${R_TOR_IPS[$i]}" dev "${RV_TOR[$i]}"
  ip -n "${RNS[$i]}" addr add "${R_NS_IPS[$i]}" dev "${RV_NS[$i]}"

  ip -n "$TOR_R" link set "${RV_TOR[$i]}" up
  ip -n "${RNS[$i]}" link set "${RV_NS[$i]}" up
  ip -n "${RNS[$i]}" route add default via "${R_TOR_GW[$i]}" || true
done

echo "[*] 开启 torL/torR IPv4 转发..."
ip netns exec "$TOR_L" sysctl -w net.ipv4.ip_forward=1 >/dev/null
ip netns exec "$TOR_R" sysctl -w net.ipv4.ip_forward=1 >/dev/null

echo "[*] 配置 torL/torR 到对侧 leaf 网段的静态路由..."
ip -n "$TOR_L" route add 10.0.3.0/24 via 10.0.100.2 dev "$VLR_A" || true
ip -n "$TOR_R" route add 10.0.1.0/24 via 10.0.100.1 dev "$VLR_B" || true

echo "[*] 连通性快速测试..."
set +e
ip netns exec l1 ping -c1 -W1 10.0.1.6 >/dev/null && echo "l1 → l2 OK" || echo "l1 → l2 FAIL"
ip netns exec l1 ping -c1 -W1 10.0.3.2 >/dev/null && echo "l1 → r1 OK" || echo "l1 → r1 FAIL"
ip netns exec r4 ping -c1 -W1 10.0.1.2 >/dev/null && echo "r4 → l1 OK" || echo "r4 → l1 FAIL"
set -e

cat <<EOF

[*] 部署完成！

Namespaces:
  ToR: $TOR_L, $TOR_R
  Left leaf: ${LNS[*]}
  Right leaf: ${RNS[*]}

Key links:
  inter-rack: $TOR_L/$VLR_A (10.0.100.1/30) <-> $TOR_R/$VLR_B (10.0.100.2/30)

Common commands:
  ip netns list
  ip -n $TOR_L addr; ip -n $TOR_R addr
  ip netns exec l1 ping -c 5 10.0.1.6   # intra-rack sample
  ip netns exec l1 ping -c 5 10.0.3.2   # inter-rack sample

Inject bottleneck on inter-rack (example):
  ip netns exec $TOR_L tc qdisc add dev $VLR_A root netem delay 5ms 1ms 15% rate 200mbit
  ip netns exec $TOR_L tc qdisc show dev $VLR_A

Cleanup:
  sudo bash experiments/08/ns_topology_aware.sh down
EOF

