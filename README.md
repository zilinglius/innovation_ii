# Network & Distributed Systems Lab

A comprehensive collection of Linux network namespace labs for exploring networking fundamentals, routing protocols, and distributed systems concepts. All labs use Bash + `iproute2` for reproducible experiments on any modern Linux host.

## Prerequisites

- Linux kernel >= 3.8 (5.x recommended) with `iproute2`, `iputils-ping`, `bridge-utils`, and `tcpdump`
- Root access via `sudo`; always launch labs from the repository root
- Optional: `shellcheck`, `iperf3`, `gcc` + `libpcap-dev`, `python3`

See `experiments/01/ns_setup_guide.md` for environment setup and module checks (`veth`, `bridge`).

## Repository Structure

| Path | Purpose |
| --- | --- |
| `experiments/01/` | Base labs: static routing, bridges, network namespaces |
| `experiments/02/` | Routing protocol design notes (RIP/OSPF/ISIS/EIGRP/BGP) |
| `experiments/03/` | OSPF-like simulator framework (Python implementation skeleton) |
| `experiments/04/` | UDP transmission timing lab with C helpers |
| `experiments/05/` | Network tail latency analysis |
| `experiments/06/` | Barrier synchronization simulation |
| `experiments/07/` | Network impact on distributed frameworks |
| `experiments/08/` | Topology-aware scheduling simulation |
| `docs/` | Background reading on networking, routing, timing, and distributed systems |

## Quick Start

### Base Network Namespace Lab

Five-namespace ring topology (ns1 -> ns2 -> ns3 -> ns4 -> ns5 -> ns1):

```bash
sudo bash experiments/01/ns.sh
ip netns list
ip netns exec ns1 ping -c1 10.0.23.2
sudo bash experiments/01/ns.sh down
```

### Bridge Lab

Bridge-centric topology with leaf namespaces:

```bash
sudo bash experiments/01/ns_bridge.sh
ip netns exec ns1a ping -c1 10.0.3.11
sudo bash experiments/01/ns_bridge.sh down
```

## Lab Guide

### Lab 1: Network Namespace Basics (`experiments/01/`)

- **ns.sh**: Five-node ring with static routes
- **ns_bridge.sh**: Software bridges with leaf namespaces
- **ns_setup_guide.md**: Setup, troubleshooting, and verification

### Lab 2: Routing Protocols (`experiments/02/`)

Design notes and scaffolds for:
- RIP (Routing Information Protocol)
- OSPF (Open Shortest Path First)
- IS-IS (Intermediate System to Intermediate System)
- EIGRP (Enhanced Interior Gateway Routing Protocol)
- BGP (Border Gateway Protocol)

### Lab 3: OSPF Simulator (`experiments/03/`)

Minimal OSPF-like framework for students to implement:
- Neighbor discovery and adjacency
- LSA flooding
- Link State Database
- SPF calculation (Dijkstra)

```bash
sudo bash experiments/01/ns.sh
sudo ip netns exec r1 python3 experiments/03/main.py --router 1.1.1.1 --config experiments/03/topo.sample.yaml
```

### Lab 4: UDP Timing (`experiments/04/`)

Precise UDP transmission timing experiments using:
- `SO_TXTIME` with ETF qdisc
- Hardware timestamping
- C helpers for timestamp collection

### Lab 5: Tail Latency (`experiments/05/`)

Inject and measure network tail latency using `tc netem`:

```bash
sudo bash experiments/01/ns.sh
ip netns exec ns2 tc qdisc add dev veth23a root netem delay 5ms 2ms 25%
# Analyze with iperf3, ping, tcpdump
```

### Lab 6: Barrier Simulation (`experiments/06/`)

Python simulator for studying barrier synchronization patterns in distributed systems.

### Lab 7: Network Impact on Distributed Frameworks (`experiments/07/`)

Simulate how network conditions affect:
- Shuffle operations
- Parameter Server push/pull
- Ring AllReduce

```bash
sudo bash experiments/07/ns_framework_topo.sh
python3 experiments/07/framework_network_sim.py shuffle --workers 12 --latency-ms 5 --bandwidth-gbps 1
```

### Lab 8: Topology-Aware Scheduling (`experiments/08/`)

Compare scheduling strategies:
- `random`: Network-oblivious placement
- `rack_local`: Rack affinity
- `score`: Network cost model-based scheduling

```bash
sudo bash experiments/08/ns_topology_aware.sh
python3 experiments/08/topology_aware_scheduler_sim.py init --outdir experiments/08/examples
bash experiments/08/run_topology_aware_lab.sh
```

## Background Reading

| Document | Topics |
| --- | --- |
| `docs/network.md` | Linux networking fundamentals |
| `docs/route.md` | Static routing |
| `docs/routing_protocol.md` | Routing protocol theory |
| `docs/udp_app_send_timing.md` | UDP timing theory |
| `docs/timestamped_packet_transmission.md` | Packet timestamping |
| `docs/network_latency_long_tail.md` | Tail latency analysis |
| `docs/network_impact_distributed_frameworks.md` | Network effects on distributed systems |
| `docs/topology_aware_distributed_framework.md` | Topology-aware scheduling |
| `docs/compute_constellation.md` | Compute constellation patterns |

## Development Guidelines

See `AGENTS.md` for:
- Project structure conventions
- Coding style (Bash with `set -Eeuo pipefail`)
- Testing and verification guidelines
- Commit message conventions

### Script Conventions

- Use `set -Eeuo pipefail` guard in all Bash scripts
- Two-space indentation
- Constants: uppercase with prefixes (`V12A`, `LAN_L_GW`)
- Functions: lowercase snake_case (`exists_ns`)
- Keep scripts beside their documentation

### Verification

```bash
bash -n experiments/01/ns.sh
shellcheck experiments/01/ns.sh
sudo bash experiments/01/ns.sh
# ... verify connectivity ...
sudo bash experiments/01/ns.sh down
```

## Contributing

1. Mirror existing code style and conventions
2. Document at least one round-trip test for new links/bridges
3. Include troubleshooting steps with relevant `ip`/`ping`/`tcpdump` output
4. Use short, verb-led commit subjects: `add leaf bridges`, `fix topology aware`
5. Reference issues and note regressions explicitly in PRs

## License

This is an educational repository for network and distributed systems labs.
