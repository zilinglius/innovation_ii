# Lab 5　长尾延迟与对冲请求

> 对应第 07 讲　｜　建议用时 1 周（基础约 3 小时；进阶任务 4 约 1 小时、任务 5 约 1.5 小时；挑战任务 6 约 1.5 小时，任务 7 选做约 0.5 小时）　｜　截止：2026-11-30　｜　产出：能预测尾部放大的模型、带预算的对冲策略，以及一份“哪种慢该用哪种措施”的证据

第 07 讲的综合动手里，你用给定的工具和固定的对冲延迟比较了三种“慢”。本实验往前走三步：把放大规律写成能和实测对账的预测函数；扫描对冲延迟，找到值得付出的代价；再实现自适应延迟和对冲预算，看它们能不能同时兼顾“对冲有用”和“对冲有害”的场景。

任务分三层：**基础**（任务 1–3）人人完成；**进阶**（任务 4、5）实现并比较对冲策略；**挑战**（任务 6、7）用同一套工具研究 incast，任务 7 为选做。计分见第七节。

---

## 一、实验目标

1. 用 $1-(1-p)^N$ 预测轮次延迟的分位数，算出跳变点，并解释预测与实测的差距。
2. 建立噪声底，区分“注入的慢”“CPU 与调度造成的慢”和“网络造成的慢”。
3. 用计数器解释丢包造成的尾部；对比响应大小不同时的恢复方式；用数据说明队列调度对尾部的影响。
4. （进阶）给出对冲延迟与额外负载的取舍曲线；实现自适应延迟和对冲预算，比较它们在三类慢下的效果。
5. （挑战）复现 incast，实现限制在途请求数的扇出，并用证据说明它缓解了什么、没有缓解什么。

---

## 二、预备知识与工具

**先读**：

- [第 07 讲](../../docs/tail_latency.md)模块三到模块五：放大公式、`tailbench.py` 的测量方法、三场景对照。
- [第 06 讲](../../docs/network_measurement.md) 1.3 节：最近秩分位数。
- [Lab 3 指导书](../03/README.md) 3.2 节：节点、接口与地址约定。Lab 3 没有做完也可以做本实验，实验床用给定的完整版。

**环境**：Linux（`sudo`）、`iproute2`、`iputils-ping`、`iperf3`、Python 3.10 及以上与 `uv`；内核支持 namespace、veth、bridge、HTB、fq 与 netem。任务 7 另需 `tcp_dctcp` 与 `sch_red` 模块，缺少时安装 `linux-modules-extra-$(uname -r)`。

**一点 asyncio**：工具用 Python 标准库的 `asyncio` 同时等待多个请求。你只在任务 6 用到它，下面三行就够了：

- `await asyncio.gather(a(), b())`：同时运行两个协程，等全部结束，按顺序返回结果；
- `asyncio.Semaphore(k)`：最多 `k` 个协程同时进入 `async with gate:` 的代码块，其余排队；
- 协程函数用 `async def` 定义，调用它得到协程对象，`await` 才真正执行。

**约定**：以下命令都**从仓库根目录执行**，需要 root 的步骤显式写了 `sudo`。所有工具都显式指定拥塞控制算法，默认 `cubic`，不依赖系统默认值。

---

## 三、目录与资源

本实验以一个目录（压缩包）分发，下表的文件都在这个目录里。脚本按自己所在的目录找其他文件，**本指导书的所有命令都在 Lab 5 目录里执行**，新开终端时先 `cd` 进去。2026-11-11 起本目录自带完整实验床（`lab4_topo.sh` 与 `reference/`），不再需要 Lab 2、Lab 4 的目录；如果你已经在旧版目录里改了 `tailkit/`，把它复制到新目录即可，已有的结果文件仍在 `/tmp/lab05-results`。

### 3.1 文件

| 文件 | 说明 |
| :--- | :--- |
| `tail.sh` | 启停后端、设置队列、启动大象流、读计数器（给定） |
| `backend.py` | 后端进程（给定），由 `tail.sh up` 在 7 台 host 上启动 |
| `tailbench.py` | 测量入口（给定），在 h1a 里运行 |
| `compare.py` | 把保存的结果排成表（给定），只读文件 |
| `bulk.py` | 定时 TCP 大流，可显式指定算法；第 07 讲 1.3 节用它对照三种算法（给定） |
| `tailkit/rpc.py`、`runner.py`、`report.py` | 协议、扇出与对冲的执行、统计（给定，建议读一遍） |
| `tailkit/predict.py` | **TODO 1–3**：放大模型 |
| `tailkit/policy.py` | **TODO 4、5**：自适应延迟、对冲预算 |
| `tailkit/windowed.py` | **TODO 6**：限制在途请求数 |
| `tests/` | 离线测试，不需要 root，也不需要实验床 |
| `lab4_topo.sh`、`reference/` | 完整实验床与 Lab 2 参考路由（给定），是 Lab 4 `topo.sh` 与 Lab 2 参考实现的副本；`up --own DIR` 可改用 DIR（你的 Lab 2 目录）里自己的 lsrd |
| `lab3_classroom.sh`、`lab3_topo.sh`、`overlay_down.sh`、`transfer.py` | 第 05 讲课堂脚本与 Lab 3 脚本的副本（给定），本实验只用它们的 `down` 清理同名节点，`up` 只支持 `--reference` |

