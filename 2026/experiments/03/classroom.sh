#!/usr/bin/env bash
set -Eeuo pipefail

# 第五讲课堂观察：一张 2 spine × 4 leaf × 8 host 拓扑，复用 Lab 2 的 lsrd。
# leaf r1–r4：brN / 10.0.N.1，host hNa/hNb：.11/.12，接口 eth0。
# leaf–spine 第 k 条链路：10.1.k.0/30，leaf .1、spine .2，k = 2*(N-1)+(S-5)。
# 只清理 /run/course05 登记的资源；与 Lab 1/2 重名时拒绝搭建。
C5_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
C5_STATE=/run/course05
C5_RESULTS=/tmp/course05-results
C5_PY="$C5_ROOT/2026/experiments/02/.venv/bin/python"
C5_TRANSFER_PY="$C5_ROOT/2026/experiments/03/.venv/bin/python"
C5_TRANSFER="$C5_ROOT/2026/experiments/03/transfer.py"
C5_BG=()
C5_PINNED=0
C5_RESTORE_A=0

stop_jobs() {
  local pid
  for pid in "${C5_BG[@]}"; do
    kill -TERM "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  C5_BG=()
}

clear_pins() {
  [[ "$C5_PINNED" -eq 1 ]] || return 0
  ip -n r1 rule del priority 105 2>/dev/null || true
  ip -n r1 rule del priority 106 2>/dev/null || true
  ip -n r1 route flush table 105 2>/dev/null || true
  ip -n r1 route flush table 106 2>/dev/null || true
  C5_PINNED=0
}

cleanup_observation() {
  stop_jobs
  clear_pins
  if [[ "$C5_RESTORE_A" -eq 1 ]]; then
    ip -n t3a link set eth0 up 2>/dev/null || true
  fi
}
trap cleanup_observation EXIT

down() {
  local ns pid
  [[ -f "$C5_STATE/namespaces" ]] || return 0
  while read -r ns; do
    for pid in $(ip netns pids "$ns" 2>/dev/null || true); do
      kill "$pid" 2>/dev/null || true
    done
  done <"$C5_STATE/namespaces"
  sleep 0.3
  while read -r ns; do
    for pid in $(ip netns pids "$ns" 2>/dev/null || true); do
      kill -KILL "$pid" 2>/dev/null || true
    done
    ip netns del "$ns" 2>/dev/null || true
  done <"$C5_STATE/namespaces"
  rm -rf -- "$C5_STATE"
  echo '[清理] 课堂拓扑与业务进程已移除；结果保留在 /tmp/course05-results。'
}

up_failed() {
  local status=$?
  down
  exit "$status"
}

new_ns() {
  ip netns add "$1"
  printf '%s\n' "$1" >>"$C5_STATE/namespaces"
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
  echo "[设置] 所有 leaf–spine 链路的两端 egress 均为 $rate Mbit/s；host 接入口为 100 Mbit/s。"
}

ready() {
  python3 - "$C5_STATE" <<'PY'
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
    assert sum(n["state"] == "Full" for n in snap["neighbors"]) == expected
    assert len(snap["lsdb"]) == 6
    if rid == 1:
        route = next(r for r in snap["fib"] if r["dst"] == "10.0.3.0/24")
        assert len(route["nexthops"]) == 2, route
PY
}

