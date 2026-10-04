# Lab 2　让网络自己找路

> 对应第 03、04 讲　｜　建议用时 2 周　｜　产出：一个会写内核路由表的路由守护进程，此后的实验床不再需要手工配置任何一条路由

第 03 讲在三台路由器连成的三角形上看过 FRR 的 OSPF 怎样发现邻居、同步地图、算出路由、写进内核，并留下了三个数字：拔线 **0 丢包**、静默故障 **34.6 秒**、cost 改动后两条路**分流**。本实验在**同一张实验床**上，用 Python 写一个简化的链路状态路由守护进程——叫它 `lsrd`——把这三个数字自己做出来，再解释它们为什么和 FRR 的不一样。

任务分三层：**基础**人人完成，**进阶**拉开区分度，**挑战**为后面的实验和综合项目铺路。第 04 讲课上会带着你写 Hello 那一部分；从 LSA 泛洪起，都是课后自己的产出。

---

## 一、实验目标

1. 按一页纸的协议规范实现邻居发现、LSA 泛洪与 Dijkstra，把算出的路由用 `ip route` 写进内核，让 Lab 1 的实验床在没有任何一条手工路由的情况下跑起来。
2. 量化收敛：断链时测一条在传数据流的中断时长，把它拆成检测、泛洪、计算、安装四段，解释与第 03 讲 FRR 三个数字的差距。
3. 闭合 Lab 1 任务 3 留下的账：新增一个机架，别的设备要改几处配置。
4. 亲手看见“地图不一致”“router id 冲突”“RIB 与 FIB 两本账”这些只有控制平面才有的故障长什么样，并能定位它们。
5. 看清一个没有认证的路由协议有多脆弱，以及规范里的一条规则（R6）能挡住什么、挡不住什么。

---

## 二、预备知识与工具

**先读**：

- 第 03 讲　3.2–3.5 节（Hello、LSA、可靠泛洪、Dijkstra）、3.7 节（收敛时间由什么决定）、5.1–5.3 节（RIB 与 FIB、管理距离、ECMP）、6.8–6.10 节（三个参照数字是怎么测出来的）
- 第 04 讲　骨架导读与 Hello 的实现
- Lab 1　你的实验床脚本还在，本实验直接复用它

**环境**：Lab 1 的环境（Linux、`sudo`、`iproute2`、`tcpdump`、`traceroute`）加上 Python 3.10 以上与 `uv`，以及 `iptables`（Ubuntu 自带）。**本实验不需要 `netem`**——链路故障用 `ip link set … down`，静默故障与丢包用 `iptables`。

**工具检查**：

```bash
# 1. uv 按官方说明安装（curl -LsSf https://astral.sh/uv/install.sh | sh），其余通常已有
which ip tcpdump iptables python3 uv
```

```bash
# 2. 准备 Python 环境。守护进程只用标准库，uv sync 只是建一个 .venv，几秒钟
(cd 2026/experiments/02 && uv sync)
```

```
Using CPython 3.12.3 interpreter at: /usr/bin/python3.12
Creating virtual environment at: .venv
Resolved 1 package in 2ms
Audited in 0.00ms
```

**约定**：以下所有命令**从仓库根目录执行**，需要 root 的步骤显式写了 `sudo`。守护进程要在 network namespace 里以 root 运行，`run.sh` 已经把 `sudo ip netns exec rN .venv/bin/python -m lsrd …` 这串包好了。

---

## 三、目录与资源

### 3.1 文件

| 文件 | 说明 |
| :--- | :--- |
| `topo.sh` | 实验床：Lab 1 的两机架 + 中转路由器 r3 − 静态路由。`up`（默认）/ `up rack3` / `rack3`（给跑着的实验床加机架 3）/ `down` / `check` / `show`。幂等。 |
| `run.sh` | 在每台路由器的 namespace 里启停守护进程：`start [选项]` / `stop` / `restart rN [选项]` / `status` / `show rN neighbors\|lsdb\|routes\|stats\|digest` / `logs rN` / `poke rN` / `check`。 |
| `lsrd/` | 守护进程。给定的部分与要你写的部分见 3.4 节。 |
| `tests/` | 离线单元测试（不需要 root、不需要实验床）：`uv run python -m unittest`。 |
| `probe.py` | 单向 UDP 探针：量“一条在传的数据流被打断了多久”。 |
| `break_lsr.sh` | 挑战任务用的控制平面故障注入：`break` / `reveal` / `fix`。 |
| `forge_lsa.py` | 挑战任务用：向某台路由器发一条伪造的 LSA。 |
| `pyproject.toml`、`.python-version`、`uv.lock` | `uv` 项目文件。没有第三方依赖。 |
| `README.md` | 本文件。 |

### 3.2 实验床

与第 03 讲 6.1 节完全相同：Lab 1 的两机架实验床加一台**只做中转、不带机架**的路由器 r3，三台路由器连成三角形——有了第二条路，路由协议才有“绕行”可绕。

```
  h1a 10.0.1.11 ─┐                                            ┌─ 10.0.2.11 h2a
                 ├─ br1 ─ r1 ───── 10.0.12.0/30 ───── r2 ─ br2 ┤
  h1b 10.0.1.12 ─┘   10.0.1.1  .1 \                 / .2  10.0.2.1 └─ 10.0.2.12 h2b
                                   \               /
                        10.0.13.0/30 \           / 10.0.23.0/30
                              r1=.1   \         /   r2=.1
                              r3=.2    \       /    r3=.2
                                        \     /
                                          r3          （进阶任务里会给它挂上机架 3：10.0.3.0/24）
```

| 对象 | 网段 | 说明 |
| :--- | :--- | :--- |
| 机架 1 / 机架 2 | `10.0.1.0/24` / `10.0.2.0/24` | 与 Lab 1 相同，网关在 `br1` / `br2` 上 |
| r1 ↔ r2 | `10.0.12.0/30` | r1 = `.1`（`r1-r2`），r2 = `.2`（`r2-r1`） |
| r1 ↔ r3 | `10.0.13.0/30` | r1 = `.1`（`r1-r3`），r3 = `.2`（`r3-r1`） |
| r2 ↔ r3 | `10.0.23.0/30` | r2 = `.1`（`r2-r3`），r3 = `.2`（`r3-r2`） |
| 机架 3（进阶） | `10.0.3.0/24` | 网关 `10.0.3.1` 在 `br3` 上，`h3a` = `.11`，`h3b` = `.12` |

`topo.sh` 做的事就是调用 Lab 1 的 `ns_topo.sh`，补上 r3 与两条链路，然后**删掉 Lab 1 写的那两条静态路由**。为什么必须删：内核只看 metric，静态路由的 metric 是 0，会压住守护进程写的 metric 20，你会以为自己的代码不工作（第 03 讲 5.2 节）。主机不变，默认路由仍指向机架网关；守护进程只跑在 r1、r2、r3。

### 3.3 协议规范：LSR-lite v1

原则：**看得见、能手推、能互操作**。报文是 JSON，`tcpdump -A` 直接能读；规则少到能在纸上推演；两个同学各自实现的守护进程应当能互相建邻。

**传输**

- UDP，端口 **5200**。
- 每个**活动接口**（有 IPv4 地址、不是 passive、`LOWER_UP`）一个套接字，用 `SO_BINDTODEVICE` 绑在接口上：收到的包一定来自这个接口，发出的包一定从这个接口出去。
- Hello 发往 `255.255.255.255`（限制广播）；LSU 与 Ack **单播**给邻居——邻居的地址就是它 Hello 的源地址。
- 报文体是 UTF-8 编码的 JSON 对象，公共字段 `"v": 1`、`"type"`、`"rid"`（router id，小整数）。

**三种报文**

```
hello   {"v":1,"type":"hello","rid":1,"hello":2,"dead":8,"seen":[2,3]}
        seen：本接口上、dead 秒内收到过其 Hello 的 router id 列表

lsu     {"v":1,"type":"lsu","rid":1,"lsas":[ <LSA>, ... ]}
LSA     {"rid":1,"seq":5,
         "links":    [{"nbr":2,"cost":10},{"nbr":3,"cost":10}],
         "prefixes": [{"p":"10.0.1.0/24","cost":10},{"p":"10.0.12.0/30","cost":10},{"p":"10.0.13.0/30","cost":10}]}
        links 只列 Full 邻居；prefixes 列所有 LOWER_UP 接口（含 passive）所在的网段

ack     {"v":1,"type":"ack","rid":1,"acks":[{"rid":2,"seq":5}]}       进阶任务 T9 才用到
```

