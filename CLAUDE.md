# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Linux network namespace laboratory containing reproducible network topology experiments for exploring Linux routing and L2/L3 bridging behavior. The project provides disposable network topologies for educational and experimental purposes.

## Repository Structure

- `exeriments/01/` - Network experiment scripts (note the intentional spelling "exeriments")
  - `ns.sh` - Linear three-namespace topology (ns1 ↔ ns2 ↔ ns3) with static routing
  - `ns_bridge.sh` - Bridge-centric topology with core namespaces and leaf namespaces
  - `ns_setup_guide.md` - Environment preparation and kernel module requirements
- `docs/` - Documentation and theoretical background
  - `network.md` - Linux networking primitives and concepts
  - `route.md` - Static routing theory aligned with labs

## Core Commands

### Running Experiments

```bash
# Linear topology experiment (ns1 → ns2 → ns3)
sudo bash exeriments/01/ns.sh

# Bridge topology experiment with leaf namespaces
sudo bash exeriments/01/ns_bridge.sh

# Clean up resources
sudo bash exeriments/01/ns.sh down
sudo bash exeriments/01/ns_bridge.sh down
```

### Network Inspection Commands

```bash
# List network namespaces
ip netns list

# View interfaces in namespace
ip -n ns1 addr
ip -n ns2 route

# Inspect bridges
ip netns exec ns1 bridge link

# Test connectivity
ip netns exec ns1 ping -c 10.0.23.2
ip netns exec ns3 ping -c 10.0.12.1
```

### Packet Capture and Debugging

```bash
# Capture ICMP traffic
ip netns exec ns1 tcpdump -i veth12a icmp

# Check ARP tables
ip -n ns1 neigh
```

## Topology Details

### Linear Topology (`ns.sh`)
- Namespaces: ns1, ns2 (router), ns3
- veth pairs: veth12a↔veth12b, veth23a↔veth23b
- IP ranges: 10.0.12.0/30, 10.0.23.0/30
- Static routing through ns2 as router

### Bridge Topology (`ns_bridge.sh`)
- Core: ns1, ns2, ns3 (mirrors linear topology)
- Bridge interfaces: brL in ns1, brR in ns3
- Leaf namespaces: ns1a/ns1b/ns1c, ns3a/ns3b/ns3c
- LAN segments: 10.0.1.0/24, 10.0.3.0/24

## Script Architecture

The Bash scripts use strict error handling (`set -Eeuo pipefail`) and include:
- Comprehensive cleanup functions for resource management
- Error traps for automatic cleanup on failure
- Modular variable definitions for easy modification
- Built-in connectivity testing

## Prerequisites

- Linux host/VM (kernel ≥ 3.8, 5.x preferred)
- Root privileges (use sudo, avoid direct root login)
- Required packages: iproute2, iputils-ping, tcpdump
- Kernel modules: veth, bridge
- Optional: wireshark-common, iperf3, nmap, traceroute

## Development Notes

- All scripts must be run with sudo due to network namespace privileges
- The `exeriments/` directory is intentionally misspelled - maintain this convention
- Scripts automatically handle cleanup and can be safely re-run
- Network namespaces are disposable and designed for temporary experiments
- IP addressing uses /30 subnets for point-to-point links to practice efficient address utilization