up() {
  local implementation=lsrd rack spine ns iface host octet k rid
  [[ "${1:-}" == --reference ]] && implementation=reference/lsrd
  local directory="$C5_ROOT/2026/experiments/02"
  [[ "$implementation" == reference/lsrd ]] && directory+=/reference
  [[ -x "$C5_PY" ]] || { echo '先执行 uv sync --project 2026/experiments/02 --frozen。' >&2; exit 1; }
  [[ -x "$C5_TRANSFER_PY" ]] || { echo '先执行 uv sync --project 2026/experiments/03 --frozen。' >&2; exit 1; }
  down
  for ns in r1 r2 r3 r4 r5 r6 h1a h1b h2a h2b h3a h3b h4a h4b; do
    if [[ -e "/run/netns/$ns" ]]; then
      echo "$ns 已被其他实验使用。请先完成并清理 Lab 1/2。" >&2; exit 1
    fi
  done
  mkdir -p "$C5_STATE" "$C5_RESULTS"
  : >"$C5_STATE/namespaces"
  trap up_failed ERR
  for ns in r1 r2 r3 r4 r5 r6; do new_ns "$ns"; done
  for rack in 1 2 3 4; do
    ip -n "r$rack" link add "br$rack" type bridge
    ip -n "r$rack" addr add "10.0.$rack.1/24" dev "br$rack"
    ip -n "r$rack" link set "br$rack" up
    for host in a b; do
      ns="h$rack$host"; iface="r$rack-$ns"; octet=11
      [[ "$host" == b ]] && octet=12
      new_ns "$ns"
      ip -n "r$rack" link add "$iface" type veth peer name eth0 netns "$ns"
      ip -n "r$rack" link set "$iface" master "br$rack"
      ip -n "r$rack" link set "$iface" up
      ip -n "$ns" addr add "10.0.$rack.$octet/24" dev eth0
      ip -n "$ns" link set eth0 up
      ip -n "$ns" route add default via "10.0.$rack.1"
      limit_port "$ns" eth0 100
      limit_port "r$rack" "$iface" 100
    done
    for spine in 5 6; do
      k=$((2 * (rack - 1) + spine - 5))
      ip -n "r$rack" link add "r$rack-r$spine" type veth peer name "r$spine-r$rack" netns "r$spine"
      ip -n "r$rack" addr add "10.1.$k.1/30" dev "r$rack-r$spine"
      ip -n "r$spine" addr add "10.1.$k.2/30" dev "r$spine-r$rack"
      ip -n "r$rack" link set "r$rack-r$spine" up
      ip -n "r$spine" link set "r$spine-r$rack" up
    done
  done
  for rid in 1 2 3 4 5 6; do
    ip netns exec "r$rid" sysctl -qw net.ipv4.ip_forward=1 \
      net.ipv4.conf.all.rp_filter=2 net.ipv4.conf.default.rp_filter=2 \
      net.ipv4.fib_multipath_hash_policy=1
    local opts=(--id "$rid" --ecmp \
      --pidfile "$C5_STATE/r$rid.pid" --sock "$C5_STATE/r$rid.sock" --log "$C5_RESULTS/r$rid.log")
    [[ "$rid" -le 4 ]] && opts+=(--passive "br$rid")
    (cd "$directory" && \
      exec setsid ip netns exec "r$rid" "$C5_PY" -m lsrd "${opts[@]}") </dev/null >/dev/null 2>&1 &
  done
  # 抓包与限速使用普通分段，减小虚拟网卡 offload 对字节口径的影响。
  while read -r ns; do
    for iface in $(ip -n "$ns" -o link show type veth | awk -F': ' '{print $2}' | cut -d@ -f1); do
      ip netns exec "$ns" ethtool -K "$iface" gro off gso off tso off tx off rx off >/dev/null 2>&1 || true
    done
  done <"$C5_STATE/namespaces"
  set_rate 100
  for _ in $(seq 1 40); do
    if ready >/dev/null 2>&1; then
      trap - ERR
      echo "[就绪] 6 台路由器、8 台主机；路由实现：$implementation；全部邻接 Full。"
      check
      return
    fi
    sleep 0.3
  done
  echo "路由未就绪，查看 $C5_RESULTS/r*.log。学生骨架需先完成 Lab 2；教师可显式使用 up --reference。" >&2
  return 1
}

check() {
  local rack spine k host
  ready
  for rack in 1 2 3 4; do
    for spine in 5 6; do
      k=$((2 * (rack - 1) + spine - 5))
      ip netns exec "r$rack" ping -c 1 -W 2 "10.1.$k.2" >/dev/null
      ip netns exec "r$spine" ping -c 1 -W 2 "10.1.$k.1" >/dev/null
    done
    for host in a b; do
      ip netns exec "h$rack$host" ping -c 1 -W 2 "10.0.$rack.1" >/dev/null
      ip netns exec "h$rack$host" ping -c 1 -W 2 10.0.3.11 >/dev/null
      ip netns exec h3a ping -c 1 -W 2 "10.0.$rack.$([[ "$host" == a ]] && echo 11 || echo 12)" >/dev/null
    done
  done
  echo '[OK] 每条上联往返、8 台 host 的网桥接入与跨机架往返。'
  ip -n r1 route show 10.0.3.0/24
}

locality() {
  local target file
  for target in 10.0.1.12 10.0.3.11; do
    file="$C5_RESULTS/locality-$target.txt"
    ip netns exec r1 timeout 2 tcpdump -n -l -i any -Q out "icmp and dst host $target" >"$file" 2>/dev/null &
    C5_BG+=("$!"); sleep 0.3
    ip netns exec h1a ping -c 1 -W 2 "$target" >/dev/null
    wait "${C5_BG[-1]}" || [[ "$?" -eq 124 ]]
    C5_BG=()
    echo "[抓包] h1a → $target："; cat "$file"
  done
  echo '[观察] 同机架从 r1-h1b 发出；跨机架从 r1-r5 或 r1-r6 发出。'
  ip netns exec h1a traceroute -n -I -q 1 -w 1 10.0.3.11
}

