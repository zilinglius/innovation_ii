#!/usr/bin/env bash
set -Eeuo pipefail

# 星型桥接拓扑，贴近典型分布式框架的 Driver + Parameter Server + 多 Worker 模型。
# namespaces: drv, ps, w1, w2, w3
#            \   |   |   |
#             \  |   |   |
#                brfw (bridge)

BR=brfw
BR_IP=10.10.0.1/24

NS_DRV=drv
NS_PS=ps
NS_W1=w1
NS_W2=w2
NS_W3=w3

V_DRV_HOST=vdrv
V_DRV_NS=vdrv_ns
V_PS_HOST=vps
V_PS_NS=vps_ns
V_W1_HOST=vw1
V_W1_NS=vw1_ns
V_W2_HOST=vw2
V_W2_NS=vw2_ns
V_W3_HOST=vw3
V_W3_NS=vw3_ns

IP_DRV=10.10.0.10/24
IP_PS=10.10.0.20/24
IP_W1=10.10.0.11/24
IP_W2=10.10.0.12/24
IP_W3=10.10.0.13/24

exists_ns() { ip netns list | awk '{print $1}' | grep -qx "$1"; }
exists_link() { ip link show "$1" &>/dev/null; }

cleanup() {
  set +e
  # remove veth pairs
  for L in "$V_DRV_HOST" "$V_DRV_NS" "$V_PS_HOST" "$V_PS_NS" "$V_W1_HOST" "$V_W1_NS" "$V_W2_HOST" "$V_W2_NS" "$V_W3_HOST" "$V_W3_NS"; do
    if exists_link "$L"; then ip link del "$L" || true; fi
    for N in "$NS_DRV" "$NS_PS" "$NS_W1" "$NS_W2" "$NS_W3"; do
      if exists_ns "$N"; then ip -n "$N" link del "$L" 2>/dev/null || true; fi
    done
  done
  # remove bridge
  if exists_link "$BR"; then ip link del "$BR" || true; fi
  # remove namespaces
  for N in "$NS_DRV" "$NS_PS" "$NS_W1" "$NS_W2" "$NS_W3"; do
    if exists_ns "$N"; then ip netns del "$N" || true; fi
  done
}
trap 'echo "[!] 出错，清理资源..." ; cleanup' ERR

if [[ "${1:-}" == "down" ]]; then
  echo "[*] 清理已创建的 namespace/bridge/veth..."
  cleanup
  echo "[*] 完成清理。"
  exit 0
fi

# 预清理确保可重复执行
cleanup || true

echo "[*] 创建 namespaces..."
ip netns add "$NS_DRV"
ip netns add "$NS_PS"
ip netns add "$NS_W1"
ip netns add "$NS_W2"
ip netns add "$NS_W3"

echo "[*] 创建桥 brfw 并启用..."
ip link add name "$BR" type bridge
ip addr add "$BR_IP" dev "$BR"
ip link set "$BR" up

create_pair() {
  local host_if=$1 ns_if=$2 ns_name=$3 ns_ip=$4
  ip link add "$host_if" type veth peer name "$ns_if"
  ip link set "$ns_if" netns "$ns_name"
  ip link set "$host_if" master "$BR"
  ip link set "$host_if" up
  ip -n "$ns_name" link set lo up
  ip -n "$ns_name" addr add "$ns_ip" dev "$ns_if"
  ip -n "$ns_name" link set "$ns_if" up
}

echo "[*] 创建 veth 并连接 bridge..."
create_pair "$V_DRV_HOST" "$V_DRV_NS" "$NS_DRV" "$IP_DRV"
create_pair "$V_PS_HOST" "$V_PS_NS" "$NS_PS" "$IP_PS"
create_pair "$V_W1_HOST" "$V_W1_NS" "$NS_W1" "$IP_W1"
create_pair "$V_W2_HOST" "$V_W2_NS" "$NS_W2" "$IP_W2"
create_pair "$V_W3_HOST" "$V_W3_NS" "$NS_W3" "$IP_W3"

echo "[*] 拓扑完成。示例连通性测试："
echo "    ip netns exec $NS_W1 ping -c 2 $IP_PS"
echo "    ip netns exec $NS_DRV ping -c 2 $IP_W3"
