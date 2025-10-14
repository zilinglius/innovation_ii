# Routing Protocols Detailed Explanation

## Overview
Routing protocols let routers exchange reachability information and build forwarding tables automatically. They fall into interior gateway protocols (IGPs) for intra-domain routing and exterior gateway protocols (EGPs) for inter-domain routing.

## 1. Routing Information Protocol (RIP)

### Working Principle

RIP is a **distance-vector** routing protocol that relies on hop count as its sole metric (maximum 15 hops). Each router periodically (every 30 seconds) broadcasts its entire routing table to its neighbors. RIP prevents routing loops using techniques such as **split horizon**, **poison reverse**, and **holddown timers**.

* **Metric**: Hop count (max 15)
* **Update Mechanism**: Periodic full-table broadcast every 30 seconds
* **Loop Prevention**: Split horizon, poison reverse, holddown
* **Advantages**: Simple and lightweight
* **Limitations**: Slow convergence and poor scalability

### Flow Diagram

```mermaid
flowchart LR
  subgraph LAN1[10.0.1.0/24]
    H1((Host A))
  end
  subgraph LAN2[10.0.2.0/24]
    H2((Host B))
  end
  subgraph LAN3[10.0.3.0/24]
    H3((Host C))
  end

  R1[[R1]] --- LAN1
  R2[[R2]] --- LAN2
  R3[[R3]] --- LAN3

  R1 --- R2
  R2 --- R3

  %% Distance vectors as simple labels
  %% (GitHub-safe: use text nodes instead of edge labels)
  DV1[(R1 tells R2: C=2 hops)]
  DV2[(R2 tells R3: A=2 hops)]

  R1 --> DV1 --> R2
  R2 --> DV2 --> R3

  %% Poison reverse illustration
  PR[(Poison Reverse: R2 says A=∞ back to R1)]
  R2 --> PR --> R1
```

**Figure Notes (RIP):**

* Example distances: R1 learns *C* via R2 in **2 hops**; R3 learns *A* via R2 in **2 hops**.
* When a route fails, R2 advertises **∞ (16)** back to the source (poison reverse) to break loops.
* Periodic updates occur every **30s**; holddown timer delays acceptance of worse metrics to stabilize.

---

## 2. Open Shortest Path First (OSPF)

### Working Principle

OSPF is a **link-state** routing protocol. Each router floods **Link-State Advertisements (LSAs)** describing its interfaces and neighbors. Every router builds an identical **Link-State Database (LSDB)** and runs **Dijkstra's SPF algorithm** to compute shortest paths.

* **Hierarchy**: Backbone Area 0 and non-backbone areas connected via ABRs
* **Key Packets**: Hello, DBD, LSR, LSU, LSAck
* **Metric**: Cost (inversely proportional to bandwidth)
* **Advantages**: Fast convergence, VLSM support, authentication
* **Limitations**: Design complexity due to area planning

### Area & Role Diagram

```mermaid
flowchart TB
  subgraph A0[Area 0 (Backbone)]
    Rb1[[ABR Rb1]] --- Rb2[[ABR Rb2]]
    DR((DR)):::role
    BDR((BDR)):::role
    Rb1 --- DR
    Rb1 --- BDR
    Rb2 --- DR
    Rb2 --- BDR
  end

  subgraph A1[Area 1]
    Ra1[[Ra1]] --- Ra2[[Ra2]] --- Ra3[[Ra3]]
  end

  subgraph A2[Area 2]
    Rc1[[Rc1]] --- Rc2[[Rc2]] --- Rc3[[Rc3]]
  end

  Rb1 --- Ra2
  Rb2 --- Rc2

  classDef role fill:#fff3cd,stroke:#d39e00;
```

### LSA & Neighbor Exchange (Simplified)

```mermaid
sequenceDiagram
  participant N1 as Router A
  participant N2 as Router B
  N1->>N2: Hello (discover & form adjacency)
  N2-->>N1: Hello (bidirectional seen)
  N1->>N2: DBD (database summary)
  N2->>N1: LSR (request missing LSAs)
  N1->>N2: LSU (send requested LSAs)
  N2->>N1: LSAck (acknowledge)
```

**Figure Notes (OSPF):**

* **DR/BDR** elected on multi-access networks to reduce LSA flooding; routers form adjacencies primarily with DR/BDR.
* **ABRs (Rb1/Rb2)** hold multiple LSDBs (one per area) and **summarize** routes between areas.
* After LSDBs converge, each router runs **SPF** to compute shortest paths.

### SPF Computation Flow

```mermaid
flowchart TD
  A[Collect LSAs] --> B[Build Topology Graph]
  B --> C[Run Dijkstra Algorithm]
  C --> D[Construct Shortest Path Tree]
  D --> E[Install Routes into RIB]
```

**Figure Notes (SPF):**

* Triggered by LSA changes with throttling/timers to avoid excessive recomputation.
* Costs are additive along a path; lowest total cost wins.
* Equal-cost paths can be installed to enable **ECMP**.

---

## 3. Enhanced Interior Gateway Routing Protocol (EIGRP)

### Working Principle

EIGRP, a Cisco proprietary **advanced distance-vector** protocol, combines features of distance-vector and link-state mechanisms. It uses the **Diffusing Update Algorithm (DUAL)** to guarantee loop-free and rapid convergence.

* **Metric**: Composite of bandwidth and delay (optionally load/reliability)
* **Algorithm**: DUAL maintains successor (primary) and feasible successor (backup) routes
* **Update Mechanism**: Partial updates on topology change
* **Advantages**: Fast convergence, efficient bandwidth use
* **Limitations**: Historically Cisco-only

### DUAL Mechanism with Feasibility Condition

