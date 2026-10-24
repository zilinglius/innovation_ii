#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# Lab 4–9 共用实验床：2 spine × 4 leaf × 8 host 的 leaf-spine 迷你数据中心（完整版）
#
#         ┌─ h1a（10.0.1.11）      每个 leaf 的机架网桥上接两台 host
#   机架 1│
#         └─ br1 ─ r1（leaf）─┬── 10.1.0.0/30 ── r5（spine）
#                              └── 10.1.1.0/30 ── r6（spine）
#   机架 2、3、4 与机架 1 同构：r2、r3、r4 各有两条上联，全网共 8 条 leaf–spine 链路。
#
# 地址规划（与 Lab 3 指导书 3.2 节、课堂脚本 classroom.sh 完全一致）：
#   机架 i       10.0.i.0/24   网关 br{i} = .1   host h{i}a = .11、h{i}b = .12
#   leaf–spine   第 k 条链路 10.1.k.0/30，leaf = .1、spine = .2，k = 2*(leaf-1)+(spine-5)
#   路由         lsrd --ecmp 写内核（proto 200），每条跨机架路由应有两个下一跳
#   限速基线     每个端口 egress 一个 HTB 类 1:10 加 fq 叶子（handle 10:）；
#                host 接入口两端 100 Mbit/s，leaf–spine 两端为当前档位（100 或 50）
#
# 本脚本是 Lab 3 学生骨架的完整版，另加测量实验用的条件注入与基线核对；
# 资源登记在 /run/lab04，与 Lab 3（/run/lab03）、课堂脚本（/run/course05）互不混用。
#
# 用法（均从仓库根目录执行）：
#   sudo bash 2026/experiments/04/topo.sh up [--own]        # 搭建；默认用 Lab 2 参考路由，--own 用自己的 lsrd
#   sudo bash 2026/experiments/04/topo.sh check             # 数据平面自检与 12 条 ECMP 路由核对
#   sudo bash 2026/experiments/04/topo.sh show              # 路由器地址与路由
#   sudo bash 2026/experiments/04/topo.sh rate 50|100       # 切换全部 leaf–spine 档位（会重建这些端口）
#   sudo bash 2026/experiments/04/topo.sh limit NS DEV MBIT # 只改一个端口的限速
#   sudo bash 2026/experiments/04/topo.sh impair NS DEV ... # 把一个端口的叶子换成 netem，参数照写，如 delay 4ms
#   sudo bash 2026/experiments/04/topo.sh clear [NS DEV]    # 恢复一个端口；不带参数时恢复全部端口并取消钉路
#   sudo bash 2026/experiments/04/topo.sh status            # 列出偏离基线的端口与策略路由
#   sudo bash 2026/experiments/04/topo.sh scenario NAME     # 加载命名场景（先恢复基线）；NAME 见 scenario_list
#   sudo bash 2026/experiments/04/topo.sh blind [--seed N]  # 随机注入 1–2 项隐藏条件；blind reveal 看答案
#   sudo bash 2026/experiments/04/topo.sh pin [HOST r5|r6]  # 按源地址钉路；不带参数时 a 经 r5、b 经 r6
#   sudo bash 2026/experiments/04/topo.sh unpin             # 取消全部钉路
#   sudo bash 2026/experiments/04/topo.sh down              # 拆除（幂等）
# ==============================================================================

L4_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
L4_STATE=/run/lab04
L4_RESULTS=/tmp/lab04-results
L4_PY="$L4_ROOT/2026/experiments/02/.venv/bin/python"
L4_ROUTERS=(r1 r2 r3 r4 r5 r6)
L4_HOSTS=(h1a h1b h2a h2b h3a h3b h4a h4b)

die() {
  echo "topo.sh：$*" >&2
  exit 1
}

require_up() {
  [[ -f "$L4_STATE/namespaces" ]] || die '实验床尚未搭建，请先执行 topo.sh up。'
}

