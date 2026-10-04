#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# Lab 2 实验床：Lab 1 的两机架实验床 + 一台中转路由器 r3 − 静态路由
#
# 与第 03 讲模块六完全相同：三台路由器连成三角形，跨机架的路由不再手工配置，
# 由跑在 r1 / r2 / r3 里的路由守护进程（lsrd）自己算出来、写进内核。
#
#   h1a ─┐                                            ┌─ h2a
#        ├─ br1 ─ r1 ───── 10.0.12.0/30 ───── r2 ─ br2 ┤
#   h1b ─┘         \                         /         └─ h2b
#         10.0.13.0/30 \                   / 10.0.23.0/30
#                        \               /
#                          ───── r3 ─────         （rack3 模式下 r3 还挂着机架 3）
#
# 地址规划：
#   机架 1 / 2   与 Lab 1 相同（10.0.1.0/24、10.0.2.0/24）
#   机架 3       10.0.3.0/24   网关 10.0.3.1（br3）  主机 h3a = .11  h3b = .12   （仅 rack3 模式）
#   r1 ↔ r3      10.0.13.0/30  r1 = .1  r3 = .2
#   r2 ↔ r3      10.0.23.0/30  r2 = .1  r3 = .2
#
# 用法（均从仓库根目录执行）：
#   sudo bash 2026/experiments/02/topo.sh            # 三角形（r3 不带机架），幂等
#   sudo bash 2026/experiments/02/topo.sh up rack3   # 三机架环：r3 挂上机架 3
#   sudo bash 2026/experiments/02/topo.sh rack3      # 给正在运行的三角形加上机架 3（不拆不停，进阶任务 T7）
#   sudo bash 2026/experiments/02/topo.sh down       # 拆除（会先停掉 lsrd）
#   sudo bash 2026/experiments/02/topo.sh check      # 连通性自检（启动 lsrd 之后才会全部通过）
#   sudo bash 2026/experiments/02/topo.sh show       # 打印三台路由器的地址与路由
#
# 实现上就是调用 Lab 1 的 ns_topo.sh，再补上 r3 与两条链路，最后删掉 Lab 1 写的两条
# 静态路由。为什么必须删：内核只看 metric，静态路由 metric 0 会压住 lsrd 写的 metric 20，
# 你会以为自己的守护进程不工作（第 03 讲 5.2 节）。
# ==============================================================================

LAB_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LAB1_TOPO="$LAB_DIR/../01/ns_topo.sh"

# 本脚本新增的对象（Lab 1 的那些由 ns_topo.sh 自己管理）
NS_NEW=(r3 h3a h3b)
VETH_NEW=(r1-r3 r3-r1 r2-r3 r3-r2 h3a-r3 r3-h3a h3b-r3 r3-h3b)

RACK3_RT=r3 ; RACK3_BR=br3 ; RACK3_GW=10.0.3.1 ; RACK3_LAN=10.0.3.0/24
RACK3_HA=h3a ; RACK3_IPA=10.0.3.11
RACK3_HB=h3b ; RACK3_IPB=10.0.3.12

P2P_R1_R3=10.0.13.1/30 ; P2P_R3_R1=10.0.13.2/30
P2P_R2_R3=10.0.23.1/30 ; P2P_R3_R2=10.0.23.2/30

# ---- 小工具函数（与 Lab 1 的 ns_topo.sh 同名同语义）----------------------------

exists_ns () { ip netns list | awk '{print $1}' | grep -qx "$1"; }
exists_link () { ip link show "$1" &>/dev/null; }

cleanup_new () {
  set +e
  for n in "${NS_NEW[@]}"; do
    exists_ns "$n" && ip netns del "$n" >/dev/null 2>&1
  done
  for l in "${VETH_NEW[@]}"; do
    exists_link "$l" && ip link del "$l" >/dev/null 2>&1
  done
  set -e
}