### 3.2 实验床与测量口径

实验床是本目录的 [`lab4_topo.sh`](lab4_topo.sh)（Lab 4 实验床脚本的副本），与第 06、07 讲相同：2 spine（`r5`、`r6`）× 4 leaf（`r1`–`r4`）× 8 host（`h1a`–`h4b`），host 接入口与 leaf–spine 链路都是 100 Mbit/s。前端固定在 h1a，后端在另外 7 台 host 上。

| 量 | 定义 |
| :--- | :--- |
| 单请求延迟 | 前端发出一个分片的请求到它完成（对冲时取先回来的那个） |
| 轮次延迟 | 前端同时发出 N 个请求到全部完成；本实验的主要指标 |
| 慢轮 | 轮次延迟超过 50 ms 的轮（`compare.py --slow-threshold` 可改） |
| 额外负载 | 备份请求数 ÷ 主请求数 |
| 备份先回 | 备份比主请求先回来的次数 |
| 分位数 | 最近秩法，第 $q$ 分位数取从小到大第 $\lceil qn\rceil$ 个 |

每次运行丢弃前 5 轮预热。慢响应是后端按概率注入的（`--slow-prob`、`--slow-ms`），每次独立抽样。结果写入 `/tmp/lab05-results/<label>.json`，**同名标签会被覆盖**，重启主机可能清除 `/tmp`，需要留存时另外复制。

### 3.3 骨架与测试

```bash
# 1. 进入 Lab 5 目录（压缩包解压后的目录，路径换成你自己的），准备 Python 环境（实验床的路由器与本实验的工具共用）
cd ~/lab05
uv sync --frozen

# 2. 离线测试：骨架原样应为 25 个测试中 4 个通过、21 个报错
uv run --frozen python -m unittest 2>&1 | tail -1
```

通过的 4 个是给定部分的环回测试。TODO 对应的测试分别在 `tests.test_predict`（TODO 1–3）、`tests.test_policy`（TODO 4、5）与 `tests.test_runner.WindowedCases`（TODO 6）。可以只跑一组，例如 `uv run --frozen python -m unittest tests.test_predict`（在实验目录下）。

---

## 四、实验步骤

### 基础任务

#### 任务 1：搭好实验床，测出噪声底

**预测**：$p=0$ 时后端固定等 5 ms。N 从 1 增加到 100，轮次 p50 会变吗？为什么？

```bash
# 3. 清理其他实验的网络（节点重名），搭完整实验床并自检
sudo bash lab3_classroom.sh down
sudo bash lab3_topo.sh down
sudo bash lab4_topo.sh up
sudo bash lab4_topo.sh check

# 4. 在 7 台 host 上启动后端，做一次往返验证
sudo bash tail.sh up
sudo bash tail.sh check

# 5. 噪声底：p=0，7 个扇出，每个 300 轮（约 1 分钟）
for n in 1 2 5 10 20 50 100; do
  sudo ip netns exec h1a python3 tailbench.py --fanout "$n" --rounds 300 --label base-n"$n" > /dev/null
done
python3 compare.py base-n1 base-n2 base-n5 base-n10 base-n20 base-n50 base-n100
```

`topo.sh check` 与 `tail.sh check` 应分别打印 `[OK]`。

**实测样例**：

```output
标签               N     轮p50     轮p90     轮p99      慢轮      备份/请求     备份先回
base-n1          1      6.2      6.5      7.3    0.0%       0.0%        0
base-n2          2      6.3      6.7      7.9    0.0%       0.0%        0
base-n5          5      6.8      7.7      8.8    0.0%       0.0%        0
base-n10        10      7.5      8.5     10.8    0.0%       0.0%        0
base-n20        20      8.5      9.7     11.0    0.0%       0.0%        0
base-n50        50     10.9     13.2     17.3    0.0%       0.0%        0
base-n100      100     15.6     19.3     24.8    0.0%       0.0%        0
```