down() {
  local ns pid
  [[ -f "$L4_STATE/namespaces" ]] || return 0
  while read -r ns; do
    for pid in $(ip netns pids "$ns" 2>/dev/null || true); do
      kill "$pid" 2>/dev/null || true
    done
  done <"$L4_STATE/namespaces"
  sleep 0.3
  while read -r ns; do
    for pid in $(ip netns pids "$ns" 2>/dev/null || true); do
      kill -KILL "$pid" 2>/dev/null || true
    done
    ip netns del "$ns" 2>/dev/null || true
  done <"$L4_STATE/namespaces"
  rm -rf -- "$L4_STATE"
  echo "[*] 实验床已拆除；路由日志保留在 $L4_RESULTS。"
}

up_failed() {
  local status=$?
  down
  exit "$status"
}

# 把 namespace 登记进清理清单并置 up 环回口；所有 namespace 都经它创建，down 才能清理到。
new_ns() {
  ip netns add "$1"
  printf '%s\n' "$1" >>"$L4_STATE/namespaces"
  ip -n "$1" link set lo up
}

# 端口基线：egress 根 HTB，一个类 1:10，rate = ceil，叶子 fq。
# 每个速率第一次建类时记下内核给的默认 burst，供 status 判断是否被改过。
limit_port() {
  ip netns exec "$1" tc qdisc del dev "$2" root 2>/dev/null || true
  ip netns exec "$1" tc qdisc add dev "$2" root handle 1: htb default 10 r2q 100
  ip netns exec "$1" tc class add dev "$2" parent 1: classid 1:10 htb rate "${3}mbit"
  ip netns exec "$1" tc qdisc add dev "$2" parent 1:10 handle 10: fq
  if [[ ! -f "$L4_STATE/burst-$3" ]]; then
    ip netns exec "$1" tc -j class show dev "$2" |
      python3 -c 'import json, sys; print(json.load(sys.stdin)[0]["burst"])' >"$L4_STATE/burst-$3"
  fi
}

fabric_rate() {
  cat "$L4_STATE/rate" 2>/dev/null || echo 100
}

set_rate() {
  local rate=$1 rack spine
  [[ "$rate" == 50 || "$rate" == 100 ]] || die 'leaf–spine 档位可选 50 或 100 Mbit/s。'
  for rack in 1 2 3 4; do
    for spine in 5 6; do
      limit_port "r$rack" "r$rack-r$spine" "$rate"
      limit_port "r$spine" "r$spine-r$rack" "$rate"
    done
  done
  echo "$rate" >"$L4_STATE/rate"
  echo "[*] 全部 leaf–spine 链路两端 egress = $rate Mbit/s；host 接入口保持 100 Mbit/s。"
}

# 输出全部限速端口：namespace、接口、基线速率（Mbit/s）。
all_ports() {
  local rack host spine tier
  tier=$(fabric_rate)
  for rack in 1 2 3 4; do
    for host in a b; do
      echo "h$rack$host eth0 100"
      echo "r$rack r$rack-h$rack$host 100"
    done
    for spine in 5 6; do
      echo "r$rack r$rack-r$spine $tier"
      echo "r$spine r$spine-r$rack $tier"
    done
  done
}

# 校验端口属于本实验床，输出它的基线速率。
port_base() {
  local ns=$1 dev=$2 line
  while read -r line; do
    if [[ "$line" == "$ns $dev "* ]]; then
      echo "${line##* }"
      return
    fi
  done < <(all_ports)
  die "$ns 的 $dev 不是本实验床的限速端口（host 用 eth0；leaf 用 rN-hNx、rN-r5/r6；spine 用 r5-rN、r6-rN）。"
}