只有 Router-LSA 一种 LSA；没有 DBD / LSR；没有 age。

**规则**（实现按编号来，验收也按编号查）

| 编号 | 规则 |
| :--- | :--- |
| R1 | 每 `hello` 秒在每个活动接口广播一次 Hello。 |
| R2 | 邻居状态：收到对方的 Hello → **Init**；对方的 `seen` 里有我 → **Full**；`dead` 秒没收到 → **Down**，删除。`hello` / `dead` 与本端不一致的 Hello 直接丢弃。邻居是接口级的：键是 (rid, 接口)。 |
| R3 | 邻居进入 Full 时，把本机 LSDB **全量**单播给它（代替 OSPF 的 DBD / LSR / LSU 三步）。 |
| R4 | 本机的 Full 邻居集合或前缀集合变化时，本机 LSA `seq + 1`，重新生成并泛洪。 |
| R5 | 收到一条 LSA：LSDB 里没有这台路由器的，或 `seq` 更大 → 存入，转发给**除来源外**的所有 Full 邻居，触发 SPF；否则丢弃。 |
| R6 | 收到 `rid` 是自己的 LSA，且它比本机当前的“新”（`seq` 更大，或 `seq` 相同但内容不同）→ 把本机 `seq` 跳到它之上，重新生成并泛洪。 |
| R7 | SPF：边 A–B 存在，当且仅当 A 的 `links` 列了 B **且** B 的 `links` 列了 A（两个方向的 cost 可以不同）。前缀 P 的距离 = 通告它的路由器的距离 + P 自己的 cost，多台路由器通告同一前缀取最小。并列时**基础版取 router id 最小的首跳**（结果确定，便于验收）；进阶版装成 ECMP。本机自己通告的前缀不参与。 |
| R8 | 安装：对每个**非直连**前缀 `ip route replace P via <下一跳地址> dev <出接口> proto 200 metric 20`；不再可达的删掉；退出时 `ip route flush proto 200`。下一跳地址 = 首跳邻居在共享链路上的地址（邻居表里有）。 |
| R9 | 可靠泛洪（进阶）：每条发出的 LSU 等 Ack；1 秒没等到就重传，直到收到 Ack 或邻居 Down。收到 LSU 的一方，不管新旧，都要 Ack。 |

**定时器与 cost**：Hello 2 秒 / Dead 8 秒（保持 OSPF 的 1 : 4；三台必须一致），接口 cost 默认 10（`--cost r1-r2=20` 覆盖），SPF 延迟 100 ms（合并短时间内的多次变化）。

**与 OSPF 的差异**（思考题从这里出）：无 DR / BDR、无 area、无 DBD / LSR、无 age / MaxAge / 周期刷新、无认证、无校验和、只有 Router-LSA、明文 JSON。

### 3.4 骨架：给了什么，你写什么

```
2026/experiments/02/lsrd/
├── __main__.py     参数解析、日志、信号、启动                              【给定】
├── loop.py         事件循环：一个 select() 同时等套接字与定时器             【给定】
├── transport.py    每接口一个 UDP 套接字、广播 / 单播、JSON 编解码与字段校验  【给定】
├── sysnet.py       ip -j addr 读接口；ip route replace / del / flush；        【给定】
│                   watch_links()：订阅 ip monitor 的链路事件                 【进阶任务 T6 你写】
├── neighbor.py     Hello 的生成与处理、邻居表、状态机                        【R1、R2　你写（课上一起）】
├── lsdb.py         LSA、LSDB、泛洪规则                                       【R3–R6　你写；R9 进阶】
├── spf.py          建图、Dijkstra、首跳、前缀表                              【R7　你写；ECMP 进阶】
├── router.py       把各部件接起来：事件 → 动作；R8 的 diff 安装             【给定】
└── cli.py          run.sh show 背后的 unix socket 服务与格式化               【给定】
```

数据在里面怎么流：

```
  网线 ──▶ transport.py（每接口一个套接字，收到就 JSON 解码、校验字段）
              │ hello                                   │ lsu / ack
              ▼                                         ▼
        neighbor.py ──邻居事件──▶ router.py ◀────── lsdb.py 的 Flooder
        （R1、R2）                   │  R3 / R4        （R3–R6、R9）
                                    │                     ▲   泛洪出去
                                    ▼ LSDB 变了           └──────▶ transport.py ──▶ 网线
                               spf.py（R7）
                                    │ 前缀表 {prefix: (cost, [首跳 rid])}
                                    ▼
                       router.py：首跳 rid → 邻居地址与出接口，与上次安装的做 diff（R8）
                                    ▼
                               sysnet.py ──▶ ip route replace / del ──▶ 内核 FIB
```

要你写的部分在代码里都标着 `# ---- TODO（规范 Rn）`，每个函数的 docstring 写明了输入、输出和该做的事。给定部分约 550 行，要写的部分参考实现约 250 行——**读懂给定部分花的时间，会比写的时间长，这是正常的**。

---

## 四、实验步骤

### 基础任务

#### 任务 1　读骨架

```bash
# 3. 离线测试。此时应当 12 个失败、5 个通过——失败的正是你要写的三块（R5、R7）
(cd 2026/experiments/02 && uv run python -m unittest 2>&1 | tail -3)
```

```
Ran 17 tests in 0.005s

FAILED (failures=9, errors=3)
```

`-v` 能看到每个测试的名字。它们只测纯逻辑（`lsdb.py` 的 seq 规则、`spf.py` 的建图与算路），所以不需要 root，也不需要实验床——先在这里把 R5 和 R7 调通，再上 namespace。

**读 `loop.py`、`transport.py`、`router.py`，回答这三个检查点**（答案写进报告）：

1. 事件循环里只有一个 `select()`，它是怎么同时伺候“套接字可读”与“定时器到期”两类事件的？`call_every` 的定时器为什么不会因为回调跑得慢而“积压”？
2. `transport.py` 为每个接口开一个套接字，而不是一个套接字听所有接口。协议的哪一条规则要求“知道报文从哪个接口进来”？如果只用一个套接字，得靠什么补上这个信息？
3. `router.py` 里安装路由时先把 SPF 的结果与上次安装的做 diff，只 `replace` / `del` 变化的那几条，而不是每次 `flush` 掉重装。两种做法在“拔线后收敛”那一刻，对正在转发的流量各有什么影响？

---

#### 任务 2　邻居发现（R1、R2）

第 04 讲课上一起写 `neighbor.py`。课后请确认它满足 R2 的全部条款——尤其是**双向确认**与 **Dead 定时器**，课上不一定来得及。

```bash
# 4. 搭实验床（Lab 1 的两机架 + r3，删掉静态路由）
sudo bash 2026/experiments/02/topo.sh
```

```
[*] 停掉可能还在跑的 lsrd，清理上次的 r3 / 机架 3...
[*] 用 Lab 1 的脚本搭两机架实验床...
[*] 预清理（保证可重复执行）...
[*] 创建 namespace...
[*] 搭建机架 1（10.0.1.0/24）...
[*] 搭建机架 2（10.0.2.0/24）...
[*] 连接两台路由器...
[*] 打开路由器的 IPv4 转发...
[*] 配置静态路由...
[*] 搭建完成。
[*] 新增中转路由器 r3，连到 r1 与 r2...
[*] 删掉 Lab 1 的两条静态路由——从现在起没有人再手工配路由...
[*] 搭建完成。r1 的路由表现在只剩直连网段：
    10.0.1.0/24 dev br1 proto kernel scope link src 10.0.1.1
    10.0.12.0/30 dev r1-r2 proto kernel scope link src 10.0.12.1
    10.0.13.0/30 dev r1-r3 proto kernel scope link src 10.0.13.1
[*] 跨机架此刻不通是正常的。启动守护进程后再自检：
    sudo bash 2026/experiments/02/run.sh start && sleep 6 && sudo bash 2026/experiments/02/run.sh check
```

```bash
# 5. 起三台守护进程。run.sh 把每个 rN namespace 里的网桥自动加成 --passive
sudo bash 2026/experiments/02/run.sh start
```

