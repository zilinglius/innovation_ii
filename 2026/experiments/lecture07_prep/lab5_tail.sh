#!/usr/bin/env bash
set -Eeuo pipefail

# 第 07 讲用的副本，源自 2026/experiments/05/tail.sh，路径已改为本目录。
# backend.py、tailbench.py、compare.py、bulk.py、tailkit/ 也是 2026/experiments/05 的副本，tailkit 的 TODO 保持留白。

# ==============================================================================
# Lab 5 辅助脚本：在完整实验床（lab4_topo.sh）上启停后端、制造共享队列与大象流
#
# 拓扑沿用 lab4_topo.sh：2 spine（r5、r6）× 4 leaf（r1–r4）× 8 host（h1a–h4b）。
# 后端：除运行前端的 h1a 外，其余 7 台 host 各运行一个 backend.py，监听 7000 端口。
# 算法：后端与大象流都显式指定 cubic，不依赖系统默认值。
#
# 用法（从仓库根目录执行）：
#   sudo bash 2026/experiments/lecture07_prep/lab5_tail.sh up [CC]                  # 启动 7 个后端（幂等），算法默认 cubic
#   sudo bash 2026/experiments/lecture07_prep/lab5_tail.sh check                    # 往返验证每个后端
#   sudo bash 2026/experiments/lecture07_prep/lab5_tail.sh queue NS DEV MBIT LIMIT  # 把端口改成指定速率 + pfifo 单队列
#   sudo bash 2026/experiments/lecture07_prep/lab5_tail.sh elephant SRC DST SECONDS # 启动一条 SRC→DST 的 iperf3 大象流
#   sudo bash 2026/experiments/lecture07_prep/lab5_tail.sh backlog NS DEV           # 查看端口队列的积压与丢包计数
#   sudo bash 2026/experiments/lecture07_prep/lab5_tail.sh tcpstat                  # 8 台 host 的重传、超时、尾部丢失探测累计值
#   sudo bash 2026/experiments/lecture07_prep/lab5_tail.sh clear                    # 停大象流，全部端口恢复基线
#   sudo bash 2026/experiments/lecture07_prep/lab5_tail.sh down                     # 停后端与大象流（幂等），不拆实验床
# ==============================================================================

L5_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
L5_DIR="$L5_ROOT/2026/experiments/lecture07_prep"
L5_TOPO="$L5_ROOT/2026/experiments/lecture07_prep/lab4_topo.sh"
L5_STATE=/run/lab05
L5_RESULTS=/tmp/lab05-results
L5_BACKENDS=(h1b h2a h2b h3a h3b h4a h4b)
L5_PORT=7000
L5_IPERF_PORT=5205

die() {
  echo "lab5_tail.sh：$*" >&2
  exit 1
}

require_topo() {
  [[ -f /run/lab04/namespaces ]] || die '实验床尚未搭建，请先执行 sudo bash 2026/experiments/lecture07_prep/lab4_topo.sh up。'
}

host_ip() {
  local name=$1
  [[ "$name" =~ ^h([1-4])([ab])$ ]] || die "未知主机 $name（h1a–h4b）。"
  if [[ "${BASH_REMATCH[2]}" == a ]]; then
    echo "10.0.${BASH_REMATCH[1]}.11"
  else
    echo "10.0.${BASH_REMATCH[1]}.12"
  fi
}

# 按登记的 pid 文件结束进程；文件不存在时什么都不做。
stop_pids() {
  local file pid
  for file in "$L5_STATE"/"$1"*.pid; do
    [[ -e "$file" ]] || continue
    pid=$(<"$file")
    kill "$pid" 2>/dev/null || true
    rm -f -- "$file"
  done
}

up() {
  local host cc=${1:-cubic}
  require_topo
  mkdir -p "$L5_STATE" "$L5_RESULTS"
  for host in "${L5_BACKENDS[@]}"; do
    if [[ -e "$L5_STATE/backend-$host.pid" ]] && kill -0 "$(<"$L5_STATE/backend-$host.pid")" 2>/dev/null; then
      continue
    fi
    # setsid 让后端脱离当前终端；pid 登记后供 down 回收。
    setsid ip netns exec "$host" python3 "$L5_DIR/backend.py" --port "$L5_PORT" --cc "$cc" \
      </dev/null >>"$L5_RESULTS/backend-$host.log" 2>&1 &
    echo "$!" >"$L5_STATE/backend-$host.pid"
  done
  sleep 0.5
  echo "[*] 后端已启动：${L5_BACKENDS[*]}，端口 $L5_PORT，算法 $cc。换算法前先执行 lab5_tail.sh down。"
}

