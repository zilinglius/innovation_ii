"""一轮本地计算（给定）。

sleep：固定时长的占位计算，不占 CPU，JCT 的差别只来自通信，这是默认值。
numpy：真实的最小二乘梯度，计算量固定、实际耗时随 CPU 争用变化。
"""

import os
import random
import time


class SleepCompute:
    """每轮固定 seconds；以 slow_prob 的概率再多等 slow_seconds，每轮独立抽样。"""

    def __init__(self, seconds, slow_prob=0.0, slow_seconds=0.0, seed=1):
        self.seconds = seconds
        self.slow_prob = slow_prob
        self.slow_seconds = slow_seconds
        self.random = random.Random(seed)
        self.slow_rounds = 0

    def step(self):
        extra = 0.0
        if self.random.random() < self.slow_prob:
            extra = self.slow_seconds
            self.slow_rounds += 1
        time.sleep(self.seconds + extra)

    def info(self):
        return {"kind": "sleep", "seconds": self.seconds, "slow_rounds": self.slow_rounds}


class NumpyCompute:
    """最小二乘：loss = ‖Xw − y‖² / (2n)。每轮把同一个梯度重复算 iters 次，用 iters 控制计算量。

    所有 worker 拟合同一个目标 w*，各自持有不同的样本 X；X 按 √dim 归一化，步长 0.5 稳定。
    """

    def __init__(self, model_bytes, iters, seed):
        os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        import numpy as np

        self.np = np
        dim = max(1, model_bytes // 8)
        rows = max(1, (1 << 21) // dim)
        target = np.random.default_rng(0).standard_normal(dim)
        self.x = np.random.default_rng(seed).standard_normal((rows, dim)) / np.sqrt(dim)
        self.y = self.x @ target
        self.w = np.zeros(dim)
        self.iters = iters
        self.gradient = np.zeros(dim)
        self.losses = []

    def step(self):
        for _ in range(self.iters):
            residual = self.x @ self.w - self.y
            self.gradient = self.x.T @ residual / len(self.y)
        self.losses.append(float(residual @ residual) / (2 * len(self.y)))

    def payload(self):
        return self.gradient.tobytes()

    def apply_model(self, buffer, length):
        self.w = self.np.frombuffer(bytes(buffer[:length]), dtype=self.np.float64).copy()

    def info(self):
        return {"kind": "numpy", "iters": self.iters, "rows": len(self.y), "dim": len(self.w),
                "first_loss": self.losses[0], "last_loss": self.losses[-1]}
