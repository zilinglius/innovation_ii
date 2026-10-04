#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# Lab 2：在每台路由器的 namespace 里启停 lsrd 守护进程，并查看它们的状态。
#
# 用法（均从仓库根目录执行）：
#   sudo bash 2026/experiments/02/run.sh start [lsrd 选项...]   # r1 r2 r3（以及任何 rN）各起一个
#   sudo bash 2026/experiments/02/run.sh stop [rN]              # 停掉全部或某一台（退出时会清掉自己写的路由）
#   sudo bash 2026/experiments/02/run.sh restart rN [选项...]   # 换参数重启某一台，例如 restart r1 --cost r1-r2=20
#   sudo bash 2026/experiments/02/run.sh status                 # 谁在跑、跑了多久
#   sudo bash 2026/experiments/02/run.sh show rN neighbors|lsdb|routes|stats|digest|json
#   sudo bash 2026/experiments/02/run.sh logs rN                # tail -f 日志
#   sudo bash 2026/experiments/02/run.sh poke rN                # 让 rN 重新生成一条 LSA（内容不变，seq+1），用来数泛洪份数
#   sudo bash 2026/experiments/02/run.sh check                  # 邻接全 Full、LSDB 一致、路由条数、连通性
#
# 路由器 = 名字形如 rN 的 namespace，router id = N；该 namespace 里的网桥自动作为 --passive 接口。
# 日志在 /tmp/lsrd/rN.log，pid 与 CLI 套接字在 /run/lsrd/。
# ==============================================================================

LAB_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LOG_DIR=/tmp/lsrd
RUN_DIR=/run/lsrd

if [ -x "$LAB_DIR/.venv/bin/python" ]; then
  PY="$LAB_DIR/.venv/bin/python"
else
  PY=$(command -v python3)
  echo "[!] 没找到 $LAB_DIR/.venv（请先在该目录执行 uv sync），改用 $PY" >&2
fi

routers () {
  ip netns list | awk '{print $1}' | grep -E '^r[0-9]+$' | sort -V
}

rid_of () { echo "${1#r}"; }

bridges_of () {
  ip -n "$1" -j link show type bridge 2>/dev/null | "$PY" -c \
    'import json,sys; print(" ".join(e["ifname"] for e in json.load(sys.stdin)))'
}

