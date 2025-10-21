#!/usr/bin/env bash
set -Eeuo pipefail

# 简易抓包脚本，便于在 namespace 内观察协议报文。

usage() {
  cat <<'EOF'
用法：
  ./capture.sh <namespace> <interface> [tcpdump-args...]

示例：
  sudo ./capture.sh r1 veth-r1-r2 -nn -vv
EOF
}

if [[ $# -lt 2 ]]; then
  usage
  exit 1
fi

ns="$1"
iface="$2"
shift 2

sudo ip netns exec "${ns}" tcpdump -i "${iface}" "${@:-}"
