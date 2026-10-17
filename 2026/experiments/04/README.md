# Lab 4　给网络做体检

> 对应第 06 讲　｜　建议用时 1 周（基础约 3 小时；进阶任务 5、6 各约 1.5 小时；挑战任务 7 约 1.5 小时，任务 8 选做约 1 小时）　｜　产出：网络画像工具 `checkup.py` 与画像文件 `profile.json`——Lab 9 的调度器以它为输入

第 06 讲的综合动手里，你做的是“一行、手工、单次”的体检：从 h1a 出发测 7 个目的地，每对测一次，对照参考范围找异常。本实验把它做成一个工具：对一组主机自动测量全部主机对的往返时间与吞吐，**每个数字都带上样本量、统计方法、测量条件与可信度标记**，写成一份机器可读的“网络画像”（Network Profile）。到 Lab 9，调度器读这份画像决定 worker 放在哪里。画像里的每个数都会成为放置决策的依据，所以它必须经得起追问：怎么测的、准不准、在什么条件下成立。

任务分三层：**基础**（任务 1–4）人人完成，产出可用的画像工具与一份基线画像；**进阶**（任务 5、6）处理多路径、单向延迟与传输时间曲线；**挑战**（任务 7、8）只凭端到端测量定位隐藏条件，并尝试找出共享瓶颈，任务 8 为选做。计分见第七节。

---

## 一、实验目标

1. 读懂并补全画像工具：从 `ping`、`iperf3` 的原始输出中取对字段（接收端而不是发送端，排除重复回复），按写明的统计方法汇总，给出可信度标记。
2. 先预测参考范围与测量用时，再为全部主机对产出一份符合格式 v1 的画像，并解释二者的差距。
3. 用数据为测量参数（计入时长、预热、重复次数）辩护；识别 CPU 争用，并说明一条标记规则能发现什么、发现不了什么。
4. （进阶）处理“同一对主机走两条不等价路径”的样本；拆开两个方向的延迟；测出传输时间与数据量的关系，为第 10 讲准备数据。
5. （挑战）只凭端到端测量定位隐藏条件并给出置信度；设计并发测量，找出共享瓶颈。

---

## 二、预备知识与工具

**先读**：

- [第 06 讲](../../docs/network_measurement.md)全文，尤其是 1.3 节（单次测量、样本与统计量）、2.4 节（丢包率的区间）、3.3 节（读懂 `iperf3`）、4.4 节（令牌桶与测量窗口）、5.2–5.5 节（重复、区间与干扰）以及模块六（体检的流程）。
- [Lab 3 指导书](../03/README.md) 3.2 节：节点、接口、地址与限速档位的约定。本实验的实验床与它完全一致。

**环境**：与 Lab 3 相同——Linux（`sudo`）、`iproute2`、`iputils-ping`、`iperf3`、Python 3 与 `uv`；内核支持 namespace、veth、bridge、HTB、fq 与 netem。先检查 netem（任务 1 之后的场景都要用到）：

```bash
# 1. 内核应能创建 netem；报错则安装 linux-modules-extra-$(uname -r)
sudo ip link add nmprobe0 type dummy && sudo tc qdisc add dev nmprobe0 root netem delay 1ms && sudo ip link del nmprobe0
```

**准备 Python 环境**（路由器复用 Lab 2 的环境，体检工具用本实验的环境；二者都只用标准库）：

```bash
# 1. 按各自锁文件初始化两个实验的环境
uv sync --project 2026/experiments/02 --frozen
uv sync --project 2026/experiments/04 --frozen
```

**约定**：以下命令都**从仓库根目录执行**，需要 root 的步骤显式写 `sudo`。体检工具要进入各个 namespace 运行 `ping` 与 `iperf3`，必须以 root 运行本实验环境里的 Python。为了少打字，先在当前终端定义一个函数（bash 与 zsh 都适用；换终端要重新定义）：

```bash
# 1. 体检工具的完整调用；之后的命令写成 ck 加参数
ck() { sudo 2026/experiments/04/.venv/bin/python 2026/experiments/04/checkup.py "$@"; }
```

---

## 三、目录与资源

### 3.1 文件

| 文件 | 说明 |
| :--- | :--- |
| `topo.sh` | **完整实验床**（给定），Lab 4–9 共用；子命令见 3.2 节 |
| `checkup.py` | **体检工具入口**（给定）：解析参数、估算用时、按顺序调度测量、写画像、打印矩阵 |
| `netprof/` | 体检工具的包，给定部分与要你写的 TODO 见 3.3 节 |
| `tests/` | 离线测试；`tests/fixtures/` 中的 `ping` 输出与 `iperf3` JSON 来自备课实验床 |
| `owd.py`、`stats.py` | 第 06 讲的单向延迟探针与统计助手；`checkup.py --owd` 会调用 `owd.py` |
| `pyproject.toml`、`.python-version`、`uv.lock` | 本实验的 uv 环境（只用标准库） |
| `/run/lab04/` | `topo.sh` 的资源登记、档位与场景记录 |
| `/tmp/lab04-results/` | 路由日志；`checkup.py` 默认把画像与原始输出写在这里，`down` 之后仍保留 |

### 3.2 实验床

节点名、接口、地址与限速档位沿用 [Lab 3 指导书](../03/README.md) 3.2 节：2 spine（`r5`、`r6`）× 4 leaf（`r1`–`r4`）× 8 host（`h1a`–`h4b`），机架 $i$ 用 `10.0.i.0/24`，host 接入口双向 100 Mbit/s，leaf–spine 链路双向 100 或 50 Mbit/s。`topo.sh` 默认加载 Lab 2 的参考路由，想用自己的 `lsrd` 时写 `up --own`。

| 子命令 | 作用 |
| :--- | :--- |
| `up [--own]` ／ `check` ／ `show` ／ `down` | 搭建、自检（含 12 条路由的 ECMP 核对）、查看地址与路由、幂等拆除 |
| `rate 50\|100` | 切换全部 leaf–spine 档位；加载了场景时拒绝执行，先 `scenario clear` |
| `limit 节点 接口 速率` | 只改一个端口的 HTB 速率（Mbit/s） |
| `impair 节点 接口 netem 参数…` | 把一个端口的叶子 qdisc 换成 netem，保留限速，如 `impair r3 r3-h3a delay 5ms` |
| `clear [节点 接口]` | 恢复一个端口；不带参数时恢复全部端口、取消钉路 |
| `status` | 逐个检查 32 个限速端口与 leaf 的策略路由，列出所有偏离基线之处 |
| `scenario 名称` ／ `scenario clear` | 加载公开场景（加载前自动恢复基线）：`lecture06`（第 06 讲模块六）、`uplink-r1r5`（任务 5） |
| `blind [--seed N]` ／ `blind reveal` | 随机注入 1–2 项隐藏条件（任务 7）；`status` 只报告偏离端口的个数 |
| `pin [主机 r5\|r6]` ／ `unpin` | 在源 leaf 上按源地址固定 spine；不带参数时 a 类主机经 r5、b 类经 r6 |

### 3.3 骨架：给了什么，你写什么

