#!/usr/bin/env python3
"""
Topology-aware scheduler simulator (no real framework required).

This tool models a simple "read data then compute" workload on a two-rack cluster:
- intra-rack transfers are "near" (low latency / high bandwidth)
- inter-rack transfers are "far" and share a bottleneck link (queueing)

It helps students connect:
topology difference -> cost model (L + D/B) -> scheduling policy -> makespan.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple


Scheduler = Literal["random", "rack_local", "score"]


def _transfer_time_ms(size_mb: float, bandwidth_gbps: float) -> float:
  if size_mb < 0:
    raise ValueError("size_mb must be >= 0")
  if bandwidth_gbps <= 0:
    raise ValueError("bandwidth_gbps must be > 0")
  bits = size_mb * 8e6
  bits_per_ms = bandwidth_gbps * 1e9 / 1000.0
  return bits / bits_per_ms


def _summarize_ms(values: Iterable[float]) -> str:
  samples = list(values)
  if not samples:
    return "no samples"
  samples.sort()
  p50 = statistics.median(samples)
  p90 = samples[int(0.9 * len(samples)) - 1]
  p99 = samples[int(0.99 * len(samples)) - 1] if len(samples) >= 100 else samples[-1]
  return (
      f"count={len(samples)}, "
      f"avg={statistics.mean(samples):.2f} ms, "
      f"p50={p50:.2f} ms, p90={p90:.2f} ms, p99={p99:.2f} ms"
  )


@dataclass(frozen=True)
class LinkModel:
  latency_ms: float
  bandwidth_gbps: float

  def validate(self) -> None:
    if self.latency_ms < 0:
      raise ValueError("latency_ms must be >= 0")
    if self.bandwidth_gbps <= 0:
      raise ValueError("bandwidth_gbps must be > 0")

  def transfer_ms(self, size_mb: float) -> float:
    return self.latency_ms + _transfer_time_ms(size_mb, self.bandwidth_gbps)


@dataclass(frozen=True)
class Topology:
  racks: Dict[str, List[str]]
  intra: LinkModel
  inter: LinkModel

  def validate(self) -> None:
    if not self.racks or any(not nodes for nodes in self.racks.values()):
      raise ValueError("racks must contain non-empty node lists")
    all_nodes: List[str] = []
    for rack, nodes in self.racks.items():
      if not rack:
        raise ValueError("rack name must be non-empty")
      for node in nodes:
        if not node:
          raise ValueError("node name must be non-empty")
      all_nodes.extend(nodes)
    if len(set(all_nodes)) != len(all_nodes):
      raise ValueError("node names must be unique across all racks")
    self.intra.validate()
    self.inter.validate()

  def node_rack(self, node: str) -> str:
    for rack, nodes in self.racks.items():
      if node in nodes:
        return rack
    raise KeyError(f"unknown node: {node}")


@dataclass(frozen=True)
class JobSpec:
  tasks: int
  data_rack_weights: Dict[str, float]
  data_mb: Dict[str, Any]
  compute_ms: Dict[str, Any]

  def validate(self, racks: Iterable[str]) -> None:
    if self.tasks <= 0:
      raise ValueError("tasks must be > 0")
    rack_set = set(racks)
    if set(self.data_rack_weights.keys()) != rack_set:
      raise ValueError("data_rack_weights must define every rack in topology")
    if any(w < 0 for w in self.data_rack_weights.values()):
      raise ValueError("data_rack_weights must be non-negative")
    if sum(self.data_rack_weights.values()) <= 0:
      raise ValueError("data_rack_weights must have positive total weight")


@dataclass(frozen=True)
class Task:
  task_id: int
  data_rack: str
  data_mb: float
  compute_ms: float


@dataclass
class NodeState:
  name: str
  rack: str
  available_ms: float = 0.0


@dataclass
class SimulationResult:
  scheduler: Scheduler
  makespan_ms: float
  cross_rack_mb: float
  local_mb: float
  task_total_ms: List[float]
  task_queue_wait_ms: List[float]


def _sample_from_spec(spec: Dict[str, Any], *, rng: random.Random) -> float:
  dist = spec.get("dist", "fixed")
  if dist == "fixed":
    return float(spec["value"])
  if dist == "uniform":
    low = float(spec["min"])
    high = float(spec["max"])
    if high < low:
      raise ValueError("uniform: max must be >= min")
    return rng.uniform(low, high)
  if dist == "lognormal":
    median = float(spec["median"])
    sigma = float(spec["sigma"])
    min_v = float(spec.get("min", 0.0))
    max_v = float(spec.get("max", float("inf")))
    if median <= 0:
      raise ValueError("lognormal: median must be > 0")
    if sigma <= 0:
      raise ValueError("lognormal: sigma must be > 0")
    value = rng.lognormvariate(math.log(median), sigma)
    return max(min_v, min(max_v, value))
  raise ValueError(f"unsupported dist: {dist}")


def _weighted_choice(items: List[Tuple[str, float]], *, rng: random.Random) -> str:
  total = sum(w for _, w in items)
  if total <= 0:
    raise ValueError("total weight must be > 0")
  r = rng.random() * total
  upto = 0.0
  for item, w in items:
    upto += w
    if upto >= r:
      return item
  return items[-1][0]


def generate_tasks(job: JobSpec, *, rng: random.Random) -> List[Task]:
  rack_items = list(job.data_rack_weights.items())
  tasks: List[Task] = []
  for task_id in range(job.tasks):
    rack = _weighted_choice(rack_items, rng=rng)
    data_mb = _sample_from_spec(job.data_mb, rng=rng)
    compute_ms = _sample_from_spec(job.compute_ms, rng=rng)
    tasks.append(Task(task_id=task_id, data_rack=rack, data_mb=data_mb, compute_ms=compute_ms))
  return tasks


def _estimate_finish_ms(
    *,
    topology: Topology,
    node: NodeState,
    task: Task,
    cross_link_available_ms: float,
) -> Tuple[float, float, float, bool]:
  is_cross = node.rack != task.data_rack
  if is_cross:
    transfer_ms = topology.inter.transfer_ms(task.data_mb)
    transfer_start_ms = max(node.available_ms, cross_link_available_ms)
    transfer_end_ms = transfer_start_ms + transfer_ms
    compute_end_ms = transfer_end_ms + task.compute_ms
    return compute_end_ms, transfer_start_ms, transfer_end_ms, True

  transfer_ms = topology.intra.transfer_ms(task.data_mb)
  transfer_start_ms = node.available_ms
  transfer_end_ms = transfer_start_ms + transfer_ms
  compute_end_ms = transfer_end_ms + task.compute_ms
  return compute_end_ms, transfer_start_ms, transfer_end_ms, False


def _choose_node(
    *,
    scheduler: Scheduler,
    topology: Topology,
    nodes: List[NodeState],
    task: Task,
    cross_link_available_ms: float,
    rng: random.Random,
) -> NodeState:
  if scheduler == "random":
    return rng.choice(nodes)

  if scheduler == "rack_local":
    local_nodes = [n for n in nodes if n.rack == task.data_rack]
    if local_nodes:
      return min(local_nodes, key=lambda n: n.available_ms)
    return min(nodes, key=lambda n: n.available_ms)

  if scheduler == "score":
    best: Optional[Tuple[float, NodeState]] = None
    for node in nodes:
      finish_ms, _, _, _ = _estimate_finish_ms(
          topology=topology,
          node=node,
          task=task,
          cross_link_available_ms=cross_link_available_ms,
      )
      if best is None or finish_ms < best[0]:
        best = (finish_ms, node)
    assert best is not None
    return best[1]

  raise ValueError(f"unknown scheduler: {scheduler}")


def simulate(
    *,
    topology: Topology,
    tasks: List[Task],
    scheduler: Scheduler,
    seed: int,
) -> SimulationResult:
  rng = random.Random(seed)
  nodes: List[NodeState] = []
  for rack, node_names in topology.racks.items():
    for name in node_names:
      nodes.append(NodeState(name=name, rack=rack))

  cross_link_available_ms = 0.0
  cross_rack_mb = 0.0
  local_mb = 0.0
  task_total_ms: List[float] = []
  task_queue_wait_ms: List[float] = []

  for task in tasks:
    node = _choose_node(
        scheduler=scheduler,
        topology=topology,
        nodes=nodes,
        task=task,
        cross_link_available_ms=cross_link_available_ms,
        rng=rng,
    )
    finish_ms, transfer_start_ms, transfer_end_ms, is_cross = _estimate_finish_ms(
        topology=topology,
        node=node,
        task=task,
        cross_link_available_ms=cross_link_available_ms,
    )

    queue_wait = max(0.0, transfer_start_ms - node.available_ms)
    task_queue_wait_ms.append(queue_wait)
    task_total_ms.append(finish_ms - node.available_ms)

    node.available_ms = finish_ms
    if is_cross:
      cross_rack_mb += task.data_mb
      cross_link_available_ms = transfer_end_ms
    else:
      local_mb += task.data_mb

  makespan_ms = max(n.available_ms for n in nodes) if nodes else 0.0
  return SimulationResult(
      scheduler=scheduler,
      makespan_ms=makespan_ms,
      cross_rack_mb=cross_rack_mb,
      local_mb=local_mb,
      task_total_ms=task_total_ms,
      task_queue_wait_ms=task_queue_wait_ms,
  )


def _load_json(path: str) -> Dict[str, Any]:
  with open(path, "r", encoding="utf-8") as f:
    return json.load(f)


def load_topology(path: str) -> Topology:
  raw = _load_json(path)
  topo = Topology(
      racks={str(k): list(v) for k, v in raw["racks"].items()},
      intra=LinkModel(
          latency_ms=float(raw["links"]["intra"]["latency_ms"]),
          bandwidth_gbps=float(raw["links"]["intra"]["bandwidth_gbps"]),
      ),
      inter=LinkModel(
          latency_ms=float(raw["links"]["inter"]["latency_ms"]),
          bandwidth_gbps=float(raw["links"]["inter"]["bandwidth_gbps"]),
      ),
  )
  topo.validate()
  return topo


def load_job(path: str) -> JobSpec:
  raw = _load_json(path)
  job = JobSpec(
      tasks=int(raw["tasks"]),
      data_rack_weights={str(k): float(v) for k, v in raw["data_rack_weights"].items()},
      data_mb=dict(raw["task_data_mb"]),
      compute_ms=dict(raw["task_compute_ms"]),
  )
  return job


def write_examples(outdir: str) -> None:
  os.makedirs(outdir, exist_ok=True)

  topology = {
      "racks": {
          "L": ["wL1", "wL2"],
          "R": ["wR1", "wR2", "wR3", "wR4"],
      },
      "links": {
          "intra": {"latency_ms": 0.4, "bandwidth_gbps": 10.0},
          "inter": {"latency_ms": 4.0, "bandwidth_gbps": 1.0},
      },
  }
  job = {
      "tasks": 60,
      "data_rack_weights": {"L": 0.8, "R": 0.2},
      "task_data_mb": {"dist": "lognormal", "median": 16, "sigma": 0.6, "min": 2, "max": 128},
      "task_compute_ms": {"dist": "uniform", "min": 80, "max": 260},
  }

  topo_path = os.path.join(outdir, "topology.json")
  job_path = os.path.join(outdir, "job.json")
  with open(topo_path, "w", encoding="utf-8") as f:
    json.dump(topology, f, ensure_ascii=False, indent=2)
    f.write("\n")
  with open(job_path, "w", encoding="utf-8") as f:
    json.dump(job, f, ensure_ascii=False, indent=2)
    f.write("\n")


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
      description="Simulate topology-aware scheduling on a two-rack cluster (no real framework required)."
  )
  sub = parser.add_subparsers(dest="cmd", required=True)

  p_init = sub.add_parser("init", help="write example topology/job JSON files")
  p_init.add_argument("--outdir", default="experiments/08/examples", help="output directory for example configs")

  p_run = sub.add_parser("run", help="run a simulation with given configs")
  p_run.add_argument("--topology", required=True, help="topology JSON path")
  p_run.add_argument("--job", required=True, help="job JSON path")
  p_run.add_argument("--scheduler", choices=["random", "rack_local", "score"], default="random")
  p_run.add_argument("--seed", type=int, default=1, help="random seed for task generation and scheduling")
  p_run.add_argument("--repeat", type=int, default=1, help="repeat with seed..seed+repeat-1 and summarize")

  return parser


def _print_one(result: SimulationResult, *, topology: Topology) -> None:
  total_mb = result.cross_rack_mb + result.local_mb
  cross_ratio = (result.cross_rack_mb / total_mb) if total_mb > 0 else 0.0
  print(f"scheduler={result.scheduler}")
  print(f"makespan={result.makespan_ms:.2f} ms")
  print(f"cross_rack_mb={result.cross_rack_mb:.2f} (ratio={cross_ratio:.2%})")
  print(f"task_total_ms: {_summarize_ms(result.task_total_ms)}")
  print(f"cross_link_queue_wait_ms: {_summarize_ms(result.task_queue_wait_ms)}")
  print(
      "links: "
      f"intra(lat={topology.intra.latency_ms}ms,bw={topology.intra.bandwidth_gbps}Gbps), "
      f"inter(lat={topology.inter.latency_ms}ms,bw={topology.inter.bandwidth_gbps}Gbps,shared_bottleneck=yes)"
  )


def main() -> None:
  args = build_parser().parse_args()

  if args.cmd == "init":
    write_examples(args.outdir)
    print(f"wrote examples to {args.outdir}")
    return

  topology = load_topology(args.topology)
  job = load_job(args.job)
  job.validate(topology.racks.keys())

  makespans: List[float] = []
  cross_mbs: List[float] = []
  for offset in range(args.repeat):
    rng = random.Random(args.seed + offset)
    tasks = generate_tasks(job, rng=rng)
    result = simulate(topology=topology, tasks=tasks, scheduler=args.scheduler, seed=args.seed + offset)
    makespans.append(result.makespan_ms)
    cross_mbs.append(result.cross_rack_mb)
    if args.repeat == 1:
      _print_one(result, topology=topology)

  if args.repeat > 1:
    print(f"scheduler={args.scheduler}, repeat={args.repeat}")
    print(f"makespan_ms: {_summarize_ms(makespans)}")
    print(f"cross_rack_mb: {_summarize_ms(cross_mbs)}")


if __name__ == "__main__":
  main()
