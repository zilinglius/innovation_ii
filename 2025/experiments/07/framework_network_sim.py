#!/usr/bin/env python3
"""
Lightweight simulator for network-bound distributed jobs.

It approximates how latency/bandwidth affect three patterns:
1) parameter server push/pull
2) ring allreduce
3) shuffle/barrier stage

Use measured numbers from the namespace topology (`ping` RTT, `iperf3` throughput)
to see how job time scales with different network settings without installing
real distributed frameworks.
"""
from __future__ import annotations

import argparse
import random
import statistics
from typing import Iterable, List


def transfer_time_ms(size_mb: float, bandwidth_gbps: float) -> float:
  """Return milliseconds to transfer `size_mb` over `bandwidth_gbps`."""
  if bandwidth_gbps <= 0:
    raise ValueError("bandwidth_gbps must be positive")
  bits = size_mb * 8e6  # MB -> bits (decimal)
  bits_per_ms = bandwidth_gbps * 1e9 / 1000.0
  return bits / bits_per_ms


def sample_tail_jitter_ms(extra_scale_ms: float) -> float:
  """Inject occasional long tails with an exponential distribution."""
  if extra_scale_ms <= 0:
    return 0.0
  return random.expovariate(1.0 / extra_scale_ms)


def summarize(samples: Iterable[float]) -> str:
  values = list(samples)
  if not values:
    return "no samples"
  values.sort()
  p50 = statistics.median(values)
  p90 = values[int(0.9 * len(values)) - 1]
  p99 = values[int(0.99 * len(values)) - 1] if len(values) >= 100 else values[-1]
  return (
      f"count={len(values)}, "
      f"avg={statistics.mean(values):.2f} ms, "
      f"p50={p50:.2f} ms, p90={p90:.2f} ms, p99={p99:.2f} ms"
  )


def simulate_parameter_server(
    workers: int,
    latency_ms: float,
    bandwidth_gbps: float,
    grad_mb: float,
    param_mb: float,
    comp_min_ms: float,
    comp_max_ms: float,
    rounds: int,
    tail_extra_ms: float,
) -> List[float]:
  samples: List[float] = []
  push = latency_ms + transfer_time_ms(grad_mb, bandwidth_gbps)
  pull = latency_ms + transfer_time_ms(param_mb, bandwidth_gbps)
  for _ in range(rounds):
    comp = max(random.uniform(comp_min_ms, comp_max_ms) for _ in range(workers))
    jitter = sample_tail_jitter_ms(tail_extra_ms)
    samples.append(comp + push + pull + jitter)
  return samples


def simulate_allreduce(
    workers: int,
    latency_ms: float,
    bandwidth_gbps: float,
    grad_mb: float,
    comp_min_ms: float,
    comp_max_ms: float,
    rounds: int,
    tail_extra_ms: float,
) -> List[float]:
  samples: List[float] = []
  comm_base = 2 * (workers - 1) * latency_ms
  comm_base += 2 * ((workers - 1) / workers) * transfer_time_ms(grad_mb, bandwidth_gbps)
  for _ in range(rounds):
    comp = max(random.uniform(comp_min_ms, comp_max_ms) for _ in range(workers))
    jitter = sample_tail_jitter_ms(tail_extra_ms)
    samples.append(comp + comm_base + jitter)
  return samples


def simulate_shuffle(
    workers: int,
    latency_ms: float,
    bandwidth_gbps: float,
    shuffle_mb_per_task: float,
    stages: int,
    comp_min_ms: float,
    comp_max_ms: float,
    tail_extra_ms: float,
) -> List[float]:
  samples: List[float] = []
  tasks_per_stage = max(2, workers * 2)
  comm_cost = latency_ms + transfer_time_ms(shuffle_mb_per_task, bandwidth_gbps)
  for _ in range(stages):
    task_times = []
    for _ in range(tasks_per_stage):
      comp = random.uniform(comp_min_ms, comp_max_ms)
      jitter = sample_tail_jitter_ms(tail_extra_ms)
      task_times.append(comp + comm_cost + jitter)
    samples.append(max(task_times))
  return samples


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
      description="Simulate how latency/bandwidth affect distributed workloads. "
      "Feed RTT (ms) and throughput (Gbps) measured from namespaces."
  )
  parser.add_argument("mode", choices=["ps", "allreduce", "shuffle"], help="communication pattern to simulate")
  parser.add_argument("--workers", type=int, default=8, help="number of workers/tasks")
  parser.add_argument("--latency-ms", type=float, default=1.0, help="one-way latency or RPC setup latency in ms")
  parser.add_argument("--bandwidth-gbps", type=float, default=1.0, help="effective bandwidth in Gbps")
  parser.add_argument("--comp-min-ms", type=float, default=40.0, help="min compute time per worker/task")
  parser.add_argument("--comp-max-ms", type=float, default=120.0, help="max compute time per worker/task")
  parser.add_argument("--rounds", type=int, default=10, help="iterations to simulate")
  parser.add_argument("--tail-extra-ms", type=float, default=0.0, help="scale for injected long-tail jitter")

  # pattern-specific knobs
  parser.add_argument("--grad-mb", type=float, default=100.0, help="gradient size for ps/allreduce")
  parser.add_argument("--param-mb", type=float, default=100.0, help="parameter size for ps pull phase")
  parser.add_argument("--stages", type=int, default=3, help="number of shuffle/barrier stages")
  parser.add_argument("--shuffle-mb-per-task", type=float, default=10.0, help="shuffle payload per task")
  return parser


def main() -> None:
  args = build_parser().parse_args()

  if args.mode == "ps":
    samples = simulate_parameter_server(
        workers=args.workers,
        latency_ms=args.latency_ms,
        bandwidth_gbps=args.bandwidth_gbps,
        grad_mb=args.grad_mb,
        param_mb=args.param_mb,
        comp_min_ms=args.comp_min_ms,
        comp_max_ms=args.comp_max_ms,
        rounds=args.rounds,
        tail_extra_ms=args.tail_extra_ms,
    )
    print("parameter server (sync) iteration time:", summarize(samples))
  elif args.mode == "allreduce":
    samples = simulate_allreduce(
        workers=args.workers,
        latency_ms=args.latency_ms,
        bandwidth_gbps=args.bandwidth_gbps,
        grad_mb=args.grad_mb,
        comp_min_ms=args.comp_min_ms,
        comp_max_ms=args.comp_max_ms,
        rounds=args.rounds,
        tail_extra_ms=args.tail_extra_ms,
    )
    print("ring allreduce iteration time:", summarize(samples))
  else:
    samples = simulate_shuffle(
        workers=args.workers,
        latency_ms=args.latency_ms,
        bandwidth_gbps=args.bandwidth_gbps,
        shuffle_mb_per_task=args.shuffle_mb_per_task,
        stages=args.stages,
        comp_min_ms=args.comp_min_ms,
        comp_max_ms=args.comp_max_ms,
        tail_extra_ms=args.tail_extra_ms,
    )
    print("shuffle/barrier stage time:", summarize(samples))


if __name__ == "__main__":
  main()