capture_syn() {
  local spine
  for spine in 5 6; do
    ip netns exec r1 tcpdump -n -l -i "r1-r$spine" -Q out \
      'tcp and tcp[13] & 0x12 == 0x02' >"$C5_RESULTS/syn-r$spine.txt" 2>/dev/null &
    C5_BG+=("$!")
  done
  sleep 0.3
}

report() {
  python3 - "$C5_RESULTS" "$@" <<'PY'
import json, pathlib, re, sys
root = pathlib.Path(sys.argv[1])
for filename in sys.argv[2:]:
    r = json.loads((root / filename).read_text())
    assert "error" not in r, r
    totals = {"r5": {"flows": 0, "bytes": 0}, "r6": {"flows": 0, "bytes": 0}}
    if "start" in r:
        streams = r["start"]["connected"]
        receivers = {s["receiver"]["socket"]: s["receiver"]["bytes"] for s in r["end"]["streams"]}
        received = r["end"]["sum_received"]
        volume, seconds, bps = received["bytes"], received["seconds"], received["bits_per_second"]
    else:
        streams = [{"local_host": r["source"], "local_port": r["source_port"],
                    "remote_host": r["destination"], "remote_port": r["destination_port"], "socket": 0}]
        volume, seconds, bps = r["received_bytes"], r["completion_seconds"], r["application_mbps"]*1e6
        receivers = {0: volume}
    for stream in streams:
        address, port = stream["local_host"], stream["local_port"]
        pattern = rf"\b{re.escape(address)}\.{port} >"
        paths = [f"r{s}" for s in (5, 6) if re.search(pattern, (root / f"syn-r{s}.txt").read_text())]
        assert len(paths) == 1, (address, port, paths)
        totals[paths[0]]["flows"] += 1
        totals[paths[0]]["bytes"] += receivers[stream["socket"]]
        print(f"[真实数据连接] {address}:{port} → {stream['remote_host']}:{stream['remote_port']} 经 {paths[0]}")
    for path, total in totals.items():
        print(f"[按 SYN 的路径分组] {path}：{total['flows']} 条数据连接，接收应用数据 {total['bytes']/1e6:.2f} MB")
    print(f"[接收应用数据] {volume/1e6:.2f} MB，{seconds:.3f} s，{bps/1e6:.2f} Mbit/s")
PY
}

ecmp() {
  local streams server
  set_rate 50
  for streams in 1 8; do
    echo "[运行] 同一主机对，$streams 条数据连接；host 100、每条上联 50 Mbit/s。"
    capture_syn
    ip netns exec h3a iperf3 -s -1 >"$C5_RESULTS/server.txt" 2>&1 &
    server=$!; C5_BG+=("$server"); sleep 0.3
    ip netns exec h1a iperf3 -c 10.0.3.11 -P "$streams" -t 5 -J >"$C5_RESULTS/ecmp-$streams.json"
    wait "$server"
    # 服务端已结束，避免清理时命中复用的 PID。
    unset 'C5_BG[-1]'
    stop_jobs
    report "ecmp-$streams.json"
  done
  echo '[解释] 控制连接不计入数据连接；8 条连接不保证 4:4。单流受一条上联限制，多流仍受 host 接入口限制。'
}

pin_paths() {
  # 对比实验固定两发送端的路径，排除 ECMP 碰撞；结束后移除策略。
  C5_PINNED=1
  ip -n r1 route add table 105 default via 10.1.0.2 dev r1-r5 onlink
  ip -n r1 route add table 106 default via 10.1.1.2 dev r1-r6 onlink
  ip -n r1 rule add priority 105 from 10.0.1.11/32 lookup 105
  ip -n r1 rule add priority 106 from 10.0.1.12/32 lookup 106
}

choose_port() {
  local src=$1 port host=h1a start=40001
  [[ "$src" == 10.0.1.12 ]] && host=h1b
  [[ ! -f "$C5_STATE/next_port" ]] || start=$(cat "$C5_STATE/next_port")
  # 使用尚未占用的端口，避免连续观察时复用 TIME_WAIT 中的连接。
  for port in $(seq "$start" "$((start + 255))"); do
    if ip netns exec "$host" python3 - "$src" "$port" <<'PY'
import socket, sys
with socket.socket() as sock:
    try:
        sock.bind((sys.argv[1], int(sys.argv[2])))
    except OSError:
        sys.exit(1)
PY
    then
      echo "$((port + 1))" >"$C5_STATE/next_port"
      echo "$port"; return
    fi
  done
  echo '未找到可用源端口。' >&2; return 1
}

