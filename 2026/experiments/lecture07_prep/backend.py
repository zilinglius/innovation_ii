"""Lab 5 后端进程（给定）。在每台 host 的 namespace 里运行一个，由 lab5_tail.sh up 启动。"""

import argparse
import asyncio

from tailkit.rpc import serve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7000)
    parser.add_argument("--cc", default="cubic", help="本后端连接使用的拥塞控制算法")
    parser.add_argument("--seed", type=int, help="服务时间抽样的随机种子，用于复现")
    args = parser.parse_args()
    try:
        asyncio.run(serve(args.port, args.cc, args.seed))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
