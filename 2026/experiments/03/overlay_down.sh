#!/usr/bin/env bash
set -Eeuo pipefail

# 只回收任务 6 写入清单的资源；可单独执行，也由 topo.sh down 调用。
L3_OVERLAY_STATE=/run/lab03/overlay-resources
[[ "$EUID" -eq 0 ]] || { echo '请用 sudo bash 执行。' >&2; exit 1; }
[[ -f "$L3_OVERLAY_STATE" ]] || exit 0

while read -r kind ns name; do
  if [[ "$kind" == ns ]]; then
    for pid in $(ip netns pids "$ns" 2>/dev/null || true); do
      kill "$pid" 2>/dev/null || true
    done
  fi
done <"$L3_OVERLAY_STATE"
sleep 0.2
while read -r kind ns name; do
  if [[ "$kind" == ns ]]; then
    for pid in $(ip netns pids "$ns" 2>/dev/null || true); do
      kill -KILL "$pid" 2>/dev/null || true
    done
    ip netns del "$ns" 2>/dev/null || true
  elif [[ "$kind" == link ]]; then
    ip -n "$ns" link del "$name" 2>/dev/null || true
  fi
done <"$L3_OVERLAY_STATE"
rm -f -- "$L3_OVERLAY_STATE"
echo '[清理] 本次登记的租户进程、namespace、VTEP 与 bridge 已回收。'
