#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# Lab 1 实验床：两机架 + 两路由器
#
# 拓扑：
#   h1a ─┐                                          ┌─ h2a
#        ├─ br1 ─ r1 ──── 10.0.12.0/30 ──── r2 ─ br2 ┤
#   h1b ─┘                                          └─ h2b
#
#   br1 建在 r1 的 namespace 内，br2 建在 r2 的 namespace 内。
#   每个机架是一个独立的广播域，机架之间靠静态路由互通。
#
# 地址规划：
#   机架 1 LAN   10.0.1.0/24   网关 10.0.1.1（配在 r1 的 br1 上）  主机 .11 / .12
#   机架 2 LAN   10.0.2.0/24   网关 10.0.2.1（配在 r2 的 br2 上）  主机 .11 / .12
#   路由器互联   10.0.12.0/30  r1 = .1   r2 = .2
#
# 接口命名：<本端>-<对端>，例如 r1-h1a 是 r1 上朝向 h1a 的那个口。
#
# 用法（均从仓库根目录执行）：
#   sudo bash 2026/experiments/01/ns_topo.sh        # 搭建，幂等，可重复执行
#   sudo bash 2026/experiments/01/ns_topo.sh down   # 拆除，幂等
#   sudo bash 2026/experiments/01/ns_topo.sh show   # 打印地址、路由与 MAC 地址表
#   sudo bash 2026/experiments/01/ns_topo.sh check  # 只跑连通性自检
# ==============================================================================

# ---- 常量 --------------------------------------------------------------------

# 全部 namespace。扩展机架时在这里加上新的路由器与主机。
NS_ALL=(h1a h1b r1 r2 h2a h2b)

# 全部 veth 名字，仅供清理时兜底扫描（正常情况下删除 namespace 就会带走它们）。
VETH_ALL=(
  h1a-r1 r1-h1a
  h1b-r1 r1-h1b
  h2a-r2 r2-h2a
  h2b-r2 r2-h2b
  r1-r2  r2-r1
)

# 机架 1
RACK1_RT=r1 ; RACK1_BR=br1 ; RACK1_GW=10.0.1.1 ; RACK1_LAN=10.0.1.0/24
RACK1_HA=h1a ; RACK1_IPA=10.0.1.11
RACK1_HB=h1b ; RACK1_IPB=10.0.1.12

# 机架 2
RACK2_RT=r2 ; RACK2_BR=br2 ; RACK2_GW=10.0.2.1 ; RACK2_LAN=10.0.2.0/24
RACK2_HA=h2a ; RACK2_IPA=10.0.2.11
RACK2_HB=h2b ; RACK2_IPB=10.0.2.12

# 路由器互联链路
P2P_R1=10.0.12.1/30
P2P_R2=10.0.12.2/30

# ---- 小工具函数 --------------------------------------------------------------

exists_ns () { ip netns list | awk '{print $1}' | grep -qx "$1"; }
exists_link () { ip link show "$1" &>/dev/null; }

# 拆除全部资源。删除 namespace 会自动回收其中的 veth 与网桥，
# 兜底再扫一遍根命名空间，清掉上次中途失败可能残留的 veth。
cleanup () {
  set +e
  for n in "${NS_ALL[@]}"; do
    exists_ns "$n" && ip netns del "$n" >/dev/null 2>&1
  done
  for l in "${VETH_ALL[@]}"; do
    exists_link "$l" && ip link del "$l" >/dev/null 2>&1
  done
  set -e
}

# 把一台主机接到某个机架的网桥上。
# 用法：attach_host <路由器ns> <网桥名> <主机ns> <主机IP> <网关IP>
attach_host () {
  local rt=$1 br=$2 host=$3 hip=$4 gw=$5
  local hdev="${host}-${rt}"   # 主机侧接口
  local bdev="${rt}-${host}"   # 路由器侧接口，插在网桥上
  ip link add "$hdev" type veth peer name "$bdev"
  ip link set "$hdev" netns "$host"
  ip link set "$bdev" netns "$rt"
  # 桥端口不配 IP，只需入桥并启用
  ip -n "$rt" link set "$bdev" master "$br"
  ip -n "$rt" link set "$bdev" up
  ip -n "$host" addr add "${hip}/24" dev "$hdev"
  ip -n "$host" link set "$hdev" up
  ip -n "$host" route add default via "$gw"
}

# 建一个机架：在路由器 namespace 内建网桥，把网关地址配在网桥上，再挂两台主机。
# 用法：make_rack <路由器ns> <网桥名> <网关IP> <主机A ns> <主机A IP> <主机B ns> <主机B IP>
make_rack () {
  local rt=$1 br=$2 gw=$3 ha=$4 ipa=$5 hb=$6 ipb=$7
  ip -n "$rt" link add name "$br" type bridge
  ip -n "$rt" link set "$br" up
  ip -n "$rt" addr add "${gw}/24" dev "$br"
  attach_host "$rt" "$br" "$ha" "$ipa" "$gw"
  attach_host "$rt" "$br" "$hb" "$ipb" "$gw"
}