```
[*] 启动守护进程：
  [OK]   r1  rid=1 --passive br1   (pid 7514, 日志 /tmp/lsrd/r1.log)
  [OK]   r2  rid=2 --passive br2   (pid 7532, 日志 /tmp/lsrd/r2.log)
  [OK]   r3  rid=3    (pid 7550, 日志 /tmp/lsrd/r3.log)
```

```bash
# 6. 一秒内看一次 r1 的邻居表，几秒后再看一次
sudo bash 2026/experiments/02/run.sh show r1 neighbors
```

```
 RID  IFACE    ADDR         STATE COST  UP-FOR LAST-HELLO
   2  r1-r2    10.0.12.2    Init    10    0.8s       0.8s
   3  r1-r3    10.0.13.2    Init    10    0.7s       0.7s
```

```
 RID  IFACE    ADDR         STATE COST  UP-FOR LAST-HELLO
   2  r1-r2    10.0.12.2    Full    10    4.9s       0.9s
   3  r1-r3    10.0.13.2    Full    10    4.7s       0.7s
```

从 Init 到 Full 要经过“我听到你 → 我告诉你我听到你了 → 你听到我说听到你了”，所以最多两个 Hello 周期。

```bash
# 7. 抓四个 Hello。-A 把 JSON 直接打出来；seen 里已经有对方
sudo ip netns exec r1 tcpdump -n -l -A -i r1-r2 udp port 5200 -c 4
```

```
tcpdump: verbose output suppressed, use -v[v]... for full protocol decode
listening on r1-r2, link-type EN10MB (Ethernet), snapshot length 262144 bytes
23:16:31.866363 IP 10.0.12.1.5200 > 255.255.255.255.5200: UDP, length 60
E..X..@.@.	.
........P.P.D.V{"dead":8,"hello":2,"rid":1,"seen":[2],"type":"hello","v":1}
23:16:31.995831 IP 10.0.12.2.5200 > 255.255.255.255.5200: UDP, length 60
E..X..@.@...
........P.P.D.W{"dead":8,"hello":2,"rid":2,"seen":[1],"type":"hello","v":1}
23:16:33.867029 IP 10.0.12.1.5200 > 255.255.255.255.5200: UDP, length 60
E..X.{@.@...
........P.P.D.V{"dead":8,"hello":2,"rid":1,"seen":[2],"type":"hello","v":1}
23:16:33.996062 IP 10.0.12.2.5200 > 255.255.255.255.5200: UDP, length 60
E..X.l@.@..'
........P.P.D.W{"dead":8,"hello":2,"rid":2,"seen":[1],"type":"hello","v":1}
4 packets captured
4 packets received by filter
0 packets dropped by kernel
```

**预测一下再往下做**：如果 r2 收不到 r1 的协议报文，而 r1 收得到 r2 的（单向故障），r1 的邻居表里 r2 会是什么状态？r2 的邻居表里 r1 呢？8 秒后呢？

```bash
# 8. 让 r2 听不见 r1（r1 仍听得见 r2）。十秒后看两边的邻居表，然后撤掉规则
sudo ip netns exec r2 iptables -I INPUT -i r2-r1 -p udp --dport 5200 -j DROP
sudo bash 2026/experiments/02/run.sh show r1 neighbors
sudo bash 2026/experiments/02/run.sh show r2 neighbors
sudo ip netns exec r2 iptables -D INPUT -i r2-r1 -p udp --dport 5200 -j DROP
```

```
r1:
 RID  IFACE    ADDR         STATE COST  UP-FOR LAST-HELLO
   2  r1-r2    10.0.12.2    Init    10    1.1s       1.1s
   3  r1-r3    10.0.13.2    Full    10   19.0s       1.0s

r2:
 RID  IFACE    ADDR         STATE COST  UP-FOR LAST-HELLO
   3  r2-r3    10.0.23.2    Full    10   19.1s       1.0s
```

r1 每 2 秒都能收到 r2 的 Hello，但 r2 的 `seen` 里已经没有 1（r2 的 Dead 定时器把 r1 删掉了），于是 r1 把 r2 **从 Full 退回 Init**；r2 那边 r1 干脆消失。一条单向链路上，谁都不会把对方当成可用的邻居——这正是 R2 里“对方的 `seen` 里有我”这个条件的用处。

> **交报告时**：写下你在 R2 上踩过的坑（如果一次就通，写下你认为最容易错的是哪一条、为什么）。

---

#### 任务 3　LSA 与泛洪（R3–R6）

实现 `lsdb.py`：`Lsdb.is_newer` / `install`（R5 前半）、`Flooder.originate`（R4）、`flood` 与 `on_lsu`（R5）、`on_neighbor_full`（R3）、`self_originated`（R6）。`router.py` 已经在正确的时机调用它们，你只需要让每个函数做 docstring 说的事。改完代码要 `run.sh stop` 再 `start`，新代码才会生效。

```bash
# 9. 看 r1 的 LSDB；check 会比对三台的指纹
sudo bash 2026/experiments/02/run.sh show r1 lsdb
sudo bash 2026/experiments/02/run.sh check
```

```
rid=1 seq=5
    links     2:10, 3:10
    prefixes  10.0.1.0/24:10, 10.0.12.0/30:10, 10.0.13.0/30:10
rid=2 seq=5
    links     1:10, 3:10
    prefixes  10.0.12.0/30:10, 10.0.2.0/24:10, 10.0.23.0/30:10
rid=3 seq=3
    links     1:10, 2:10
    prefixes  10.0.13.0/30:10, 10.0.23.0/30:10
digest 75c235d52c  (3 LSAs)
```

```
[*] 守护进程：
  [OK]   r1 在运行
  [OK]   r2 在运行
  [OK]   r3 在运行
[*] 邻接（每条路由器间链路的两端都应 Full；期望数 = 该路由器上非网桥的 IPv4 接口数）：
  [OK]   r1 Full={2,3}
  [OK]   r2 Full={1,3}
  [OK]   r3 Full={1,2}
[*] LSDB 一致性（指纹应完全相同）：
         r1 75c235d52c
         r2 75c235d52c
         r3 75c235d52c
  [OK]   一致
[*] 内核里 lsrd 写的路由（proto 200）：
  r1: 2 条
  r2: 2 条
  r3: 3 条
[*] 静态路由自检（r1、r2 上不该再有手工配置的 via 路由）：
  [OK]   r1
  [OK]   r2
[*] 连通性自检：
  [OK]   h1a → h1b 10.0.1.12（同机架，二层直通）
  [OK]   h1a → h2a 10.0.2.11（跨机架）
  [OK]   h2b → h1a 10.0.1.11（跨机架，反向）
  [OK]   h1a → r3 10.0.13.2（机架 → 中转路由器）
  [OK]   r3  → h2a 10.0.2.11（中转路由器 → 机架 2）
```

三条 LSA、指纹一致，就说明 R3–R5 基本对了（`check` 后半段的路由条数与连通性要等任务 4）。r1、r2 的 seq 是 5 而 r3 是 3：第 8 步的单向故障让它们俩各失去又找回了一次邻居，每次都是 R4 的一次 `seq + 1`——seq 就是这样一条一条涨上去的。

**预测一下再往下做**：在三角形上让 r1 重新生成一条 LSA，这条 LSA 会在线上出现几份？其中几份会被收到的一方判为“不新”而丢弃？（提示：R5 说“转发给除来源外的所有 Full 邻居”，r2 和 r3 互为邻居。）

```bash
# 10. 记下三台的计数器
for r in r1 r2 r3; do echo "--- $r"; sudo bash 2026/experiments/02/run.sh show $r stats | grep -E "lsa_(originated|installed|dropped_stale|flooded)"; done

# 11. 让 r1 重新生成一条 LSA（内容不变、seq + 1），两秒后再看一次计数器
sudo bash 2026/experiments/02/run.sh poke r1
```

```
--- r1
  lsa_dropped_stale    4
  lsa_flooded          10
  lsa_installed        8
  lsa_originated       5
--- r2
  lsa_dropped_stale    7
  lsa_flooded          9
  lsa_installed        7
  lsa_originated       5
--- r3
  lsa_dropped_stale    5
  lsa_flooded          11
  lsa_installed        8
  lsa_originated       3
```

```
--- r1
  lsa_dropped_stale    4
  lsa_flooded          12
  lsa_installed        8
  lsa_originated       6
--- r2
  lsa_dropped_stale    8
  lsa_flooded          10
  lsa_installed        8
  lsa_originated       5
--- r3
  lsa_dropped_stale    6
  lsa_flooded          12
  lsa_installed        9
  lsa_originated       3
```

