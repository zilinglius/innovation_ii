#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# Lab 3 实验床：2 spine × 4 leaf × 8 host 的 leaf-spine 迷你数据中心
#
#         ┌─ h1a（10.0.1.11）      每个 leaf 的机架网桥上接两台 host
#   机架 1│
#         └─ br1 ─ r1（leaf）─┬── 10.1.0.0/30 ── r5（spine）
#                              └── 10.1.1.0/30 ── r6（spine）
#   机架 2、3、4 与机架 1 同构：r2、r3、r4 各有两条上联，全网共 8 条 leaf–spine 链路。
#   leaf 与 spine 都是 network namespace 里的内核协议栈，路由由 lsrd --ecmp 写入。
#
# 地址规划（与课堂脚本 classroom.sh 完全一致；Lab 4–9 沿用这套约定）：
#   机架 i       10.0.i.0/24   网关 br{i} = .1   host h{i}a = .11、h{i}b = .12
#   leaf–spine   第 k 条链路 10.1.k.0/30，leaf = .1、spine = .2，k = 2*(leaf-1)+(spine-5)
#                即 r1–r5 = 10.1.0.0/30、r1–r6 = 10.1.1.0/30、…、r4–r6 = 10.1.7.0/30
#   路由         lsrd --ecmp 写内核（proto 200），每条跨机架路由应有两个下一跳
#   限速         host 接入口双向 100 Mbit/s；leaf–spine 两端 100 / 50 Mbit/s 可切换
#
# 用法（均从仓库根目录执行）：
#   sudo bash 2026/experiments/03/topo.sh up              # 搭建并启动 lsrd（幂等，先清理再搭）
#   sudo bash 2026/experiments/03/topo.sh up --reference  # 同上，路由改用 02/reference 参考实现
#   sudo bash 2026/experiments/03/topo.sh check           # 连通性自检（up 之后）
#   sudo bash 2026/experiments/03/topo.sh rate 50         # 切换全部上联档位（50 或 100 Mbit/s）
#   sudo bash 2026/experiments/03/topo.sh show            # 打印路由器的地址与路由
#   sudo bash 2026/experiments/03/topo.sh down            # 拆除（幂等）
# ==============================================================================

L3_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
L3_STATE=/run/lab03
L3_RESULTS=/tmp/lab03-results
L3_PY="$L3_ROOT/2026/experiments/02/.venv/bin/python"
L3_ROUTERS=(r1 r2 r3 r4 r5 r6)
L3_HOSTS=(h1a h1b h2a h2b h3a h3b h4a h4b)

todo_missing() {
  echo "topo.sh：${1}还没完成——先按文件内的 TODO 注释补全，再重跑。" >&2
  return 1
}

down() {
  local ns pid
  bash "$L3_ROOT/2026/experiments/03/overlay_down.sh"
  [[ -f "$L3_STATE/namespaces" ]] || return 0
  while read -r ns; do
    for pid in $(ip netns pids "$ns" 2>/dev/null || true); do
      kill "$pid" 2>/dev/null || true
    done
  done <"$L3_STATE/namespaces"
  sleep 0.3
  while read -r ns; do
    for pid in $(ip netns pids "$ns" 2>/dev/null || true); do
      kill -KILL "$pid" 2>/dev/null || true
    done
    ip netns del "$ns" 2>/dev/null || true
  done <"$L3_STATE/namespaces"
  rm -rf -- "$L3_STATE"
  echo '[*] 实验床已拆除；日志保留在 /tmp/lab03-results。'
}

up_failed() {
  local status=$?
  down
  exit "$status"
}

# new_ns 与裸 ip netns add 的差别：把 namespace 登记进清理清单、置 up 环回口。
# 所有 namespace（包括你在 TODO 里建的 host）都必须经它创建，down 才能清理到。
new_ns() {
  ip netns add "$1"
  printf '%s\n' "$1" >>"$L3_STATE/namespaces"
  ip -n "$1" link set lo up
}

limit_port() {
  ip netns exec "$1" tc qdisc del dev "$2" root 2>/dev/null || true
  ip netns exec "$1" tc qdisc add dev "$2" root handle 1: htb default 10 r2q 100
  ip netns exec "$1" tc class add dev "$2" parent 1: classid 1:10 htb rate "${3}mbit"
  ip netns exec "$1" tc qdisc add dev "$2" parent 1:10 handle 10: fq
}

