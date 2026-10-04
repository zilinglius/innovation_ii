#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# Lab 2 挑战任务：控制平面故障盲测。
#
# Lab 1 的 break_topo.sh 破坏的是数据平面（接口、地址、转发开关、静态路由）；
# 这个脚本破坏的是**路由协议本身**——链路都通、地址都对，但守护进程之间“说不上话”，
# 或者说上了话却算错了、算对了却没写进内核。
#
# 用法（从仓库根目录执行；实验床与三台 lsrd 都在运行的状态下）：
#   sudo bash 2026/experiments/02/break_lsr.sh          # 随机注入一处故障（不会告诉你是哪一处）
#   sudo bash 2026/experiments/02/break_lsr.sh break 3  # 指定注入第 3 种（自己练习用）
#   sudo bash 2026/experiments/02/break_lsr.sh reveal   # 看答案
#   sudo bash 2026/experiments/02/break_lsr.sh fix      # 恢复
#
# 六种故障（rack3 模式下全部可用；三角形模式下不会抽到第 5 种）：
#   1  单向阻断：r2 听不见 r1 的协议报文（r1 听得见 r2 的）
#   2  控制面静默：r1–r2 之间双向丢弃协议报文（数据报文照常转发）
#   3  参数不一致：r3 的 hello / dead 定时器被改成 3 / 12
#   4  router id 冲突：r3 以 --id 2 启动
#   5  只算不装：r3 以 --no-install 启动（RIB 有、FIB 无）
#   6  静态路由残留：有人在 r1 上手工加了一条去机架 2 的静态路由（metric 0）
#
# 状态文件 /tmp/innovation_ii_lab02_fault 记录当前注入的故障；重复注入会被拦住。
# ==============================================================================

LAB_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RUN="$LAB_DIR/run.sh"
STATE=/tmp/innovation_ii_lab02_fault
PORT=5200

exists_ns () { ip netns list | awk '{print $1}' | grep -qx "$1"; }
has_rack3 () { exists_ns h3a; }
is_running () { [ -f "/run/lsrd/$1.pid" ] && kill -0 "$(cat "/run/lsrd/$1.pid")" 2>/dev/null; }

require_env () {
  exists_ns r3 || { echo "[!] 实验床没搭：sudo bash 2026/experiments/02/topo.sh" >&2 ; exit 1; }
  for n in 1 2 3; do
    is_running "$n" || { echo "[!] r$n 的 lsrd 没在运行：sudo bash 2026/experiments/02/run.sh start" >&2 ; exit 1; }
  done
}

describe () {
  case "$1" in
    1) echo "单向阻断：r2 上 iptables 丢弃从 r2-r1 进来的 UDP $PORT（r2 听不见 r1，r1 听得见 r2）" ;;
    2) echo "控制面静默：r1、r2 互相丢弃对方的 UDP $PORT（数据报文照常转发）" ;;
    3) echo "参数不一致：r3 以 --hello 3 --dead 12 重启（另外两台是 2 / 8）" ;;
    4) echo "router id 冲突：r3 以 --id 2 重启（与 r2 撞号）" ;;
    5) echo "只算不装：r3 以 --no-install 重启（SPF 照跑，内核路由表不写）" ;;
    6) echo "静态路由残留：r1 上手工加了 10.0.2.0/24 via 10.0.13.2（metric 0，压住 lsrd 的 metric 20）" ;;
    *) echo "未知故障 $1" ;;
  esac
}

inject () {
  case "$1" in
    1) ip netns exec r2 iptables -I INPUT -i r2-r1 -p udp --dport "$PORT" -j DROP ;;
    2) ip netns exec r1 iptables -I INPUT -i r1-r2 -p udp --dport "$PORT" -j DROP
       ip netns exec r2 iptables -I INPUT -i r2-r1 -p udp --dport "$PORT" -j DROP ;;
    3) bash "$RUN" restart r3 --hello 3 --dead 12 >/dev/null ;;
    4) bash "$RUN" restart r3 --id 2 --pidfile /run/lsrd/3.pid --sock /run/lsrd/3.sock >/dev/null ;;
    5) bash "$RUN" restart r3 --no-install >/dev/null ;;
    6) ip -n r1 route add 10.0.2.0/24 via 10.0.13.2 ;;
  esac
}

repair () {
  set +e
  case "$1" in
    1) ip netns exec r2 iptables -D INPUT -i r2-r1 -p udp --dport "$PORT" -j DROP 2>/dev/null ;;
    2) ip netns exec r1 iptables -D INPUT -i r1-r2 -p udp --dport "$PORT" -j DROP 2>/dev/null
       ip netns exec r2 iptables -D INPUT -i r2-r1 -p udp --dport "$PORT" -j DROP 2>/dev/null ;;
    3|4|5) bash "$RUN" restart r3 >/dev/null ;;
    6) ip -n r1 route del 10.0.2.0/24 via 10.0.13.2 2>/dev/null ;;
  esac
  set -e
}

# 故障 4：run.sh 给的 --id 3 与后面的 --id 2 重复，argparse 取最后一个；pid 与 CLI 套接字
# 显式仍写到 3.pid / 3.sock，run.sh 才能继续管理它（show r3 会看到它自称 rid 2）。

case "${1:-break}" in
  break)
    require_env
    if [ -f "$STATE" ]; then
      echo "[!] 已有故障（$(cat "$STATE")）未修复，先 fix 再 break。" >&2 ; exit 1
    fi
    if [ -n "${2:-}" ]; then
      F=$2
    else
      if has_rack3; then F=$(( RANDOM % 6 + 1 )); else
        F=$(( RANDOM % 5 + 1 )); [ "$F" -ge 5 ] && F=6; fi
    fi
    [[ "$F" =~ ^[1-6]$ ]] || { echo "[!] 故障编号须为 1–6" >&2 ; exit 1; }
    if [ "$F" = 5 ] && ! has_rack3; then
      echo "[!] 第 5 种故障需要机架 3（sudo bash 2026/experiments/02/topo.sh rack3）" >&2 ; exit 1
    fi
    inject "$F"
    echo "$F" > "$STATE"
    echo "[*] 已注入一处故障。去找吧：run.sh show rN neighbors|lsdb|routes、ip route、tcpdump。"
    echo "    找到后：sudo bash 2026/experiments/02/break_lsr.sh reveal"
    ;;
  reveal)
    [ -f "$STATE" ] || { echo "[*] 当前没有注入的故障。" ; exit 0; }
    F=$(cat "$STATE")
    echo "[*] 故障 $F：$(describe "$F")"
    ;;
  fix)
    [ -f "$STATE" ] || { echo "[*] 当前没有注入的故障。" ; exit 0; }
    F=$(cat "$STATE")
    repair "$F"
    rm -f "$STATE"
    echo "[*] 已恢复（故障 $F：$(describe "$F")）。几秒后 run.sh check 应全部通过。"
    ;;
  *)
    echo "用法：sudo bash $0 [break [N]|reveal|fix]" >&2
    exit 1
    ;;
esac