差值：r1 `originated` +1、`flooded` +2；r2 与 r3 各 `installed` +1、`flooded` +1、`dropped_stale` +1。线上一共 **4 份** LSU，有用的 2 份——r2 和 r3 各把它转发给了对方一次，对方看一眼 seq 就扔了。r2 的日志里就是这两行：

```
23:16:51.804 INFO    lsdb: LSA rid=1 seq=6 from 10.0.12.1 on r2-r1: newer, stored, flooding
23:16:51.805 INFO    lsdb: LSA rid=1 seq=6 from 10.0.23.2 on r2-r3: not newer, dropped
```

（绝对值与你的不同没关系，启动阶段几台路由器建邻的先后顺序决定了那些数字；只看差值。）

> [!TIP]
> 想数“线上真的有几份”，在 r3 上 `sudo ip netns exec r3 tcpdump -n -l -A -i any udp port 5200` 再 `poke r1`：r3 会看到两份进来的、一份出去的。

---

#### 任务 4　SPF 与写内核（R7、R8）

实现 `spf.py`：`build_graph`（R7 的双向检查）、`dijkstra`（记住首跳）、`compute_routes`（前缀表）。R8 的安装 `router.py` 已经写好——它把你的前缀表里的首跳 rid 翻译成邻居地址与出接口，与上次装的做 diff，再交给 `sysnet.route_replace`。

**先手推，再跑**。全部 cost 10，三台路由器各自的路由表应当是（并列时按 R7 取 rid 最小的首跳）：

| 路由器 | 目的前缀 | cost | 下一跳 |
| :--- | :--- | :--- | :--- |
| r1 | `10.0.2.0/24` | | |
| r1 | `10.0.23.0/30` | | |
| r2 | `10.0.1.0/24` | | |
| r2 | `10.0.13.0/30` | | |
| r3 | `10.0.1.0/24` | | |
| r3 | `10.0.2.0/24` | | |
| r3 | `10.0.12.0/30` | | |

共 7 条（r1 两条、r2 两条、r3 三条）。想清楚为什么 r1 不需要去 `10.0.13.0/30` 的路由，而 r3 需要去 `10.0.12.0/30` 的。

```bash
# 12. 离线测试应全部通过（tests/graphs/ 里有三角形、拔线瞬间的“半截边”、五节点图）
(cd 2026/experiments/02 && uv run python -m unittest 2>&1 | tail -3)
```

```
Ran 17 tests in 0.002s

OK
```

```bash
# 13. 重启三台。守护进程算出的表（RIB）与内核里的（FIB）
sudo bash 2026/experiments/02/run.sh stop
sudo bash 2026/experiments/02/run.sh start
sudo bash 2026/experiments/02/run.sh show r1 routes
sudo ip -n r1 route show
```

```
PREFIX           COST  NEXTHOP(S)                           KERNEL
10.0.2.0/24        20  10.0.12.2 dev r1-r2                  installed
10.0.23.0/30       20  10.0.12.2 dev r1-r2                  installed
```

```
10.0.1.0/24 dev br1 proto kernel scope link src 10.0.1.1
10.0.2.0/24 via 10.0.12.2 dev r1-r2 proto 200 metric 20
10.0.12.0/30 dev r1-r2 proto kernel scope link src 10.0.12.1
10.0.13.0/30 dev r1-r3 proto kernel scope link src 10.0.13.1
10.0.23.0/30 via 10.0.12.2 dev r1-r2 proto 200 metric 20
```

`proto 200 metric 20` 的两条是你写的；三条 `proto kernel` 是直连网段，内核自己维护，R8 说了不许碰。三台一起看：

```bash
# 14. 三台路由器上 lsrd 写的全部路由（过滤条件已含 proto 200，输出里就不再打印它）
for r in r1 r2 r3; do echo "--- $r"; sudo ip -n $r route show proto 200; done
```

```
--- r1
10.0.2.0/24 via 10.0.12.2 dev r1-r2 metric 20
10.0.23.0/30 via 10.0.12.2 dev r1-r2 metric 20
--- r2
10.0.1.0/24 via 10.0.12.1 dev r2-r1 metric 20
10.0.13.0/30 via 10.0.12.1 dev r2-r1 metric 20
--- r3
10.0.1.0/24 via 10.0.13.1 dev r3-r1 metric 20
10.0.2.0/24 via 10.0.23.1 dev r3-r2 metric 20
10.0.12.0/30 via 10.0.13.1 dev r3-r1 metric 20
```

对照你手推的表。然后是主机之间真的通了没有——这是 Lab 1 以来第一次，路由表里没有任何一条是人写的：

```bash
# 15. 两跳经 r2；连通性自检全部通过
sudo ip netns exec h1a traceroute -n 10.0.2.11
sudo bash 2026/experiments/02/run.sh check
```

```
traceroute to 10.0.2.11 (10.0.2.11), 30 hops max, 60 byte packets
 1  10.0.1.1  0.037 ms  0.004 ms  0.003 ms
 2  10.0.12.2  0.009 ms  0.004 ms  0.003 ms
 3  10.0.2.11  0.012 ms  0.006 ms  0.005 ms
```

> [!IMPORTANT]
> 从这一步起，`run.sh check` 必须**全部 OK** 才算基础任务的守护进程完成。它检查的四件事——三台在跑、六条邻接全 Full、LSDB 指纹一致、机架间连通——分别对应 R1–R2、R3–R5、R7–R8。

---

#### 任务 5　拔线：只靠 Dead 定时器的收敛

现在守护进程只从 Hello 里感知世界：接口拔了它不知道，要等 Dead 定时器。先算一算这意味着什么。

**先写下你的预测，再往下做**：

- 100 pps 的数据流从 h1a 发往 h2a，拔掉 r1 的 `r1-r2`，数据流会中断多久？（提示：距离上一个 Hello 已经过去了 0–2 秒，Dead 是 8 秒，再加泛洪与 SPF）
- 第 03 讲 6.8 节 FRR 在同样的操作下是 0 丢包。差距来自四段中的哪一段？
- 中断结束时，r1 是靠自己的 Dead 定时器发现的，还是靠别人告诉它的？

开四个终端：

```bash
# 16. 终端 1：接收端（h2a）
sudo ip netns exec h2a python3 2026/experiments/02/probe.py recv
```

```bash
# 17. 终端 2：在 r1 里盯着内核的链路与路由事件，带时间戳
sudo ip netns exec r1 ip -ts monitor link route
```

```bash
# 18. 终端 3：发送端（h1a），100 pps 跑 30 秒
sudo ip netns exec h1a python3 2026/experiments/02/probe.py send --to 10.0.2.11 --seconds 30
```

```bash
# 19. 终端 4：发送开始约 5 秒后拔线；3 秒后、11 秒后各看一次 r1 的邻居表
sudo ip -n r1 link set r1-r2 down
sudo bash 2026/experiments/02/run.sh show r1 neighbors
```

发送端跑完后，终端 1 会给出统计：

```
listening on udp/9100 (Ctrl-C or END marker to finish)
received 2200 / 3000 (up to seq 2999), lost 800 (26.7%)
1 gap(s):
  seq 497..1296  800 packets  8010 ms  (starting 5.0s into the run)
longest interruption: 8010 ms (800 packets)
```

终端 2 里链路事件与路由变化之间隔了 8 秒：

```
[2026-09-26T23:17:02.145656] 46: r1-r2@if45: <BROADCAST,MULTICAST> mtu 1500 qdisc noqueue state DOWN group default
    link/ether 5e:c9:76:08:6e:33 brd ff:ff:ff:ff:ff:ff link-netns r2
[2026-09-26T23:17:10.146300] 10.0.2.0/24 via 10.0.13.2 dev r1-r3 proto 200 metric 20
[2026-09-26T23:17:10.148222] 10.0.23.0/30 via 10.0.13.2 dev r1-r3 proto 200 metric 20
```

拔线 3 秒后与 11 秒后 r1 的邻居表——`LAST-HELLO` 一路涨，涨过 8 秒那一条就没了：

```
 RID  IFACE    ADDR         STATE COST  UP-FOR LAST-HELLO
   2  r1-r2    10.0.12.2    Full    10   19.2s       3.2s
   3  r1-r3    10.0.13.2    Full    10   39.0s       1.0s
```

