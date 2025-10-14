# Routing Protocols Lecture Note

## Overview
Routing protocols let routers exchange reachability information and build forwarding tables automatically. They fall into interior gateway protocols (IGPs) for intra-domain routing and exterior gateway protocols (EGPs) for inter-domain routing.

# Routing Protocols Detailed Explanation

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
sequenceDiagram
    participant R1 as Router 1
    participant R2 as Router 2
    participant R3 as Router 3

    R1->>R2: Sends full routing table (every 30s)
    R2->>R3: Propagates updated hop counts
    R3-->>R2: Updates local routing table
    Note over R1,R3: Each node stores next-hop and hop count
```

---

## 2. Open Shortest Path First (OSPF)

### Working Principle

OSPF is a **link-state** routing protocol. Each router floods **Link-State Advertisements (LSAs)** describing its interfaces and neighbors. Every router builds an identical **Link-State Database (LSDB)** and runs **Dijkstra's SPF algorithm** to compute shortest paths.

* **Hierarchy**: Backbone Area 0 and non-backbone areas connected via ABRs
* **Key Packets**: Hello, DBD, LSR, LSU, LSAck
* **Metric**: Cost (inversely proportional to bandwidth)
* **Advantages**: Fast convergence, VLSM support, authentication
* **Limitations**: Design complexity due to area planning

### Area Structure Diagram

```mermaid
graph TD
    subgraph Area0["Area 0 (Backbone)"]
        Rb1((Rb1)) --- Rb2((Rb2))
    end
    subgraph Area1
        Ra1((Ra1)) --- Ra2((Ra2)) --- Ra3((Ra3))
    end
    subgraph Area2
        Rc1((Rc1)) --- Rc2((Rc2)) --- Rc3((Rc3))
    end
    Rb1 --- Ra2
    Rb2 --- Rc2
    style Area0 fill:#eaf6ff,stroke:#4a90e2
```

### SPF Computation Flow

```mermaid
flowchart TD
    A[Collect LSAs] --> B[Build Topology Graph]
    B --> C[Run Dijkstra Algorithm]
    C --> D[Construct Shortest Path Tree]
    D --> E[Install Routes into RIB]
```

---

## 3. Enhanced Interior Gateway Routing Protocol (EIGRP)

### Working Principle

EIGRP, a Cisco proprietary **advanced distance-vector** protocol, combines features of distance-vector and link-state mechanisms. It uses the **Diffusing Update Algorithm (DUAL)** to guarantee loop-free and rapid convergence.

* **Metric**: Composite of bandwidth and delay (optionally load/reliability)
* **Algorithm**: DUAL maintains successor (primary) and feasible successor (backup) routes
* **Update Mechanism**: Partial updates on topology change
* **Advantages**: Fast convergence, efficient bandwidth use
* **Limitations**: Historically Cisco-only

### DUAL Mechanism

```mermaid
flowchart LR
    A[Successor Route] --> B[Feasible Successor]
    B --> C[Immediate failover upon failure]
    C --> D[Loop-free recalculation avoided]
```

---

## 4. Intermediate System to Intermediate System (IS-IS)

### Working Principle

IS-IS is a **link-state routing protocol** that operates at **Layer 2** of the OSI model. It uses **TLV (Type-Length-Value)** structures for extensibility and supports both IPv4 and IPv6 through Multi-Topology extensions.

* **Levels**: Level 1 (intra-area) and Level 2 (inter-area)
* **Encapsulation**: Runs directly over Layer 2 (no IP dependency)
* **Advantages**: High scalability, minimal reliance on IP
* **Limitations**: Smaller operator base, TLV complexity

### Hierarchical Topology

```mermaid
graph TD
    subgraph L2["Level-2 (Backbone)"]
        R4((R4)) --- R5((R5)) --- R6((R6))
    end
    subgraph L1A["Level-1 Area A"]
        R1((R1)) --- R2((R2))
    end
    subgraph L1B["Level-1 Area B"]
        R3((R3)) --- R7((R7))
    end
    R2 --- R4
    R3 --- R5
    style L2 fill:#f9f9e0,stroke:#d4b106
```

---

## 5. Border Gateway Protocol (BGP)

### Working Principle

BGP is a **path-vector** protocol designed for **inter-domain routing**. Instead of computing shortest paths, BGP uses **policy-based decisions** guided by **path attributes** such as AS_PATH, NEXT_HOP, LOCAL_PREF, MED, and COMMUNITY.

* **eBGP**: Between autonomous systems (ASes)
* **iBGP**: Within a single AS
* **Attributes**: Control routing preference and path selection
* **Advantages**: Highly scalable, flexible policy control
* **Limitations**: Slow convergence, complex policies

### Topology Diagram

```mermaid
flowchart LR
   subgraph ISP_A["AS 65010 (ISP-A)"]
   A1((A1)) --- A2((A2))
   end
   subgraph ENT["AS 65100 (Enterprise)"]
   E1((E1)) --- E2((E2))
   end
   subgraph ISP_B["AS 65020 (ISP-B)"]
   B1((B1)) --- B2((B2))
   end


   %% eBGP sessions to upstream ISPs
   E1 --> A1
   E2 --> B1


   %% iBGP session within enterprise AS
   E1 --- E2
```

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

## Further Study
Review RFC 1058 (RIP), RFC 2328 (OSPFv2), RFC 5308 (IS-IS IPv6), RFC 4271 (BGP), and Cisco’s EIGRP whitepaper. For lab practice, use Linux network namespaces, FRRouting, or virtual routers (e.g., Cisco CSR1000v) to observe adjacency formation, SPF runs, and convergence behavior firsthand.