set_rate() {
  local rate=$1 rack spine
  [[ "$rate" == 50 || "$rate" == 100 ]] || { echo '上联速率可选 50 或 100 Mbit/s。' >&2; exit 2; }
  for rack in 1 2 3 4; do
    for spine in 5 6; do
      limit_port "r$rack" "r$rack-r$spine" "$rate"
      limit_port "r$spine" "r$spine-r$rack" "$rate"
    done
  done
  echo "[*] 全部 leaf–spine 链路两端 egress = $rate Mbit/s；host 接入口保持 100 Mbit/s。"
}

# 数据平面就绪的断言：6 台路由器邻接数、LSDB 规模、r1 的跨机架路由两个下一跳。
ready() {
  python3 - "$L3_STATE" <<'PY'
import json, pathlib, socket, sys
root = pathlib.Path(sys.argv[1])
for rid in range(1, 7):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(1)
        sock.connect(str(root / f"r{rid}.sock"))
        sock.sendall(b"snapshot\n")
        data = bytearray()
        while chunk := sock.recv(65536):
            data.extend(chunk)
    snap = json.loads(data)
    expected = 2 if rid <= 4 else 4
    assert sum(n["state"] == "Full" for n in snap["neighbors"]) == expected, f"r{rid} 邻接数"
    assert len(snap["lsdb"]) == 6, f"r{rid} LSDB 规模"
    if rid == 1:
        route = next(r for r in snap["fib"] if r["dst"] == "10.0.3.0/24")
        assert len(route["nexthops"]) == 2, route
PY
}

start_lsrd() {
  local implementation=lsrd rid directory opts
  [[ "${1:-}" == --reference ]] && implementation=reference/lsrd
  directory="$L3_ROOT/2026/experiments/02"
  [[ "$implementation" == reference/lsrd ]] && directory+="/reference"
  for rid in 1 2 3 4 5 6; do
    opts=(--id "$rid" --ecmp \
      --pidfile "$L3_STATE/r$rid.pid" --sock "$L3_STATE/r$rid.sock" --log "$L3_RESULTS/r$rid.log")
    [[ "$rid" -le 4 ]] && opts+=(--passive "br$rid")
    (cd "$directory" && \
      exec setsid ip netns exec "r$rid" "$L3_PY" -m lsrd "${opts[@]}") </dev/null >/dev/null 2>&1 &
  done
}

sysctl_routers() {
  local ns
  for ns in "${L3_ROUTERS[@]}"; do
    ip netns exec "$ns" sysctl -qw net.ipv4.ip_forward=1 \
      net.ipv4.conf.all.rp_filter=2 net.ipv4.conf.default.rp_filter=2 \
      net.ipv4.fib_multipath_hash_policy=1
  done
}

# 抓包与限速使用普通分段，减小虚拟网卡 offload 对字节口径的影响。
disable_offload() {
  local ns iface
  while read -r ns; do
    for iface in $(ip -n "$ns" -o link show type veth | awk -F': ' '{print $2}' | cut -d@ -f1); do
      ip netns exec "$ns" ethtool -K "$iface" gro off gso off tso off tx off rx off >/dev/null 2>&1 || true
    done
  done <"$L3_STATE/namespaces"
}

build_access() {
  # TODO 1　机架接入网：4 个机架，每个机架 = 1 个网桥 + 2 台 host
  #
  # 对照阅读：classroom.sh 的 up() 里 for rack in 1 2 3 4 循环的前一半。
  # 对 rack = 1..4 逐个完成（建议写循环，不要复制粘贴四份）：
  #   1) 在 r{rack} 里建网桥 br{rack}，地址 10.0.{rack}.1/24，置 up——它就是机架网关；
  #      网桥上不跑 lsrd 的邻接（start_lsrd 已经用 --passive br{rack} 处理）
  #   2) 对 host ∈ {a, b}，namespace 名为 h{rack}{host}：
  #      - new_ns h{rack}{host}（务必用 new_ns，否则 down 清理不到它）
  #      - 建 veth 对：leaf 侧叫 r{rack}-h{rack}{host}，peer 在 host 里叫 eth0
  #      - leaf 侧 veth 打进网桥（master）并置 up
  #      - host 地址 10.0.{rack}.11 / .12，eth0 置 up
  #      - host 的默认路由指向 10.0.{rack}.1
  #      - host 侧 eth0 与 leaf 侧端口都用 limit_port 限速 100 Mbit/s（两边都要）
  # 完成后删除下面的 todo_missing 一行。
  todo_missing 'TODO 1（build_access：机架接入网）'
}