**报告中回答**：p50 从 6.2 ms 涨到 15.6 ms，这部分来自哪里？设计一个对照，把“N 个请求取最大值”和“CPU 处理开销”分开（比如用 `--gap-ms` 或在任务运行时观察 `top`）。你的实验床的噪声底决定了后面哪些差别可以相信：差别必须明显超过它。

#### 任务 2：写放大模型，先算后测（TODO 1–3）

补全 `tailkit/predict.py`，让 `tests.test_predict` 全部通过。

**预测**：$p=1\%$、慢响应多等 100 ms 时，先用你的 `knee()` 算出 p50、p90、p99 的跳变点，填好下表的预测行，再运行。

| $N$ | 1 | 2 | 5 | 10 | 20 | 50 | 100 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 理论慢轮比例 | | | | | | | |
| p50 落在哪一档 | | | | | | | |
| p90 落在哪一档 | | | | | | | |
| p99 落在哪一档 | | | | | | | |

```bash
# 6. 跳变点（TODO 2）
python3 -c "from tailkit.predict import knee; print({q: knee(0.01, q) for q in (0.5, 0.9, 0.99)})"

# 7. 每个 N 跑 1000 轮，约 3 分钟
for n in 1 2 5 10 20 50 100; do
  sudo ip netns exec h1a python3 tailbench.py --fanout "$n" --rounds 1000 --slow-prob 0.01 --label amp-n"$n" > /dev/null
done

# 8. 对账：--fast、--slow 填你在任务 1 测到的典型值（样例用 8 与 108）
python3 compare.py --predict --fast 8 --slow 108 amp-n1 amp-n2 amp-n5 amp-n10 amp-n20 amp-n50 amp-n100
```

**实测样例**（使用了补全 TODO 的版本）：

```output
{0.5: 69, 0.9: 11, 0.99: 2}
标签               N     轮p50     轮p90     轮p99      慢轮      备份/请求     备份先回
amp-n1           1      6.1      6.5    106.2    1.3%       0.0%        0
  预测                    8.0      8.0      8.0    1.0%
amp-n2           2      6.3      6.9    106.3    1.4%       0.0%        0
  预测                    8.0      8.0    108.0    2.0%
amp-n5           5      6.8      7.8    107.2    5.2%       0.0%        0
  预测                    8.0      8.0    108.0    4.9%
amp-n10         10      7.6     10.8    108.3    9.3%       0.0%        0
  预测                    8.0      8.0    108.0    9.6%
amp-n20         20      9.4    108.1    110.0   20.1%       0.0%        0
  预测                    8.0    108.0    108.0   18.2%
amp-n50         50     15.4    111.2    114.8   39.2%       0.0%        0
  预测                    8.0    108.0    108.0   39.5%
amp-n100       100    111.0    118.2    124.4   64.6%       0.0%        0
  预测                  108.0    108.0    108.0   63.4%
```

**报告中回答**：

1. 慢轮比例的预测和实测差多少？如果把每个比例看成二项分布，1000 轮的合理波动有多大（标准差 $\sqrt{P(1-P)/1000}$）？你的差距在这个范围内吗？
2. 样例里 N=1 的 p99 预测是 8 ms，实测是 106 ms。这是模型错了吗？（理论慢轮恰好 1%，看你自己的结果。）
3. 模型只有“快”“慢”两档。N=50 的 p50 预测 8 ms，实测 15.4 ms，差在哪？怎样改进预测？（提示：任务 1 的噪声底。）

#### 任务 3：网络也会制造尾部

**（一）丢包。预测**：r1→h1a 注入 2% 丢包。128 字节的响应只有一个报文，64 KB 的响应有约 45 个报文。哪一种响应丢包更多？哪一种 p99 更差？哪一种慢轮比例更高？

```bash
# 9. 注入丢包；每次运行前后读计数器
sudo bash lab4_topo.sh impair r1 r1-h1a loss 2%
sudo bash tail.sh tcpstat
sudo ip netns exec h1a python3 tailbench.py --fanout 1 --primaries h3a --rounds 1000 --label loss-small | sed -n 1,2p
sudo bash tail.sh tcpstat
sudo ip netns exec h1a python3 tailbench.py --fanout 1 --primaries h3a --rounds 300 --resp-bytes 64000 --label loss-large | sed -n 1,2p
sudo bash tail.sh tcpstat

# 10. 恢复端口，再测无丢包的 64 KB 作为对照
sudo bash lab4_topo.sh clear r1 r1-h1a
sudo ip netns exec h1a python3 tailbench.py --fanout 1 --primaries h3a --rounds 300 --resp-bytes 64000 --label noloss-large | sed -n 1,2p

# 11. 排成表，并列出最慢的 12 轮
python3 compare.py --tail 12 loss-small loss-large noloss-large
```

