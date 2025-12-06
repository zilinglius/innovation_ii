import asyncio
import random
import time

# 获得服从长尾分布的随机延迟
def long_tail_delay(min_delay_ms: float, max_delay_ms: float) -> float:
    # 使用指数分布模拟长尾特性
    scale = (max_delay_ms - min_delay_ms) / 5.0
    delay = random.expovariate(1.0 / scale) + min_delay_ms
    return min(delay, max_delay_ms)

async def worker(i: int, barrier_delay_ms: float):
    # 计算阶段：50~150ms 随机
    comp = long_tail_delay(50, 300)
    await asyncio.sleep(comp / 1000)

    # 通信阶段：模拟 barrier / AllReduce 的网络延迟
    await asyncio.sleep(barrier_delay_ms / 1000.0)

async def run_round(p: int, barrier_delay_ms: float) -> float:
    t0 = time.time()
    await asyncio.gather(*(worker(i, barrier_delay_ms) for i in range(p)))
    t1 = time.time()
    return (t1 - t0) * 1000  # 返回毫秒

async def main():
    p = 32
    for delay in [0.1, 1, 5, 10]:  # 单位 ms
        # 这里 delay 只是逻辑上的“网络延迟”
        t = await run_round(p, delay)
        print(f"p={p}, barrier_delay={delay} ms -> round_time={t:.2f} ms")

if __name__ == "__main__":
    asyncio.run(main())