limit() {
  local ns=$1 dev=$2 mbit=$3
  port_base "$ns" "$dev" >/dev/null
  [[ "$mbit" =~ ^[0-9]+$ && "$mbit" -ge 1 && "$mbit" -le 1000 ]] || die '速率取 1–1000 的整数（Mbit/s）。'
  ip netns exec "$ns" tc class change dev "$dev" parent 1: classid 1:10 htb rate "${mbit}mbit" ceil "${mbit}mbit"
}

# 把 HTB 类下的叶子换成 netem，保留限速。Linux 7.0 拒绝用 replace 把同一 handle 换成另一种 qdisc，
# 所以先删后加。
impair() {
  local ns=$1 dev=$2
  shift 2
  port_base "$ns" "$dev" >/dev/null
  [[ "$#" -gt 0 ]] || die 'impair 需要 netem 参数，例如 delay 4ms、delay 5ms 1ms、loss 1%。'
  ip netns exec "$ns" tc qdisc del dev "$dev" parent 1:10 2>/dev/null || true
  ip netns exec "$ns" tc qdisc add dev "$dev" parent 1:10 handle 10: netem "$@"
}

clear_port() {
  local rate
  rate=$(port_base "$1" "$2")
  limit_port "$1" "$2" "$rate"
}

clear_all() {
  local ns dev rate
  while read -r ns dev rate; do
    limit_port "$ns" "$dev" "$rate"
  done < <(all_ports)
  unpin
  rm -f -- "$L4_STATE/scenario" "$L4_STATE/blind"
}

ready() {
  python3 - "$L4_STATE" <<'PY'
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
  local directory="$L4_ROOT/2026/experiments/02/reference" rid opts
  [[ "${1:-}" == --own ]] && directory="$L4_ROOT/2026/experiments/02"
  for rid in 1 2 3 4 5 6; do
    opts=(--id "$rid" --ecmp \
      --pidfile "$L4_STATE/r$rid.pid" --sock "$L4_STATE/r$rid.sock" --log "$L4_RESULTS/r$rid.log")
    [[ "$rid" -le 4 ]] && opts+=(--passive "br$rid")
    (cd "$directory" && \
      exec setsid ip netns exec "r$rid" "$L4_PY" -m lsrd "${opts[@]}") </dev/null >/dev/null 2>&1 &
  done
}

sysctl_routers() {
  local ns
  for ns in "${L4_ROUTERS[@]}"; do
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
  done <"$L4_STATE/namespaces"
}

# 机架接入网：r{rack} 内的网桥 br{rack} 作网关，两台 host 经 veth 接入，两端各限速 100 Mbit/s。
build_access() {
  local rack host ns iface octet
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
  done
}

# leaf–spine 上联：8 条 /30 点到点链路；限速由 up() 结尾的 set_rate 统一配置。
build_fabric() {
  local rack spine k
  for rack in 1 2 3 4; do
    for spine in 5 6; do
      k=$((2 * (rack - 1) + spine - 5))
      ip -n "r$rack" link add "r$rack-r$spine" type veth peer name "r$spine-r$rack" netns "r$spine"
      ip -n "r$rack" addr add "10.1.$k.1/30" dev "r$rack-r$spine"
      ip -n "r$spine" addr add "10.1.$k.2/30" dev "r$spine-r$rack"
      ip -n "r$rack" link set "r$rack-r$spine" up
      ip -n "r$spine" link set "r$spine-r$rack" up
    done
  done
}

