"""课堂用定量 TCP 传输：接收端读到 EOF 后回执，确认有效数据已全部到达。"""

import argparse
import json
import socket
import time


def receive(port):
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.settimeout(30)
        listener.bind(("0.0.0.0", port))
        listener.listen(1)
        conn, _ = listener.accept()
        with conn:
            conn.settimeout(30)
            total = 0
            while data := conn.recv(100_000):
                total += len(data)
            receipt = {"received_bytes": total}
            conn.sendall(json.dumps(receipt).encode() + b"\n")
    print(json.dumps(receipt))


def send(destination, port, source, source_port, volume):
    started = time.monotonic()
    with socket.socket() as conn:
        conn.settimeout(30)
        conn.bind((source, source_port))
        conn.connect((destination, port))
        block = bytes(100_000)
        remaining = volume
        while remaining:
            size = min(remaining, len(block))
            conn.sendall(block[:size])
            remaining -= size
        conn.shutdown(socket.SHUT_WR)
        # 等待接收端读完全部应用数据；sendall 返回只代表交给本地 TCP。
        reply = bytearray()
        while data := conn.recv(4096):
            reply.extend(data)
        receipt = json.loads(reply)
        if receipt["received_bytes"] != volume:
            raise RuntimeError(f"接收字节不符：{receipt}")
    elapsed = time.monotonic() - started
    result = {
        "source": source,
        "source_port": source_port,
        "destination": destination,
        "destination_port": port,
        "received_bytes": volume,
        "completion_seconds": elapsed,
        "application_mbps": 8 * volume / elapsed / 1e6,
    }
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    server = commands.add_parser("server")
    server.add_argument("--port", type=int, required=True)
    client = commands.add_parser("client")
    client.add_argument("--destination", required=True)
    client.add_argument("--port", type=int, required=True)
    client.add_argument("--source", required=True)
    client.add_argument("--source-port", type=int, required=True)
    client.add_argument("--bytes", type=int, default=30_000_000)
    args = parser.parse_args()
    if args.mode == "server":
        receive(args.port)
    else:
        if args.bytes <= 0:
            parser.error("--bytes 必须大于零")
        send(args.destination, args.port, args.source, args.source_port, args.bytes)


if __name__ == "__main__":
    main()
