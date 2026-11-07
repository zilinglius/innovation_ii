"""定时 TCP 大流：显式指定拥塞控制算法，用来对照不同算法的队列行为。

两端都在连接建立之前设置算法。这一点对 DCTCP 是必需的：ECN 能力在握手时协商，
连接建立后才切换到 dctcp，内核会退回 dctcp-reno（ss 显示 dctcp:fallback_mode）。
用套接字选项设置算法，不要求算法出现在 tcp_allowed_congestion_control 里，但需要 root。

  sudo ip netns exec h3a python3 2026/experiments/05/bulk.py server --port 5301 --cc dctcp
  sudo ip netns exec h1b python3 2026/experiments/05/bulk.py client --destination 10.0.3.11 --port 5301 --cc dctcp --seconds 15

只用 Python 标准库。
"""

import argparse
import json
import socket
import time


def congestion(sock, cc):
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_CONGESTION, cc.encode())


def serve(port, cc):
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        congestion(listener, cc)  # 接受的连接继承监听套接字的算法。
        listener.settimeout(60)
        listener.bind(("0.0.0.0", port))
        listener.listen(1)
        conn, _ = listener.accept()
        with conn:
            conn.settimeout(60)
            total = 0
            while data := conn.recv(262144):
                total += len(data)
            conn.sendall(json.dumps({"received_bytes": total}).encode() + b"\n")


def send(destination, port, cc, seconds):
    block = bytes(65536)
    with socket.socket() as conn:
        congestion(conn, cc)  # 必须在 connect 之前。
        conn.settimeout(30)
        started = time.monotonic()
        conn.connect((destination, port))
        deadline = started + seconds
        while time.monotonic() < deadline:
            conn.sendall(block)
        conn.shutdown(socket.SHUT_WR)
        reply = bytearray()
        while data := conn.recv(4096):
            reply.extend(data)
        elapsed = time.monotonic() - started
    received = json.loads(reply)["received_bytes"]
    print(f"[{cc}] 接收端收到 {received} B，用时 {elapsed:.2f} s，应用层 {8 * received / elapsed / 1e6:.1f} Mbit/s")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="mode", required=True)
    server = commands.add_parser("server")
    server.add_argument("--port", type=int, required=True)
    server.add_argument("--cc", required=True)
    client = commands.add_parser("client")
    client.add_argument("--destination", required=True)
    client.add_argument("--port", type=int, required=True)
    client.add_argument("--cc", required=True)
    client.add_argument("--seconds", type=float, default=15)
    args = parser.parse_args()
    if args.mode == "server":
        serve(args.port, args.cc)
    else:
        send(args.destination, args.port, args.cc, args.seconds)


if __name__ == "__main__":
    main()