up() {
  local ns implementation='Lab 2 参考实现（02/reference）'
  [[ "${1:-}" == "" || "${1:-}" == --own ]] || die "未知参数 $1；用法 topo.sh up [--own]。"
  [[ "${1:-}" == --own ]] && implementation='自己的 lsrd（02/lsrd）'
  [[ -x "$L4_PY" ]] || die '先执行 uv sync --project 2026/experiments/02 --frozen。'
  down
  for ns in "${L4_ROUTERS[@]}" "${L4_HOSTS[@]}"; do
    if [[ -e "/run/netns/$ns" ]]; then
      die "$ns 已存在：先执行 classroom.sh down 或 Lab 3 的 topo.sh down，或按 Lab 1/2 指导书清理。"
    fi
  done
  mkdir -p "$L4_STATE" "$L4_RESULTS"
  : >"$L4_STATE/namespaces"
  trap up_failed ERR
  for ns in "${L4_ROUTERS[@]}"; do new_ns "$ns"; done
  build_access
  build_fabric
  sysctl_routers
  start_lsrd "$@"
  disable_offload
  set_rate 100
  for _ in $(seq 1 40); do
    if ready >/dev/null 2>&1; then
      trap - ERR
      echo "[*] 路由：$implementation。6 台路由器全部 Full；r1 的跨机架路由有两个下一跳。"
      echo '[*] 下一步自检：sudo bash 2026/experiments/04/topo.sh check'
      return
    fi
    sleep 0.3
  done
  trap - ERR
  echo "路由未就绪：查看 $L4_RESULTS/r*.log；拓扑已保留，可 down 后重试。" >&2
  [[ "${1:-}" == --own ]] && echo '自己的 lsrd 需完成 Lab 2 任务 8（ECMP）；也可去掉 --own 改用参考实现。' >&2
  return 1
}

reach() {
  # 不通时说出是哪一对，再继续检查其余各对。
  ip netns exec "$1" ping -c 1 -W 2 "$2" >/dev/null && return 0
  echo "[失败] $1 → $2 无回应" >&2
  return 1
}

check() {
  local rack spine k host other prefix count failed=0
  ready || die "ready 断言未通过：先看 $L4_RESULTS/r*.log 与 topo.sh show。"
  for rack in 1 2 3 4; do
    for spine in 5 6; do
      k=$((2 * (rack - 1) + spine - 5))
      reach "r$rack" "10.1.$k.2" || failed=1
      reach "r$spine" "10.1.$k.1" || failed=1
    done
    for host in a b; do
      reach "h$rack$host" "10.0.$rack.1" || failed=1
    done
  done
  reach h1a 10.0.3.11 || failed=1
  reach h3a 10.0.1.11 || failed=1
  reach h4b 10.0.2.12 || failed=1
  [[ "$failed" -eq 0 ]] || die "以上往返不通：对照路径上各路由器的 ip route show proto 200 与 $L4_RESULTS/r*.log。"
  echo '[OK] 8 条上联往返、8 台 host 网关可达、跨机架往返。'
  for rack in 1 2 3 4; do
    for other in 1 2 3 4; do
      [[ "$other" -ne "$rack" ]] || continue
      prefix="10.0.$other.0/24"
      count=$(ip -n "r$rack" route show "$prefix" | grep -c 'nexthop via' || true)
      [[ "$count" -eq 2 ]] || die "r$rack 去往 $prefix 的下一跳数为 $count，应为 2。"
    done
  done
  echo '[OK] 4 个 leaf 去往其他 3 个机架的 12 条路由均有两个下一跳。'
  ip -n r1 route show 10.0.3.0/24
}

show() {
  local ns
  for ns in "${L4_ROUTERS[@]}"; do
    echo "== $ns =="
    ip -n "$ns" -br addr show | grep -v '^lo' || true
    ip -n "$ns" route show
  done
}