```
2026/experiments/04/
├── checkup.py        【给定】参数、计划与用时估算、调度、写画像、打印矩阵；进阶与挑战的测量模式
└── netprof/
    ├── hosts.py      【给定】主机表（默认 8 台）、有向对与无序对
    ├── sysrun.py     【给定】在 namespace 中运行命令、一次性 iperf3 服务端、记录环境与负载
    ├── schema.py     【给定】画像格式 v1：校验 validate()、读取 load()；Lab 9 直接 import
    ├── measure.py    【给定】ping()、iperf3_once()
    │                 【TODO 5】throughput_runs()：一个有向对的多次独立测量
    ├── parse.py      【TODO 1】parse_ping()：取样本与收发数
    │                 【TODO 2】parse_iperf3()：取接收端速率、重传与两端 CPU
    ├── summary.py    【TODO 3】nearest_rank()、summarize_rtt()
    │                 【TODO 4】summarize_throughput()：中位数、极值与均值的 95% t 区间
    │                 【TODO 6】flags()：unreachable、lossy、cpu_bound
    └── extras.py     【TODO 7，进阶】is_bimodal()
                      【TODO 8，进阶】fit_transfer_curve()
```

一对主机的数据怎么流：

```
  checkup.py ──▶ measure.ping() ──原始文本──▶ parse.parse_ping()（TODO 1）──▶ summary.summarize_rtt()（TODO 3）──┐
             ──▶ measure.throughput_runs()（TODO 5）                                                            ├─▶ 一条 pairs[] 记录
                   └─ 每次 iperf3_once() ──JSON──▶ parse.parse_iperf3()（TODO 2）                               │   + flags()（TODO 6）
                 ──多次读数──▶ summary.summarize_throughput()（TODO 4）────────────────────────────────────────┘
  全部记录 ──▶ schema.validate() ──▶ profile.json；原始文本与 JSON ──▶ profile.raw/
```

*图 1：一对主机的数据从测量到画像记录。往返时间一路（`measure.ping()` → TODO 1 → TODO 3）得到 `rtt_ms`；吞吐一路（TODO 5 中每次调用 `iperf3_once()` → TODO 2 → TODO 4）得到 `throughput_mbps`；TODO 6 根据两路结果给出 `flags`。三者合成 `pairs[]` 中的一条记录，全部记录经 `schema.validate()` 写成 `profile.json`；`ping` 的原始文本与每次 `iperf3` 的 JSON 另存在 `profile.raw/`。*

每个 TODO 的 docstring 写明了输入、输出与要处理的边界情况；它们都是不需要 root 的纯函数（TODO 5 除外），先用离线测试调通，再上实验床。参考实现的 TODO 部分约 60 行，**难点不在代码量，而在想清楚每个字段的口径**。

### 3.4 画像格式 v1

`schema.py` 是 Lab 4 与 Lab 9 之间的接口：Lab 9 用 `schema.load(路径)` 读画像，用 `rtt(src, dst)`、`throughput(src, dst)`、`flags(src, dst)` 取数。下面是一份实测画像的节选（基线、默认参数；省略了其余 55 条记录）：

```output
{
 "schema": "lab04.netprofile/v1",
 "created": "2026-10-17T08:46:10-07:00",
 "environment": {"kernel": "7.0.0-38-generic", "cpus": 2, "iperf3": "iperf 3.20 (cJSON 1.7.15)",
   "testbed": "2026/experiments/04/topo.sh", "scenario": "baseline", "fabric_mbps": 100,
   "loadavg_start": 0.54, "loadavg_end": 0.41},
 "method": {
  "rtt": {"tool": "ping", "count": 20, "interval_s": 0.05, "pairs": "unordered", "statistic": "nearest-rank"},
  "throughput": {"tool": "iperf3", "seconds": 2, "omit_s": 1, "repeats": 3, "reading": "receiver",
                 "concurrent": false, "statistic": "median; ci95 = mean ± t·s/√n"}},
 "hosts": {"h1a": {"ip": "10.0.1.11", "rack": 1}, …},
 "pairs": [
  {"src": "h1a", "dst": "h3a",
   "rtt_ms": {"p50": 0.163, "p90": 0.207, "n": 20, "lost": 0},
   "throughput_mbps": {"median": 95.7, "min": 95.66, "max": 95.74, "n": 3, "ci95": [95.59, 95.81]},
   "flags": [], "cpu_max_pct": 10.8},
  …
 ]
}
```

| 字段 | 含义 |
| :--- | :--- |
| `environment` | 测量条件：内核、CPU 数、iperf3 版本、场景名、leaf–spine 档位，以及开始与结束时的 1 分钟平均负载 |
| `method` | 测量方法：`ping` 的次数与间隔、`iperf3` 的 `-t`、`-O`、重复次数，取接收端读数，统计方法 |
| `pairs[].rtt_ms` | 往返时间（ms）：最近秩法的 `p50`、`p90`，样本数 `n`，丢失数 `lost`。每个**无序对**测一次，两个方向的记录相同 |
| `pairs[].throughput_mbps` | 吞吐（Mbit/s，10⁶ bit/s）：多次独立测量的 `median`、`min`、`max`、`n` 与均值的 95% 区间 `ci95`（$n<2$ 时为 `null`） |
| `pairs[].flags` | 可信度标记：`unreachable`、`lossy`、`cpu_bound`、`bimodal`（进阶） |
| `pairs[].errors` | 失败原因；某项测过却没有结果时必须写明 |
| `pairs[].cpu_max_pct` | 各次测量中两端 CPU 占用的最大值（%），供核对 `cpu_bound` |
| `owd_ms`、`by_path`、`transfer_curve` | 进阶任务产生的可选字段，见任务 5、6 |

画像的语义要说清：**它记录的是“同一时刻只测一对、没有其他流量”时的读数**（`--concurrent` 除外）。它告诉调度器“这对主机单独通信时能有多快”，不告诉调度器“几对同时通信时会不会互相拖慢”——后者是任务 8 的问题。

### 3.5 测量口径

- **吞吐取接收端**（`end.sum_received`），单位 Mbit/s = 10⁶ bit/s；100 档单流应用吞吐的帧级上界为 $100\times1448/1514\approx95.6$ Mbit/s（第 06 讲 3.2 节）。
- **每次吞吐测量都是一个新的一次性服务端与一条新连接**。自然 ECMP 下，不同次可能走不同的 spine。
- **往返时间按无序对测**，由主机表中靠前的一方发起；本实验床的 RTT 在 0.1 ms 级，主要是主机软件转发与调度的噪声底（第 06 讲 1.4 节）。
- **同一时刻只测一对**。测量期间不要在同一台机器上运行其他实验或抓包，也不要让几个人同时测。
- **原始输出留存**：每份画像旁有同名 `.raw/` 目录，存 `ping` 文本与每次 `iperf3` 的 JSON。报告中的数字都应能回溯到这里。工具拒绝覆盖已有的画像与目录，重测请换 `--out`。

---

## 四、实验步骤

### 基础任务

#### 任务 1　搭实验床、读骨架、先写参考范围

```bash
# 1. 清理课堂与 Lab 3 的网络（节点重名），再搭完整实验床并自检
sudo bash 2026/experiments/03/classroom.sh down
sudo bash 2026/experiments/03/topo.sh down
sudo bash 2026/experiments/04/topo.sh up
sudo bash 2026/experiments/04/topo.sh check
sudo bash 2026/experiments/04/topo.sh status
```

```output
[*] 全部 leaf–spine 链路两端 egress = 100 Mbit/s；host 接入口保持 100 Mbit/s。
[*] 路由：Lab 2 参考实现（02/reference）。6 台路由器全部 Full；r1 的跨机架路由有两个下一跳。
[*] 下一步自检：sudo bash 2026/experiments/04/topo.sh check
[OK] 8 条上联往返、8 台 host 网关可达、跨机架往返。
[OK] 4 个 leaf 去往其他 3 个机架的 12 条路由均有两个下一跳。
10.0.3.0/24 proto 200 metric 20
	nexthop via 10.1.0.2 dev r1-r5 weight 1
	nexthop via 10.1.1.2 dev r1-r6 weight 1
[档位] leaf–spine 100 Mbit/s；host 接入 100 Mbit/s。场景：无。
[基线] 32 个限速端口均为 HTB + fq，速率与 burst 为基线值。
[基线] r1–r4 没有额外策略路由（自然 ECMP）。
```

