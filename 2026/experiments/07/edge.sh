#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# Lab 7 B 段：在实验床的 host 上启动服务实例，并用 cgroup v2 的 cpu.max 给每个实例限定算力。
#
#   实例       instance.py，每台 host 的 namespace 里一个，监听 7700 端口
#   算力       /sys/fs/cgroup/lab07/<host>/cpu.max = "<配额> <周期>"，周期固定 10 ms；
#              限额 30 表示这个实例的计算进程最多用 30% 的一个 CPU 核
#   预设       一组 host 与限额的组合；lecture11 是第 11 讲模块一到三用的，
#              lecture11x 是综合动手用的（课上先不看定义）
#
# 用法（在本目录执行；先用 lab4_topo.sh up 搭好实验床）：
#   sudo bash edge.sh up [PRESET]      # 按预设建 cgroup 并启动实例（默认 lecture11）
#   sudo bash edge.sh cpu HOST PCT     # 只改一个实例的限额，PCT 取 1–100
#   sudo bash edge.sh status           # 列出实例、限额与计算进程
#   sudo bash edge.sh down             # 停实例、删 cgroup（幂等）
# ==============================================================================

E7_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
E7_STATE=/run/lab07
E7_CG=/sys/fs/cgroup/lab07
E7_PORT=7700
E7_PERIOD=10000        # 微秒；周期短，几十毫秒的计算也能被均匀地限速

die() {
  echo "edge.sh：$*" >&2
  exit 1
}

preset() {
  case "$1" in
    lecture11) echo 'h1b:15 h3a:30 h4a:60' ;;
    lecture11x) echo 'h2a:60 h3b:15 h4b:30' ;;
    *) die "没有预设 $1；可用：lecture11、lecture11x" ;;
  esac
}

set_cpu() {
  local host=$1 pct=$2
  [[ "$pct" =~ ^[0-9]+$ && "$pct" -ge 1 && "$pct" -le 100 ]] || die '限额取 1–100 的整数（一个 CPU 核的百分比）。'
  [[ -d "$E7_CG/$host" ]] || die "没有实例 $host；先执行 edge.sh up。"
  echo "$((E7_PERIOD * pct / 100)) $E7_PERIOD" >"$E7_CG/$host/cpu.max"
}

down() {
  local pidfile pid host
  for pidfile in "$E7_STATE"/*.pid; do
    [[ -e "$pidfile" ]] || continue
    pid=$(cat "$pidfile")
    kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
  done
  sleep 0.2
  if [[ -d "$E7_CG" ]]; then
    for host in "$E7_CG"/*/; do
      [[ -d "$host" ]] || continue
      while read -r pid; do kill -KILL "$pid" 2>/dev/null || true; done <"$host/cgroup.procs"
    done
    sleep 0.1
    find "$E7_CG" -mindepth 1 -maxdepth 1 -type d -exec rmdir {} + 2>/dev/null || true
    rmdir "$E7_CG" 2>/dev/null || true
  fi
  rm -rf -- "$E7_STATE"
}

up() {
  local name=${1:-lecture11} item host pct
  [[ -f /run/lab04/namespaces ]] || die '实验床尚未搭建，请先执行 lab4_topo.sh up。'
  [[ -f /sys/fs/cgroup/cgroup.controllers ]] || die '需要 cgroup v2（/sys/fs/cgroup/cgroup.controllers 不存在）。'
  grep -qw cpu /sys/fs/cgroup/cgroup.controllers || die '这台机器的 cgroup v2 没有 cpu 控制器。'
  down
  # 只有真正的根 cgroup（没有 cgroup.type 文件）才可以在有进程的情况下给子组开启 cpu 控制器。
  # 在容器里，这里的“根”其实是宿主机上的一个子组，改它会把整个容器切到线程模式，所以不碰它。
  if [[ ! -e /sys/fs/cgroup/cgroup.type ]]; then
    echo +cpu >/sys/fs/cgroup/cgroup.subtree_control 2>/dev/null || true
  fi
  grep -qw cpu /sys/fs/cgroup/cgroup.subtree_control \
    || die '这里不能给子 cgroup 开启 cpu 控制器（常见于容器内）。请在标准的 Ubuntu 虚拟机上运行。'
  mkdir -p "$E7_STATE" "$E7_CG"
  echo +cpu >"$E7_CG/cgroup.subtree_control"
  echo "$name" >"$E7_STATE/preset"
  for item in $(preset "$name"); do
    host=${item%%:*}
    pct=${item##*:}
    mkdir -p "$E7_CG/$host"
    set_cpu "$host" "$pct"
    setsid ip netns exec "$host" python3 "$E7_DIR/instance.py" --name "$host" --port "$E7_PORT" \
      --pidfile "$E7_STATE/$host.worker" </dev/null >"$E7_STATE/$host.log" 2>&1 &
    echo $! >"$E7_STATE/$host.pid"
  done
  # 实例把计算进程的进程号写进 .worker 文件；在这里（namespace 外面）把它放进对应的 cgroup。
  for item in $(preset "$name"); do
    host=${item%%:*}
    for _ in $(seq 30); do
      [[ -s "$E7_STATE/$host.worker" ]] && break
      sleep 0.1
    done
    [[ -s "$E7_STATE/$host.worker" ]] || die "实例 $host 没有起来：$(tail -2 "$E7_STATE/$host.log")"
    cat "$E7_STATE/$host.worker" >"$E7_CG/$host/cgroup.procs"
  done
  echo "[*] 预设 $name：实例已启动，端口 $E7_PORT。查看限额用 edge.sh status；结束后执行 edge.sh down。"
}

status() {
  local host quota period
  [[ -d "$E7_CG" ]] || { echo '[实例] 没有在运行的实例。'; return; }
  echo "[预设] $(cat "$E7_STATE/preset" 2>/dev/null || echo '?')"
  for host in "$E7_CG"/*/; do
    [[ -d "$host" ]] || continue
    read -r quota period <"$host/cpu.max"
    echo "[实例] $(basename "$host")  cpu.max $quota $period（$((quota * 100 / period))% 个核）  计算进程 $(tr '\n' ' ' <"$host/cgroup.procs")"
  done
}

[[ "$EUID" -eq 0 ]] || die '需要 root：sudo bash edge.sh ...'
case "${1:-}" in
  up) up "${2:-lecture11}" ;;
  cpu)
    [[ "$#" -eq 3 ]] || die '用法：edge.sh cpu HOST PCT'
    set_cpu "$2" "$3"
    echo "[*] $2 的限额改为 $3%。"
    ;;
  status) status ;;
  down)
    down
    echo '[*] 实例已停止，cgroup 已删除。'
    ;;
  *) die '用法：edge.sh up [PRESET] | cpu HOST PCT | status | down' ;;
esac
