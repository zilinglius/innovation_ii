#!/usr/bin/env bash
set -Eeuo pipefail

# 在 Ubuntu VM 内执行；工具与自检可重复安装，已有作业不自动覆盖。
CIP_SOURCE=${1:?请指定只读挂载的源仓库根目录}
CIP_USER=${SUDO_USER:?请通过普通 VM 用户执行 sudo bash provision.sh}
CIP_UV_VERSION=0.12.23
CIP_KERNEL=$(uname -r)
CIP_DIR=''

[[ "$EUID" -eq 0 ]] || { echo '请使用 sudo 执行。' >&2; exit 1; }
[[ -d "$CIP_SOURCE/2026/environment" ]] || { echo '找不到挂载的课程源仓库。' >&2; exit 1; }
# shellcheck source=/dev/null
. /etc/os-release
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 24.04 ]] || {
  echo '本安装脚本针对 Ubuntu 24.04。' >&2; exit 1;
}
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  bash bash-completion ca-certificates curl ethtool frr git \
  iperf3 iproute2 iptables iputils-ping jq kmod less nano nftables \
  procps python3 python3-numpy python3-venv python3-yaml \
  rsync shellcheck sudo tcpdump traceroute util-linux vim-tiny

# 云镜像常用精简 virtual 软件包；补齐与当前运行内核精确匹配的 extra 模块。
if apt-cache show "linux-modules-extra-$CIP_KERNEL" >/dev/null 2>&1; then
  apt-get install -y "linux-modules-extra-$CIP_KERNEL"
fi
for module in sch_netem sch_htb sch_fq sch_red sch_etf tcp_bbr tcp_dctcp vxlan; do
  if ! modprobe "$module"; then
    echo "当前内核缺少 $module；需安装匹配模块或更换 Ubuntu 内核后重启。" >&2
    exit 1
  fi
done
cat >/etc/modules-load.d/innovation-ii.conf <<'MODULES'
sch_netem
sch_htb
sch_fq
sch_red
sch_etf
tcp_bbr
tcp_dctcp
vxlan
MODULES

if ! command -v uv >/dev/null || [[ "$(uv --version | awk '{print $2}')" != "$CIP_UV_VERSION" ]]; then
  CIP_DIR=$(mktemp -d /tmp/course-uv.XXXXXX)
  trap '[[ -z "$CIP_DIR" ]] || rm -rf -- "$CIP_DIR"' EXIT
  curl --fail --location --retry 3 "https://astral.sh/uv/$CIP_UV_VERSION/install.sh" \
    --output "$CIP_DIR/install.sh"
  UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh "$CIP_DIR/install.sh"
fi
install -m 0755 "$CIP_SOURCE/2026/environment/check.sh" /usr/local/bin/course-check
install -m 0755 "$CIP_SOURCE/2026/environment/kernel_check.sh" /usr/local/bin/course-kernel-check
cat >/etc/profile.d/innovation-ii.sh <<'PROFILE'
export UV_PYTHON_DOWNLOADS=never
export UV_LINK_MODE=copy
export PYTHONDONTWRITEBYTECODE=1
PROFILE

# FRR 由讲义在各 namespace 内启动，避免系统级服务提前占用资源。
systemctl disable --now frr
if [[ ! -d /workspace/2026 ]]; then
  install -d -o "$CIP_USER" -g "$(id -gn "$CIP_USER")" /workspace
  rsync -a \
    --exclude='.git/' --exclude='.venv/' --exclude='__pycache__/' \
    --exclude='.DS_Store' --exclude='.env' --exclude='*.pcap' --exclude='*.log' \
    "$CIP_SOURCE/" /workspace/
  chown -R "$CIP_USER:$(id -gn "$CIP_USER")" /workspace
fi
sudo -u "$CIP_USER" env UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy \
  uv sync --project /workspace/2026/experiments/02 --frozen --offline
echo "[完成] Ubuntu $VERSION_ID，内核 $CIP_KERNEL，工作目录 /workspace；已有作业保持原样。"