```bash
# 2. 离线测试：此时 8 个通过（给定的格式校验）、26 个报错（全部来自尚未完成的 TODO）
(cd 2026/experiments/04 && uv run --frozen python -m unittest 2>&1 | tail -3)
```

```output
Ran 34 tests in 0.009s

FAILED (errors=26)
```

`-v` 可以看到每个测试的名字。`test_schema` 的 8 个测试开箱即过；`test_parse`、`test_summary` 对应 TODO 1–4、6，是基础任务要调通的 20 个；`test_extras` 的 6 个对应进阶的 TODO 7、8。

```bash
# 3. 只看计划与预计用时，不测量（不需要 root）
2026/experiments/04/.venv/bin/python 2026/experiments/04/checkup.py --dry-run
```

```output
[计划] 56 个有向对；往返时间 28 个无序对 × 20 个探测；吞吐 56 对 × 3 次 × (-O 1 + -t 2) 秒
[计划] 预计约 10.7 分钟
```

**读 `checkup.py` 与 `netprof/measure.py`、`netprof/sysrun.py`，回答三个检查点**（写进报告）：

1. 为什么往返时间只测 28 个无序对，吞吐却测 56 个有向对？在什么条件下，“往返时间对两个方向相同”这个前提会让你漏掉信息？（提示：第 06 讲 2.3 节。）
2. `iperf3_once()` 每次都起一个新的一次性服务端，而不是起一个长期服务端反复测。这样做的好处与代价各是什么？`iperf3_server()` 为什么要先用 `ss` 确认端口在监听，再启动客户端？
3. 按第 4 步的计划，你预计全量体检要多久？`plan()` 里每次吞吐测量多算的 0.6 秒是什么开销？任务 3 跑完后，用实际用时检验这个估计。

再写一张**参考范围表**（报告附表一），任务 2、3 的读数都要与它对照：

| 主机对类别 | 往返时间 | 吞吐 | 依据 |
| :--- | :--- | :--- | :--- |
| 同机架（如 h1a→h1b） | 待填 | 待填 | 待填 |
| 跨机架（如 h1a→h3a） | 待填 | 待填 | 待填 |

#### 任务 2　往返时间：取样本、算分位数（TODO 1、3）

补全 `parse.parse_ping()`、`summary.nearest_rank()` 与 `summary.summarize_rtt()`。fixtures 中有四份真实输出：全部收到、丢了 5 个、带 4 个重复回复（`(DUP!)`）、全部丢失。注意重复回复那份：`ping` 自己摘要中的 `max` 来自一个重复回复，**你的样本里不应出现它**。

```bash
# 4. 只跑与本任务有关的离线测试
(cd 2026/experiments/04 && uv run --frozen python -m unittest tests.test_parse.PingCases tests.test_summary.RankCases tests.test_summary.RttCases -v 2>&1 | tail -3)
```

```output
Ran 9 tests in 0.002s

OK
```

```bash
# 5. 只测往返时间：28 个无序对，每对 20 个探测
ck --skip-tput --out /tmp/lab04-results/rtt.json
```

```output
[计划] 56 个有向对；往返时间 28 个无序对 × 20 个探测；吞吐 0 对 × 3 次 × (-O 1 + -t 2) 秒
[计划] 预计约 0.6 分钟
[RTT]  h1a ⇄ h1b  p50 0.099 ms  p90 0.123 ms  丢 0/20
[RTT]  h1a ⇄ h2a  p50 0.156 ms  p90 0.192 ms  丢 0/20
[RTT]  h1a ⇄ h2b  p50 0.157 ms  p90 0.192 ms  丢 0/20
…（其余 24 个无序对略）
[RTT]  h4a ⇄ h4b  p50 0.094 ms  p90 0.116 ms  丢 0/20

往返时间 p50（ms）（行＝源，列＝目的）
             h1a     h1b     h2a     h2b     h3a     h3b     h4a     h4b
     h1a       ·   0.099   0.156   0.157   0.173   0.154   0.153   0.155
     h1b   0.099       ·   0.156   0.156   0.178   0.148   0.155   0.151
     h2a   0.156   0.156       ·   0.092   0.159   0.165   0.153   0.164
     h2b   0.157   0.156   0.092       ·   0.156   0.166   0.152   0.157
     h3a   0.173   0.178   0.159   0.156       ·   0.094   0.152   0.152
     h3b   0.154   0.148   0.165   0.166   0.094       ·   0.155   0.155
     h4a   0.153   0.155   0.153   0.152   0.152   0.155       ·   0.094
     h4b   0.155   0.151   0.164   0.157   0.152   0.155   0.094       ·

[标记] 无
[完成] 用时 0.5 分钟；画像 /tmp/lab04-results/rtt.json；原始输出 /tmp/lab04-results/rtt.raw/
```

**读数据**：

1. **用时**：28 个无序对各发 20 个探测，计划约 0.6 分钟，实际 0.5 分钟。
2. **两类主机对**：同机架 0.092–0.099 ms，跨机架 0.148–0.178 ms。跨机架多经过两台路由器（多两次软件转发），所以大约多出 0.06 ms；这个差别稳定可见，但仍在本机软件转发的噪声底之内（第 06 讲 1.4 节），**不能用来给跨机架的主机对排先后**。证据：任务 3 的全量体检中同一批主机对又测了一次，跨机架的 p50 为 0.143–0.190 ms，单个主机对两次之间相差 0.01–0.02 ms，例如 h1b⇄h3a 本次 0.178 ms、上一次 0.169 ms。
3. **矩阵是对称的**：这是工具的设计（每个无序对测一次，两个方向写同一个值），不是测量的发现。
4. **“丢 0/20”能说明什么**：按第 06 讲 2.4 节的 3/n 法则，20 个探测全部收到只能说丢包率大概率低于 15%。画像中的 `lost` 是这些探测的结果，不是丢包率的估计；想发现 1% 量级的丢包，需要多得多的探测（思考题 2）。

#### 任务 3　吞吐：读对字段、按次重复（TODO 2、4、5）

补全 `parse.parse_iperf3()`、`summary.summarize_throughput()` 与 `measure.throughput_runs()`。`iperf3_ok.json` 中发送端读数 96.41 Mbit/s 高于帧级上界，接收端读数是 95.34 Mbit/s，测试会检查你取的是哪一个。`summarize_throughput()` 的测试用的正是第 06 讲 5.2 节那 5 个读数。

```bash
# 6. 离线测试：TODO 1–4 完成后，基础部分 20 个测试中只剩 FlagCases 的 5 个报错（TODO 6 在任务 4 写）
(cd 2026/experiments/04 && uv run --frozen python -m unittest tests.test_parse tests.test_summary 2>&1 | tail -3)
```

```output
Ran 20 tests in 0.011s

FAILED (errors=5)
```

TODO 5 没有离线测试，要在实验床上检验。TODO 6 在任务 4 才写，此时全量体检会提示“还没有完成：TODO 6”。先写一个最简单的 `flags()`（例如总是返回空列表）让流程跑通，任务 4 再按规则补全——报告中要说明你在两个时刻用的分别是什么。

**先预测**：56 个有向对的吞吐中位数各应在什么范围？哪些对之间的差异应当可以忽略？用任务 1 的计划估计用时，记下开始时间。

```bash
# 7. 全量体检：28 个无序对的往返时间 + 56 个有向对的吞吐，每对 3 次
ck --out /tmp/lab04-results/base.json
```

