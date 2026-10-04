#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# Lab 1 挑战任务：故障盲测
#
# 在 ns_topo.sh 搭好的实验床上随机破坏一处，由你来把它找出来。
# 六种故障覆盖二层与三层各自的典型失效方式，现象各不相同，
# 但**都只表现为"某些 ping 不通"**——必须靠定位手段区分，不能靠猜。
#
# 用法（均从仓库根目录执行）：
#   sudo bash 2026/experiments/01/ns_topo.sh              # 先搭好实验床
#   sudo bash 2026/experiments/01/break_topo.sh           # 随机注入一处故障
#   sudo bash 2026/experiments/01/break_topo.sh reveal    # 看答案（找完再看）
#   sudo bash 2026/experiments/01/break_topo.sh fix       # 恢复（重建实验床）
#   sudo bash 2026/experiments/01/break_topo.sh break 3   # 指定注入第 3 种（自测用）
#
# 定位建议见第 02 讲 4.2 节的清单：
#   ip addr show → ip route get → ip neigh show → sysctl ip_forward → 中间节点抓包
# ==============================================================================

STATE_FILE=/tmp/innovation_ii_lab01_fault
FAULT_COUNT=6

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOPO_SCRIPT="${SCRIPT_DIR}/ns_topo.sh"

exists_ns () { ip netns list | awk '{print $1}' | grep -qx "$1"; }

require_topo () {
  if ! exists_ns r1; then
    echo "[!] 实验床尚未搭建，请先执行：sudo bash ${TOPO_SCRIPT}" >&2
    exit 1
  fi
}

# 每种故障的一句话答案，仅在 reveal 时打印。
fault_desc () {
  case "$1" in
    1) echo "机架 1 的桥端口 r1-h1b 被置为 down（二层：h1b 的线被拔了）" ;;
    2) echo "r2 的 net.ipv4.ip_forward 被关成 0（三层：r2 退化成一台主机，不再转发）" ;;
    3) echo "r2 少了通往 10.0.1.0/24 的回程路由（三层：去程通、回程断）" ;;
    4) echo "h2b 的默认路由被删除（三层：它只能和同机架的邻居说话）" ;;
    5) echo "h1b 的地址被改成 10.0.9.12/24，与本机架网段不符（三层：连网关都不在同一网段）" ;;
    6) echo "r2-h2a 被从网桥 br2 上摘下（二层：端口脱离交换平面，地址却还在）" ;;
    *) echo "未知故障编号：$1" ;;
  esac
}

apply_fault () {
  case "$1" in
    1) ip -n r1 link set r1-h1b down ;;
    2) ip netns exec r2 sysctl -qw net.ipv4.ip_forward=0 ;;
    3) ip -n r2 route del 10.0.1.0/24 via 10.0.12.1 ;;
    4) ip -n h2b route del default via 10.0.2.1 ;;
    5) ip -n h1b addr del 10.0.1.12/24 dev h1b-r1
       ip -n h1b addr add 10.0.9.12/24 dev h1b-r1 ;;
    6) ip -n r2 link set r2-h2a nomaster ;;
    *) echo "[!] 故障编号必须是 1 到 ${FAULT_COUNT}" >&2 ; exit 1 ;;
  esac
}

case "${1:-break}" in
  reveal)
    if [[ ! -f "$STATE_FILE" ]]; then
      echo "[!] 当前没有已注入的故障记录（$STATE_FILE 不存在）。" >&2
      exit 1
    fi
    n="$(cat "$STATE_FILE")"
    echo "[*] 本次注入的是第 $n 种故障："
    echo "    $(fault_desc "$n")"
    echo
    echo "[*] 恢复：sudo bash ${TOPO_SCRIPT}"
    ;;

  fix)
    echo "[*] 重建实验床以恢复到干净状态..."
    rm -f "$STATE_FILE"
    bash "$TOPO_SCRIPT"
    ;;

  break)
    require_topo
    if [[ -f "$STATE_FILE" ]]; then
      echo "[!] 实验床上已经有一处未修复的故障了。" >&2
      echo "    先恢复：sudo bash $0 fix" >&2
      exit 1
    fi
    if [[ -n "${2:-}" ]]; then
      n="$2"
    else
      n=$(( (RANDOM % FAULT_COUNT) + 1 ))
    fi
    apply_fault "$n"
    echo "$n" > "$STATE_FILE"
    echo "[*] 已在实验床上注入一处故障。"
    echo "[*] 请用第 02 讲 4.2 节的定位清单把它找出来，写清你的判据。"
    echo "[*] 找完了看答案：sudo bash $0 reveal"
    ;;

  *)
    echo "用法：sudo bash $0 [break [1-${FAULT_COUNT}] | reveal | fix]" >&2
    exit 1
    ;;
esac