```
 RID  IFACE    ADDR         STATE COST  UP-FOR LAST-HELLO
   3  r1-r3    10.0.13.2    Full    10   47.1s       1.1s
```

r1 日志里这一段值得逐行读：

```
23:17:10.041 INFO    lsdb: LSA rid=2 seq=6 from 10.0.13.2 on r1-r3: newer, stored, flooding
23:17:10.146 INFO    router: route replace 10.0.2.0/24 via 10.0.13.2 dev r1-r3
23:17:10.148 INFO    router: route replace 10.0.23.0/30 via 10.0.13.2 dev r1-r3
23:17:10.403 INFO    router: neighbor rid=2 via r1-r2 (10.0.12.2): Down
23:17:10.409 INFO    router: originated LSA(rid=1 seq=7 links=[3:10] prefixes=[10.0.1.0/24:10,10.0.13.0/30:10])
```

第一行：r1 收到的是 **r2** 的新 LSA（r2 的 Dead 定时器先到了，它把 r1 从 `links` 里删掉后重新泛洪，经 r3 转来）；r1 据此重跑 SPF——图上 r1 → r2 那条边因为 r2 不再声明而消失（R7 的双向检查），路由改走 r3。而 r1 **自己的** Dead 定时器（第四行）要到 0.36 秒之后才响。两台路由器的定时器谁先到期，取决于拔线那一刻各自离上一个 Hello 有多远。

```bash
# 20. 路径变成四跳；再看一次计数器，数一数这次泛洪了几份 LSU
sudo ip netns exec h1a traceroute -n 10.0.2.11
for r in r1 r2 r3; do echo "--- $r"; sudo bash 2026/experiments/02/run.sh show $r stats | grep -E "lsa_(originated|installed|dropped_stale|flooded)"; done

# 21. 恢复链路。几秒后邻接重建、路由切回两跳，数据流不会再断（想想为什么）
sudo ip -n r1 link set r1-r2 up
sudo ip -n r1 route show proto 200
```

报告里给出**预测值、实测值、差距的解释**，并与第 03 讲 6.8 节 FRR 的 0 丢包对照：FRR 之所以是 0，是因为 zebra 通过 netlink **听得见内核**，接口一 down 它立刻知道；你的守护进程只听 Hello，于是一个“响的故障”被当成了“静默故障”。这就是进阶任务 T6 要补的。

---

### 进阶任务

#### 任务 6　听内核的话

实现 `sysnet.watch_links()`：起一个 `ip -o monitor link` 子进程，把它的输出挂进事件循环，每读到一行就用给定的 `parse_monitor_line()` 解析，接口失去 `LOWER_UP` 就调用回调。`router.on_link_change()` 已经写好：它会把该接口上的邻居立即置 Down（`neighbor.link_down`，R2 的第三个函数），不再等 Dead 定时器。

**预测一下再往下做**：有了它，任务 5 的中断会降到多少？剩下的时间花在哪一段？

```bash
# 22. 换上 --watch-links 重启三台，重复第 16–19 步
sudo bash 2026/experiments/02/run.sh stop
sudo bash 2026/experiments/02/run.sh start --watch-links
```

```
listening on udp/9100 (Ctrl-C or END marker to finish)
received 2989 / 3000 (up to seq 2999), lost 11 (0.4%)
1 gap(s):
  seq 498..508  11 packets  120 ms  (starting 5.0s into the run)
longest interruption: 120 ms (11 packets)
```

从 8 秒到 0.12 秒。r1 的日志把这 0.12 秒拆开了：

```
23:17:59.356 INFO    router: link r1-r2: down
23:17:59.356 INFO    router: neighbor rid=2 via r1-r2 (10.0.12.2): Down
23:17:59.359 INFO    router: originated LSA(rid=1 seq=4 links=[3:10] prefixes=[10.0.1.0/24:10,10.0.13.0/30:10])
23:17:59.360 INFO    lsdb: LSA rid=2 seq=4 from 10.0.13.2 on r1-r3: newer, stored, flooding
23:17:59.463 INFO    router: route replace 10.0.2.0/24 via 10.0.13.2 dev r1-r3
23:17:59.466 INFO    router: route replace 10.0.23.0/30 via 10.0.13.2 dev r1-r3
23:17:59.466 INFO    router: spf: 2 prefixes (2.3 ms), installed 2, deleted 0 (4.2 ms)
```

| 段 | 从 | 到 | 用时 |
| :--- | :--- | :--- | :--- |
| 检测 | 内核报告链路 down | 邻居 Down | 0 ms |
| 泛洪 | 邻居 Down | 本机新 LSA 生成、r2 的新 LSA 经 r3 到达 | 4 ms |
| 等待合并 | 新 LSA 到达 | SPF 开始 | 100 ms（`--spf-delay` 的默认值） |
| 计算 + 安装 | SPF 开始 | 两条路由 replace 完成 | 2.3 + 4.2 ms |

**预测一下再往下做**：把 `--spf-delay` 改成 0 会怎样？会不会有副作用？（提示：一次拔线在三角形上会引起两条新 LSA，它们不会同时到。）

```bash
# 23. 把合并延迟去掉再测一次
sudo bash 2026/experiments/02/run.sh stop
sudo bash 2026/experiments/02/run.sh start --watch-links --spf-delay 0
```

```
listening on udp/9100 (Ctrl-C or END marker to finish)
received 1998 / 2000 (up to seq 1999), lost 2 (0.1%)
1 gap(s):
  seq 498..499  2 packets  30 ms  (starting 5.0s into the run)
longest interruption: 30 ms (2 packets)
```

```
23:19:31.506 INFO    router: link r1-r2: down
23:19:31.506 INFO    router: neighbor rid=2 via r1-r2 (10.0.12.2): Down
23:19:31.512 INFO    router: originated LSA(rid=1 seq=4 links=[3:10] prefixes=[10.0.1.0/24:10,10.0.13.0/30:10])
23:19:31.522 INFO    router: route replace 10.0.2.0/24 via 10.0.13.2 dev r1-r3
23:19:31.523 INFO    router: route replace 10.0.23.0/30 via 10.0.13.2 dev r1-r3
23:19:31.523 INFO    router: spf: 2 prefixes (7.3 ms), installed 2, deleted 0 (3.4 ms)
23:19:31.525 INFO    router: spf: 2 prefixes (1.8 ms), installed 0, deleted 0 (0.0 ms)
```

30 ms（探针 10 ms 的分辨率下是 2 个包；路由实际在拔线后 16 ms 就换好了），SPF 跑了两次——一次为自己的新 LSA，一次为 r2 的。报告里填一张与上面一样的四段表，并回答：这 30 ms 里最大的一段是什么，还能不能压？

**静默故障**。链路两端把从这条链路进来的所有报文丢掉（接口本身不动）——与第 03 讲 6.9 节相同的操作：

```bash
# 24. 恢复默认参数重启，再起一轮探针（第 16、18 步），5 秒后注入静默故障
sudo bash 2026/experiments/02/run.sh stop
sudo bash 2026/experiments/02/run.sh start --watch-links
sudo ip netns exec r1 iptables -I INPUT   -i r1-r2 -j DROP
sudo ip netns exec r1 iptables -I FORWARD -i r1-r2 -j DROP
sudo ip netns exec r2 iptables -I INPUT   -i r2-r1 -j DROP
sudo ip netns exec r2 iptables -I FORWARD -i r2-r1 -j DROP

# 25. 每隔几秒看一次 r1 的邻居表，LAST-HELLO 一路涨到 8 秒
sudo bash 2026/experiments/02/run.sh show r1 neighbors

# 26. 撤掉
sudo ip netns exec r1 iptables -F
sudo ip netns exec r2 iptables -F
```

```
listening on udp/9100 (Ctrl-C or END marker to finish)
received 2207 / 3000 (up to seq 2999), lost 793 (26.4%)
1 gap(s):
  seq 498..1290  793 packets  7940 ms  (starting 5.0s into the run)
longest interruption: 7940 ms (793 packets)
```

```
 RID  IFACE    ADDR         STATE COST  UP-FOR LAST-HELLO
   2  r1-r2    10.0.12.2    Full    10   28.3s       4.3s
   3  r1-r3    10.0.13.2    Full    10   52.1s       0.1s
```