**实测样例（逐对进度行只保留开头与结尾几行，矩阵保留全部；备课时输出目录不同，最后一行的路径已按本文命令改写）**：

```output
[计划] 56 个有向对；往返时间 28 个无序对 × 20 个探测；吞吐 56 对 × 3 次 × (-O 1 + -t 2) 秒
[计划] 预计约 10.7 分钟
[RTT]  h1a ⇄ h1b  p50 0.104 ms  p90 0.121 ms  丢 0/20
[RTT]  h1a ⇄ h2a  p50 0.155 ms  p90 0.199 ms  丢 0/20
[RTT]  h1a ⇄ h2b  p50 0.143 ms  p90 0.194 ms  丢 0/20
…（其余 25 个无序对略）
[吞吐] h1a → h1b  95.5 Mbit/s（95.4–95.7，n=3）
[吞吐] h1a → h2a  95.6 Mbit/s（95.6–95.8，n=3）
[吞吐] h1a → h2b  95.3 Mbit/s（92.7–95.4，n=3）
…（其余 52 个有向对略）
[吞吐] h4b → h4a  95.4 Mbit/s（95.4–95.5，n=3）
往返时间 p50（ms）（行＝源，列＝目的）
             h1a     h1b     h2a     h2b     h3a     h3b     h4a     h4b
     h1a       ·   0.104   0.155   0.143   0.163   0.165   0.168   0.153
     h1b   0.104       ·   0.168   0.156   0.169   0.160   0.146   0.147
     h2a   0.155   0.168       ·   0.110   0.169   0.164   0.190   0.175
     h2b   0.143   0.156   0.110       ·   0.158   0.154   0.153   0.154
     h3a   0.163   0.169   0.169   0.158       ·   0.110   0.164   0.171
     h3b   0.165   0.160   0.164   0.154   0.110       ·   0.149   0.150
     h4a   0.168   0.146   0.190   0.153   0.164   0.149       ·   0.099
     h4b   0.153   0.147   0.175   0.154   0.171   0.150   0.099       ·

吞吐中位数（Mbit/s）（行＝源，列＝目的）
             h1a     h1b     h2a     h2b     h3a     h3b     h4a     h4b
     h1a       ·    95.5    95.6    95.3    95.7    95.7    95.7    95.5
     h1b    95.4       ·    95.5    95.5    95.6    95.7    95.7    95.5
     h2a    95.5    95.7       ·    95.4    95.6    95.4    95.5    95.6
     h2b    95.8    95.3    95.7       ·    95.2    95.3    95.6    95.1
     h3a    95.2    95.3    95.3    95.5       ·    95.4    95.6    95.4
     h3b    95.3    95.6    95.7    95.3    95.5       ·    95.2    95.5
     h4a    95.7    95.7    95.7    95.7    95.5    95.7       ·    95.4
     h4b    95.7    95.3    95.7    95.8    95.7    95.5    95.4       ·

[标记] 无
[完成] 用时 9.9 分钟；画像 /tmp/lab04-results/base.json；原始输出 /tmp/lab04-results/base.raw/
```

**读数据**：

1. **用时**：计划预计 10.7 分钟，实际 9.9 分钟。168 次吞吐测量平均每次约 3.4 秒：计入 2 秒、预热 1 秒，起停服务端与建连约 0.4 秒。
2. **读数与参考范围**：56 个中位数都在 95.1–95.8 Mbit/s 之间，同机架与跨机架分不出差别。100 档下每个端口都是 100 Mbit/s，单流的瓶颈与跨不跨机架无关，这与参考范围表一致。
3. **为什么有 18 个中位数高于 95.6 的上界**：原始 JSON 给出原因。以 `tput-h4b-h2a-1.json` 为例，接收端在统计窗口内记了 24 248 320 字节，发送端在同一窗口只发出 24 117 248 字节，多出的 131 072 字节正好是 iperf3 一次读写的块（`blksize` 128 KiB）：两端的统计窗口在边界上相差了一块，例如预热结束时已在路上的一块被算进了接收端的窗口。2 秒窗口里一块约合 $8\times131072/2\approx0.5$ Mbit/s，所以 ±0.5 Mbit/s 以内的差异在这种测法的分辨率之内。任务 4 会看到，加长 `-t` 能缩小它。
4. **区间**：区间宽度的中位数约 1.1 Mbit/s；最宽的是 h1a→h2b，三次读数为 92.69、95.31、95.43，一次偏低就把区间撑到 90.64–98.31。上限超过了容量，因为 t 区间描述的是“均值的统计不确定度”，并不知道物理上界；n = 3 时它对单个偏离很敏感，这是任务 4 讨论重复次数的出发点。
5. **可信度**：两端 CPU 占用最大 13.8%，平均负载从 0.54 降到 0.41（2 核），没有任何标记。注意“没有标记”只说明你写的规则没有触发，不说明测量没有问题——任务 4 会找出规则的盲区。

#### 任务 4　方法学：用数据定参数，给可信度打标（TODO 6）

默认参数（`-t 2 -O 1`、3 次）是我们替你选的。本任务用数据检验它们，并补全可信度标记。

**（一）窗口、预热与重复次数。** 在一对跨机架主机上，比较几组参数的读数、区间宽度与耗时：

```bash
# 8. 同一对主机，四组参数各测 5 次；只测吞吐
for cfg in 1:0 1:1 2:1 5:1; do
  t=${cfg%:*}; o=${cfg#*:}
  ck --pairs h1a:h3a --skip-rtt --tput-seconds "$t" --tput-omit "$o" --tput-repeats 5 \
     --out "/tmp/lab04-results/method-t$t-o$o.json" | grep -E '^\[(吞吐|完成)'
done
```

```output
[吞吐] h1a → h3a  94.9 Mbit/s（94.7–95.0，n=5）
[完成] 用时 0.1 分钟；画像 /tmp/lab04-results/method-t1-o0.json；原始输出 /tmp/lab04-results/method-t1-o0.raw/
[吞吐] h1a → h3a  95.0 Mbit/s（94.6–95.3，n=5）
[完成] 用时 0.2 分钟；画像 /tmp/lab04-results/method-t1-o1.json；原始输出 /tmp/lab04-results/method-t1-o1.raw/
[吞吐] h1a → h3a  95.6 Mbit/s（95.5–95.7，n=5）
[完成] 用时 0.3 分钟；画像 /tmp/lab04-results/method-t2-o1.json；原始输出 /tmp/lab04-results/method-t2-o1.raw/
[吞吐] h1a → h3a  95.5 Mbit/s（95.3–95.5，n=5）
[完成] 用时 0.5 分钟；画像 /tmp/lab04-results/method-t5-o1.json；原始输出 /tmp/lab04-results/method-t5-o1.raw/
```

**读数据**：把 5 次读数（各次 JSON 在对应 `.raw/` 目录中）与耗时整理成表：

| `-t` / `-O` | 中位数 | 最小–最大 | 区间宽度 | 5 次耗时 | 全量体检（56 对 × 3 次）估计 |
| :--- | ---: | :--- | ---: | ---: | ---: |
| 1 / 0 | 94.88 | 94.73–95.01 | 0.28 | 0.1 分钟 | 约 4 分钟 |
| 1 / 1 | 95.05 | 94.59–95.26 | 0.62 | 0.2 分钟 | 约 7 分钟 |
| 2 / 1 | 95.58 | 95.52–95.71 | 0.22 | 0.3 分钟 | 约 10 分钟 |
| 5 / 1 | 95.49 | 95.33–95.53 | 0.19 | 0.5 分钟 | 约 18 分钟 |