**实测样例**（省略了脚本的 `[*]` 提示行；计数器是累计值）：

```output
重传段 683，超时 8，尾部丢失探测 222
[loss-small] N=1 轮数=1000 p=0 对冲=off cc=cubic
  轮次延迟 ms   n=1000 p50=6.2 p90=6.5 p99=212.2 max=421.0 mean=10.5
重传段 722，超时 9，尾部丢失探测 260
[loss-large] N=1 轮数=300 p=0 对冲=off cc=cubic
  轮次延迟 ms   n=300 p50=11.3 p90=17.2 p99=218.7 max=428.6 mean=18.9
重传段 1019，超时 13，尾部丢失探测 323
[noloss-large] N=1 轮数=300 p=0 对冲=off cc=cubic
  轮次延迟 ms   n=300 p50=11.0 p90=11.3 p99=12.1 max=14.0 mean=11.1
标签               N     轮p50     轮p90     轮p99      慢轮      备份/请求     备份先回
loss-small       1      6.2      6.5    212.2    2.0%       0.0%        0
              最慢 12 轮：211 212 212 213 213 213 213 213 215 215 215 421
loss-large       1     11.3     17.2    218.7    3.0%       0.0%        0
              最慢 12 轮：25 28 30 73 113 215 215 215 219 223 281 429
noloss-large     1     11.0     11.3     12.1    0.0%       0.0%        0
              最慢 12 轮：12 12 12 12 12 12 12 12 12 12 13 14
```