内核不知道这条链路坏了（接口还是 UP，只是包进不来），`ip monitor` 一声不吭，只剩 Dead 定时器。第 03 讲 6.9 节 FRR 丢了 34.6 秒的包，你的是 7.9 秒——**不是你的更好，是 Dead 不一样**（40 秒对 8 秒）。报告里按 Dead 归一化再比，并回答：把 Dead 调到 1 秒，代价是什么？（第 03 讲思考题 2）

---

#### 任务 7　机架 3 上线：改几处配置？

Lab 1 任务 3 数过：静态路由下每加一个机架，全网总条数按 $N(N-1)$ 涨，而且要登录每一台设备。现在换成守护进程，三台都在跑着，给 r3 挂上机架 3（规格与 Lab 1 任务 3 相同）：

```bash
# 27. 记下三台的 pid，然后给跑着的实验床加机架 3
sudo bash 2026/experiments/02/run.sh status
sudo bash 2026/experiments/02/topo.sh rack3
```

```
[*] 搭建机架 3（10.0.3.0/24）...
[*] r1、r2 上什么都不用改。让 r3 的守护进程知道 br3 是机架侧接口：sudo bash 2026/experiments/02/run.sh restart r3
```

```bash
# 28. 只重启 r3（run.sh 会自动把 br3 加成 --passive）；r1、r2 一个字不改
sudo bash 2026/experiments/02/run.sh restart r3 --watch-links

# 29. 几秒后：r1、r2 的 pid 没变，路由表里多了机架 3，六台主机两两可达
sudo bash 2026/experiments/02/run.sh status
sudo ip -n r1 route show proto 200
sudo ip netns exec h1a traceroute -n 10.0.3.11
sudo bash 2026/experiments/02/run.sh check
```

```
r1: 运行中 (pid 11248)，rid 1  uptime 17.9s  hello/dead 2/8s  ecmp=False ack=False watch_links=True install=True
r2: 运行中 (pid 11266)，rid 2  uptime 17.8s  hello/dead 2/8s  ecmp=False ack=False watch_links=True install=True
r3: 运行中 (pid 11450)，rid 3  uptime 8.2s  hello/dead 2/8s  ecmp=False ack=False watch_links=True install=True
```

```
10.0.2.0/24 via 10.0.12.2 dev r1-r2 metric 20
10.0.3.0/24 via 10.0.13.2 dev r1-r3 metric 20
10.0.23.0/30 via 10.0.12.2 dev r1-r2 metric 20
```

```
traceroute to 10.0.3.11 (10.0.3.11), 30 hops max, 60 byte packets
 1  10.0.1.1  0.244 ms  0.196 ms  0.187 ms
 2  10.0.13.2  0.180 ms  0.165 ms  0.157 ms
 3  10.0.3.11  0.148 ms  0.109 ms  0.098 ms
```

把 Lab 1 任务 3 的那张表补上最后一列，并写出通项：

| 机架数 N | 静态路由：全网总条数 | 静态路由：新增一个机架要改几台设备 | lsrd：要改几台设备 |
| :--- | :--- | :--- | :--- |
| 2 | | | |
| 3 | | | |
| N | | | |

再看一眼 r3 的日志。它重启后 `seq` 从 1 起步，收到自己的旧 LSA 后**跳**到了 7：

```
23:26:22.906 INFO    router: originated LSA(rid=3 seq=1 links=[] prefixes=[10.0.13.0/30:10,10.0.23.0/30:10,10.0.3.0/24:10])
23:26:23.087 INFO    router: originated LSA(rid=3 seq=2 links=[1:10] prefixes=[10.0.13.0/30:10,10.0.23.0/30:10,10.0.3.0/24:10])
23:26:23.214 INFO    router: originated LSA(rid=3 seq=3 links=[1:10,2:10] prefixes=[10.0.13.0/30:10,10.0.23.0/30:10,10.0.3.0/24:10])
23:26:24.958 INFO    router: originated LSA(rid=3 seq=7 links=[1:10,2:10] prefixes=[10.0.13.0/30:10,10.0.23.0/30:10,10.0.3.0/24:10])
```

这是 R6 在工作。想一想：如果没有 R6，重启后的 r3 发出的 seq 1、2、3 会被谁接受？它的新地图要到什么时候才能传到别人那里？

---

#### 任务 8　cost 与等价多路径

实现 R7 的并列分支：`compute_routes(..., ecmp=True)` 时保留全部等价首跳；`router.py` 会把多个下一跳一起交给 `sysnet.route_replace`，装成内核的 multipath 路由。`tests/graphs/cost20.json` 与 `triangle.json` 里都有 `expected_ecmp`。

把 r1–r2 直连链路两端的 cost 改成 20，r1 去机架 2 就有两条等价路：直连 20 + 10，绕 r3 10 + 10 + 10。

```bash
# 30. 三台一起带参数重启：直连链路两端 cost 20，允许多下一跳（每台只认自己有的接口，其余忽略）
sudo bash 2026/experiments/02/run.sh stop
sudo bash 2026/experiments/02/run.sh start --watch-links --ecmp --cost r1-r2=20 --cost r2-r1=20

# 31. r1 去机架 2 现在有两个下一跳
sudo bash 2026/experiments/02/run.sh show r1 routes
sudo ip -n r1 route show 10.0.2.0/24
```

```
PREFIX           COST  NEXTHOP(S)                           KERNEL
10.0.2.0/24        30  10.0.12.2 dev r1-r2 + 10.0.13.2 dev r1-r3 installed
10.0.23.0/30       20  10.0.13.2 dev r1-r3                  installed
10.0.3.0/24        20  10.0.13.2 dev r1-r3                  installed
```

```
10.0.2.0/24 proto 200 metric 20
	nexthop via 10.0.12.2 dev r1-r2 weight 1
	nexthop via 10.0.13.2 dev r1-r3 weight 1
```

与第 03 讲 6.10 节 FRR 装出来的一模一样。内核怎么分流也一样——**按流**不按包：

```bash
# 32. 默认按源、目的地址哈希：四对地址全走了一边
sudo ip netns exec r1 sysctl net.ipv4.fib_multipath_hash_policy
for s in 10.0.1.11 10.0.1.12; do for d in 10.0.2.11 10.0.2.12; do
  sudo ip netns exec r1 ip route get $d from $s iif br1 | head -1
done; done

# 33. 改成按五元组哈希：不同源端口的流被分到两边
sudo ip netns exec r1 sysctl -w net.ipv4.fib_multipath_hash_policy=1
for p in 40000 40001 40002 40003 40004 40005; do
  sudo ip netns exec r1 ip route get 10.0.2.11 from 10.0.1.11 iif br1 ipproto udp sport $p dport 9100 | head -1
done
```

```
net.ipv4.fib_multipath_hash_policy = 0
10.0.2.11 from 10.0.1.11 via 10.0.13.2 dev r1-r3
10.0.2.12 from 10.0.1.11 via 10.0.13.2 dev r1-r3
10.0.2.11 from 10.0.1.12 via 10.0.13.2 dev r1-r3
10.0.2.12 from 10.0.1.12 via 10.0.13.2 dev r1-r3
```

```
net.ipv4.fib_multipath_hash_policy = 1
10.0.2.11 from 10.0.1.11 via 10.0.13.2 dev r1-r3
10.0.2.11 from 10.0.1.11 via 10.0.13.2 dev r1-r3
10.0.2.11 from 10.0.1.11 via 10.0.13.2 dev r1-r3
10.0.2.11 from 10.0.1.11 via 10.0.12.2 dev r1-r2
10.0.2.11 from 10.0.1.11 via 10.0.12.2 dev r1-r2
10.0.2.11 from 10.0.1.11 via 10.0.13.2 dev r1-r3
```

哪几个端口分到哪边由内核的哈希决定，你的结果和这里的不必相同。挑一个走 r3 的端口、一个走直连的端口，各起一条探针流，在 r3 上数包——这是“内核说的”与“线上发生的”之间的对账：

