#!/usr/bin/env bash
set -Eeuo pipefail

# Quick runner for the topology-aware scheduling lab.
# It generates example configs (if missing) and runs three schedulers side-by-side.

OUTDIR="${1:-experiments/08/examples}"
LOGDIR="${2:-logs/topology_aware}"

mkdir -p "$LOGDIR"

if [[ ! -f "$OUTDIR/topology.json" || ! -f "$OUTDIR/job.json" ]]; then
  python3 experiments/08/topology_aware_scheduler_sim.py init --outdir "$OUTDIR"
fi

for s in random rack_local score; do
  echo "[*] scheduler=$s"
  python3 experiments/08/topology_aware_scheduler_sim.py run \
    --topology "$OUTDIR/topology.json" \
    --job "$OUTDIR/job.json" \
    --scheduler "$s" \
    --seed 1 | tee "$LOGDIR/$s.txt"
  echo
done

echo "[*] done. outputs in $LOGDIR/"