is_running () {
  local pidfile
  pidfile="$RUN_DIR/$(rid_of "$1").pid"
  [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

# 守护进程是否还在 rN 这个 namespace 里（实验床被重建过的话，旧进程会留在已删除的 namespace 里）
in_current_ns () {
  local r=$1 pid=$2
  [ -e "/run/netns/$r" ] || return 1
  [ "$(stat -L -c %i "/proc/$pid/ns/net" 2>/dev/null)" = "$(stat -L -c %i "/run/netns/$r" 2>/dev/null)" ]
}

# 有 pid 文件的全部路由器（不依赖 namespace 是否还在）
routers_with_pid () {
  for f in "$RUN_DIR"/*.pid; do
    [ -f "$f" ] || continue
    echo "r$(basename "$f" .pid)"
  done
}

start_one () {
  local r=$1 ; shift
  local rid ; rid=$(rid_of "$r")
  if is_running "$r"; then
    if in_current_ns "$r" "$(cat "$RUN_DIR/$rid.pid")"; then
      echo "  [--]   $r 已在运行（pid $(cat "$RUN_DIR/$rid.pid")），跳过"
      return
    fi
    echo "  [!]    $r 的旧进程还留在已经不存在的 namespace 里（实验床重建过），先停掉它"
    stop_one "$r"
  fi
  local passive=()
  for br in $(bridges_of "$r"); do passive+=(--passive "$br"); done
  mkdir -p "$LOG_DIR" "$RUN_DIR"
  : > "$LOG_DIR/$r.log"        # 每次启动从空日志开始
  # setsid：让守护进程脱离当前终端；日志走 --log，标准输入输出全部接到 /dev/null
  # （整个子 shell 都重定向，否则它会攥着调用方的管道不放）
  ( cd "$LAB_DIR" && exec setsid ip netns exec "$r" "$PY" -m lsrd --id "$rid" "${passive[@]}" \
      --log "$LOG_DIR/$r.log" "$@" ) </dev/null >/dev/null 2>&1 &
  for _ in $(seq 1 20); do
    is_running "$r" && break
    sleep 0.1
  done
  if is_running "$r"; then
    echo "  [OK]   $r  rid=$rid ${passive[*]:-} $*  (pid $(cat "$RUN_DIR/$rid.pid"), 日志 $LOG_DIR/$r.log)"
  else
    echo "  [FAIL] $r 没有起来，看日志：tail $LOG_DIR/$r.log"
    return 1
  fi
}

stop_one () {
  local r=$1 rid ; rid=$(rid_of "$r")
  local pidfile="$RUN_DIR/$rid.pid"
  if is_running "$r"; then
    local pid ; pid=$(cat "$pidfile")
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 30); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
    echo "  [OK]   $r 已停止"
  else
    echo "  [--]   $r 没有在运行"
  fi
  rm -f "$pidfile" "$RUN_DIR/$rid.sock"
  # 守护进程退出时会 flush 自己的路由；万一是被 kill -9 的，这里兜底
  if ip netns list | awk '{print $1}' | grep -qx "$r"; then
    ip -n "$r" route flush proto 200 2>/dev/null || true
  fi
}

show_one () {
  local r=$1 what=${2:-neighbors}
  ( cd "$LAB_DIR" && "$PY" -m lsrd.cli "$(rid_of "$r")" "$what" )
}

check () {
  local rc=0 rs ; rs=$(routers)
  [ -n "$rs" ] || { echo "[!] 没有 rN namespace，实验床没搭？" >&2 ; return 1; }
  echo "[*] 守护进程："
  for r in $rs; do
    if is_running "$r"; then echo "  [OK]   $r 在运行"; else echo "  [FAIL] $r 没有在运行"; rc=1; fi
  done
  echo "[*] 邻接（每条路由器间链路的两端都应 Full；期望数 = 该路由器上非网桥的 IPv4 接口数）："
  for r in $rs; do
    is_running "$r" || continue
    local full init nfull want
    full=$(show_one "$r" json | "$PY" -c 'import json,sys; s=json.load(sys.stdin); print(",".join(str(n["rid"]) for n in s["neighbors"] if n["state"]=="Full"))')
    init=$(show_one "$r" json | "$PY" -c 'import json,sys; s=json.load(sys.stdin); print(",".join(str(n["rid"]) for n in s["neighbors"] if n["state"]!="Full"))')
    nfull=$(show_one "$r" json | "$PY" -c 'import json,sys; s=json.load(sys.stdin); print(sum(1 for n in s["neighbors"] if n["state"]=="Full"))')
    want=$(ip -n "$r" -j addr show | "$PY" -c 'import json,sys; b=set(sys.argv[1].split()); print(sum(1 for e in json.load(sys.stdin) if e["ifname"]!="lo" and e["ifname"] not in b and any(a["family"]=="inet" for a in e.get("addr_info",[]))))' "$(bridges_of "$r")")
    if [ -n "$init" ]; then echo "  [FAIL] $r Full={$full} 非 Full={$init}"; rc=1
    elif [ "$nfull" != "$want" ]; then echo "  [FAIL] $r Full={$full}，期望 $want 个邻居"; rc=1
    else echo "  [OK]   $r Full={$full}"; fi
  done
  echo "[*] LSDB 一致性（指纹应完全相同）："
  local digests="" d
  for r in $rs; do
    is_running "$r" || continue
    d=$(show_one "$r" digest)
    echo "         $r $d"
    digests="$digests $d"
  done
  if [ "$(echo "$digests" | tr ' ' '\n' | grep -c .)" -gt 0 ] && [ "$(echo "$digests" | tr ' ' '\n' | grep . | sort -u | wc -l)" -eq 1 ]; then
    echo "  [OK]   一致"
  else
    echo "  [FAIL] 不一致"; rc=1
  fi
  echo "[*] 内核里 lsrd 写的路由（proto 200）："
  for r in $rs; do
    echo "  $r: $(ip -n "$r" route show proto 200 | wc -l) 条"
  done
  bash "$LAB_DIR/topo.sh" check || rc=1
  return $rc
}

CMD="${1:-}" ; shift || true
case "$CMD" in
  start)
    echo "[*] 启动守护进程："
    for r in $(routers); do start_one "$r" "$@"; done
    ;;
  stop)
    echo "[*] 停止守护进程："
    if [ $# -gt 0 ]; then for r in "$@"; do stop_one "$r"; done
    else for r in $(routers_with_pid); do stop_one "$r"; done; fi
    ;;
  restart)
    [ $# -ge 1 ] || { echo "用法：run.sh restart rN [选项...]" >&2 ; exit 1; }
    r=$1 ; shift
    stop_one "$r"
    start_one "$r" "$@"
    ;;
  status)
    for r in $(routers); do
      if is_running "$r"; then
        echo "$r: 运行中 (pid $(cat "$RUN_DIR/$(rid_of "$r").pid"))，$(show_one "$r" stats | head -1)"
      else
        echo "$r: 未运行"
      fi
    done
    ;;
  show)
    [ $# -ge 1 ] || { echo "用法：run.sh show rN [neighbors|lsdb|routes|stats|digest|json]" >&2 ; exit 1; }
    show_one "$@"
    ;;
  logs)
    [ $# -ge 1 ] || { echo "用法：run.sh logs rN" >&2 ; exit 1; }
    tail -n 30 -f "$LOG_DIR/$1.log"
    ;;
  poke)
    [ $# -ge 1 ] || { echo "用法：run.sh poke rN" >&2 ; exit 1; }
    is_running "$1" || { echo "[!] $1 没有在运行" >&2 ; exit 1; }
    kill -USR1 "$(cat "$RUN_DIR/$(rid_of "$1").pid")"
    echo "[*] 已让 $1 重新生成一条 LSA（seq+1）"
    ;;
  check)
    check
    ;;
  *)
    sed -n '5,18p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