# 用一条点对点链路连接两台路由器。
# 用法：link_routers <路由器A ns> <A的地址/掩码> <路由器B ns> <B的地址/掩码>
link_routers () {
  local ra=$1 ipa=$2 rb=$3 ipb=$4
  local da="${ra}-${rb}" db="${rb}-${ra}"
  ip link add "$da" type veth peer name "$db"
  ip link set "$da" netns "$ra"
  ip link set "$db" netns "$rb"
  ip -n "$ra" addr add "$ipa" dev "$da" ; ip -n "$ra" link set "$da" up
  ip -n "$rb" addr add "$ipb" dev "$db" ; ip -n "$rb" link set "$db" up
}

# 一条连通性断言。
# 用法：expect_ping <源ns> <目的IP> <说明>
expect_ping () {
  local src=$1 dst=$2 desc=$3
  if ip netns exec "$src" ping -c 1 -W 1 "$dst" >/dev/null 2>&1; then
    echo "  [OK]   $desc"
  else
    echo "  [FAIL] $desc"
    RC=1
  fi
}

check () {
  RC=0
  echo "[*] 连通性自检："
  expect_ping "$RACK1_HA" "$RACK1_GW"  "h1a → 网关 10.0.1.1（同机架，经网桥）"
  expect_ping "$RACK1_HA" "$RACK1_IPB" "h1a → h1b 10.0.1.12（同机架，二层直通）"
  expect_ping "$RACK2_HA" "$RACK2_IPB" "h2a → h2b 10.0.2.12（同机架，二层直通）"
  expect_ping "$RACK1_HA" "$RACK2_IPA" "h1a → h2a 10.0.2.11（跨机架，两跳路由）"
  expect_ping "$RACK1_HB" "$RACK2_IPB" "h1b → h2b 10.0.2.12（跨机架，两跳路由）"
  expect_ping "$RACK2_HB" "$RACK1_IPA" "h2b → h1a 10.0.1.11（跨机架，反向）"
  return "$RC"
}

show () {
  echo "=== 地址 ==="
  for n in "${NS_ALL[@]}"; do
    echo "--- $n ---"
    ip -n "$n" -br addr show | grep -v '^lo'
  done
  echo
  echo "=== 路由表 ==="
  for n in "${NS_ALL[@]}"; do
    echo "--- $n ---"
    ip -n "$n" route show
  done
  echo
  echo "=== 网桥 MAC 地址表（只显示自学习到的条目）==="
  echo "--- $RACK1_RT / $RACK1_BR ---"
  ip netns exec "$RACK1_RT" bridge fdb show br "$RACK1_BR" | grep -v permanent || true
  echo "--- $RACK2_RT / $RACK2_BR ---"
  ip netns exec "$RACK2_RT" bridge fdb show br "$RACK2_BR" | grep -v permanent || true
}

# ---- 主流程 ------------------------------------------------------------------

case "${1:-up}" in
  down)
    echo "[*] 拆除实验床..."
    cleanup
    echo "[*] 完成。"
    exit 0
    ;;
  show)
    exists_ns "$RACK1_RT" || { echo "[!] 实验床尚未搭建，请先执行 sudo bash $0" >&2 ; exit 1; }
    show
    exit 0
    ;;
  check)
    exists_ns "$RACK1_RT" || { echo "[!] 实验床尚未搭建，请先执行 sudo bash $0" >&2 ; exit 1; }
    check
    exit $?
    ;;
  up)
    : # 继续往下走
    ;;
  *)
    echo "用法：sudo bash $0 [up|down|show|check]" >&2
    exit 1
    ;;
esac

# 搭建过程中任何一步出错就清理掉已创建的资源。只在搭建路径上启用：
# check 的失败（自检不通过、返回 1）不是"出错"，不能把实验床拆掉。
trap 'echo "[!] 出错，正在清理已创建的资源..." >&2 ; cleanup' ERR

# 幂等的做法：先无条件拆干净，再从头建一遍。
# 好处是逻辑简单、结果确定；代价是重复执行会打断正在跑的流量。
echo "[*] 预清理（保证可重复执行）..."
cleanup

echo "[*] 创建 namespace..."
for n in "${NS_ALL[@]}"; do
  ip netns add "$n"
  ip -n "$n" link set lo up
done

echo "[*] 搭建机架 1（$RACK1_LAN）..."
make_rack "$RACK1_RT" "$RACK1_BR" "$RACK1_GW" \
          "$RACK1_HA" "$RACK1_IPA" "$RACK1_HB" "$RACK1_IPB"

echo "[*] 搭建机架 2（$RACK2_LAN）..."
make_rack "$RACK2_RT" "$RACK2_BR" "$RACK2_GW" \
          "$RACK2_HA" "$RACK2_IPA" "$RACK2_HB" "$RACK2_IPB"

echo "[*] 连接两台路由器..."
link_routers "$RACK1_RT" "$P2P_R1" "$RACK2_RT" "$P2P_R2"

echo "[*] 打开路由器的 IPv4 转发..."
for r in "$RACK1_RT" "$RACK2_RT"; do
  ip netns exec "$r" sysctl -qw net.ipv4.ip_forward=1
done

echo "[*] 配置静态路由..."
# 每台路由器各需要一条通往对端机架 LAN 的路由。
# 注意：机架数量增加时，这里的条数按 N×(N-1) 增长——这正是 Lab 2 要解决的问题。
ip -n "$RACK1_RT" route add "$RACK2_LAN" via 10.0.12.2
ip -n "$RACK2_RT" route add "$RACK1_LAN" via 10.0.12.1

echo "[*] 搭建完成。"
check
