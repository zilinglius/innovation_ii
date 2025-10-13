# Routing Protocols Lecture Note

## Overview
Routing protocols let routers exchange reachability information and build forwarding tables automatically. They fall into interior gateway protocols (IGPs) for intra-domain routing and exterior gateway protocols (EGPs) for inter-domain routing.

## Routing Information Protocol (RIP)
- **Type**: Distance-vector IGP using hop-count (maximum 15).
- **Operation**: Periodic full-table updates every 30 seconds; split horizon, poison reverse, and holddown timers mitigate loops.
- **Pros**: Simple configuration, low resource requirements.
- **Cons**: Slow convergence, poor scalability, limited metric granularity.
- **Typical Use**: Small, flat topologies or lab demonstrations.

## Open Shortest Path First (OSPF)
- **Type**: Link-state IGP running Dijkstra’s SPF algorithm.
- **Hierarchy**: Areas (backbone Area 0 plus non-backbone areas) reduce flooding scope; ABRs summarize routes between areas.
- **Packet Types**: Hello for neighbor discovery; DBD, LSR, and LSU for LSA exchange.
- **Metric**: Cost based on interface bandwidth, allowing fine-grained tuning.
- **Pros**: Fast convergence, supports VLSM, authentication, and route tagging.
- **Cons**: More complex design, requires careful area and LSA planning.
- **Typical Use**: Enterprise networks and service-provider cores.

## Enhanced Interior Gateway Routing Protocol (EIGRP)
- **Type**: Cisco-originated advanced distance-vector protocol.
- **Metric**: Composite of bandwidth and delay by default (load and reliability optional).
- **Algorithm**: Diffusing Update Algorithm (DUAL) keeps loop-free successors and feasible successors for quick failover.
- **Pros**: Rapid convergence, reduced bandwidth consumption via partial updates.
- **Cons**: Historically vendor-specific, limited multi-vendor support.
- **Typical Use**: Cisco-centric environments that need fast convergence.

## Intermediate System to Intermediate System (IS-IS)
- **Type**: Link-state IGP operating directly over Layer 2.
- **Hierarchy**: Level 1 (intra-area) and Level 2 (inter-area) routing; wide metrics support large-scale design.
- **Extensions**: Multi-Topology IS-IS, IPv6 support via TLVs.
- **Pros**: Scales well, minimal reliance on IP before adjacency.
- **Cons**: Smaller talent pool, TLV-based configuration can feel opaque.
- **Typical Use**: Large service-provider backbones and MPLS cores.

## Border Gateway Protocol (BGP)
- **Type**: Path-vector EGP controlling inter-domain routing.
- **Key Concepts**: Attributes such as AS_PATH, NEXT_HOP, LOCAL_PREF, MED, and COMMUNITIES drive policy; eBGP (between ASes) and iBGP (within an AS).
- **Convergence**: Event-driven updates; route reflectors or confederations prevent full-mesh requirements.
- **Pros**: Policy-rich, scales to internet-sized tables.
- **Cons**: Complex policy design, slower convergence, vulnerable to route hijacks without safeguards.
- **Typical Use**: ISP peering and large enterprises with multi-homing.

## Illustrative Topologies
- **RIP Starter Lab**
  ```text
  10.0.1.0/24          10.0.2.0/24          10.0.3.0/24
      |                    |                    |
     R1 ------------------ R2 ------------------ R3
               (hop count propagates end-to-end)
  ```
- **OSPF Two-Area Design**
  ```text
        Area 0 (Backbone)
     Rb1 ----------- Rb2
      | \             / |
      |  \           /  |
      |   \         /   |
  Area 1   \       /   Area 2
   Ra1--Ra2--Ra3  Rc1--Rc2--Rc3
  (ABRs: Rb1, Rb2 summarizing intra-area routes)
  ```
- **BGP Dual-Homing Scenario**
  ```text
                AS 65010 (ISP-A)
                 /           \
          eBGP  /             \  eBGP
              R1 --- iBGP --- R2
                 \           /
                AS 65020 (ISP-B)
  (Enterprise AS 65100 chooses exit via LOCAL_PREF and MED)
  ```

## Comparative Notes
IGPs aim for fast convergence inside an administrative domain, optimize for speed and resource usage, and coexist with BGP for edge policy control. BGP emphasizes policy enforcement and scalability across domains. Choose protocols according to network size, vendor mix, and operational requirements—often combining an IGP (OSPF, IS-IS, or EIGRP) with BGP at the edges.

## Lab Exercises
1. **Namespace RIP Lab**
   - Provision three namespaces (`ns1`, `ns2`, `ns3`) in a line using `ip netns` and connect them with /24 veth pairs mirroring the RIP starter topology.
   - Install FRRouting or `bird` (if available) inside each namespace; configure `router rip`, set `network 10.0.x.0/24`, and enable `redistribute connected`.
   - Verify convergence with `ip netns exec ns1 vtysh -c "show ip rip"` and ensure hop counts remain within limits.
2. **OSPF Area Boundary Exercise**
   - Reuse the `exeriments/01/ns_bridge.sh` pattern to create two core namespaces acting as ABRs (`ns-backbone-1`, `ns-backbone-2`) and four leaf namespaces split into Area 1 and Area 2.
   - Run FRR OSPFv2 inside each namespace; place backbone interfaces in Area 0 and leaf interfaces in their respective areas.
   - Capture `show ip ospf interface` and `show ip ospf database` outputs to confirm LSAs stay within their areas and summarize routes on ABRs.
3. **BGP Policy Lab**
   - Spin up four namespaces to emulate an enterprise AS with two upstream providers; configure loopback addresses as router IDs.
   - Establish eBGP sessions between the enterprise edge nodes and each provider, then use `LOCAL_PREF` and `MED` adjustments to steer traffic.
   - Validate policy by tracing routes (`show ip bgp`) and testing reachability with `ip netns exec <ns> traceroute`.

## Further Study
Review RFC 1058 (RIP), RFC 2328 (OSPFv2), RFC 5308 (IS-IS IPv6), RFC 4271 (BGP), and Cisco’s EIGRP whitepaper. For lab practice, use Linux network namespaces, FRRouting, or virtual routers (e.g., Cisco CSR1000v) to observe adjacency formation, SPF runs, and convergence behavior firsthand.
