# Linux Network Namespace Labs

Reproducible Linux network-namespace labs for exploring static routing, bridges, and timing-sensitive UDP workflows. Lab scripts live beside their guides under `experiments/01/` (older docs may reference the intentionally misspelled `exeriments/01/`). Provisioning happens entirely with Bash and `iproute2`, so you can iterate on any modern Linux host.

## Prerequisites
- Linux kernel ≥ 3.8 (5.x 推荐) with `iproute2`, `iputils-ping`, `bridge-utils`, and `tcpdump`.
- Root access via `sudo`; always launch labs from the repository root.
- Optional tooling: `shellcheck`, `mermaid` preview, `gcc` + `libpcap-dev` for timing labs.
- Before a first run, walk through `experiments/01/ns_setup_guide.md` to confirm modules (`veth`, `bridge`) and sudo permissions.

## Repository Layout
| Path | Purpose |
| --- | --- |
| `experiments/01/ns.sh` | Five-namespace ring (ns1→ns2→ns3→ns4→ns5→ns1) with /30 links and static routes along the loop. |
| `experiments/01/ns_bridge.sh` | Bridge-centric core (ns1, ns2, ns3) with three leaf namespaces hanging off software bridges inside ns1/ns3. |
| `experiments/01/ns_setup_guide.md` | Environment preparation, module checks, troubleshooting checklist. |
| `experiments/02/` | Routing-protocol design notes (RIP/OSPF/ISIS/EIGRP/BGP) with namespace scaffolds and FRRouting examples. |
| `experiments/03/` | Minimal OSPF-like simulator skeleton (`main.py`, `ospf/`, CLI, sample topology) for students to finish. |
| `experiments/04/` | UDP transmission timing lab: namespace topologies, C helpers (`udp_txtime_replay.c`, `udp_rx_timestamp.c`), and guide. |
| `docs/` | Background reading: Linux networking fundamentals, static routing, routing protocols, UDP timing theory. |

## Running the Base Labs
Both scripts self-clean on startup and accept a `down` argument for teardown. Always lint first:

```bash
bash -n experiments/01/ns.sh
shellcheck experiments/01/ns.sh
```

### `experiments/01/ns.sh` — 五节点环形拓扑
Topology:
```
ns1 -- ns2 -- ns3 -- ns4 -- ns5
 \___________________________/
```

1. **Provision**
   ```bash
   sudo bash experiments/01/ns.sh
   ```
2. **Baseline inspection**
   ```bash
   ip netns list
   ip -n ns1 addr
   ip -n ns3 route
   ip netns exec ns4 sysctl net.ipv4.ip_forward
   ```
3. **Connectivity checks**（脚本已执行，可根据需要复测）
   ```bash
   ip netns exec ns1 ping -c1 10.0.23.2    # 顺时针
   ip netns exec ns4 ping -c1 10.0.12.2    # 逆时针
   ip netns exec ns2 ping -c1 10.0.45.2    # 最远节点
   ```
4. **Teardown**
   ```bash
   sudo bash experiments/01/ns.sh down
   ```

### `experiments/01/ns_bridge.sh` — 桥接+叶子拓扑
- ns1 与 ns3 各自创建软件桥 (`brL`, `brR`)。
- 叶子命名空间 (`ns1a/ns1b/ns1c`, `ns3a/ns3b/ns3c`) 通过 veth 上行口接入桥。
- ns2 作为中间三层节点，静态路由贯通两侧 LAN (`10.0.1.0/24` ↔ `10.0.3.0/24`)。

1. **Provision**
   ```bash
   sudo bash experiments/01/ns_bridge.sh
   ```
2. **Inspect bridges and leaves**
   ```bash
   ip netns exec ns1 bridge link
   ip netns exec ns3 bridge link
   ip -n ns1a addr; ip -n ns3b route
   ```
3. **Ping matrix（示例）**
   ```bash
   ip netns exec ns1a ping -c1 10.0.3.11
   ip netns exec ns3c ping -c1 10.0.12.1
   ```
4. **Teardown**
   ```bash
   sudo bash experiments/01/ns_bridge.sh down
   ```

## Validation & Troubleshooting
- Capture namespace state after provisioning for lab notes / PRs:
  ```bash
  ip netns list
  ip -n ns1 addr
  ip netns exec ns3 sysctl net.ipv4.ip_forward
  ```
- Use `ip netns exec <ns> tcpdump -i <if>` to trace ICMP/UDP flows; pair with `tools/capture.sh` in `experiments/03/tools/` when working on the OSPF simulator.
- 如果脚本失败，可直接重跑；脚本启动前会尝试清理同名资源。
- Manual cleanup command: `sudo bash <script> down`.

## Beyond the Base Labs
- `experiments/02/*.md` document full routing protocol labs with namespace scaffolds and FRRouting configs.
- `experiments/03/` hosts a Python framework for实现/调试 OSPF-like 协议，结合 `topo.sample.yaml` 与 CLI (`show neighbors`, `show lsdb` 等)。
- `experiments/04/udp_app_send_timing_lab.md` ties the bridge topology to precise UDP timing experiments (`SO_TXTIME`, ETF qdisc, timestamp collection) and references `docs/udp_app_send_timing.md`.

## Contributing Tips
- Mirror the `set -Eeuo pipefail` guard and two-space indentation in new Bash scripts.
- Keep runnable artifacts next to their documentation (scripts under `experiments/<lab>/`, notes in the same directory).
- Document至少一次往返测试 for every new link or bridge you add; record troubleshooting steps and relevant `ip`/`ping` output for reviewers.
- Commit subjects use short, verb-led lowercase phrases (`add leaf bridges`, `clean up`).