# 与基线比较：叶子是否为 fq、rate/ceil 是否等于基线、burst/cburst 是否为默认值；另列 leaf 的策略路由。
status() {
  local scenario
  scenario=$(cat "$L4_STATE/scenario" 2>/dev/null || echo '无')
  echo "[档位] leaf–spine $(fabric_rate) Mbit/s；host 接入 100 Mbit/s。场景：$scenario。"
  python3 - "$scenario" "$L4_STATE" "$(all_ports)" <<'PY'
import json, pathlib, subprocess, sys

def tc(ns, *args):
    out = subprocess.run(["ip", "netns", "exec", ns, "tc", "-j", *args],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out or "[]")

hidden = sys.argv[1] == "blind"
state = pathlib.Path(sys.argv[2])
issues = []
for line in sys.argv[3].splitlines():
    ns, dev, rate = line.split()
    qdiscs = tc(ns, "qdisc", "show", "dev", dev)
    classes = [c for c in tc(ns, "class", "show", "dev", dev) if c.get("handle") == "1:10"]
    kinds = sorted((q["kind"], q["handle"]) for q in qdiscs)
    problems = []
    if kinds != [("fq", "10:"), ("htb", "1:")]:
        leaf = next((q for q in qdiscs if q.get("parent") == "1:10"), None)
        text = subprocess.run(["ip", "netns", "exec", ns, "tc", "qdisc", "show", "dev", dev, "parent", "1:10"],
                              capture_output=True, text=True).stdout.strip()
        problems.append(f"叶子 qdisc 为 {leaf['kind'] if leaf else '缺失'}（{text or '无'}）")
    if len(classes) != 1:
        problems.append("缺少 HTB 类 1:10")
    else:
        c = classes[0]
        expected = int(rate) * 125000
        if c["rate"] != expected or c["ceil"] != expected:
            problems.append(f"rate {c['rate'] * 8 / 1e6:g} / ceil {c['ceil'] * 8 / 1e6:g} Mbit/s（基线 {rate}）")
        record = state / f"burst-{rate}"
        if record.exists():
            default_burst = int(record.read_text())
            if c["burst"] != default_burst or c["cburst"] != default_burst:
                problems.append(f"burst {c['burst']} B / cburst {c['cburst']} B（基线 {default_burst} B）")
    if problems:
        issues.append(f"[偏离] {ns} {dev}：" + "；".join(problems))

if hidden and issues:
    print(f"[盲测] 有 {len(issues)} 个端口偏离基线，细节隐藏；定位完再执行 blind reveal。")
elif issues:
    print("\n".join(issues))
else:
    print("[基线] 32 个限速端口均为 HTB + fq，速率与 burst 为基线值。")
PY
  local rack rules=0 line
  for rack in 1 2 3 4; do
    while read -r line; do
      [[ -n "$line" ]] || continue
      echo "[钉路] r$rack：$line"
      rules=$((rules + 1))
    done < <(ip -n "r$rack" rule show | grep -vE '^(0|32766|32767):' || true)
  done
  [[ "$rules" -gt 0 ]] || echo '[基线] r1–r4 没有额外策略路由（自然 ECMP）。'
}

host_ip() {
  local host=$1
  [[ "$host" =~ ^h([1-4])([ab])$ ]] || die "$host 不是本实验床的 host（h1a … h4b）。"
  if [[ "${BASH_REMATCH[2]}" == a ]]; then
    echo "10.0.${BASH_REMATCH[1]}.11"
  else
    echo "10.0.${BASH_REMATCH[1]}.12"
  fi
}

# 钉路：在源 host 所在 leaf 上，按源地址查表 105（经 r5）或 106（经 r6）。
# 规则优先级沿用 Lab 3：a 类 host 用 105，b 类用 106。只影响该 host 发出的报文。
pin_host() {
  local host=$1 spine=$2 rack prio table k
  local ip
  ip=$(host_ip "$host")
  [[ "$spine" == r5 || "$spine" == r6 ]] || die 'spine 取 r5 或 r6。'
  rack=${host:1:1}
  prio=105; [[ "${host:2:1}" == b ]] && prio=106
  table=105; [[ "$spine" == r6 ]] && table=106
  for k in 5 6; do
    ip -n "r$rack" route replace table "10$k" default \
      via "10.1.$((2 * (rack - 1) + k - 5)).2" dev "r$rack-r$k" onlink
  done
  ip -n "r$rack" rule del priority "$prio" from "$ip/32" 2>/dev/null || true
  ip -n "r$rack" rule add priority "$prio" from "$ip/32" lookup "$table"
  echo "[*] $host（$ip）发出的报文在 r$rack 固定经 $spine。"
}