attach_host () {
  local rt=$1 br=$2 host=$3 hip=$4 gw=$5
  local hdev="${host}-${rt}" bdev="${rt}-${host}"
  ip link add "$hdev" type veth peer name "$bdev"
  ip link set "$hdev" netns "$host"
  ip link set "$bdev" netns "$rt"
  ip -n "$rt" link set "$bdev" master "$br"
  ip -n "$rt" link set "$bdev" up
  ip -n "$host" addr add "${hip}/24" dev "$hdev"
  ip -n "$host" link set "$hdev" up
  ip -n "$host" route add default via "$gw"
}

make_rack () {
  local rt=$1 br=$2 gw=$3 ha=$4 ipa=$5 hb=$6 ipb=$7
  ip -n "$rt" link add name "$br" type bridge
  ip -n "$rt" link set "$br" up
  ip -n "$rt" addr add "${gw}/24" dev "$br"
  attach_host "$rt" "$br" "$ha" "$ipa" "$gw"
  attach_host "$rt" "$br" "$hb" "$ipb" "$gw"
}

link_routers () {
  local ra=$1 ipa=$2 rb=$3 ipb=$4
  local da="${ra}-${rb}" db="${rb}-${ra}"
  ip link add "$da" type veth peer name "$db"
  ip link set "$da" netns "$ra"
  ip link set "$db" netns "$rb"
  ip -n "$ra" addr add "$ipa" dev "$da" ; ip -n "$ra" link set "$da" up
  ip -n "$rb" addr add "$ipb" dev "$db" ; ip -n "$rb" link set "$db" up
}

expect_ping () {
  local src=$1 dst=$2 desc=$3
  if ip netns exec "$src" ping -c 1 -W 1 "$dst" >/dev/null 2>&1; then
    echo "  [OK]   $desc"
  else
    echo "  [FAIL] $desc"
    RC=1
  fi
}

has_rack3 () { exists_ns "$RACK3_HA"; }

add_rack3 () {
  if has_rack3; then
    echo "[*] 机架 3 已经在了，跳过。"
    return
  fi
  echo "[*] 搭建机架 3（$RACK3_LAN）..."
  for n in "$RACK3_HA" "$RACK3_HB"; do
    ip netns add "$n"
    ip -n "$n" link set lo up
  done
  make_rack "$RACK3_RT" "$RACK3_BR" "$RACK3_GW" \
            "$RACK3_HA" "$RACK3_IPA" "$RACK3_HB" "$RACK3_IPB"
}

