"""分发器与算力画像工具共用的客户端部分（给定）：进入客户端的 namespace、发一个请求、找出有哪些实例。"""

import json
import os
from pathlib import Path
import socket
import sys
import time

PORT = 7700
STATE = Path("/run/lab07")


def enter(client):
    """实例的地址只有在实验床的 namespace 里才连得上：还没进去时，用 ip netns exec 把自己重新启动一遍。"""
    if os.environ.get("LAB07_NETNS") == client:
        return
    os.environ["LAB07_NETNS"] = client
    os.execvp("ip", ["ip", "netns", "exec", client, sys.executable, *sys.argv])


def running_instances():
    """edge.sh up 为每个实例在 /run/lab07 下登记了一个 <主机名>.pid。"""
    names = sorted(path.stem for path in STATE.glob("*.pid"))
    if not names:
        raise SystemExit("没有在运行的实例；先执行 edge.sh up。")
    return names


def send(request_id, input_bytes, work_ms, address, cc="cubic"):
    """发一个请求并等结果。返回实例的应答，另加 sent（发出时刻）与 done（收到结果的时刻）。"""
    record = {"sent": time.monotonic()}
    with socket.create_connection((address, PORT), timeout=120) as conn:
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_CONGESTION, cc.encode())
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        header = {"id": request_id, "input_bytes": input_bytes, "work_ms": work_ms}
        conn.sendall(json.dumps(header).encode() + b"\n")
        conn.sendall(bytes(input_bytes))
        with conn.makefile("rb") as stream:
            record.update(json.loads(stream.readline()))
    record["done"] = time.monotonic()
    return record


def stat(address, cc="cubic"):
    """查询一个实例当前的状态：{"queued": 排队与在算的请求数, "backlog_ms": 还没算完的工作量之和}。"""
    with socket.create_connection((address, PORT), timeout=10) as conn:
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_CONGESTION, cc.encode())
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        conn.sendall(b'{"op": "stat"}\n')
        with conn.makefile("rb") as stream:
            return json.loads(stream.readline())