build_fabric() {
  # TODO 2　leaf–spine 上联：8 条三层点到点链路
  #
  # 对照阅读：classroom.sh 的 up() 里 for spine in 5 6 一段。
  # 对每个 rack（leaf 为 r{rack}）和每台 spine（r5、r6）：
  #   k = 2*(rack-1) + (spine-5)        # 链路编号：10.1.0.0/30 … 10.1.7.0/30
  #   - 建 veth 对：leaf 侧叫 r{rack}-r{spine}，peer 在 spine 里叫 r{spine}-r{rack}
  #     （spine 的 namespace 已在 up() 里创建好）
  #   - leaf 侧地址 10.1.{k}.1/30，spine 侧地址 10.1.{k}.2/30，两端置 up
  #   - 上联不限速：up() 结尾的 set_rate 会按当前档位统一配置，便于任务中切换
  # 完成后删除下面的 todo_missing 一行。
  todo_missing 'TODO 2（build_fabric：leaf–spine 上联）'
}

up() {
  local ns
  [[ -x "$L3_PY" ]] || { echo '先执行 uv sync --project 2026/experiments/02 --frozen。' >&2; exit 1; }
  down
  for ns in "${L3_ROUTERS[@]}" "${L3_HOSTS[@]}"; do
    if [[ -e "/run/netns/$ns" ]]; then
      echo "$ns 已存在：先执行 classroom.sh down 清理课堂拓扑，或按 Lab 1/2 指导书清理。" >&2; exit 1
    fi
  done
  mkdir -p "$L3_STATE" "$L3_RESULTS"
  : >"$L3_STATE/namespaces"
  trap up_failed ERR
  for ns in "${L3_ROUTERS[@]}"; do new_ns "$ns"; done
  build_access
  build_fabric
  sysctl_routers
  start_lsrd "$@"
  disable_offload
  set_rate 100
  for _ in $(seq 1 40); do
    if ready >/dev/null 2>&1; then
      trap - ERR
      echo '[*] 6 台路由器全部 Full；r1 的跨机架路由有两个下一跳。实验床就绪。'
      echo '[*] 下一步自检：sudo bash 2026/experiments/03/topo.sh check'
      return
    fi
    sleep 0.3
  done
  echo '路由未就绪：查看 /tmp/lab03-results/r*.log。'
  echo '单下一跳或邻接不齐，通常是 Lab 2 任务 8 的 ECMP（--ecmp）还没实现。' >&2
  return 1
}

check() {
  # TODO 3　连通性自检。ready 只断言了控制平面，这里验证数据平面。
  #
  # 至少覆盖四组检查；任何一处不通就以非零退出（脚本头部的 set -e 会帮你）：
  #   1) 8 条上联：每条链路两端互 ping 对方直连地址（r1 ping 10.1.0.2、r5 ping 10.1.0.1，…）
  #   2) 8 台 host：各自 ping 自己的网关 10.0.{rack}.1
  #   3) 跨机架往返：h1a → 10.0.3.11、h3a → 10.0.1.11、h4b → 10.0.2.12
  #   4) 每个 leaf 去往其他 3 个机架前缀的路由都有两个下一跳（共 12 条；ready 只查了 r1 → 10.0.3.0/24）
  # 全部通过后打印（保持这两行文字，便于对照验收）：
  #   [OK] 8 条上联往返、8 台 host 网关可达、跨机架往返。
  #   [OK] 4 个 leaf 去往其他 3 个机架的 12 条路由均有两个下一跳。
  # 再打印 r1 去往 10.0.3.0/24 的路由——应有 proto 200 的两个下一跳。
  ready || { echo 'ready 断言未通过：先看 /tmp/lab03-results/r*.log 与 topo.sh show。' >&2; return 1; }
  todo_missing 'TODO 3（check：连通性自检）'
}

show() {
  local ns
  for ns in "${L3_ROUTERS[@]}"; do
    echo "== $ns =="
    ip -n "$ns" -br addr show | grep -v '^lo' || true
    ip -n "$ns" route show
  done
}

[[ "$EUID" -eq 0 ]] || { echo '请从仓库根目录用 sudo bash 2026/experiments/03/topo.sh 执行。' >&2; exit 1; }
case "${1:-up}" in
  up) if [[ "$#" -gt 0 ]]; then shift; fi; up "$@" ;;
  down) down ;;
  rate)
    [[ -f "$L3_STATE/namespaces" ]] || { echo '请先执行 topo.sh up。' >&2; exit 1; }
    set_rate "${2:-100}"
    ;;
  check|show)
    [[ -f "$L3_STATE/namespaces" ]] || { echo '请先执行 topo.sh up。' >&2; exit 1; }
    "$1"
    ;;
  *) echo '用法：topo.sh [up [--reference]|check|rate 50|rate 100|show|down]' >&2; exit 2 ;;
esac
