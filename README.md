# Linux Network Namespace Labs

This repository collects repeatable network-namespace mini-labs for exploring Linux routing and L2/L3 bridging behavior. Each lab is packaged as a Bash script that provisions a disposable topology under `exeriments/01/` (note the intentional spelling).

## Repository Layout

| Path | Purpose |
| --- | --- |
| `exeriments/01/ns.sh` | Three-namespace linear topology (`ns1` ↔ `ns2` ↔ `ns3`) showcasing static routing through a middle router namespace. |
| `exeriments/01/ns_bridge.sh` | Bridge-centric lab with core namespaces (`ns1`, `ns2`, `ns3`) and six leaf namespaces hanging off software bridges. |
| `exeriments/01/ns_setup_guide.md` | Environment preparation checklist (kernel modules, packages, permissions). |
| `docs/network.md` | Background notes on Linux networking primitives. |
| `docs/route.md` | Static routing theory walkthrough tied to the labs. |

## Prerequisites

- Linux host or VM (kernel ≥ 3.8 recommended; 5.x preferred).
- Root privileges (run commands with `sudo`, avoid logging in as root).
- `iproute2`, `iputils-ping`, `tcpdump`; optional extras listed in `ns_setup_guide.md`.

Before running a lab, skim `exeriments/01/ns_setup_guide.md` to verify kernel modules (`veth`, `bridge`) and namespace support.

## Lab 1: Linear Topology (`ns.sh`)

Topology: `ns1` — `ns2` — `ns3`, with /30 links and static routes installed so the edge namespaces talk through `ns2`.

1. Provision
	```bash
	sudo bash exeriments/01/ns.sh
	```
2. Inspect
	```bash
	ip netns list
	ip -n ns1 addr
	ip -n ns2 route
	```
3. Sanity pings (script already attempts these; rerun as needed)
	```bash
	ip netns exec ns1 ping -c1 10.0.23.2
	ip netns exec ns3 ping -c1 10.0.12.1
	```
4. Cleanup
	```bash
	sudo bash exeriments/01/ns.sh down
	```

## Lab 2: Bridge Topology (`ns_bridge.sh`)

Core namespaces mirror Lab 1, but `ns1` and `ns3` each host a software bridge with three leaf namespaces. Static routing and per-namespace IP forwarding allow any leaf to reach the opposite side.

1. Provision
	```bash
	sudo bash exeriments/01/ns_bridge.sh
	```
2. Inspect bridges and leaves
	```bash
	ip netns exec ns1 bridge link
	ip netns exec ns3 bridge link
	ip netns exec ns1a ping -c1 10.0.3.11
	```
3. Cleanup
	```bash
	sudo bash exeriments/01/ns_bridge.sh down
	```

## Troubleshooting Tips

- Always start from the repo root so relative paths resolve.
- If a run fails midway, re-run the script; it self-cleans before provisioning.
- Use `ip netns exec <ns> tcpdump -i <if>` to trace ICMP flows.
- For persistent issues, run the environment checklist script in `ns_setup_guide.md`.

## Further Reading

- `docs/route.md` — detailed routing primer aligned with the linear topology.
- `docs/network.md` — supplementary notes on Linux networking tools and concepts.

When sharing experiment results, capture relevant `ip` outputs after provisioning and note any deviations from the baseline topology.*** End Patch