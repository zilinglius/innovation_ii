"""第 09 讲课堂用的 Ring 流量替身（给定）。不是 Lab 6 的答案：TODO 5、7 在 Lab 6 目录的 jobkit/ring.py 里完成。

替身只复现 Ring AllReduce 的“节奏”：2(size−1) 步，每步向右邻居发一块、从左邻居收一块，
前 size−1 步把收到的块合并一次。每步的字节数、步数和合并次数都与真实 Ring 相同，
所以时间与流量可以用来观察；但它不按块号记账，最后的结果不正确，jobrun.py 的副本不核对结果。
"""


def split_chunks(vector, parts):
    """把 vector（bytes）切成 parts 块（与 06 相同）；除不尽时前面的块多一个字节。"""
    size, extra = divmod(len(vector), parts)
    chunks, start = [], 0
    for index in range(parts):
        stop = start + size + (1 if index < extra else 0)
        chunks.append(vector[start:stop])
        start = stop
    return chunks


def ring_allreduce(rank, size, chunks, exchange, combine):
    """流量替身：每步发出的块大小与真实 Ring 相同（取第 0 块，最多多 1 字节），结果不正确。"""
    held = chunks[0]
    for step in range(2 * (size - 1)):
        received = exchange(held)
        held = combine(held, received) if step < size - 1 else received
    return list(chunks)


def topology_ring_order(hosts, rack_of):
    """本副本不提供拓扑感知环序（Lab 6 的 TODO 7）；课上用 --workers 按顺序直接给出环序。"""
    raise NotImplementedError("第 09 讲的副本不提供 --order topo，请用 --workers 按顺序列出主机")