```mermaid
flowchart LR
  subgraph Net[Example Network]
    A[[A]] -- 100Mbps/1ms --> B[[B]]
    B -- 100Mbps/2ms --> D[[D]]
    A -- 10Mbps/10ms --> C[[C]]
    C -- 100Mbps/2ms --> D
  end

  note1[(Successor at A to D: A→B→D, FD=3ms)]
  note2[(Feasible Successor at A: A→C→D if AD(C)<FD)]

  A --> note1
  A --> note2
```

**Figure Notes (EIGRP):**

* **Feasibility Condition**: A neighbor's **advertised distance (AD)** to a destination must be **<** the local **feasible distance (FD)** of the current successor to be a valid **feasible successor**.
* When the successor fails, traffic switches to the feasible successor **without a diffusing query**, ensuring fast convergence.
* If no feasible successor exists, DUAL enters **active** state and diffuses queries to find a new path.

---

## 4. Intermediate System to Intermediate System (IS-IS)

### Working Principle

IS-IS is a **link-state routing protocol** that operates at **Layer 2** of the OSI model. It uses **TLV (Type-Length-Value)** structures for extensibility and supports both IPv4 and IPv6 through Multi-Topology extensions.

* **Levels**: Level 1 (intra-area) and Level 2 (inter-area)
* **Encapsulation**: Runs directly over Layer 2 (no IP dependency)
* **Advantages**: High scalability, minimal reliance on IP
* **Limitations**: Smaller operator base, TLV complexity

### Hierarchical Topology & LSP Flooding

```mermaid
flowchart TB
  subgraph L2[Level-2 Backbone]
    R4[[R4]] --- R5[[R5]] --- R6[[R6]]
  end
  subgraph L1A[Level-1 Area A]
    R1[[R1]] --- R2[[R2]]
  end
  subgraph L1B[Level-1 Area B]
    R3[[R3]] --- R7[[R7]]
  end

  R2 --- R4
  R3 --- R5

  LSP1[(L1 LSP Flooding within Area A)]
  LSP2[(L2 LSP Flooding across Backbone)]

  R1 --> LSP1 --> R2
  R4 --> LSP2 --> R5
```

**Figure Notes (IS-IS):**

* **Level-1** routers know only intra-area routes; **Level-2** routers provide inter-area connectivity.
* IS-IS uses **LSPs**, **CSNP/PSNP** for database synchronization; extensible **TLVs** carry IPv4/IPv6 reachability.
* Running at Layer 2 avoids dependency on IP to bring up adjacencies.

---

## 5. Border Gateway Protocol (BGP)

### Working Principle

BGP is a **path-vector** protocol designed for **inter-domain routing**. Instead of computing shortest paths, BGP uses **policy-based decisions** guided by **path attributes** such as AS_PATH, NEXT_HOP, LOCAL_PREF, MED, and COMMUNITY.

* **eBGP**: Between autonomous systems (ASes)
* **iBGP**: Within a single AS
* **Attributes**: Control routing preference and path selection
* **Advantages**: Highly scalable, flexible policy control
* **Limitations**: Slow convergence, complex policies

### Topology & Attribute Flow

```mermaid
flowchart LR
  subgraph ISP_A[AS65010 (ISP-A)]
    A1[[A1]]
  end
  subgraph ENT[AS65100 (Enterprise)]
    E1[[E1]] --- E2[[E2]]
  end
  subgraph ISP_B[AS65020 (ISP-B)]
    B1[[B1]]
  end

  %% eBGP
  E1 --> A1
  E2 --> B1

  %% iBGP
  E1 --- E2

  %% Attribute annotations as standalone nodes (GitHub-safe)
  ATTR1[(Path via ISP-A: AS_PATH "65010", LOCAL_PREF=200)]
  ATTR2[(Path via ISP-B: AS_PATH "65020", LOCAL_PREF=100, MED=50)]

  A1 --> ATTR1 --> E1
  B1 --> ATTR2 --> E2
```

**Figure Notes (BGP):**

* Enterprise prefers **ISP-A** due to higher **LOCAL_PREF=200**; **AS_PATH** also influences selection (shorter preferred).
* **MED** from ISP-B suggests inbound preference to its path for specific prefixes.
* Within the enterprise, **iBGP** propagates chosen paths; in larger deployments use **route reflectors** to avoid full meshes.

**Legend:**

* `E1 → A1`, `E2 → B1`: eBGP sessions to upstream ISPs.
* `E1 — E2`: iBGP session within the enterprise AS (route reflection not shown).

---

## 6. Comparative Summary

| Protocol | Type                     | Metric            | Convergence | Hierarchy | Typical Use            |
| -------- | ------------------------ | ----------------- | ----------- | --------- | ---------------------- |
| RIP      | Distance Vector          | Hop count         | Slow        | No        | Small networks         |
| OSPF     | Link State               | Cost (bandwidth)  | Fast        | Yes       | Enterprise & ISP cores |
| EIGRP    | Advanced Distance Vector | Bandwidth + Delay | Fast        | Partial   | Cisco networks         |
| IS-IS    | Link State               | Wide metric       | Fast        | Yes       | Provider backbones     |
| BGP      | Path Vector              | Policy attributes | Slow        | AS-level  | Inter-domain routing   |

---

## 7. Lab Applications

1. **Namespace RIP Lab**: Create three namespaces linked linearly and run RIP within FRRouting.
2. **OSPF Area Boundary Exercise**: Two ABRs connecting two non-backbone areas to Area 0.
3. **BGP Policy Lab**: Simulate dual-homed enterprise network and tune route selection with LOCAL_PREF and MED.

---

## 8. References

* RFC 1058 (RIP)
* RFC 2328 (OSPFv2)
* RFC 5308 (IS-IS IPv6)
* RFC 4271 (BGP)
* Cisco EIGRP Whitepaper
