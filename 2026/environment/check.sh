#!/usr/bin/env bash
set -Eeuo pipefail

# 三个临时 namespace：主机 A、交换机 S、主机 B。S 内的 bridge 连接两端 veth。
# 地址使用基准测试保留网段 198.18.0.0/24；所有资源在退出时清理。
CIC_NS_A=course-check-a
CIC_NS_B=course-check-b
CIC_NS_S=course-check-s
CIC_IP_A=198.18.0.11
CIC_IP_B=198.18.0.12
CIC_DIR=''
CIC_PIDS=()
CIC_CREATED=()
CIC_WARNINGS=0

warn() {
  CIC_WARNINGS=$((CIC_WARNINGS + 1))
  echo "[提示] $*"
}

cleanup() {
  local pid ns
  for pid in "${CIC_PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  for ns in "${CIC_CREATED[@]}"; do
    ip netns del "$ns" 2>/dev/null || true
  done
  [[ -z "$CIC_DIR" ]] || rm -rf -- "$CIC_DIR"
}

check_tools() {
  local tool
  for tool in ip tc bridge ping traceroute tcpdump iperf3 iptables nft \
      ss sysctl setsid timeout python3 uv shellcheck rsync sudo vtysh; do
    command -v "$tool" >/dev/null
  done
  test -x /usr/lib/frr/zebra
  test -x /usr/lib/frr/ospfd
  python3 -c 'import numpy, yaml; print("[OK] Python、numpy、pyyaml")'
  uv --version
  echo '[OK] 课程命令与 FRR 已安装'
}

case "${1:-full}" in
  tools) check_tools; exit 0 ;;
  down)
    CIC_CREATED=("$CIC_NS_A" "$CIC_NS_B" "$CIC_NS_S")
    cleanup
    exit 0
    ;;
  full) ;;
  *) echo '用法：course-check [tools|full|down]' >&2; exit 2 ;;
esac

[[ "$EUID" -eq 0 ]] || { echo '请执行 sudo course-check' >&2; exit 1; }
check_tools
for ns in "$CIC_NS_A" "$CIC_NS_B" "$CIC_NS_S"; do
  if ip netns list | awk '{print $1}' | grep -qx "$ns"; then
    echo "已有 $ns，请先执行 sudo course-check down" >&2
    exit 1
  fi
done
CIC_DIR=$(mktemp -d /tmp/course-check.XXXXXX)
trap cleanup EXIT
for ns in "$CIC_NS_A" "$CIC_NS_B" "$CIC_NS_S"; do
  ip netns add "$ns"
  CIC_CREATED+=("$ns")
  ip -n "$ns" link set lo up
done
echo '[OK] network namespace 与 ip netns exec'

# 1. veth 的两端直接创建在对应 namespace，避免残留在容器根 namespace。
ip -n "$CIC_NS_A" link add ca0 type veth peer name sa0 netns "$CIC_NS_S"
ip -n "$CIC_NS_B" link add cb0 type veth peer name sb0 netns "$CIC_NS_S"
ip -n "$CIC_NS_S" link add br0 type bridge
ip -n "$CIC_NS_S" link set br0 up
for dev in sa0 sb0; do
  ip -n "$CIC_NS_S" link set "$dev" master br0
  ip -n "$CIC_NS_S" link set "$dev" up
done
ip -n "$CIC_NS_A" addr add "$CIC_IP_A/24" dev ca0
ip -n "$CIC_NS_B" addr add "$CIC_IP_B/24" dev cb0
ip -n "$CIC_NS_A" link set ca0 up
ip -n "$CIC_NS_B" link set cb0 up
ip -n "$CIC_NS_S" addr add 198.18.0.1/24 dev br0
ip netns exec "$CIC_NS_A" ping -c 1 -W 2 "$CIC_IP_B" >/dev/null
ip netns exec "$CIC_NS_B" ping -c 1 -W 2 "$CIC_IP_A" >/dev/null
echo '[OK] veth、bridge、双向 ping'

# 2. 检查路由安装接口与五元组 ECMP 开关；这里只验证安装，不测量分流比例。
ip netns exec "$CIC_NS_S" sysctl -qw net.ipv4.ip_forward=1
ip netns exec "$CIC_NS_A" sysctl -qw net.ipv4.fib_multipath_hash_policy=1
ip -n "$CIC_NS_A" route add 198.18.99.0/24 proto 200 metric 20 \
  nexthop via 198.18.0.1 dev ca0 weight 1 \
  nexthop via "$CIC_IP_B" dev ca0 weight 1