1. **不预热（`-O 0`）**：读数整齐，却整体偏低约 0.7 Mbit/s。1 秒窗口从建连开始计时，连接建立与开头的爬升都算在里面。**分散小不等于准**：这是一个系统偏差，重复多少次都消不掉。
2. **只测 1 秒（`-t 1 -O 1`）**：去掉了开头的偏低，但分散变大。任务 3 中“一块 128 KiB”的边界效应在 1 秒窗口里约合 1 Mbit/s，是 2 秒窗口的两倍。
3. **2 秒与 5 秒**：中位数都贴近 95.6 的上界，5 秒的分散更小，但全量体检的耗时将近翻倍。
4. **怎么选**：参数要按“画像要支持什么决策”来定。Lab 9 要区分的是 95 与 28、95 与 19 这类差别，0.5 Mbit/s 以内的差异不影响放置，所以 `-t 2 -O 1` 足够；如果要比较两条只差 1–2% 的路径，就该用更长的窗口。注意这些结论只在本实验床的低 RTT 下成立：RTT 到几十毫秒时，慢启动会让短窗口的偏差大得多（第 06 讲 5.1 节）。

**（二）CPU 争用与 `cpu_bound` 标记。** 补全 `summary.flags()`，让 `test_summary.FlagCases` 通过；此时基础部分的 20 个离线测试应全部通过。然后照第 06 讲 5.4 节，临时去掉 h1a→h1b 两个端口的限速，分别在空闲与占满 CPU 时体检这一对：

```bash
# 9. 去掉 h1a 出口与 r1→h1b 出口的限速（同机架这对主机不再受 100 Mbit/s 约束）
sudo ip netns exec h1a tc qdisc del dev eth0 root
sudo ip netns exec r1 tc qdisc del dev r1-h1b root

# 10. 空闲时体检；再在每个 CPU 上各起一个 yes，重复一次，然后结束 yes
ck --pairs h1a:h1b,h1a:h3a --skip-rtt --out /tmp/lab04-results/cpu-idle.json | grep -E '^\[(吞吐|标记)'
for i in $(seq "$(nproc)"); do yes > /dev/null & done
ck --pairs h1a:h1b,h1a:h3a --skip-rtt --out /tmp/lab04-results/cpu-busy.json | grep -E '^\[(吞吐|标记)'
sudo pkill -x yes

# 11. 恢复两个端口，并核对基线
sudo bash 2026/experiments/04/topo.sh clear h1a eth0
sudo bash 2026/experiments/04/topo.sh clear r1 r1-h1b
sudo bash 2026/experiments/04/topo.sh status
```

```output
[吞吐] h1a → h1b  4165.8 Mbit/s（4119.0–4273.4，n=3）
[吞吐] h1a → h3a  95.4 Mbit/s（95.4–95.8，n=3）
[标记] h1a→h1b：cpu_bound
[吞吐] h1a → h1b  2287.5 Mbit/s（2153.5–3033.6，n=3）
[吞吐] h1a → h3a  95.4 Mbit/s（95.3–95.6，n=3）
[标记] 无
[*] h1a eth0 已恢复基线（HTB 100 Mbit/s + fq）。
[*] r1 r1-h1b 已恢复基线（HTB 100 Mbit/s + fq）。
[档位] leaf–spine 100 Mbit/s；host 接入 100 Mbit/s。场景：无。
[基线] 32 个限速端口均为 HTB + fq，速率与 burst 为基线值。
[基线] r1–r4 没有额外策略路由（自然 ECMP）。
```

**读数据**：下表把画像中的读数与各次 JSON 的 CPU 字段放在一起（`host_total` 为发送端 iperf3 进程，`remote_total` 为接收端），平均负载取自画像的 `environment`：

| 条件 | 主机对 | 吞吐中位数 | 各次 `host_total` | 平均负载（开始→结束） | 标记 |
| :--- | :--- | ---: | :--- | :--- | :--- |
| 空闲 | h1a→h1b（不限速） | 4165.8 | 79.7、90.9、99.2 | 0.36 → 0.94 | `cpu_bound` |
| 空闲 | h1a→h3a（100 档） | 95.4 | 0.9、1.3、0.9 | 同上 | 无 |
| 占满 2 核 | h1a→h1b（不限速） | 2287.5 | 58.1、46.5、57.5 | 0.94 → 1.68 | **无** |
| 占满 2 核 | h1a→h3a（100 档） | 95.4 | 0.5、0.5、0.7 | 同上 | 无 |

1. **规则发现了什么**：空闲时不限速的那一对，发送进程用满了一个核，读数反映的是 CPU 而不是网络，`cpu_bound` 标对了。限速的那一对 CPU 占用不到 2%，没有被误标。
2. **规则发现不了什么**：占满 CPU 后，不限速的那一对掉了 45%，iperf3 自己的 CPU 占用反而降到 47–58%，因为它抢不到 CPU。规则只看 iperf3 自己用了多少，**看不见别的进程在争用**，于是没有标记。这是一条规则的盲区，不是代码的错误。
3. **哪些证据能补上**：画像 `environment` 中的平均负载从基线的 0.4 左右升到 1.68（2 核）。但 1 分钟平均负载有滞后，测量开始时只有 0.94。报告中提出你的改进，例如在每对测量前后各读一次负载、读 `/proc/stat` 算这段时间的 CPU 空闲比例，或者把“读数远高于任何限速档位”也作为 CPU 主导的信号。说明改进后的规则依据什么阈值，还会漏掉什么。
4. **对 Lab 9 意味着什么**：100 档的读数在 CPU 被占满时仍然可信（95.4 未变），所以实验床把链路压到 100 Mbit/s 一档。但第 06 讲 5.4 节看到，亚毫秒级的往返时间会随 CPU 状态改变；画像只用平均负载提醒“测量时机器不空闲”，不修正读数。

**（三）交付基线画像。** 用你在（一）中定下的参数与（二）中改进后的标记，重新做一次全量体检，命名为 `/tmp/lab04-results/profile-baseline.json`。这份画像随报告提交，Lab 9 会用到它。报告中写明：参数取值及依据（引用（一）的数据）、`CPU_LIMIT` 的取值及依据、你的标记规则还发现不了什么。

### 进阶任务

#### 任务 5　一对主机，两条路（TODO 7）

场景 `uplink-r1r5` 只把 r1 与 r5 之间那一条上联的两个方向降到 20 Mbit/s，其余不变。

**先预测**：哪些有向对会受影响？自然 ECMP 下，h1a→h3a 重复测 7 次，读数会是什么样？只测 3 次时，有多大概率完全看不出异常？（提示：每次连接各自按哈希选 spine，两条路概率各半。）

补全 `extras.is_bimodal()`，让 `tests.test_extras.BimodalCases` 通过。工具会在某对主机有 3 次以上读数且判为两簇时打上 `bimodal` 标记。

```bash
# 12. 加载场景；从 h1a 出发测一行吞吐，每对 7 次
sudo bash 2026/experiments/04/topo.sh scenario uplink-r1r5
ck --src h1a --skip-rtt --tput-repeats 7 --out /tmp/lab04-results/t5-natural.json

# 13. 分路测量：对跨机架的对，先把 h1a 钉在 r5 测一遍，再钉在 r6 测一遍（工具结束时自动 unpin）
ck --src h1a --skip-rtt --by-path --out /tmp/lab04-results/t5-bypath.json
```

**实测样例（两条命令的进度行与标记；只有一行源主机，矩阵略）**：