check() {
  require_topo
  ip netns exec h1a python3 "$L5_DIR/tailbench.py" --fanout 7 --rounds 20 --label check
  echo '[OK] 7 个后端都完成了 20 轮往返。'
}

queue() {
  local ns=$1 dev=$2 mbit=$3 limit=$4
  require_topo
  [[ "$limit" =~ ^[0-9]+$ && "$limit" -ge 1 ]] || die '队列上限取正整数（报文数）。'
  bash "$L5_TOPO" limit "$ns" "$dev" "$mbit"
  ip netns exec "$ns" tc qdisc del dev "$dev" parent 1:10 2>/dev/null || true
  ip netns exec "$ns" tc qdisc add dev "$dev" parent 1:10 handle 10: pfifo limit "$limit"
  echo "[*] $ns 的 $dev：$mbit Mbit/s，单队列 pfifo，上限 $limit 个报文。"
}

elephant() {
  local src=$1 dst=$2 seconds=$3 address
  require_topo
  address=$(host_ip "$dst")
  mkdir -p "$L5_STATE" "$L5_RESULTS"
  setsid ip netns exec "$dst" iperf3 -s -1 -p "$L5_IPERF_PORT" </dev/null >/dev/null 2>&1 &
  echo "$!" >"$L5_STATE/elephant-server.pid"
  sleep 0.3
  setsid ip netns exec "$src" iperf3 -c "$address" -p "$L5_IPERF_PORT" -t "$seconds" -C cubic \
    </dev/null >"$L5_RESULTS/elephant.log" 2>&1 &
  echo "$!" >"$L5_STATE/elephant-client.pid"
  echo "[*] 大象流 $src→$dst（cubic，$seconds 秒）已启动；记录在 $L5_RESULTS/elephant.log。"
}

backlog() {
  ip netns exec "$1" tc -s qdisc show dev "$2" parent 1:10
}

# 汇总全部后端与前端的 TCP 计数器（累计值）；两次读数相减即本次实验的增量。
tcpstat() {
  local host
  for host in h1a "${L5_BACKENDS[@]}"; do
    ip netns exec "$host" nstat -asz TcpRetransSegs TcpExtTCPTimeouts TcpExtTCPLossProbes
  done | awk '$1 ~ /^Tcp/ { sum[$1] += $2 }
    END { printf "重传段 %d，超时 %d，尾部丢失探测 %d\n", sum["TcpRetransSegs"], sum["TcpExtTCPTimeouts"], sum["TcpExtTCPLossProbes"] }'
}

clear_all() {
  require_topo
  stop_pids elephant
  bash "$L5_TOPO" clear
  echo '[*] 大象流已停，全部端口恢复基线。'
}

down() {
  stop_pids elephant
  stop_pids backend
  rm -rf -- "$L5_STATE"
  echo "[*] 后端与大象流已停；结果保留在 $L5_RESULTS。"
}

case "${1:-}" in
  up) up "${2:-cubic}" ;;
  check) check ;;
  queue)
    [[ $# -eq 5 ]] || die '用法：lab5_tail.sh queue NS DEV MBIT LIMIT'
    queue "$2" "$3" "$4" "$5"
    ;;
  elephant)
    [[ $# -eq 4 ]] || die '用法：lab5_tail.sh elephant SRC DST SECONDS'
    elephant "$2" "$3" "$4"
    ;;
  backlog)
    [[ $# -eq 3 ]] || die '用法：lab5_tail.sh backlog NS DEV'
    backlog "$2" "$3"
    ;;
  tcpstat) tcpstat ;;
  clear) clear_all ;;
  down) down ;;
  *) die '用法：lab5_tail.sh up|check|queue|elephant|backlog|tcpstat|clear|down' ;;
esac