pin() {
  local host
  if [[ "$#" -eq 0 ]]; then
    for host in "${L4_HOSTS[@]}"; do
      if [[ "${host:2:1}" == a ]]; then pin_host "$host" r5; else pin_host "$host" r6; fi
    done
  else
    [[ "$#" -eq 2 ]] || die '用法：topo.sh pin [HOST r5|r6]'
    pin_host "$1" "$2"
  fi
}

unpin() {
  local rack prio
  for rack in 1 2 3 4; do
    for prio in 105 106; do
      while ip -n "r$rack" rule del priority "$prio" 2>/dev/null; do :; done
      ip -n "r$rack" route flush table "$prio" 2>/dev/null || true
    done
  done
}

# 命名场景：公开的条件组合，加载前先恢复基线。
scenario_list() {
  cat <<'EOF'
  lecture06     第 06 讲综合动手：两项条件，课上先不看定义
  uplink-r1r5   Lab 4 任务 5：只把 r1–r5 一条上联两个方向降到 20 Mbit/s
EOF
}

scenario() {
  local name=${1:-}
  case "$name" in
    lecture06)
      clear_all
      # X：两台 spine 发往机架 4 的出口都降到 30 Mbit/s（避开 ECMP 只影响一半流的歧义）
      limit r5 r5-r4 30
      limit r6 r6-r4 30
      # Y：r2 发往 h2b 的接入出口加 4 ms 单向延迟
      impair r2 r2-h2b delay 4ms
      ;;
    uplink-r1r5)
      clear_all
      limit r1 r1-r5 20
      limit r5 r5-r1 20
      ;;
    clear)
      clear_all
      echo '[*] 已恢复基线：全部端口 HTB + fq、档位不变，钉路已取消。'
      return
      ;;
    *)
      echo '可用场景：' >&2
      scenario_list >&2
      echo '  clear         恢复基线' >&2
      exit 2
      ;;
  esac
  echo "$name" >"$L4_STATE/scenario"
  echo "[*] 场景 $name 已加载。结束后执行 topo.sh scenario clear，再用 topo.sh status 核对。"
}

# 盲测：从下列六类中随机选 1–2 类、随机落点。描述写入登记目录，reveal 时打印。
# 必须在当前 shell 中调用（不要放进 $(...)），否则 RANDOM 的状态不会前进，两项会落在同一位置。
blind_apply() {
  local kind=$1 rack host spine
  rack=$((RANDOM % 4 + 1)); spine=$((RANDOM % 2 + 5))
  if ((RANDOM % 2)); then host="h${rack}b"; else host="h${rack}a"; fi
  case "$kind" in
    1) limit r5 "r5-r$rack" 30; limit r6 "r6-r$rack" 30
       echo "  - 两台 spine 发往机架 $rack 的出口（r5-r$rack、r6-r$rack）限速 30 Mbit/s" ;;
    2) impair "r$rack" "r$rack-$host" delay 3ms
       echo "  - r$rack 发往 $host 的接入出口加 3 ms 单向延迟" ;;
    3) impair "r$rack" "r$rack-$host" loss 1%
       echo "  - r$rack 发往 $host 的接入出口随机丢包 1%" ;;
    4) limit "r$rack" "r$rack-r$spine" 20
       echo "  - r$rack 经 r$spine 的上行出口限速 20 Mbit/s（只影响哈希到 r$spine 的流）" ;;
    5) limit "$host" eth0 40
       echo "  - $host 自己的发送出口限速 40 Mbit/s" ;;
    6) local leaf
       for leaf in 1 2 3 4; do impair "r$spine" "r$spine-r$leaf" delay 2ms; done
       echo "  - r$spine 发往全部 4 个 leaf 的出口加 2 ms（只影响经过 r$spine 的流）" ;;
  esac
}