```output
[*] 场景 uplink-r1r5 已加载。结束后执行 topo.sh scenario clear，再用 topo.sh status 核对。
[计划] 7 个有向对；往返时间 0 个无序对 × 20 个探测；吞吐 7 对 × 7 次 × (-O 1 + -t 2) 秒
[计划] 预计约 2.9 分钟
[吞吐] h1a → h1b  95.4 Mbit/s（95.3–95.5，n=7）
[吞吐] h1a → h2a  95.2 Mbit/s（18.8–95.7，n=7）
[吞吐] h1a → h2b  18.9 Mbit/s（18.6–95.6，n=7）
[吞吐] h1a → h3a  18.9 Mbit/s（18.9–95.8，n=7）
[吞吐] h1a → h3b  18.9 Mbit/s（18.7–95.6，n=7）
[吞吐] h1a → h4a  95.3 Mbit/s（18.6–95.8，n=7）
[吞吐] h1a → h4b  95.2 Mbit/s（18.8–96.0，n=7）
[标记] h1a→h2a：bimodal；h1a→h2b：bimodal；h1a→h3a：bimodal；h1a→h3b：bimodal；h1a→h4a：bimodal；h1a→h4b：bimodal
[完成] 用时 2.7 分钟；画像 /tmp/lab04-results/t5-natural.json；原始输出 /tmp/lab04-results/t5-natural.raw/
[计划] 7 个有向对；往返时间 0 个无序对 × 20 个探测；吞吐 7 对 × 3 次 × (-O 1 + -t 2) 秒；分路 6 对
[计划] 预计约 3.4 分钟
[吞吐] h1a → h1b  95.1 Mbit/s（95.0–95.2，n=3）
[吞吐] h1a → h2a  95.7 Mbit/s（18.9–95.8，n=3）
[吞吐] h1a → h2b  95.6 Mbit/s（18.7–95.7，n=3）
[吞吐] h1a → h3a  18.9 Mbit/s（18.9–95.7，n=3）
[吞吐] h1a → h3b  95.5 Mbit/s（18.9–95.6，n=3）
[吞吐] h1a → h4a  95.0 Mbit/s（18.9–95.2，n=3）
[吞吐] h1a → h4b  18.9 Mbit/s（18.7–95.3，n=3）
[吞吐-r5] h1a → h2a  18.8 Mbit/s（18.6–18.9，n=3）
[吞吐-r5] h1a → h2b  18.9 Mbit/s（18.9–19.4，n=3）
[吞吐-r5] h1a → h3a  18.9 Mbit/s（18.9–18.9，n=3）
[吞吐-r5] h1a → h3b  18.9 Mbit/s（18.9–18.9，n=3）
[吞吐-r5] h1a → h4a  18.6 Mbit/s（18.6–18.9，n=3）
[吞吐-r5] h1a → h4b  18.9 Mbit/s（18.7–18.9，n=3）
[吞吐-r6] h1a → h2a  95.6 Mbit/s（95.2–95.7，n=3）
[吞吐-r6] h1a → h2b  95.6 Mbit/s（95.4–95.6，n=3）
[吞吐-r6] h1a → h3a  95.7 Mbit/s（95.5–95.7，n=3）
[吞吐-r6] h1a → h3b  95.2 Mbit/s（95.1–95.7，n=3）
[吞吐-r6] h1a → h4a  95.3 Mbit/s（95.2–95.3，n=3）
[吞吐-r6] h1a → h4b  95.7 Mbit/s（95.4–95.7，n=3）
[标记] h1a→h2a：bimodal；h1a→h2b：bimodal；h1a→h3a：bimodal；h1a→h3b：bimodal；h1a→h4a：bimodal；h1a→h4b：bimodal
[完成] 用时 3.2 分钟；画像 /tmp/lab04-results/t5-bypath.json；原始输出 /tmp/lab04-results/t5-bypath.raw/
```

**读数据**：

1. **影响范围**：同机架的 h1a→h1b 不经过上联，7 次都在 95.3–95.5 Mbit/s；6 个跨机架对都受影响。场景也限制了 r5→r1 方向，所以发往 h1a 的跨机架对同样受影响，本步没有测。
2. **一对主机，两簇读数**：自然 ECMP 下 7 次读数分成约 18.8 与约 95 两簇，6 对全部被标记 `bimodal`。物理情况对这 6 对完全一样，中位数却有的是 18.9、有的是 95.2，取决于 7 次里哪一簇占多数。区间同样失去意义：h1a→h3a 的 `ci95` 为 13.82–89.68，覆盖的范围里没有一个真实读数。**对两簇数据，中位数与 t 区间都会误导**。
3. **测几次才看得出**：每次连接独立地按哈希选 spine，两条路各半。3 次全落在同一条路上的概率为 $2\times(1/2)^3=25\%$，7 次时为 $2\times(1/2)^7\approx1.6\%$。本次两轮都没有漏掉，但默认 3 次的全量体检平均会有四分之一的受影响对看起来“正常”。
4. **分路测量把两簇拆开**：钉在 r5 时 6 对都是 18.6–18.9 Mbit/s，钉在 r6 时是 95.2–95.7 Mbit/s。20 Mbit/s 端口的帧级上界为 $20\times1448/1514\approx19.1$ Mbit/s，读数略低于它。`by_path` 字段记录了两条路各自的读数，这是能把“为什么分两簇”说清楚的证据。

报告中回答：Lab 9 的调度器读 `throughput("h1a", "h3a")` 时应该得到什么？只给中位数、只给最小值、给两条路各自的读数，分别会让调度器做出什么决定？给出你的表示方法与理由。结束后 `scenario clear`。

#### 任务 6　单向延迟与传输时间曲线（TODO 8）

**（一）单向延迟。** 加载第 06 讲的场景，对与 h2b 相关的两个方向发单向探针：

```bash
# 14. 第 06 讲场景；h1a 与 h2b、h1a 与 h4a 两个方向各发 50 个单向探针
sudo bash 2026/experiments/04/topo.sh scenario lecture06
ck --pairs h1a:h2b,h2b:h1a,h1a:h4a,h4a:h1a --owd 50 --skip-tput --out /tmp/lab04-results/t6-owd.json
```

**实测样例（矩阵略）**：

```output
[*] 场景 lecture06 已加载。结束后执行 topo.sh scenario clear，再用 topo.sh status 核对。
[计划] 4 个有向对；往返时间 2 个无序对 × 20 个探测；吞吐 0 对 × 3 次 × (-O 1 + -t 2) 秒；单向延迟 50 包
[计划] 预计约 0.2 分钟
[RTT]  h1a ⇄ h2b  p50 4.240 ms  p90 4.300 ms  丢 0/20
[RTT]  h1a ⇄ h4a  p50 0.160 ms  p90 0.189 ms  丢 0/20
[单向] h1a → h2b  p50 4.316 ms  p90 4.428 ms
[单向] h2b → h1a  p50 0.245 ms  p90 0.345 ms
[单向] h1a → h4a  p50 0.256 ms  p90 0.388 ms
[单向] h4a → h1a  p50 0.224 ms  p90 0.360 ms
[标记] 无
[完成] 用时 0.1 分钟；画像 /tmp/lab04-results/t6-owd.json；原始输出 /tmp/lab04-results/t6-owd.raw/
```

**读数据**：两对的往返时间分别约 4.24 ms 与 0.16 ms，但往返时间分不出方向。单向探针给出 h1a→h2b 约 4.3 ms、h2b→h1a 约 0.25 ms：延迟只在进入 h2b 的方向上。h1a 与 h4a 之间两个方向都在 0.22–0.26 ms，也就是 `owd.py` 自身的噪声底（第 06 讲 2.3 节）：机架 4 的条件是限速，并不增加空载延迟。画像中每个有向对多了一个 `owd_ms` 字段，统计方法与 `rtt_ms` 相同。

**（二）传输时间曲线。** 补全 `extras.fit_transfer_curve()`，让 `tests.test_extras.CurveCases` 通过。工具用 Lab 3 的 `transfer.py` 测不同数据量的完成时间（接收端确认收齐才停表），再拟合 $T=a+8m/(b\times10^6)$：