run_pairs() {
  local label=$1 second=$2 first_port second_port server1 server2 client1 client2 start end
  pin_paths
  capture_syn
  first_port=$(choose_port 10.0.1.11)
  second_port=$(choose_port 10.0.1.12)
  local second_ns=h4a
  [[ "$second" == 10.0.3.11 ]] && second_ns=h3a
  echo "[运行] $label：h1a → h3a 30 MB；h1b → $second_ns 30 MB；临时策略路由固定到不同上联。"
  ip netns exec h3a "$C5_TRANSFER_PY" "$C5_TRANSFER" server --port 5201 >"$C5_RESULTS/server1.txt" 2>&1 &
  server1=$!; C5_BG+=("$server1")
  ip netns exec "$second_ns" "$C5_TRANSFER_PY" "$C5_TRANSFER" server --port 5202 >"$C5_RESULTS/server2.txt" 2>&1 &
  server2=$!; C5_BG+=("$server2"); sleep 0.3
  start=$("$C5_TRANSFER_PY" -c 'import time; print(time.monotonic())')
  ip netns exec h1a "$C5_TRANSFER_PY" "$C5_TRANSFER" client --destination 10.0.3.11 --port 5201 \
    --source 10.0.1.11 --source-port "$first_port" >"$C5_RESULTS/$label-1.json" &
  client1=$!; C5_BG+=("$client1")
  ip netns exec h1b "$C5_TRANSFER_PY" "$C5_TRANSFER" client --destination "$second" --port 5202 \
    --source 10.0.1.12 --source-port "$second_port" >"$C5_RESULTS/$label-2.json" &
  client2=$!; C5_BG+=("$client2")
  wait "$client1"
  wait "$client2"
  end=$("$C5_TRANSFER_PY" -c 'import time; print(time.monotonic())')
  wait "$server1"
  wait "$server2"
  C5_BG=("${C5_BG[0]}" "${C5_BG[1]}")
  stop_jobs
  clear_pins
  report "$label-1.json" "$label-2.json"
  python3 - "$C5_RESULTS" "$label" "$start" "$end" <<'PY'
import json, pathlib, sys
root, label = pathlib.Path(sys.argv[1]), sys.argv[2]
volume = sum(json.loads((root / f"{label}-{i}.json").read_text())["received_bytes"] for i in (1, 2))
assert volume == 60000000, volume
elapsed = float(sys.argv[4]) - float(sys.argv[3])
result = {"label": label, "bytes": volume, "wall_seconds": elapsed, "shared_window_mbps": 8*volume/elapsed/1e6}
(root / f"{label}-summary.json").write_text(json.dumps(result, indent=2))
print(f"[共同窗口] 两流全部完成 {elapsed:.3f} s；合计 {volume/1e6:.2f} MB；平均应用有效速率 {result['shared_window_mbps']:.2f} Mbit/s（含建连与启动）")
PY
}

matrix() {
  set_rate 100
  run_pairs spread 10.0.4.11
  run_pairs hotspot 10.0.3.11
  echo '[解释] 总量与每个发送端的行和相同，接收端列和不同；热点受到同一个 100 Mbit/s 接入口限制。'
}

capacity() {
  set_rate 100; run_pairs capacity-100 10.0.4.11
  set_rate 50; run_pairs capacity-50 10.0.4.11
  echo '[解释] 下联总容量 200 Mbit/s；上联从 200 降为 100，收敛比从 1:1 变为 2:1；实际数据连接已抓包核对分路。'
}

overlay_up() {
  local rack tenant vni ns bridge remote
  [[ -f "$C5_STATE/overlay" ]] && return
  for ns in t1a t3a t1b t3b; do
    [[ ! -e "/run/netns/$ns" ]] || { echo "$ns 已被其他实验使用。" >&2; exit 1; }
  done
  for rack in 1 3; do
    remote=3; [[ "$rack" == 3 ]] && remote=1
    for tenant in a b; do
      vni=100; [[ "$tenant" == b ]] && vni=200
      ns="t$rack$tenant"; bridge="br$vni"
      new_ns "$ns"
      ip -n "r$rack" link add "$bridge" type bridge
      ip -n "r$rack" link add "r$rack-$tenant" type veth peer name eth0 netns "$ns"
      ip -n "r$rack" link add "vx$vni" type vxlan id "$vni" \
        local "10.0.$rack.1" remote "10.0.$remote.1" dstport 4789
      for port in "r$rack-$tenant" "vx$vni"; do
        ip -n "r$rack" link set "$port" mtu 1450 master "$bridge" up
      done
      ip -n "r$rack" link set "$bridge" mtu 1450 up
      ip -n "$ns" link set eth0 mtu 1450 up
      ip -n "$ns" addr add "192.168.10.$([[ "$rack" == 1 ]] && echo 11 || echo 12)/24" dev eth0
    done
  done
  touch "$C5_STATE/overlay"
  # 新建 bridge 没有 IP，租户前缀不会被 lsrd 混入 underlay。
}