```bash
# 34. 终端 1：h2a 收；终端 2：在 r3 的 r3-r1 口上抓探针流量；终端 3：两条流，源端口不同
sudo ip netns exec h2a python3 2026/experiments/02/probe.py recv
sudo ip netns exec r3 tcpdump -n -l -i r3-r1 udp dst port 9100
sudo ip netns exec h1a python3 2026/experiments/02/probe.py send --to 10.0.2.11 --seconds 5 --sport 40000
sudo ip netns exec h1a python3 2026/experiments/02/probe.py send --to 10.0.2.11 --seconds 5 --sport 40003

# 35. 把哈希策略改回默认
sudo ip netns exec r1 sysctl -w net.ipv4.fib_multipath_hash_policy=0
```

本机的结果：源端口 40000 的 500 个探针包（加 5 个结束标记）全部经过了 `r3-r1`，40003 的一个都没有。报告里给出你的两个端口、`ip route get` 的答复与 `tcpdump` 数出的包数。再回答：如果内核真的按包轮转，一条 TCP 连接会看到什么？（第 03 讲思考题 4）

---

### 挑战任务

#### 任务 9　可靠泛洪（R9）

R5 把 LSA 转发出去就不管了。UDP 会丢包，一条丢掉的 LSU 意味着两台路由器从此拿着两张不同的地图，而且**没有任何机制会让它们重新一致**——本协议没有周期性刷新。

实现 R9：`Flooder.send` 里登记待确认（给定），`on_lsu` 里对收到的每条 LSA 回 Ack，`on_ack` 撤销登记，`retransmit` 每秒重发超过 1 秒未确认的（重发 LSDB 里该 rid 的**当前**版本）。启动时加 `--ack`。

用 `iptables` 造一个确定的丢包场景：让 r1 在 10 秒内收不到任何 LSU（只丢长度 150 字节以上的包，Hello 不受影响），在这个窗口里让机架 3 上线：

```bash
# 36. 先用没有 R9 的版本（不加 --ack）。机架 3 下线——这条 LSA 人人收到
sudo bash 2026/experiments/02/run.sh stop
sudo bash 2026/experiments/02/run.sh start --watch-links
sudo ip -n r3 link set br3 down

# 37. 关上 r1 的耳朵，再让机架 3 上线——这条 LSA r1 收不到；5 秒后把耳朵打开
sudo ip netns exec r1 iptables -I INPUT -p udp --dport 5200 -m length --length 150:65535 -j DROP
sudo ip -n r3 link set br3 up
sudo ip netns exec r1 iptables -D INPUT -p udp --dport 5200 -m length --length 150:65535 -j DROP

# 38. 三台的指纹、r1 眼里的 r3、h1a 到机架 3
for r in r1 r2 r3; do echo "$r $(sudo bash 2026/experiments/02/run.sh show $r digest)"; done
sudo bash 2026/experiments/02/run.sh show r1 lsdb
sudo ip netns exec h1a ping -c 1 -W 1 10.0.3.11
```

```
r1 d437b1373f
r2 e61a24d98b
r3 e61a24d98b
```

```
rid=3 seq=4
    links     1:10, 2:10
    prefixes  10.0.13.0/30:10, 10.0.23.0/30:10
```

```
PING 10.0.3.11 (10.0.3.11) 56(84) bytes of data.
From 10.0.1.1 icmp_seq=1 Destination Net Unreachable

--- 10.0.3.11 ping statistics ---
1 packets transmitted, 0 received, +1 errors, 100% packet loss, time 0ms
```

r1 停在 seq 4（没有机架 3 的那一版），机架 3 对 r1 来说永远不存在——直到 r3 因为别的原因再发一条 LSA。加上 `--ack` 重做第 36–38 步：

```
r1 e61a24d98b
r2 e61a24d98b
r3 e61a24d98b
```

```
23:21:30.682 INFO    lsdb: retransmit LSA rid=3 seq=5 to rid=1 via r3-r1 (10.0.13.1)
23:21:31.683 INFO    lsdb: retransmit LSA rid=3 seq=5 to rid=1 via r3-r1 (10.0.13.1)
23:21:32.683 INFO    lsdb: retransmit LSA rid=3 seq=5 to rid=1 via r3-r1 (10.0.13.1)
23:21:33.684 INFO    lsdb: retransmit LSA rid=3 seq=5 to rid=1 via r3-r1 (10.0.13.1)
23:21:34.684 INFO    lsdb: retransmit LSA rid=3 seq=5 to rid=1 via r3-r1 (10.0.13.1)
```

r3 每秒重发一次，耳朵一打开就补上了。报告里说明：没有 R9 时地图分叉持续了多久、有 R9 时重传了几次；再回答 OSPF 为什么还要有周期性刷新（LSRefreshTime，30 分钟）——R9 不是已经保证送达了吗？

> [!TIP]
> 想看随机丢包下的表现，把 `-j DROP` 前面加上 `-m statistic --mode random --probability 0.5`，然后用 `run.sh poke` 多制造几条 LSA。

---

#### 任务 10　控制平面故障盲测

Lab 1 的 `break_topo.sh` 破坏的是数据平面。这个脚本破坏的是**协议本身**——链路都通、地址都对，但守护进程之间说不上话，或者说上了话却算错了，或者算对了却没写进内核。

```bash
# 39. 三台都在跑（rack3 模式）的状态下随机注入一处故障
sudo bash 2026/experiments/02/break_lsr.sh

# 40. 找完了看答案，然后恢复
sudo bash 2026/experiments/02/break_lsr.sh reveal
sudo bash 2026/experiments/02/break_lsr.sh fix
```

六种故障：单向阻断协议报文、双向丢弃协议报文（数据照转）、一台的 hello / dead 被改、两台 router id 相同、一台只算不写内核、有人手工加了一条 metric 0 的静态路由。你的工具是 `run.sh show rN neighbors | lsdb | routes`、`ip route`、`traceroute`、`tcpdump`，以及每台的日志。

**要求**：与 Lab 1 任务 5 相同——每一步记录你**看到了什么**、因此**排除了什么**，让人能顺着你的记录复现推理。至少做三轮。

> [!TIP]
> 六种故障里，有两种在 `run.sh check` 的邻接一节里几乎一样（都是“某两台之间少了一个邻居，机架间照样通”），要在两边都 `show neighbors`，看清是 Init 还是消失；有一种邻接、指纹全绿，只是 r3 的路由 0 条、机架 3 只通一半——`show routes` 与 `ip route` 放在一起看，RIB 与 FIB 是两本账；还有一种只有静态路由自检那一行红——先想清楚一条 metric 0 的路由为什么能压住你的，`traceroute` 会证实你的解释。

---

#### 任务 11　伪造一条 LSA：R6 挡得住什么

LSR-lite 没有认证：任何人往 5200 端口发一条格式正确的 JSON，路由器都照单全收。站在 r3 的位置，告诉 r1“router 2 的最新 LSA（seq 一百万）说它一条链路、一个网段都没有”：

```bash
# 41. 伪造 r2 的 LSA 发给 r1，三秒后看 r1 眼里的 r2、r1 的路由表、h1a 到机架 2
sudo ip netns exec r3 python3 2026/experiments/02/forge_lsa.py --to 10.0.13.1 --victim 2 --seq 1000000
sudo bash 2026/experiments/02/run.sh show r1 lsdb
sudo ip -n r1 route show proto 200
sudo ip netns exec h1a ping -c 1 -W 1 10.0.2.11
```

有 R6 时，r2 从 r1 和 r3 那里收到这条冒名的 LSA，把自己的 seq 跳到 1000001 重新泛洪，全网 50 毫秒内恢复：

```
23:22:37.949 WARNING lsdb: received my own LSA with seq=1000000 (mine is 3): jumping ahead
23:22:37.950 WARNING lsdb: received my own LSA with seq=1000000 (mine is 3): jumping ahead
23:22:38.002 INFO    router: originated LSA(rid=2 seq=1000001 links=[1:10,3:10] prefixes=[10.0.12.0/30:10,10.0.2.0/24:10,10.0.23.0/30:10])
```

```
rid=2 seq=1000001
    links     1:10, 3:10
    prefixes  10.0.12.0/30:10, 10.0.2.0/24:10, 10.0.23.0/30:10

10.0.2.0/24 via 10.0.12.2 dev r1-r2 metric 20
10.0.3.0/24 via 10.0.13.2 dev r1-r3 metric 20
10.0.23.0/30 via 10.0.12.2 dev r1-r2 metric 20

1 packets transmitted, 1 received, 0% packet loss, time 0ms
rtt min/avg/max/mdev = 0.052/0.052/0.052/0.000 ms
```