**先预测**：本场景中，h1a→h3a（无条件）、h1a→h2b（进入 h2b 的方向加 4 ms）、h1a→h4a（进入机架 4 限速 30 Mbit/s）的 $a$ 与 $b$ 各约多少？哪一对的 $a$ 最大，大约是几个往返时间？

```bash
# 15. 四档数据量：10 KB、100 KB、1 MB、10 MB；每档一次定量传输
ck --pairs h1a:h3a,h1a:h2b,h1a:h4a --skip-rtt --skip-tput --curve 10000,100000,1000000,10000000 \
   --out /tmp/lab04-results/t6-curve.json
sudo bash 2026/experiments/04/topo.sh scenario clear
```

**实测样例**：

```output
[计划] 3 个有向对；往返时间 0 个无序对 × 20 个探测；吞吐 0 对 × 3 次 × (-O 1 + -t 2) 秒；传输曲线 4 档
[计划] 预计约 0.2 分钟
[曲线] h1a → h3a  0.01 MB 2.9 ms，0.1 MB 9.0 ms，1 MB 85.9 ms，10 MB 839.4 ms
[曲线] h1a → h3a  a = 1.6 ms，b = 95.5 Mbit/s，最大残差 0.9 ms
[曲线] h1a → h2b  0.01 MB 11.0 ms，0.1 MB 21.9 ms，1 MB 97.1 ms，10 MB 850.4 ms
[曲线] h1a → h2b  a = 12.3 ms，b = 95.4 Mbit/s，最大残差 2.1 ms
[曲线] h1a → h4a  0.01 MB 3.4 ms，0.1 MB 28.9 ms，1 MB 281.1 ms，10 MB 2796.1 ms
[曲线] h1a → h4a  a = 1.0 ms，b = 28.6 Mbit/s，最大残差 0.5 ms
[标记] 无
[完成] 用时 0.1 分钟；画像 /tmp/lab04-results/t6-curve.json；原始输出 /tmp/lab04-results/t6-curve.raw/
[*] 已恢复基线：全部端口 HTB + fq、档位不变，钉路已取消。
```

**读数据**：

1. **$b$ 与吞吐一致**：h1a→h3a、h1a→h2b 的 $b$ 约 95.4–95.5 Mbit/s，h1a→h4a 约 28.6 Mbit/s，分别对应 100 与 30 Mbit/s 端口的帧级上界（95.6、28.7）。4 ms 的单向延迟没有降低 $b$。
2. **$a$ 把延迟变成了成本**：h1a→h2b 的 $a$ 约 12 ms，约为其往返时间（4.24 ms，见第一步）的 3 倍。建立连接要一个往返，开头的数据受拥塞窗口限制要再走几个往返，接收端的回执还要一个往返。另外两对的往返时间约 0.16 ms，$a$ 只有 1 ms 左右，主要是进程与系统调用的开销。
3. **对两类作业意味着什么**：传 10 KB 时，h1a→h2b 要 11.0 ms，h1a→h3a 只要 2.9 ms，固定开销决定了小消息的成本；传 10 MB 时，h1a→h4a 要 2.8 s，h1a→h3a 只要 0.84 s，$b$ 决定了大数据量的成本。这正是第 06 讲 1.1 节的作业 B 与作业 A；第 10 讲的 α-β 模型 $T=\alpha+\beta m$ 中，$a$ 对应 α，$8/(b\times10^6)$ 对应每字节的 β。
4. **看残差再信 $a$**：h1a→h2b 的最大残差约 2 ms，说明直线只是近似：小传输要等整数个往返，不是严格线性。备课时再测一次，三对的 $a$ 分别为 0.7、11.8、0.4 ms，$b$ 几乎不变：往返时间很小时，$a$ 的读数在 ±1 ms 内波动，只有 h1a→h2b 的 $a$ 明显高于这个范围。
5. **数据量要覆盖你关心的区间**：备课时曾只用 0.1、1、10、30 MB 四档拟合 h1a→h3a，得到 $a=-5.5$ ms。固定开销不可能为负：30 MB 那一档的速率略低于 10 MB，最小二乘被大数据量的点主导，截距就被“拉”到了负值。要估计 $a$，就要有足以让 $a$ 显现的小数据量，并检查残差。

### 挑战任务

#### 任务 7　盲测体检

`topo.sh blind` 从六类条件中随机选 1–2 项、随机落点注入：机架入方向限速、主机接入单方向延迟、主机接入随机丢包、单条上联限速、主机自身出口限速、某台 spine 全部下行加延迟。**只允许端到端测量**：可以用 `checkup.py`、`ping`、`iperf3`、`owd.py`、`traceroute`，不能在路由器上查 `tc` 或路由配置，也不能先看 `blind reveal` 或 `status` 的细节。

```bash
# 16. 注入隐藏条件，记下打印出的 seed
sudo bash 2026/experiments/04/topo.sh blind

# 17. ……用你的方法体检、定位（参数自定，记录每一步的命令与理由）……

# 18. 写完结论后再看答案，然后恢复基线
sudo bash 2026/experiments/04/topo.sh blind reveal
sudo bash 2026/experiments/04/topo.sh scenario clear
```

至少做两个不同的 seed。每个 seed 交一张诊断表：发现了什么异常（引用画像中的数字与标记）、定位到哪一段与哪个方向、是哪一类条件、置信度与依据、还有哪些候选没能排除。报告最后对照 `blind reveal`，分析判对与判错的原因。

备课时用两个 seed 各做过一次默认参数的全量体检（各约 10 分钟），每项条件都在画像中留下了可见的痕迹：

1. **先看矩阵的形状，再看单个数**：整行偏低（连同机架的格子一起）指向源主机自己的发送出口；整列偏低指向目的一侧。同机架的格子正常、跨机架的格子有高有低并多被标为 `bimodal`，指向某一条上联，可以用 `--by-path` 拆开。往返时间也会分两簇：部分跨机架格子高出约 4 ms、同机架全部正常、也没有哪台主机整行整列偏高，说明问题在 fabric 中某台 spine 上；`pin` 同样改变 `ping` 走的 spine，可以用来确认是哪一台。还要留意任务 5 说过的情形：某一对 3 次都落在慢的那条路上时，读数整齐地偏低，不会被标为 `bimodal`。
2. **丢包最难从 `ping` 看出**：1% 的随机丢包在全量体检的往返时间探测中只露出 1 次（一个 `lossy` 标记）。更显眼的线索是进入那台主机的吞吐普遍下降，而且同一对主机的几次读数相差很大，有的还被标成了 `bimodal`——这个标记只看读数是否分成两簇，不问原因。要证实是丢包，需要对可疑方向发多得多的探测（3/n 法则），或者用单向探针统计丢失。

#### 任务 8　共享瓶颈（选做）

画像只描述“单独通信时”的读数。调度器同时放置多个作业时，还需要知道哪些主机对会争用同一段链路。`--concurrent` 让所选的有向对同时各测一次：

```bash
# 19. 对照：两对主机都钉在 r5（共用 r1→r5 与 r5→r3），同时测
sudo bash 2026/experiments/04/topo.sh pin h1a r5
sudo bash 2026/experiments/04/topo.sh pin h1b r5
ck --pairs h1a:h3a,h1b:h3b --skip-rtt --concurrent --out /tmp/lab04-results/t8-pinned.json
sudo bash 2026/experiments/04/topo.sh unpin
```

**实测样例（矩阵略）**：