读这组数时注意：大响应重传了 297 段，比小响应的 39 段多得多，p90 也因此从 11.3 ms 涨到 17.2 ms，但慢轮比例只是 2% 对 3%，同一量级。多数丢包靠重复确认很快恢复了，只有丢在末尾、后面没有报文触发重复确认的那些，才要等约 200 ms。这个解释与 [RFC 8985](https://www.rfc-editor.org/rfc/rfc8985) 的机制相符，但以上只是计数器层面的证据。

**（二）队列。预测**：大象流 h2a→h1a 把 r1→h1a（50 Mbit/s）占满。基线的 fq 和单队列 pfifo 300，小请求的轮次延迟分别是多少？

```bash
# 12. fq：只限速，不换队列
sudo bash lab4_topo.sh limit r1 r1-h1a 50
sudo bash tail.sh elephant h2a h1a 30
sleep 3
sudo ip netns exec h1a python3 tailbench.py --fanout 10 --rounds 300 --primaries h3a,h3b --label q-fq > /dev/null
sudo bash tail.sh clear

# 13. pfifo：同样的速率和大象流
sudo bash tail.sh queue r1 r1-h1a 50 300
sudo bash tail.sh elephant h2a h1a 30
sleep 3
sudo ip netns exec h1a python3 tailbench.py --fanout 10 --rounds 300 --primaries h3a,h3b --label q-pfifo > /dev/null
sudo bash tail.sh clear
python3 compare.py q-fq q-pfifo
```

**实测样例**：

```output
标签               N     轮p50     轮p90     轮p99      慢轮      备份/请求     备份先回
q-fq            10      7.8      8.8     10.5    0.0%       0.0%        0
q-pfifo         10     67.0     75.5     79.2  100.0%       0.0%        0
```

**报告中回答**：

1. 用 `tcpstat` 的增量说明小响应的慢轮靠什么恢复。你的计数器支持“超时重传”还是“尾部丢失探测”？
2. 为小响应、大响应各写一句话：丢包造成了什么后果、证据是哪一行。
3. 把“服务慢”“排队慢”“丢包慢”三种情况的证据（分布形状、计数器、队列积压）整理成一张判别表。

### 进阶任务

本部分的固定条件与第 07 讲模块五相同，条件表和对照图见[第 07 讲 5.1 节](../../docs/tail_latency.md)。先定义简写，下面都在同一个终端里操作：

```bash
# 14. 固定条件：N=10，主副本 h3a、h3b，备份副本 h4a、h4b
run() { sudo ip netns exec h1a python3 tailbench.py --fanout 10 --rounds 300 --primaries h3a,h3b --backups h4a,h4b "$@"; }
```

#### 任务 4：对冲延迟的取舍

**预测**：场景 A（$p=1\%$），对冲延迟 $d$ 从 50 ms 减到 3 ms。p99 和额外负载分别怎样变？在哪个 $d$ 附近额外负载开始急剧上升？（提示：后端固定等 5 ms。）

```bash
# 15. 7 个延迟，每个 300 轮（约 30 秒）
for d in 3 5 6 8 12 20 50; do
  run --slow-prob 0.01 --hedge-ms "$d" --label a-d"$d" > /dev/null
done
python3 compare.py a-d3 a-d5 a-d6 a-d8 a-d12 a-d20 a-d50
```

**实测样例**：

```output
标签               N     轮p50     轮p90     轮p99      慢轮      备份/请求     备份先回
a-d3            10      8.2     10.8     13.0    0.0%     100.0%       39
a-d5            10      8.6     12.4     14.3    0.0%      85.2%       31
a-d6            10      8.2     13.0     15.0    0.0%      21.0%       31
a-d8            10      8.0     14.6     17.1    0.3%       1.2%       29
a-d12           10      8.0     19.2     21.0    0.0%       1.4%       38
a-d20           10      8.3     28.1     29.7    0.0%       1.2%       35
a-d50           10      8.0     56.9     59.4   10.3%       1.1%       32
```

**报告中回答**：

1. 画出 p99 对额外负载的曲线（横轴额外负载，纵轴 p99，每个点标上 $d$）。曲线的拐点在哪？你会选哪个 $d$，依据是什么？
2. 样例里 $d=3$ 时额外负载 100%，备份却只先回了 39 次。解释这两个数为什么不矛盾。
3. 用 4.2 节的模型 $\min(T_{\text{主}},\ d+T_{\text{备}})$ 估算 $d=20$ 时的 p99，和实测比较。

#### 任务 5：实现自适应延迟与对冲预算（TODO 4、5）

固定的 $d$ 有两个问题：系统变慢后 $d$ 不再合适；所有请求都超过 $d$ 时，负载翻倍（第 07 讲场景 C）。补全 `tailkit/policy.py` 的 `AdaptiveDelay` 与 `BudgetedHedge`，让 `tests.test_policy` 全部通过。

**预测**：先填表，再运行。对冲预算 5% 指备份不超过主请求的 5%。

| 场景 | 固定 12 ms | 自适应 p95 | 固定 12 ms + 预算 5% |
| :--- | :--- | :--- | :--- |
| A：p50、p99、额外负载 | | | |
| B：p50、p99、额外负载 | | | |
| C：p50、p99、额外负载 | | | |

```bash
# 16. 场景 A
run --slow-prob 0.01 --hedge-ms 12 --label a-fix > /dev/null
run --slow-prob 0.01 --adaptive 0.95 --label a-ad > /dev/null
run --slow-prob 0.01 --hedge-ms 12 --budget 0.05 --label a-bud > /dev/null
python3 compare.py a-fix a-ad a-bud

# 17. 场景 B：一台后端的路径堵塞
sudo bash tail.sh queue r3 r3-h3a 50 300
sudo bash tail.sh elephant h2a h3a 70
sleep 3
run --hedge-ms 12 --label b-fix > /dev/null
run --adaptive 0.95 --label b-ad > /dev/null
run --hedge-ms 12 --budget 0.05 --label b-bud > /dev/null
sudo bash tail.sh clear
python3 compare.py b-fix b-ad b-bud

# 18. 场景 C：前端自己的入口堵塞
sudo bash tail.sh queue r1 r1-h1a 50 300
sudo bash tail.sh elephant h2a h1a 80
sleep 3
run --hedge-ms 12 --label c-fix > /dev/null
run --adaptive 0.95 --label c-ad > /dev/null
run --hedge-ms 12 --budget 0.05 --label c-bud > /dev/null
sudo bash tail.sh clear
python3 compare.py c-fix c-ad c-bud
```

**实测样例**（使用了补全 TODO 的版本）：

```output
标签               N     轮p50     轮p90     轮p99      慢轮      备份/请求     备份先回
a-fix           10      8.1     19.3     20.9    0.0%       1.1%       34
a-ad            10      8.4     14.3     18.4    0.3%       1.3%       33
a-bud           10      8.1     10.2     20.7    0.0%       1.1%       28
标签               N     轮p50     轮p90     轮p99      慢轮      备份/请求     备份先回
b-fix           10     20.4     21.8     25.1    0.0%      50.0%     1500
b-ad            10     71.4     78.1     81.1   99.0%       5.0%       35
b-bud           10     68.0     75.4     78.3  100.0%       5.0%      151
标签               N     轮p50     轮p90     轮p99      慢轮      备份/请求     备份先回
c-fix           10     66.3     73.4     76.6  100.0%     100.0%        0
c-ad            10     71.7     78.6    105.9  100.0%       2.3%        3
c-bud           10     71.1     76.9     79.1  100.0%       5.0%        0
```

**报告中回答**：

1. 两个策略在 C 里把额外负载从 100% 压到几个百分点，这是好事。但在 B 里它们也放弃了固定对冲的收益（p50 回到约 70 ms）。这是实现的问题，还是同一种机制的两面？
2. `AdaptiveDelay` 的窗口里放的是分片完成的延迟。备份胜出时，这个值已经被对冲“截短”了。这对它估计 p95 有什么影响？你会改成记录什么？
3. 有没有一个策略能同时做到“B 里继续对冲、C 里停止对冲”？它需要多知道什么信息？（提示：备份先回的比例。）可以把想法实现出来，作为加分项。

### 挑战任务

#### 任务 6：复现 incast，限制在途请求数（TODO 6）

补全 `tailkit/windowed.py`，让 `tests.test_runner.WindowedCases` 通过。限制同时在途的请求数，等于把一轮的响应错开。

**预测**：N=20、64 KB，队列上限 30 个报文。窗口 K 从 20 减到 1，一轮的时间单调下降吗？K=1 时大约多久？（提示：一个响应的传输时间，加上服务时间和往返时间。）

```bash
# 19. 浅队列，5 个窗口；每次运行前读计数器，相邻两次相减即增量
sudo bash tail.sh queue r1 r1-h1a 100 30
for k in 20 10 5 2 1; do
  sudo bash tail.sh tcpstat
  sudo ip netns exec h1a python3 tailbench.py --fanout 20 --base-ms 1 --resp-bytes 64000 --rounds 100 --max-inflight "$k" --label win-"$k" > /dev/null
done
sudo bash tail.sh tcpstat
sudo bash tail.sh clear

# 20. 对照：深队列，不限制窗口
sudo bash tail.sh queue r1 r1-h1a 100 1000
sudo ip netns exec h1a python3 tailbench.py --fanout 20 --base-ms 1 --resp-bytes 64000 --rounds 100 --label win-deep > /dev/null
sudo bash tail.sh clear
python3 compare.py win-deep win-20 win-10 win-5 win-2 win-1
```

**实测样例**（使用了补全 TODO 的版本）：

```output
重传段 320，超时 2，尾部丢失探测 24
重传段 9617，超时 343，尾部丢失探测 620
重传段 15335，超时 400，尾部丢失探测 843
重传段 18178，超时 405，尾部丢失探测 913
重传段 18916，超时 405，尾部丢失探测 945
重传段 18916，超时 405，尾部丢失探测 945
标签               N     轮p50     轮p90     轮p99      慢轮      备份/请求     备份先回
win-deep        20    109.4    109.8    111.0  100.0%       0.0%        0
win-20          20    292.5    320.1    359.8  100.0%       0.0%        0
win-10          20    171.2    288.2    304.1  100.0%       0.0%        0
win-5           20    110.4    290.3    311.8  100.0%       0.0%        0
win-2           20    116.3    125.1    296.3  100.0%       0.0%        0
win-1           20    140.5    142.7    146.8  100.0%       0.0%        0
```

这里所有轮都超过 50 ms，“慢轮”这一列没有意义，要看分位数和重传增量。

**报告中回答**：

1. 把窗口和重传、超时的增量排成表（K=20 的重传增量是 $9617-320=9297$）。窗口变小时，什么先消失？
2. K=5 的 p50 已接近深队列，p99 却还在 300 ms 左右；K=1 没有重传，但 p50 比深队列慢约 30%。如果你要定一个默认值，选哪个？依据写清楚。
3. 窗口是在前端限制的。这要求前端知道什么？如果多个前端同时访问同一批后端，它还管用吗？

#### 任务 7（选做）：DCTCP 能解决 incast 吗

把任务 6 的 pfifo 30 换成同样大小（45000 字节）的 RED，队列约 10 个报文开始打标记，两端都用 DCTCP。

```bash
# 21. 后端换成 DCTCP（要先停），队列换成带 ECN 标记的 RED
sudo modprobe tcp_dctcp
sudo bash tail.sh down
sudo bash tail.sh up dctcp
sudo bash lab4_topo.sh limit r1 r1-h1a 100
sudo ip netns exec r1 tc qdisc del dev r1-h1a parent 1:10
sudo ip netns exec r1 tc qdisc add dev r1-h1a parent 1:10 handle 10: red limit 45000 min 15000 max 16000 avpkt 1514 burst 11 bandwidth 100mbit probability 1 ecn

# 22. 运行并读计数器；前端也要用 dctcp
sudo bash tail.sh tcpstat
sudo ip netns exec h1a python3 tailbench.py --fanout 20 --base-ms 1 --resp-bytes 64000 --rounds 100 --cc dctcp --label inc-dctcp > /dev/null
sudo bash tail.sh tcpstat
sudo bash tail.sh backlog r1 r1-h1a

# 23. 恢复：后端换回默认的 cubic
sudo bash tail.sh clear
sudo bash tail.sh down
sudo bash tail.sh up
python3 compare.py win-20 inc-dctcp
```

**实测样例**：

```output
重传段 18935，超时 405，尾部丢失探测 981
重传段 23123，超时 489，尾部丢失探测 1683
qdisc red 10: parent 1:10 limit 45000b min 15000b max 16000b ecn 
 Sent 140675853 bytes 94562 pkt (dropped 4188, overlimits 86816 requeues 0) 
 backlog 0b 0p requeues 0
  marked 86816 early 0 pdrop 4188 other 0 
标签               N     轮p50     轮p90     轮p99      慢轮      备份/请求     备份先回
win-20          20    292.5    320.1    359.8  100.0%       0.0%        0
inc-dctcp       20    239.4    290.0    304.0  100.0%       0.0%        0
```

**这组样例不足以下结论**：备课时另一次运行的 p50 是 129 ms（p90 282 ms、p99 307 ms），两次相差很大。你需要多跑几次，再说明 DCTCP 改善了什么、没有改善什么。提示：看 `pdrop`。标记要一个往返才能反馈回来，这段时间内的突发还是会把队列撑满。

---

## 五、故障排查

| 现象 | 先看什么 | 常见原因 |
| :--- | :--- | :--- |
| `tail.sh up` 报实验床尚未搭建 | `ls /run/lab04` | 没有在本目录执行 `lab4_topo.sh up`，或搭的是 Lab 3 或课堂网络 |
| `tailbench.py` 报 `ConnectionRefusedError` | `sudo bash tail.sh check` | 后端没启动；`topo.sh down` 之后要重新 `tail.sh up` |
| 报错的最后一行是 `NotImplementedError: TODO n` | 对应的 TODO | 选项 `--adaptive`、`--budget`、`--max-inflight` 需要先完成 TODO |
| `setsockopt` 报 `No such file or directory` | `sudo modprobe tcp_dctcp` | 算法模块没有加载或没有安装 |
| `setsockopt` 报 `Operation not permitted` | 是否用了 `sudo` | 非 root 只能选 `tcp_allowed_congestion_control` 里的算法 |
| 用 `sysctl` 在 namespace 里设 `dctcp` 报 `Operation not permitted` | `sysctl net.ipv4.tcp_allowed_congestion_control` | 非初始 namespace 只能把默认值设成允许列表里的算法；工具用套接字选项，不受影响 |
| 场景 B、C 的延迟和基线差不多 | `tail.sh backlog`；`/tmp/lab05-results/elephant.log` | 大象流没跑起来或已结束；`sleep 3` 不够 |
| 噪声底比样例高很多 | `top`；是否有其他测量 | 其他进程占 CPU；虚拟机核数太少。后面的结论看相对差别 |
| `compare.py` 找不到标签 | `ls /tmp/lab05-results` | 拼写错误；重启后 `/tmp` 被清空 |
| 实验中断后状态不明 | `sudo bash lab4_topo.sh status` | 执行 `tail.sh clear` 恢复；再不行就 `tail.sh down` 后 `topo.sh down` 重来 |

---

## 六、思考题

1. **p 从哪里来？** 真实系统里没有 `--slow-prob`。你怎样从线上数据估计 $p$？如果慢请求集中在某些后端，放大公式要怎么改？
2. **对冲的前提**：哪些请求不能对冲？写操作、带副作用的请求要怎样处理？
3. **取消有多重要**：`rpc.py` 的 `cancel()` 通知后端放弃未完成的请求。如果不取消，额外负载的计算要怎么改？后端要多做多少工作？
4. **尾部的代价**：任务 2 的 N=100 时，平均值和 p99 分别是多少？如果只看平均值监控，你能发现问题吗？
5. **接到第 08 讲**：barrier 要等所有 worker 到齐。如果一个 worker 以 1% 的概率慢 100 ms，64 个 worker 的迭代时间会怎样？能对冲吗？计算任务和这里的请求有什么不同？

---

## 七、提交要求

**截止时间**：2026-11-30。

| 层次 | 提交内容 | 分值 |
| :--- | :--- | :--- |
| 基础任务 1–3，人人完成 | `predict.py`（`test_predict` 全部通过）；噪声底与对照；放大的预测表与实测对账；丢包与队列的判别表 | 60 |
| 进阶任务 4 | 取舍曲线、选定的 $d$ 及依据 | 10 |
| 进阶任务 5 | `policy.py`（`test_policy` 全部通过）；三场景预测与实测；对两种策略的分析 | 15 |
| 挑战任务 6 | `windowed.py`（`WindowedCases` 通过）；窗口与重传的表；默认值的选择及依据 | 10 |
| 挑战任务 7（选做） | 多次运行的数据与结论 | 5 |

报告建议 3–5 页，做了进阶与挑战可增至 6–8 页。每项都要有预测、证据、解释：预测被推翻同样有价值，评分看证据是否充分、解释是否不超出数据。

提交 `tailkit/` 目录、报告和 `/tmp/lab05-results` 下的结果文件。不提交 `.venv/` 与 `__pycache__/`。

```bash
# 24. 打包代码与结果
tar -czf "$HOME/lab05-submission.tgz" tailkit -C /tmp/lab05-results .
tar -tzf "$HOME/lab05-submission.tgz" | head
```

全部做完后清理（重复执行应成功）：

```bash
# 25. 停后端与大象流，拆实验床
sudo bash tail.sh down
sudo bash lab4_topo.sh down
```

### 维护与验证

本文样例的来源与验证范围：

| 项目 | 内容 |
| :--- | :--- |
| 环境 | 2026-11-07，备课虚拟机：Ubuntu 26.04.1、Linux `7.0.0-43-generic`、x86_64、2 核 2.8 GB；iproute2 6.19.0、iperf3 3.20、Python 3.14；实验床使用 Lab 2 参考路由。这台机器的系统默认拥塞控制是 `bbr`，工具都显式指定算法 |
| 离线测试 | 骨架原样 25 个测试：4 个通过、21 个报错。补全 TODO 的参考实现 25 个全部通过。在 Python 3.10、3.12、3.14 下结果相同 |
| 实验床 | 任务 1–7 的命令按本文原样运行，其中 `tailbench.py` 与 `compare.py` 指向补全了 TODO 的临时副本，实测样例均来自这些运行。清理后没有残留进程和 namespace。在 Python 3.10 下只做了一次短测 |
| Ubuntu 24.04 | 2026-11-11 发现 24.04 上 `04/topo.sh` 搭不起来（iproute2 6.1 的 `tc -j class show` 不输出 JSON，见 [Lab 4 指导书](../04/README.md)末尾的“维护与验证”），`tail.sh queue` 里的限速也受影响；修复后在 Ubuntu 24.04.5 用户态容器（iproute2 6.1.0、iperf3 3.16、Python 3.12.3；宿主内核 Linux 7.3、4 vCPU）中按本文原样运行了不依赖 TODO 的命令：3.3 节离线测试（骨架结果与上文相同）、任务 1、任务 3、任务 4、任务 5 的固定延迟对冲、任务 6 的深队列对照，以及 `tail.sh` 的全部子命令与清理。读数与本文样例一致，例如丢包时 `loss-small` 的 p99 为 210.1 ms，`win-deep` 的 p50 为 109.5 ms。依赖 TODO 的命令（`--predict`、`--adaptive`、`--budget`、`--max-inflight`）与任务 7 没有在 24.04 上运行，这个容器只能用 reno 与 cubic |
| 单独运行 | 2026-11-11 起本实验以压缩包分发，目录里自带完整实验床（`lab4_topo.sh`、`reference/`），脚本按自身所在目录定位文件，命令在本目录执行。改动后把本目录复制到仓库外（`~/lab05`），在同一个 shell 里按本文原样运行了不依赖 TODO 的命令：备课虚拟机上全部运行（含任务 7 的 DCTCP），24.04 容器上除任务 7 外全部运行，均通过，读数与样例一致（如 `loss-small` 的 p99 为 210.1 ms、209.2 ms） |
| 未覆盖 | Ubuntu 24.04 上依赖 TODO 的命令、任务 7 与 24.04 自带的内核；学生自己的实现；4 核以上的机器（CPU 噪声底会不同）；`bulk.py` 与任务 7 在其他内核上的 DCTCP 行为 |

阅读版 `README.html` 由 `2026/tools/build_lab5_html.py` 从本文生成，用法见 [`tools/README.md`](../../tools/README.md)。仓库中的 TODO 保持留白；参考实现只用于备课验证，没有放进仓库。学生实现须独立验收，样例中的单次读数不作为验收标准。