vxlan() {
  overlay_up
  ip netns exec t1a ping -c 1 -W 2 192.168.10.12 >/dev/null
  ip netns exec t3a ping -c 1 -W 2 192.168.10.11 >/dev/null
  ip netns exec t1b ping -c 1 -W 2 192.168.10.12 >/dev/null
  ip netns exec t3b ping -c 1 -W 2 192.168.10.11 >/dev/null
  ip netns exec t1a timeout 3 tcpdump -n -l -vv -i eth0 -c 1 icmp >"$C5_RESULTS/inner.txt" 2>/dev/null &
  C5_BG+=("$!")
  # UDP 内偏移：VNI 12–14，内层 EtherType 28–29，IPv4 协议 39，ICMP 类型 50。
  # 限定 VNI 100 的 IPv4 echo request，避免抓到后台 ARP / IPv6 控制报文。
  ip netns exec r1 timeout 3 tcpdump -n -l -vv -i any -Q out -c 1 \
    'udp dst port 4789 and udp[12:4] = 0x00006400 and udp[28:2] = 0x0800 and udp[39] = 1 and udp[50] = 8' \
    >"$C5_RESULTS/outer.txt" 2>/dev/null &
  C5_BG+=("$!"); sleep 0.3
  ip netns exec t1a ping -c 1 -W 2 -s 32 192.168.10.12 >/dev/null
  for pid in "${C5_BG[@]}"; do wait "$pid"; done
  C5_BG=()
  echo '[租户侧]'; cat "$C5_RESULTS/inner.txt"
  echo '[underlay]'; cat "$C5_RESULTS/outer.txt"
  grep -q 'vni 100' "$C5_RESULTS/outer.txt"
  grep -q '192.168.10.11 > 192.168.10.12: ICMP echo request' "$C5_RESULTS/outer.txt"
  # B 的相同 IP 仍在线，不能代替已关闭的 A 接收端响应 A 的请求。
  C5_RESTORE_A=1
  ip -n t3a link set eth0 down
  if ip netns exec t1a ping -c 1 -W 1 192.168.10.12 >/dev/null; then
    ip -n t3a link set eth0 up
    echo '跨 VNI 隔离检查失败。' >&2; exit 1
  fi
  ip netns exec t1b ping -c 1 -W 2 192.168.10.12 >/dev/null
  ip -n t3a link set eth0 up
  C5_RESTORE_A=0
  echo '[OK] 两租户使用相同 IP；同 VNI 往返可达。关闭 A 接收端后，B 仍可达且不会替 A 响应。'
}

mtu() {
  overlay_up
  ip netns exec t1a ping -M 'do' -c 1 -W 2 -s 1422 192.168.10.12
  if ip netns exec t1a ping -M 'do' -c 1 -W 1 -s 1423 192.168.10.12; then
    echo 'MTU 边界检查失败。' >&2; exit 1
  fi
  echo '[观察] 1422+8+20=1450 可发送；再加 1 B 被源租户接口的 MTU 拒绝，这不是远端丢包。'
}

[[ "$EUID" -eq 0 ]] || { echo '请从仓库根目录用 sudo bash 2026/experiments/03/classroom.sh 执行。' >&2; exit 1; }
case "${1:-up}" in
  up) up "${2:-}" ;;
  down) down ;;
  check|locality|ecmp|matrix|capacity|vxlan|mtu)
    [[ -f "$C5_STATE/namespaces" ]] || { echo '请先执行 classroom.sh up。' >&2; exit 1; }
    "$1"
    ;;
  rate)
    [[ -f "$C5_STATE/namespaces" ]] || { echo '请先执行 classroom.sh up。' >&2; exit 1; }
    set_rate "${2:-100}"
    ;;
  *) echo '用法：classroom.sh [up [--reference]|check|locality|ecmp|matrix|capacity|vxlan|mtu|rate 50|rate 100|down]' >&2; exit 2 ;;
esac
