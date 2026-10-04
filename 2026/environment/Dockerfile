# 课程共用 Linux 工具环境；构建上下文只需本目录，不包含本机 Python 环境。
ARG UV_VERSION=0.12.23
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM ubuntu:24.04

LABEL org.opencontainers.image.title="云网融合创新实践 · 实验环境" \
      org.opencontainers.image.description="Ubuntu 24.04、Linux 网络工具、FRR、Python 3.12 与 uv"

# 禁止软件包安装时交互询问或自动启动服务，FRR 按讲义在各 namespace 内启动。
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
    && chmod +x /usr/sbin/policy-rc.d \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        bash bash-completion ca-certificates curl ethtool frr git \
        iperf3 iproute2 iptables iputils-ping jq kmod less nano nftables \
        procps python3 python3-numpy python3-venv python3-yaml \
        rsync shellcheck sudo tcpdump traceroute util-linux vim-tiny \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /usr/local/bin/
COPY check.sh /usr/local/bin/course-check
COPY entrypoint.sh /usr/local/bin/course-entrypoint
RUN chmod +x /usr/local/bin/course-check /usr/local/bin/course-entrypoint \
    && python3 -c 'import numpy, yaml' \
    && uv --version

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/course-entrypoint"]
CMD ["bash"]
