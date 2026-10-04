#!/usr/bin/env bash
set -Eeuo pipefail

# 后续实验的内核能力检查：qdisc、拥塞算法选择和实际 cgroup CPU 限额。
CIK_NS=course-kernel-check
CIK_CREATED=0

cleanup() {
  if [[ "$CIK_CREATED" -eq 1 ]]; then
    ip netns del "$CIK_NS" 2>/dev/null || true
  fi
}

case "${1:-full}" in
  down) CIK_CREATED=1; cleanup; exit 0 ;;
  full) ;;
  *) echo '用法：course-kernel-check [full|down]' >&2; exit 2 ;;
esac
[[ "$EUID" -eq 0 ]] || { echo '请执行 sudo course-kernel-check。' >&2; exit 1; }
if ip netns list | awk '{print $1}' | grep -qx "$CIK_NS"; then
  echo "已有 $CIK_NS，请先执行 sudo course-kernel-check down。" >&2
  exit 1
fi
trap cleanup EXIT
ip netns add "$CIK_NS"
CIK_CREATED=1
ip -n "$CIK_NS" link set lo up
ip -n "$CIK_NS" link add q0 type veth peer name q1
ip -n "$CIK_NS" link set q0 up
ip -n "$CIK_NS" link set q1 up

# 1. 逐一安装真实 qdisc；ETF 使用软件时间戳路径，不要求硬件 offload。
ip netns exec "$CIK_NS" tc qdisc replace dev q0 root fq
ip netns exec "$CIK_NS" tc qdisc show dev q0 | grep -q 'qdisc fq '
ip netns exec "$CIK_NS" tc qdisc replace dev q0 root red \
  limit 100000 min 30000 max 60000 avpkt 1000 burst 55 bandwidth 10mbit ecn
ip netns exec "$CIK_NS" tc qdisc show dev q0 | grep -q 'qdisc red '
ip netns exec "$CIK_NS" tc qdisc replace dev q0 root etf clockid CLOCK_TAI delta 300000
ip netns exec "$CIK_NS" tc qdisc show dev q0 | grep -q 'qdisc etf '
echo '[OK] fq、RED / ECN、软件 ETF qdisc 可安装'

# 2. 验证 TCP 套接字能实际选择两种算法，保留全局默认 CUBIC。
ip netns exec "$CIK_NS" python3 - <<'PY'
import socket
for algorithm in ("cubic", "bbr", "dctcp"):
    with socket.socket() as sock:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_CONGESTION, algorithm.encode())
        selected = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_CONGESTION, 32).rstrip(b"\0").decode()
        assert selected == algorithm, selected
        print(f"[OK] TCP 套接字可选择 {selected}")
PY

# 3. 在临时 systemd 单元中设置 50% CPU 限额，执行忙循环并观察内核限流。
# 单元结束后 --collect 自动回收；不更改根 cgroup 或其他进程的限额。
[[ -f /sys/fs/cgroup/cgroup.controllers ]] || { echo '需要 cgroup v2。' >&2; exit 1; }
systemd-run --quiet --pipe --wait --collect --unit="course-check-cpu-$BASHPID" \
  --property=CPUQuota=50% python3 -c '
import pathlib, time
cg_path = next(line.split(":", 2)[2] for line in pathlib.Path("/proc/self/cgroup").read_text().splitlines() if line.startswith("0::"))
cg = pathlib.Path("/sys/fs/cgroup") / cg_path.lstrip("/")
quota, period = (cg / "cpu.max").read_text().split()
assert quota != "max" and int(quota) / int(period) == 0.5, (quota, period)
def stats():
    return dict(line.split() for line in (cg / "cpu.stat").read_text().splitlines())
before = stats()
start = time.monotonic()
while time.monotonic() - start < 1.5:
    pass
after = stats()
assert int(after["nr_throttled"]) > int(before["nr_throttled"]), (before, after)
print("[OK] cgroup v2 CPU 限额 50%，忙循环触发真实 CPU 限流")
'
echo '[完成] 后续内核能力自检通过；算法性能、ECN 标记效果与精确定时仍需各实验验证。'
