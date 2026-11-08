"""TODO 5、6、7 的离线测试。"""

import queue
import threading
import unittest

from jobkit.alphabeta import predict_ring_round
from jobkit.ring import ring_allreduce, split_chunks, topology_ring_order


def xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def simulate(size, vectors):
    """每个节点一个线程，用内存队列连成环；返回 (各节点的结果, 各节点 exchange 的次数与发送字节数)。"""
    links = [queue.Queue() for _ in range(size)]  # links[r] 是 r 收到的数据
    results, stats, errors = [None] * size, [None] * size, []

    def node(rank):
        counts = [0, 0]

        def exchange(payload):
            counts[0] += 1
            counts[1] += len(payload)
            links[(rank + 1) % size].put(payload)
            return links[rank].get(timeout=5)

        try:
            original = split_chunks(vectors[rank], size)
            copy = list(original)
            results[rank] = ring_allreduce(rank, size, original, exchange, xor)
            if original != copy:
                errors.append("修改了传入的 chunks")
        except Exception as error:  # 让测试报告失败，而不是挂起
            errors.append(repr(error))
        stats[rank] = counts

    threads = [threading.Thread(target=node, args=(rank,)) for rank in range(size)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    if errors:
        raise AssertionError(errors)
    return results, stats


def vectors_for(size, length):
    return [bytes((rank * 37 + index * 11 + 1) % 256 for index in range(length)) for rank in range(size)]


def expected(vectors):
    total = bytes(len(vectors[0]))
    for vector in vectors:
        total = xor(total, vector)
    return total


class SplitCases(unittest.TestCase):
    def test_given_split_keeps_all_bytes(self):
        data = bytes(range(10))
        parts = split_chunks(data, 3)
        self.assertEqual([len(p) for p in parts], [4, 3, 3])
        self.assertEqual(b"".join(parts), data)


class RingCases(unittest.TestCase):
    def check(self, size, length):
        vectors = vectors_for(size, length)
        results, _ = simulate(size, vectors)
        for rank, result in enumerate(results):
            self.assertEqual(b"".join(result), expected(vectors), f"节点 {rank} 的结果不对")

    def test_two_nodes(self):
        self.check(2, 64)

    def test_three_nodes(self):
        self.check(3, 90)

    def test_seven_nodes_uneven_chunks(self):
        self.check(7, 100)

    def test_one_node_no_exchange(self):
        vector = bytes(range(20))
        calls = []
        result = ring_allreduce(0, 1, [vector], lambda p: calls.append(p), xor)
        self.assertEqual(b"".join(result), vector)
        self.assertEqual(calls, [])

    def test_step_count_and_volume(self):
        size, length = 5, 500
        _, stats = simulate(size, vectors_for(size, length))
        for steps, volume in stats:
            self.assertEqual(steps, 2 * (size - 1))
            self.assertEqual(volume, 2 * (size - 1) * length // size)


class RingPredictCases(unittest.TestCase):
    def test_round(self):
        result = predict_ring_round(0.001, 1e-7, 1_000_000, 5, 0.2)
        self.assertAlmostEqual(result["communicate"], 8 * (0.001 + 1e-7 * 200_000))
        self.assertAlmostEqual(result["round"], 0.2 + result["communicate"])
        self.assertAlmostEqual(result["compute"], 0.2)

    def test_single_node_has_no_communication(self):
        result = predict_ring_round(0.001, 1e-7, 1_000_000, 1, 0.2)
        self.assertEqual(result["communicate"], 0)
        self.assertAlmostEqual(result["round"], 0.2)


def rack(name):
    return int(name[1])


def cross(order):
    return sum(rack(a) != rack(b) for a, b in zip(order, order[1:] + order[:1]))


class OrderCases(unittest.TestCase):
    HOSTS = ["h1a", "h3a", "h2a", "h4a", "h1b", "h3b", "h2b", "h4b"]

    def test_is_permutation(self):
        self.assertEqual(sorted(topology_ring_order(self.HOSTS, rack)), sorted(self.HOSTS))

    def test_minimal_cross_rack_edges(self):
        self.assertEqual(cross(topology_ring_order(self.HOSTS, rack)), 4)

    def test_two_racks_of_unequal_size(self):
        hosts = ["h2a", "h1a", "h1b", "h2b", "h3a"]
        self.assertEqual(cross(topology_ring_order(hosts, rack)), 3)

    def test_one_rack_has_no_cross_edge(self):
        self.assertEqual(cross(topology_ring_order(["h1b", "h1a"], rack)), 0)

    def test_same_input_same_output(self):
        self.assertEqual(topology_ring_order(self.HOSTS, rack), topology_ring_order(list(self.HOSTS), rack))


if __name__ == "__main__":
    unittest.main()
