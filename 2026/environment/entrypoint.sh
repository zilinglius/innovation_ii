#!/usr/bin/env bash
set -Eeuo pipefail

# 宿主仓库只读挂到 /course-src；首次启动时复制为容器内的独立 Linux 工作副本。
# 保留容器中后续的修改，不在重启时覆盖作业；排除 Mac 虚拟环境与运行产物。
if [[ -d /course-src/2026 && ! -e /workspace/2026 ]]; then
  rsync -a \
    --exclude='.git/' --exclude='.venv/' --exclude='__pycache__/' \
    --exclude='.DS_Store' --exclude='.env' --exclude='*.pcap' --exclude='*.log' \
    /course-src/ /workspace/
  echo '[课程环境] 已复制仓库到 /workspace；原仓库保持只读。'
fi

exec "$@"