stop_daemons () {
  # 拆实验床前先停掉守护进程，否则它们会带着已删除的 namespace 继续活着
  if [ -f "$LAB_DIR/run.sh" ] && ls /run/lsrd/*.pid >/dev/null 2>&1; then
    bash "$LAB_DIR/run.sh" stop || true
  fi
}

check () {
  RC=0
  echo "[*] 静态路由自检（r1、r2 上不该再有手工配置的 via 路由）："
  for r in r1 r2; do
    local foreign
    foreign=$(ip -n "$r" -j route show | python3 -c '
import json, sys
for e in json.load(sys.stdin):
  if ("gateway" in e or "nexthops" in e) and str(e.get("protocol")) != "200":
    print("         " + e["dst"] + " via " + (e.get("gateway") or ",".join(n["gateway"] for n in e["nexthops"])))')
    if [ -n "$foreign" ]; then
      echo "  [FAIL] $r 上有非 lsrd 写的 via 路由：" ; echo "$foreign"
      RC=1
    else
      echo "  [OK]   $r"
    fi
  done
  echo "[*] 连通性自检："
  expect_ping h1a 10.0.1.12 "h1a → h1b 10.0.1.12（同机架，二层直通）"
  expect_ping h1a 10.0.2.11 "h1a → h2a 10.0.2.11（跨机架）"
  expect_ping h2b 10.0.1.11 "h2b → h1a 10.0.1.11（跨机架，反向）"
  expect_ping h1a 10.0.13.2 "h1a → r3 10.0.13.2（机架 → 中转路由器）"
  expect_ping r3  10.0.2.11 "r3  → h2a 10.0.2.11（中转路由器 → 机架 2）"
  if has_rack3; then
    expect_ping h3a 10.0.3.12 "h3a → h3b 10.0.3.12（同机架，二层直通）"
    expect_ping h1a 10.0.3.11 "h1a → h3a 10.0.3.11（跨机架，机架 1 → 3）"
    expect_ping h3b 10.0.2.12 "h3b → h2b 10.0.2.12（跨机架，机架 3 → 2）"
  fi
  return "$RC"
}

show () {
  local routers=(r1 r2 r3)
  echo "=== 地址 ==="
  for n in "${routers[@]}"; do
    echo "--- $n ---"
    ip -n "$n" -br addr show | grep -v '^lo'
  done
  echo
  echo "=== 路由表（proto 200 的是 lsrd 写的）==="
  for n in "${routers[@]}"; do
    echo "--- $n ---"
    ip -n "$n" route show
  done
}

# ---- 主流程 ------------------------------------------------------------------

MODE="${1:-up}"
case "$MODE" in
  down)
    echo "[*] 拆除 Lab 2 实验床：先停 lsrd，删掉 r3 与机架 3，再拆 Lab 1 的部分..."
    stop_daemons
    cleanup_new
    bash "$LAB1_TOPO" down
    exit 0
    ;;
  show)
    exists_ns r3 || { echo "[!] 实验床尚未搭建，请先执行 sudo bash $0" >&2 ; exit 1; }
    show
    exit 0
    ;;
  check)
    exists_ns r3 || { echo "[!] 实验床尚未搭建，请先执行 sudo bash $0" >&2 ; exit 1; }
    check
    exit $?
    ;;
  rack3)
    exists_ns r3 || { echo "[!] 实验床尚未搭建，请先执行 sudo bash $0" >&2 ; exit 1; }
    add_rack3
    echo "[*] r1、r2 上什么都不用改。让 r3 的守护进程知道 br3 是机架侧接口：sudo bash 2026/experiments/02/run.sh restart r3"
    exit 0
    ;;
  up)
    : # 继续往下走
    ;;
  *)
    echo "用法：sudo bash $0 [up [rack3]|rack3|down|show|check]" >&2
    exit 1
    ;;
esac

WITH_RACK3=0
[ "${2:-}" = "rack3" ] && WITH_RACK3=1

[ -f "$LAB1_TOPO" ] || { echo "[!] 找不到 Lab 1 的拓扑脚本 $LAB1_TOPO" >&2 ; exit 1; }

# 搭建过程中任何一步出错就清理掉本脚本新建的资源。只在搭建路径上启用：
# check 的失败（返回 1）不是"出错"，不能把实验床拆掉。
trap 'echo "[!] 出错，正在清理已创建的资源..." >&2 ; cleanup_new' ERR

echo "[*] 停掉可能还在跑的 lsrd，清理上次的 r3 / 机架 3..."
stop_daemons
cleanup_new

echo "[*] 用 Lab 1 的脚本搭两机架实验床..."
bash "$LAB1_TOPO" up | grep -v '^  \[\|连通性自检' || true     # 它末尾的连通性自检此时必然通过，省略不看

echo "[*] 新增中转路由器 r3，连到 r1 与 r2..."
ip netns add r3
ip -n r3 link set lo up
ip netns exec r3 sysctl -qw net.ipv4.ip_forward=1
link_routers r1 "$P2P_R1_R3" r3 "$P2P_R3_R1"
link_routers r2 "$P2P_R2_R3" r3 "$P2P_R3_R2"

if [ "$WITH_RACK3" = 1 ]; then
  add_rack3
fi

echo "[*] 删掉 Lab 1 的两条静态路由——从现在起没有人再手工配路由..."
ip -n r1 route del 10.0.2.0/24
ip -n r2 route del 10.0.1.0/24

echo "[*] 搭建完成。r1 的路由表现在只剩直连网段："
ip -n r1 route show | sed 's/^/    /'
echo "[*] 跨机架此刻不通是正常的。启动守护进程后再自检："
echo "    sudo bash 2026/experiments/02/run.sh start && sleep 6 && sudo bash 2026/experiments/02/run.sh check"