blind() {
  local seed count first second
  if [[ "${1:-}" == reveal ]]; then
    [[ -f "$L4_STATE/blind" ]] || die '当前没有盲测。'
    cat "$L4_STATE/blind"
    return
  fi
  if [[ "${1:-}" == --seed ]]; then
    [[ "${2:-}" =~ ^[0-9]+$ ]] || die '用法：topo.sh blind [--seed N]'
    seed=$2
  else
    seed=$(( $(date +%s%N) % 1000000 ))
  fi
  clear_all
  RANDOM=$seed
  count=$((RANDOM % 2 + 1))
  first=$((RANDOM % 6 + 1))
  second=$(( (first + RANDOM % 5) % 6 + 1 ))   # 与 first 不同的另一类
  echo "[盲测] seed $seed，共 $count 项：" >"$L4_STATE/blind.tmp"
  blind_apply "$first" >>"$L4_STATE/blind.tmp"
  if [[ "$count" -eq 2 ]]; then
    # 两项都是接入口 netem 时可能落在同一端口，后一项会覆盖前一项；遇到时换一类。
    if [[ "$first" =~ ^[23]$ && "$second" =~ ^[23]$ ]]; then second=4; fi
    blind_apply "$second" >>"$L4_STATE/blind.tmp"
  fi
  mv "$L4_STATE/blind.tmp" "$L4_STATE/blind"
  chmod 600 "$L4_STATE/blind"
  echo blind >"$L4_STATE/scenario"
  echo "[*] 已注入隐藏条件（seed $seed）。只用端到端测量定位；完成后 topo.sh blind reveal，再 scenario clear。"
}

[[ "$EUID" -eq 0 ]] || { echo '请从仓库根目录用 sudo bash 2026/experiments/04/topo.sh 执行。' >&2; exit 1; }
case "${1:-up}" in
  up) if [[ "$#" -gt 0 ]]; then shift; fi; up "$@" ;;
  down) down ;;
  check|show|status|unpin)
    require_up
    "$1"
    [[ "$1" != unpin ]] || echo '[*] 已取消全部钉路，回到自然 ECMP。'
    ;;
  rate)
    require_up
    # 切档会重建全部 leaf–spine 端口，场景在这些端口上的条件会被悄悄抹掉，所以先要求恢复基线。
    if [[ -f "$L4_STATE/scenario" ]]; then
      die "当前加载了场景 $(cat "$L4_STATE/scenario")；先 scenario clear 再切档，切档后可重新加载场景。"
    fi
    set_rate "${2:-100}"
    ;;
  limit)
    require_up
    [[ "$#" -eq 4 ]] || die '用法：topo.sh limit NS DEV MBIT'
    limit "$2" "$3" "$4"
    echo "[*] $2 $3 egress 限速 $4 Mbit/s；恢复用 topo.sh clear $2 $3。"
    ;;
  impair)
    require_up
    [[ "$#" -ge 4 ]] || die '用法：topo.sh impair NS DEV NETEM 参数…（如 delay 4ms）'
    shift
    impair "$@"
    echo "[*] $1 $2 叶子已换成 netem ${*:3}；恢复用 topo.sh clear $1 $2。"
    ;;
  clear)
    require_up
    if [[ "$#" -eq 1 ]]; then
      scenario clear
    else
      [[ "$#" -eq 3 ]] || die '用法：topo.sh clear [NS DEV]'
      clear_port "$2" "$3"
      echo "[*] $2 $3 已恢复基线（HTB $(port_base "$2" "$3") Mbit/s + fq）。"
    fi
    ;;
  scenario)
    require_up
    scenario "${2:-}"
    ;;
  blind)
    require_up
    shift
    blind "$@"
    ;;
  pin)
    require_up
    shift
    pin "$@"
    ;;
  *)
    echo '用法：topo.sh [up [--own]|check|show|rate 50|100|limit|impair|clear|status|scenario|blind|pin|unpin|down]' >&2
    exit 2
    ;;
esac