```output
[*] h1a（10.0.1.11）发出的报文在 r1 固定经 r5。
[*] h1b（10.0.1.12）发出的报文在 r1 固定经 r5。
[计划] 2 个有向对；往返时间 0 个无序对 × 20 个探测；吞吐 2 对 × 1 次 × (-O 1 + -t 2) 秒
[计划] 预计约 0.1 分钟
[并发] h1a → h3a  47.7 Mbit/s
[并发] h1b → h3b  47.8 Mbit/s
[标记] 无
[完成] 用时 0.1 分钟；画像 /tmp/lab04-results/t8-pinned.json；原始输出 /tmp/lab04-results/t8-pinned.raw/
[*] 已取消全部钉路，回到自然 ECMP。
```


两对同时各得 47.7、47.8 Mbit/s，约为单独测量（95 左右）的一半：它们被钉在同一条 r1→r5 上联，又经同一条 r5→r3 下行，两段 100 Mbit/s 由两条流分享。作为对照，备课时还让 h1a→h3a 与 h2a→h4a 同时测（不钉路），读数为 95.1 与 95.4 Mbit/s：两对的源机架、目的机架都不同，没有共用的限速端口。

设计一组并发测量，在**不钉路**的自然 ECMP 下找出全网中哪些主机对组合会共享瓶颈、哪些不会；说明你如何区分“共享瓶颈”与“碰巧被哈希到同一条上联”。可以把结论写成画像顶层的可选字段 `shared`（格式自定，在报告中说明），供 Lab 9 参考。

---

## 五、故障排查

| 现象 | 先查什么 | 常见原因 |
| :--- | :--- | :--- |
| `topo.sh up` 报某个 namespace 已存在 | `ip netns list` | 课堂或 Lab 3 的网络没清理：执行 `classroom.sh down` 或 `03/topo.sh down` |
| `checkup.py` 提示“还没有完成：TODO n” | 对应的离线测试 | 函数仍是 `raise NotImplementedError` |
| 提示“需要 root” | 命令是否以 `sudo` 开头 | 没有用 `ck` 或漏了 `sudo` |
| 某对吞吐“全部失败”、`errors` 中有 Connection refused | `ip netns pids <目的主机>`、`ps -ef \| grep iperf3` | 残留的 iperf3 进程占着端口：`sudo pkill -x iperf3` 后重测 |
| 吞吐普遍低于 95 Mbit/s | `topo.sh status`、`uptime`、`cpu_max_pct` | 上一个任务的条件没恢复；机器上还有别的负载；几个测量同时在跑 |
| 往返时间全部丢失（`unreachable`） | `topo.sh check`、`ip -n h1a route` | 路由没就绪或拓扑被改动 |
| 提示 `.raw` 已存在 | 换一个 `--out` | 工具拒绝覆盖上一次的证据 |
| `topo.sh rate` 被拒绝 | `topo.sh status` | 加载了场景：先 `scenario clear` |

---

## 六、思考题

1. **画像能不能替代业务测量？** 某作业在 h1a、h3a 上运行，画像说二者之间 95 Mbit/s，作业实际只用到 40 Mbit/s。列出至少三个可能的原因，并说明各自要看什么证据。
2. **探测数怎么定？** 一条链路的真实丢包率为 0.5%。要有约 95% 的把握在 RTT 测量中看到至少一个丢失，每对主机要发多少个探测？画像要覆盖 28 个无序对，这样做的代价是什么？有没有更省的办法？
3. **测量会不会骗过自己？** 如果某个端口配置了很大的 burst，`-t 2` 的测量会读到什么？你的画像工具如何发现这种情况？（提示：第 06 讲 4.4 节。）
4. **多久测一次？** Lab 9 的调度器每次放置前都要用画像。全量体检要 10 分钟左右，网络条件随时可能变化。你会怎样安排画像的更新：全量、增量、按需？各自的风险是什么？
5. **两个维度怎么合成一个数？** 调度器最终要比较“放在 A 还是放在 B”。用第 06 讲 1.1 节的两类作业，写出由画像中的往返时间与吞吐估算通信时间的公式，并说明它在什么情况下会严重低估。

---

## 七、提交要求

| 层次 | 提交内容 | 分值 |
| :--- | :--- | :--- |
| 基础任务 1–4，人人完成 | 补全的 `netprof/`（离线测试 `test_parse`、`test_summary` 全部通过）；任务 1 的检查点与参考范围表；任务 2、3 的预测、读数与解释（含用时预测与实际）；任务 4 的参数对照与依据、CPU 实验与标记规则的盲区；基线画像 `profile-baseline.json` | 60 |
| 进阶任务 5 | `is_bimodal` 通过测试；两份画像；对“一对主机两条路”的表示方法与理由 | 15 |
| 进阶任务 6 | `fit_transfer_curve` 通过测试；单向延迟与曲线两份画像；$a$、$b$ 的预测与解释 | 10 |
| 挑战任务 7 | 至少两个 seed 的诊断表与对照分析 | 10 |
| 挑战任务 8（选做） | 并发测量设计、数据与 `shared` 的格式说明 | 5 |

报告建议 3–5 页，做了进阶与挑战可增至 6–8 页。每项都要有预测、证据、解释：预测被推翻同样有价值，评分看证据是否充分、解释是否不超出数据。

提交代码目录 `netprof/`、报告，以及各画像文件与它们的 `.raw/` 目录（都是文本与 JSON，体积很小）。不提交 `.venv/` 与 `__pycache__/`。

```bash
# 20. 打包代码与 /tmp/lab04-results 下的全部画像及原始输出
tar -czf "$HOME/lab04-submission.tgz" -C 2026/experiments/04 netprof -C /tmp/lab04-results .
tar -tzf "$HOME/lab04-submission.tgz" | head
```

全部做完后清理：`sudo bash 2026/experiments/04/topo.sh down`（重复执行应成功）；若接着做后续实验，可以保留实验床。

### 维护与验证

本文样例的来源与验证范围：

| 项目 | 内容 |
| :--- | :--- |
| 环境 | 2026-10-17，备课虚拟机：Ubuntu 26.04.1、Linux `7.0.0-38-generic`、x86_64、2 核 2.8 GB；iproute2 6.19.0、iputils 20250605、iperf3 3.20、Python 3.12.15；实验床使用 Lab 2 参考路由 |
| 离线测试 | 骨架原样为 34 个测试：8 个通过、26 个报错；只缺 TODO 6 时，`test_parse` 与 `test_summary` 为 20 个中 5 个报错。补全 TODO 的参考实现 34 个全部通过 |
| 实验床 | 任务 1–8 的全部命令按本文原样运行（`ck` 指向补全了 TODO 的临时副本），实测样例均来自这些运行；全量体检实际 9.9 分钟（计划估计 10.7 分钟）；`blind` 用 seed 4 与 seed 12 各做一次全量体检，四类条件均在画像中可见；任务 6 的曲线命令连续运行两次 |
| 未覆盖 | Ubuntu 22.04／24.04；学生自己的实现与 `up --own`；`--hosts` 指定的其他拓扑；六类盲测条件中的“主机接入单方向延迟”与“机架入方向限速”只在第 06 讲场景中出现过，没有作为盲测条件单独验证 |

阅读版 `README.html` 由 `2026/tools/build_lab4_html.py` 从本文生成，用法见 [`tools/README.md`](../../tools/README.md)。仓库中的 TODO 保持留白；参考实现只用于备课验证，没有放进仓库。学生实现须独立验收，样例中的端口、用时与单次读数不作为验收标准。`tests/fixtures/` 中的 `ping` 输出与 `iperf3` JSON 采自上述环境：丢包与重复回复由 `topo.sh impair` 注入 netem 产生，连接被拒的 JSON 来自不存在服务端的端口。
