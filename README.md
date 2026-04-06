# Network & Distributed Systems Lab

A comprehensive collection of Linux network namespace labs for exploring networking fundamentals, routing protocols, and distributed systems concepts. All labs use Bash + `iproute2` for reproducible experiments on any modern Linux host.

## Prerequisites

- Linux kernel >= 3.8 (5.x recommended) with `iproute2`, `iputils-ping`, `bridge-utils`, and `tcpdump`
- Root access via `sudo`; always launch labs from the repository root
- Optional: `shellcheck`, `iperf3`, `gcc` + `libpcap-dev`, `python3`

See `2025/experiments/01/ns_setup_guide.md` for environment setup and module checks (`veth`, `bridge`).

## Repository Structure

| Path | Purpose |
| --- | --- |
| `2025/experiments/01/` | Base labs: static routing, bridges, network namespaces |
| `2025/experiments/02/` | Routing protocol design notes (RIP/OSPF/ISIS/EIGRP/BGP) |
| `2025/experiments/03/` | OSPF-like simulator framework (Python implementation skeleton) |
| `2025/experiments/04/` | UDP transmission timing lab with C helpers |
| `2025/experiments/05/` | Network tail latency analysis |
| `2025/experiments/06/` | Barrier synchronization simulation |
| `2025/experiments/07/` | Network impact on distributed frameworks |
| `2025/experiments/08/` | Topology-aware scheduling simulation |
| `2025/docs/` | Background reading on networking, routing, timing, and distributed systems |

## Quick Start

### Base Network Namespace Lab

Five-namespace ring topology (ns1 -> ns2 -> ns3 -> ns4 -> ns5 -> ns1):

```bash
sudo bash 2025/experiments/01/ns.sh
ip netns list
ip netns exec ns1 ping -c1 10.0.23.2
sudo bash 2025/experiments/01/ns.sh down
```

### Bridge Lab

Bridge-centric topology with leaf namespaces:

```bash
sudo bash 2025/experiments/01/ns_bridge.sh
ip netns exec ns1a ping -c1 10.0.3.11
sudo bash 2025/experiments/01/ns_bridge.sh down
```

## Lab Guide

### Lab 1: Network Namespace Basics (`2025/experiments/01/`)

- **ns.sh**: Five-node ring with static routes
- **ns_bridge.sh**: Software bridges with leaf namespaces
- **ns_setup_guide.md**: Setup, troubleshooting, and verification

### Lab 2: Routing Protocols (`2025/experiments/02/`)

Design notes and scaffolds for:
- RIP (Routing Information Protocol)
- OSPF (Open Shortest Path First)
- IS-IS (Intermediate System to Intermediate System)
- EIGRP (Enhanced Interior Gateway Routing Protocol)
- BGP (Border Gateway Protocol)

### Lab 3: OSPF Simulator (`2025/experiments/03/`)

Minimal OSPF-like framework for students to implement:
- Neighbor discovery and adjacency
- LSA flooding
- Link State Database
- SPF calculation (Dijkstra)

```bash
sudo bash 2025/experiments/01/ns.sh
sudo ip netns exec r1 python3 2025/experiments/03/main.py --router 1.1.1.1 --config 2025/experiments/03/topo.sample.yaml
```

### Lab 4: UDP Timing (`2025/experiments/04/`)

Precise UDP transmission timing experiments using:
- `SO_TXTIME` with ETF qdisc
- Hardware timestamping
- C helpers for timestamp collection

### Lab 5: Tail Latency (`2025/experiments/05/`)

Inject and measure network tail latency using `tc netem`:

```bash
sudo bash 2025/experiments/01/ns.sh
ip netns exec ns2 tc qdisc add dev veth23a root netem delay 5ms 2ms 25%
# Analyze with iperf3, ping, tcpdump
```

### Lab 6: Barrier Simulation (`2025/experiments/06/`)

Python simulator for studying barrier synchronization patterns in distributed systems.

### Lab 7: Network Impact on Distributed Frameworks (`2025/experiments/07/`)

Simulate how network conditions affect:
- Shuffle operations
- Parameter Server push/pull
- Ring AllReduce

```bash
sudo bash 2025/experiments/07/ns_framework_topo.sh
python3 2025/experiments/07/framework_network_sim.py shuffle --workers 12 --latency-ms 5 --bandwidth-gbps 1
```

### Lab 8: Topology-Aware Scheduling (`2025/experiments/08/`)

Compare scheduling strategies:
- `random`: Network-oblivious placement
- `rack_local`: Rack affinity
- `score`: Network cost model-based scheduling

```bash
sudo bash 2025/experiments/08/ns_topology_aware.sh
python3 2025/experiments/08/topology_aware_scheduler_sim.py init --outdir 2025/experiments/08/examples
bash 2025/experiments/08/run_topology_aware_lab.sh
```

## Background Reading

| Document | Topics |
| --- | --- |
| `2025/docs/network.md` | Linux networking fundamentals |
| `2025/docs/route.md` | Static routing |
| `2025/docs/routing_protocol.md` | Routing protocol theory |
| `2025/docs/udp_app_send_timing.md` | UDP timing theory |
| `2025/docs/timestamped_packet_transmission.md` | Packet timestamping |
| `2025/docs/network_latency_long_tail.md` | Tail latency analysis |
| `2025/docs/network_impact_distributed_frameworks.md` | Network effects on distributed systems |
| `2025/docs/topology_aware_distributed_framework.md` | Topology-aware scheduling |
| `2025/docs/compute_constellation.md` | Compute constellation patterns |

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
bash -n 2025/experiments/01/ns.sh
shellcheck 2025/experiments/01/ns.sh
sudo bash 2025/experiments/01/ns.sh
# ... verify connectivity ...
sudo bash 2025/experiments/01/ns.sh down
```

## Contributing

1. Mirror existing code style and conventions
2. Document at least one round-trip test for new links/bridges
3. Include troubleshooting steps with relevant `ip`/`ping`/`tcpdump` output
4. Use short, verb-led commit subjects: `add leaf bridges`, `fix topology aware`
5. Reference issues and note regressions explicitly in PRs

## License

This is an educational repository for network and distributed systems labs.