**把 `self_originated` 临时改成 `return False`（等于没有 R6），三台重启，再做一遍第 41 步**：

```
rid=2 seq=1000000
    links     -
    prefixes  -

10.0.3.0/24 via 10.0.13.2 dev r1-r3 metric 20
10.0.23.0/30 via 10.0.13.2 dev r1-r3 metric 20

1 packets transmitted, 0 received, +1 errors, 100% packet loss, time 0ms
```

r2 在所有人的地图上消失，去机架 2 的路由被删掉，而且**永远不会恢复**——r2 之后再发的 LSA seq 是 4、5、6，谁都比不过一百万。改回去，三台重启。

报告里回答：R6 挡住了这一种伪造，那如果攻击者伪造的是 **r3 自己**的 LSA、宣称 r3 直连 `10.0.2.0/24` 且 cost 为 1，会发生什么？R6 能挡住吗？OSPF 用什么办法（RFC 2328 附录 D 与 RFC 5709）？这与第 03 讲 4.6 节 BGP 的劫持有什么异同？

---

#### 任务 12（选做）　互操作

规范写清楚了，两个独立的实现就应当能互相建邻、地图一致、路由正确。找一位同学，用他的 `lsrd/` 目录替换你实验床里 r2 的那一份（`run.sh` 只认目录，`restart r2` 之前把 `lsrd/` 换掉即可），跑 `run.sh check`。

报告里写：能不能建邻、LSDB 是否一致、路由是否一样；如果不行，是哪一条规则两个人理解得不一样——**规范哪一句应该写得更清楚**。

---

## 五、故障排查

| 现象 | 可能原因 | 怎么查 |
| :--- | :--- | :--- |
| `run.sh start` 报 `[FAIL] rN 没有起来` | 守护进程启动即崩溃 | `tail /tmp/lsrd/rN.log`，最后是 Python 的栈；`NotImplementedError` 说明那一段还没写 |
| `[!] 没找到 .venv` | 还没 `uv sync` | `(cd 2026/experiments/02 && uv sync)`；没有 uv 时脚本会退回系统 `python3`，也能跑 |
| 邻居一直停在 Init | 对方的 `seen` 里没有我：`build_hello` 的 `seen` 没填对，或对方 `hello` / `dead` 与本端不一致（R2 要求丢弃） | `tcpdump -A` 看两个方向的 Hello；`show rN stats` 看 `hello_rx` 有没有涨 |
| 邻居 Full 了，`show lsdb` 却只有自己一条 | R3 没发、或 R5 的 `install` 总返回 False | 日志里搜 `sending full LSDB` 与 `newer, stored`；`stats` 里的 `lsa_installed` |
| 三台 LSDB 指纹不一致 | R5 转发时漏了邻居，或把 LSA 发回了来源以外的错误对象 | 分别 `show rN lsdb` 比较哪条 LSA 的 seq 落后；`poke` 一下再看谁没收到 |
| `show routes` 有路由，`ip route` 里没有 | `ip route replace` 失败，通常是把**直连**前缀也交给了安装（`RTNETLINK answers: File exists` 或覆盖了 `proto kernel` 路由） | 日志里搜 `ip route`；`compute_routes` 要跳过本机自己通告的前缀 |
| 路由有，`ping` 不通 | 下一跳地址或出接口翻译错了；或对端没有回程路由 | `ip route get` 看内核打算怎么走；Lab 1 任务 5 的定位清单 |
| 拔线后路由不变 | 没开 `--watch-links`（基础版要等 8 秒）；开了但 `watch_links` 没把 fd 挂进事件循环 | `ip -ts monitor link` 与日志里的 `link … down` 对时间 |
| 重启一台后它的改动不生效 | 网络里还留着它的旧 LSA，seq 更大 | R6 没实现或有 bug。应急办法：三台一起 `run.sh stop` 再 `start` |
| 守护进程崩了，路由还在内核里 | 退出时没来得及 flush | `sudo ip -n rN route flush proto 200`；`run.sh stop` 也会兜底 |
| `Address already in use` | 上一个实例没退干净 | `run.sh stop`；`ls /run/lsrd/`；必要时 `pkill -f "lsrd --id"` |
| `topo.sh` 报找不到 `../01/ns_topo.sh` | 目录结构被动过 | 它依赖 Lab 1 的脚本，位置要在 `2026/experiments/01/` |

拆不干净时的兜底：

```bash
# 42. 停守护进程、拆实验床；列出残留
sudo bash 2026/experiments/02/run.sh stop
sudo bash 2026/experiments/02/topo.sh down
ip netns list
ip link show type veth
```

---

## 六、思考题

1. **为什么要双向确认**
   任务 2 第 8 步里，如果 R2 不要求“对方的 `seen` 里有我”，只要收到 Hello 就算 Full，r1 会把哪些路由装进内核？流量会怎样？OSPF 的 2-Way 与 Full 之间还隔着什么，本协议为什么可以省掉？

2. **全量同步的代价**
   R3 把整个 LSDB 发给新邻居，OSPF 用 DBD / LSR 先对摘要再只要缺的。在 1000 台路由器、每台 LSA 2 KB 的网络里，一次建邻各要传多少字节？什么情况下全量同步反而是对的？（提示：第 03 讲 4.7 节数据中心里的 BGP 就是全量的。）

3. **序列号的三个麻烦**
   回绕、重启后从 1 开始、发起者已经不在了但它的 LSA 还在。本协议分别怎么应对（或者没有应对）？OSPF 的 seq 空间、R6 式的跳跃、MaxAge 各解决其中哪一个？任务 9 的 `--ack` 加上去之后，还有没有必要做周期性刷新？

4. **两本账**
   任务 10 里有一种故障是“算对了却没写进内核”。反过来，守护进程崩溃后内核里的路由还在、流量照走，这是好事还是坏事？zebra 重启时怎么处理内核里残留的路由（提示：第 02 讲 3.2 节的 `proto` 字段就是为这个准备的）？OSPF 的 graceful restart 想解决的是什么？

5. **泛洪份数的通项**
   N 台路由器、E 条链路的连通图上，一条 LSA 按 R5 最多会被发送多少次？如果把 R5 的“seq 更大才存”注释掉（第 04 讲课上演示过），会发生什么？把 Dead 从 8 秒改成 1 秒，每秒的控制报文是多少——这个数字和真正的代价（误判、SPF 重算、路由抖动）哪个更要紧？

6. **调度延迟与误判**
   任务 6 里最大的一段是 `--spf-delay`。单机上三台守护进程与探针共享 CPU，如果虚拟机很忙，Dead 8 秒会不会误判？把 Hello 改成 100 ms 的代价在哪？BFD（RFC 5880）为什么能把探测做到几十毫秒而 OSPF 自己不行？
   *提示：想想“谁在跑这个定时器”——用户态进程、内核，还是网卡。*

---

## 七、提交要求

提交一个压缩包或仓库分支，包含：

1. **你的 `lsrd/`**（整个目录），要求：
   - `uv run python -m unittest` 全部通过；
   - 在干净的实验床上 `run.sh start` 后 6 秒内 `run.sh check` 全部 OK；
   - 进阶、挑战任务实现的部分在 `--watch-links`、`--ecmp`、`--ack` 下也能通过 `check`。
2. **实验报告**（Markdown 或 PDF，正文建议 4–8 页），包含：
   - 任务 1 三个检查点的回答；
   - 任务 2 的踩坑记录；
   - 任务 3 泛洪份数的预测与计数器差值；
   - 任务 4 手推的路由表；
   - 任务 5、6 的**预测 / 实测 / 解释**对照表与四段时间线；
   - 任务 7 补全的表与通项；
   - 任务 8 的两个端口、`ip route get` 与 `tcpdump` 的对账；
   - 挑战任务：任务 9 的两次对比、任务 10 至少三轮的定位过程、任务 11 的两次对比与问题回答；
   - 选做任务的结论（如果做了）。
3. 不要提交 `.venv/`、`__pycache__/`、`*.pcap`、日志等中间产物（仓库 `.gitignore` 已覆盖）。

**评分**：基础任务 60%、进阶任务 25%、挑战任务 15%。与 Lab 1 一样，**评分侧重解释而非截图**：同样跑通了实验，能说清“为什么是这个数”的报告分数显著更高；只贴命令输出、不做解释的报告不算完成。守护进程能跑通 `check` 是基础任务的门槛，不是终点。
