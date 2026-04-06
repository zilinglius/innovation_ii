"""
教学版 OSPF 实现使用的默认定时器。

这些取值兼顾了实验的可视化效果与本地调试成本：足够快速以观察
邻居/LSDB 变化，又不会在笔记本上产生过多报文洪泛。若需模拟更大
拓扑，可通过拓扑文件中的 defaults 覆盖这些值。
"""

HELLO_INTERVAL = 5
DEAD_INTERVAL = 20
LS_REFRESH_TIME = 30 * 60  # LSA 默认 30 分钟刷新
SPF_INITIAL_DELAY = 0.2    # SPF 触发的初始延迟，用于抑制抖动
SPF_HOLD_TIME = 2.0        # 当前实现未使用，预留给后续 hold-down
NEIGHBOR_TICK = 1.0        # 邻居与 LSDB aging 的周期性检查间隔
