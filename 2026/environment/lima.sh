#!/usr/bin/env bash
set -Eeuo pipefail

# 备课沙箱的宿主机入口：只管理本项目实例，开发修改与 Python 环境保存在 VM 内。
CIL_NAME=innovation-ii
CIL_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
CIL_CONFIG="$CIL_ROOT/2026/environment/lima.yaml"

command -v limactl >/dev/null || { echo '请先安装 Lima。' >&2; exit 1; }

case "${1:-shell}" in
  up)
    if limactl list --quiet | grep -qx "$CIL_NAME"; then
      limactl start --tty=false "$CIL_NAME"
    else
      limactl start --tty=false --name="$CIL_NAME" --mount-only="$CIL_ROOT" "$CIL_CONFIG"
    fi
    limactl shell --workdir=/ "$CIL_NAME" sudo bash \
      "$CIL_ROOT/2026/environment/provision.sh" "$CIL_ROOT"
    ;;
  shell)
    if [[ "$#" -gt 0 ]]; then shift; fi
    limactl shell --workdir=/workspace "$CIL_NAME" "$@"
    ;;
  check)
    limactl shell --workdir=/workspace "$CIL_NAME" sudo course-check
    limactl shell --workdir=/workspace "$CIL_NAME" sudo course-kernel-check
    ;;
  sync)
    # 同名源文件会被覆盖；先导出 VM 内需要保留的开发修改。
    limactl shell --workdir=/workspace "$CIL_NAME" rsync -a \
      --exclude='.git/' --exclude='.venv/' --exclude='__pycache__/' \
      --exclude='.DS_Store' --exclude='.env' --exclude='*.pcap' --exclude='*.log' \
      "$CIL_ROOT/" /workspace/
    ;;
  down)
    # 只停止运行中的实例，重复执行不报错；保留磁盘与开发工作副本。
    if limactl list --quiet --filter '.status == "Running"' | grep -qx "$CIL_NAME"; then
      limactl stop "$CIL_NAME"
    fi
    ;;
  *) echo '用法：bash 2026/environment/lima.sh [up|shell [命令...]|check|sync|down]' >&2; exit 2 ;;
esac
