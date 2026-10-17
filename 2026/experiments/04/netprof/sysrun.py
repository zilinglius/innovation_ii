"""在 network namespace 里运行命令的薄封装：超时、iperf3 服务端起停、读取实验床状态。只用标准库。"""

import contextlib
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
STATE = Path("/run/lab04")


def require_root():
    if os.geteuid() != 0:
        raise SystemExit("需要 root：请用 sudo 运行（命令示例见指导书第四节）。")


def require_tools(*names):
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise SystemExit(f"缺少工具：{' '.join(missing)}；见指导书第二节的安装命令。")


def namespace_exists(ns):
    return Path("/run/netns", ns).exists()


def run_in(ns, args, timeout=60, check=False):
    """在 ns 中运行 args，返回 CompletedProcess（文本模式）。超时会抛出 subprocess.TimeoutExpired。"""
    return subprocess.run(["ip", "netns", "exec", ns, *args], capture_output=True, text=True,
                          timeout=timeout, check=check)


def wait_listening(ns, port, timeout=3.0):
    """用 ss 确认 ns 中的 TCP 端口已在监听，避免客户端先于服务端启动。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        out = run_in(ns, ["ss", "-Hltn", f"sport = :{port}"], timeout=5).stdout
        if out.strip():
            return True
        time.sleep(0.05)
    return False


@contextlib.contextmanager
def iperf3_server(ns, port=5201):
    """在 ns 中起一次性 iperf3 服务端（-1：服务完一个客户端就退出），离开 with 时确保它已结束。"""
    proc = subprocess.Popen(["ip", "netns", "exec", ns, "iperf3", "-s", "-1", "-p", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        if not wait_listening(ns, port):
            raise RuntimeError(f"{ns} 的 iperf3 服务端没有在 {port} 端口监听：{proc.stderr.read() if proc.poll() is not None else ''}")
        yield proc
    finally:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def topo(*args, timeout=60):
    """调用同目录的 topo.sh 子命令（如 pin、unpin），失败时抛出异常。"""
    return subprocess.run(["bash", str(LAB / "topo.sh"), *args], capture_output=True, text=True,
                          timeout=timeout, check=True)


def environment():
    """记录测量条件：内核、CPU 数、iperf3 版本、实验床场景与档位。"""
    def read(name, default):
        try:
            return (STATE / name).read_text().strip() or default
        except OSError:
            return default
    iperf = subprocess.run(["iperf3", "--version"], capture_output=True, text=True).stdout.split("\n")[0]
    return {
        "kernel": platform.release(),
        "cpus": os.cpu_count(),
        "iperf3": iperf.strip(),
        "testbed": "2026/experiments/04/topo.sh",
        "scenario": read("scenario", "baseline"),
        "fabric_mbps": int(read("rate", "100")),
        "loadavg_start": loadavg(),
    }


def loadavg():
    """1 分钟平均负载；与 CPU 数比较，可看出测量时机器上是否还有别的负载在争用 CPU。"""
    return float(Path("/proc/loadavg").read_text().split()[0])
