"""Ring AllReduce 与环序（TODO 5、7）。纯计算，可以离线测试。"""


def split_chunks(vector, parts):
    """把 vector（bytes）切成 parts 块（给定）；除不尽时前面的块多一个字节。"""
    size, extra = divmod(len(vector), parts)
    chunks, start = [], 0
    for index in range(parts):
        stop = start + size + (1 if index < extra else 0)
        chunks.append(vector[start:stop])
        start = stop
    return chunks


def ring_allreduce(rank, size, chunks, exchange, combine):
    """TODO 5　在环上完成一次 AllReduce，返回合并好的 size 块结果（列表，下标是块号）。

    rank：自己在环上的位置，0 到 size−1。
    chunks：自己的向量，已切成 size 块。不要修改原列表，先复制一份。
    exchange(payload)：向右邻居发 payload，同时从左邻居收一块，返回收到的块。
    combine(a, b)：合并两块，满足交换律和结合律，返回新的块。

    分两个阶段，各 size−1 步，每一步每个节点恰好调用一次 exchange：
      1. Reduce-Scatter，第 s 步（s 从 0 数）：
         发出块 (rank − s) mod size；收到的是块 (rank − 1 − s) mod size，把它合并进自己的同号块。
         这一阶段结束后，块 (rank + 1) mod size 已经包含全部节点的贡献。
      2. Allgather，第 s 步：
         发出块 (rank + 1 − s) mod size（已合并完）；收到的是块 (rank − s) mod size，直接覆盖。

    size 为 1 时不需要通信，直接返回副本。
    """
    raise NotImplementedError("TODO 5：ring_allreduce")


def topology_ring_order(hosts, rack_of):
    """TODO 7　排出拓扑感知的环序：同一机架的主机在环上连续，返回主机列表。

    hosts：主机名列表（顺序任意）。rack_of(host)：返回主机所在机架。
    要求：环上跨机架的边数最少（机架数为 1 时是 0 条，否则等于机架数）；
    结果是 hosts 的一个排列，同样的输入总是得到同样的输出。
    """
    raise NotImplementedError("TODO 7：topology_ring_order")