ip -n "$CIC_NS_A" route show proto 200 | grep -q nexthop
echo '[OK] IP 转发、ECMP 路由安装与哈希开关'

# 3. 在真实虚拟链路上安装 netem 与 htb；fq 是后续 pacing 的可选能力检查。
ip netns exec "$CIC_NS_A" tc qdisc add dev ca0 root netem delay 10ms
ip netns exec "$CIC_NS_A" tc qdisc show dev ca0 | grep -q netem
ip netns exec "$CIC_NS_A" ping -c 1 -W 2 "$CIC_IP_B" >/dev/null
ip netns exec "$CIC_NS_A" tc qdisc replace dev ca0 root handle 1: htb r2q 100 default 10
ip netns exec "$CIC_NS_A" tc class add dev ca0 parent 1: classid 1:10 htb rate 100mbit
echo '[OK] tc netem 与 htb'
if ip netns exec "$CIC_NS_A" tc qdisc add dev ca0 parent 1:10 handle 10: fq 2>"$CIC_DIR/fq.err"; then
  echo '[OK] fq 队列调度器'
else
  warn 'VM 内核不支持 fq；后续 pacing 实验需另行准备内核。'
  cat "$CIC_DIR/fq.err" >&2
fi

# 4. 抓取一次真实 ICMP 往返，再让 iperf3 在两个 namespace 间传输。
ip netns exec "$CIC_NS_B" timeout 5 tcpdump -n -l -i cb0 -c 2 icmp \
  >"$CIC_DIR/capture.txt" 2>"$CIC_DIR/capture.err" &
CIC_PIDS+=("$!")
sleep 0.3
ip netns exec "$CIC_NS_A" ping -c 1 -W 2 "$CIC_IP_B" >/dev/null
wait "${CIC_PIDS[-1]}"
CIC_PIDS=()
grep -q 'ICMP echo request' "$CIC_DIR/capture.txt"
grep -q 'ICMP echo reply' "$CIC_DIR/capture.txt"
ip netns exec "$CIC_NS_B" iperf3 -s -1 >"$CIC_DIR/server.txt" 2>&1 &
CIC_PIDS+=("$!")
sleep 0.3
ip netns exec "$CIC_NS_A" iperf3 -c "$CIC_IP_B" -t 1 -J >"$CIC_DIR/iperf.json"
wait "${CIC_PIDS[-1]}"
CIC_PIDS=()
python3 - "$CIC_DIR/iperf.json" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    result = json.load(f)
assert result['end']['sum_received']['bytes'] > 0, result
print('[OK] tcpdump 抓包与 iperf3 真实 TCP 流量')
PY

# 5. 检查 VXLAN 设备与 namespace 内防火墙；完整 overlay 是 Lab 3 的任务。
if ip -n "$CIC_NS_S" link add vx0 type vxlan id 100 \
    local 198.18.0.1 remote "$CIC_IP_B" dev br0 dstport 4789 2>"$CIC_DIR/vxlan.err"; then
  ip -n "$CIC_NS_S" link set vx0 up
  echo '[OK] VXLAN 设备创建'
else
  warn 'VM 内核不支持 VXLAN；Lab 3 的 overlay 进阶任务需另行准备内核。'
  cat "$CIC_DIR/vxlan.err" >&2
fi
ip netns exec "$CIC_NS_A" iptables -A INPUT -p udp --dport 49999 -j DROP
ip netns exec "$CIC_NS_A" iptables -D INPUT -p udp --dport 49999 -j DROP
echo '[OK] iptables 规则'

if [[ -f /sys/fs/cgroup/cgroup.controllers ]]; then
  echo "[信息] cgroup v2，当前控制器：$(cat /sys/fs/cgroup/cgroup.controllers)"
  echo '[信息] Lab 9 的 CPU 控制器委派与限额仍需单独验证。'
else
  echo '[提示] 当前未挂载 cgroup v2；Lab 9 需要另行准备。'
fi
echo "[信息] TCP 拥塞算法：$(ip netns exec "$CIC_NS_A" sysctl -n net.ipv4.tcp_available_congestion_control)"
echo "[完成] 基础环境自检通过，可选能力提示 $CIC_WARNINGS 项；临时资源将自动清理。"
