# Lab 7　算网协同调度

> 对应第 10、11 讲　｜　建议用时 2 周　｜　A 段（第 10 讲后）约 4 小时；B 段（第 11 讲后）约 4 小时　｜　截止：2026-12-28　｜　产出：A 段是一个能读画像、给放置打分并在全部候选里选出最好放置的调度器；B 段是一个把网络和算力放在一起估计的请求分发器；两者都要有与现成策略的实测对照

第 10 讲的课上，你读了一张网络画像，手算了三种放置的作业完成时间，又凭观察在一个未知的网络里挑出了一种好的放置。本实验把这些手算写成程序：让它读画像文件，给任意一种放置打分，在全部 280 种放置里找出预测最好的一个，再用实测检验它比“同机架优先”和“随机”好多少。

本实验分两段：**A 段**（任务 1–5）对应第 10 讲，只考虑网络，其中任务 1–3 人人完成，任务 4 是进阶，任务 5 是挑战。**B 段**（任务 6–10）对应第 11 讲：主机的算力也不相同时，把网络和算力放在一起，决定每个请求发给哪个实例，其中任务 6–8 人人完成，任务 9 是进阶，任务 10 是挑战。计分见第七节。

---

## 一、实验目标

1. 用体检工具测一张全部主机对的网络画像，读出网络哪里慢。
2. 把第 10 讲的三项代价模型写成函数，预测一种放置的每轮时间与作业完成时间（JCT），并与实测对账。
3. 给全部候选放置打分并排序，选出预测最好的放置；用后悔值比较“同机架优先”“随机”“按画像打分”三种策略。
4. 用机架信息给共享上联做修正，说明修正解决了什么、还剩什么没有解决。
5. 测出网络与算力两张画像，把“传输、排队、计算”三项写成函数，估计一个请求在各实例上的完成时间（B 段）。
6. 实现联合代价分发器，与“就近”“算力最强”“最空闲”对照；实测实例状态上报有滞后时会发生什么（B 段）。

---

## 二、预备知识与工具

**先读**：

- [第 10 讲](../../docs/topology_aware_scheduling.md)模块二：画像矩阵的读法；模块三：代价模型与共享上联；模块五：后悔值。
- [第 08 讲](../../docs/communication_cost.md)模块一：参数服务器一轮的时间结构与 barrier。
- [第 11 讲](../../docs/computing_aware_steering.md)模块一到三：请求的四段时间、两张画像、三项的估计与联合代价的手工推演（B 段）。
- [Lab 3 指导书](../03/README.md) 3.2 节：节点、接口与地址约定。Lab 3、Lab 4、Lab 6 没有做完也可以做本实验：实验床、画像工具和作业都是给定的完整版。

**环境**：Linux（`sudo`）、`iproute2`、`iputils-ping`、`iperf3`、Python 3.10 及以上与 `uv`；内核支持 namespace、veth、bridge、HTB、fq 与 netem。B 段另外需要 cgroup v2 及其 `cpu` 控制器（`cat /sys/fs/cgroup/cgroup.controllers` 的输出里有 `cpu`；Ubuntu 22.04 起默认满足）。

**约定**：需要 root 的步骤显式写了 `sudo`。作业与测量都显式指定拥塞控制算法，默认 `cubic`，不依赖系统默认值。

---

## 三、目录与资源

本实验以一个目录（压缩包）分发，下表的文件都在这个目录里。脚本按自己所在的目录找其他文件，**本指导书的所有命令都在 Lab 7 目录里执行**，新开终端时先 `cd` 进去。

### 3.1 文件

| 文件 | 内容 | 你要做什么 |
| :--- | :--- | :--- |
| [`sched/cost.py`](sched/cost.py) | 代价模型 | **TODO 1**：`predict_round`；**TODO 3**：`expected_shared_time` 与 `predict_round(shared=True)` |
| [`sched/strategy.py`](sched/strategy.py) | 放置策略：随机、同机架优先（给定） | **TODO 2**：`rank_placements` |
| [`sched/model.py`](sched/model.py) | 作业 `Job`、放置 `Placement`、画像表 `Table`、全部候选 `all_placements` | 给定，先读懂 |
| [`place.py`](place.py) | 选位置、预测一种放置、把几次作业排成表 | 给定 |
| [`evaluate.py`](evaluate.py) | 在当前场景下把几种策略各跑几次，输出预测、实测与后悔值；`--show TAG` 重新打印已有的结果，不运行作业 | 给定 |
| [`jobrun.py`](jobrun.py)、`job.py`、`jobkit/`、[`timeline.py`](timeline.py) | Lab 6 的参数服务器作业与时间线工具的副本 | 给定。本实验只用参数服务器 |
| [`checkup.py`](checkup.py)、`netprof/`、`owd.py` | Lab 4 的体检工具；`netprof/` 是完整实现 | 给定 |
| [`lab4_topo.sh`](lab4_topo.sh)、`reference/`、`lab3_classroom.sh`、`lab3_topo.sh`、`overlay_down.sh`、`transfer.py` | 完整实验床、Lab 2 参考路由，以及清理同名节点用的脚本 | 给定 |
| [`sched/steering.py`](sched/steering.py) | B 段：请求 `Request`、实例 `Instance`；三种分发策略（给定） | **TODO 4**：`estimate`；**TODO 5**：`Joint.choose` |
| [`edge.sh`](edge.sh)、[`instance.py`](instance.py) | B 段：在 host 上启动服务实例，并用 cgroup 的 `cpu.max` 给每个实例限定算力 | 给定 |
| [`cpuprof.py`](cpuprof.py) | B 段：算力画像 | 给定 |
| [`steer.py`](steer.py)、`edge_client.py` | B 段：请求分发器（运行一批请求、排表、估计表） | 给定 |
| `tests/` | 离线测试；`tests/fixtures/` 是两份实测的画像 | 给定，用来检查 TODO |

### 3.2 实验床与测量口径

实验床是本目录的 [`lab4_topo.sh`](lab4_topo.sh)，与第 06–10 讲是同一张：2 spine（`r5`、`r6`）× 4 leaf（`r1`–`r4`）× 8 host（`h1a`–`h4b`），基线时 host 接入口与 leaf–spine 链路都是 100 Mbit/s。本实验用到三个场景：

| 场景 | 内容 | 用在哪里 |
| :--- | :--- | :--- |
| `rack2-slow` | 机架 2 的两条上联、两个方向都降到 10 Mbit/s | 任务 1–4 |
| `lecture10` | 第 10 讲综合动手的场景：h1a 接入两个方向 20 Mbit/s，机架 3 的上联 10 Mbit/s | 任务 3 |
| `blind --seed N` | 随机注入 1–2 项隐藏条件 | 任务 5 |
| `lecture11` | 机架 3 的上联降到 30 Mbit/s，机架 4 的上联降到 10 Mbit/s | 任务 6–9 |
| `lecture11x` | 第 11 讲综合动手的场景：机架 2 的上联 10 Mbit/s，机架 4 的上联 30 Mbit/s | 任务 10 |

| 量 | 定义 |
| :--- | :--- |
| 作业 | 参数服务器，默认 N=4、模型 1 MB（$10^6$ 字节）、10 轮、每个 worker 每轮计算 200 ms（`time.sleep`，不占 CPU）、CUBIC |
| 放置 | PS 所在的主机，加上 N 个 worker 所在的主机；8 台主机共 $8 \times \binom{7}{4} = 280$ 种 |
| JCT | 最晚的 `model_last` 减最早的 `compute_start` |
| 画像里的吞吐 | `iperf3` 接收端速率，Mbit/s（$10^6$ bit/s）；一次只测一对主机；快速画像每对测 1 次、统计 1 秒 |
| 预测 JCT | 轮数 × 预测的每轮时间；每轮时间 = 计算 + 上传 + 下发（第 10 讲 3.1 节） |
| 后悔值 | 一种放置的平均实测 JCT ÷ 参与比较的放置中最小的平均实测 JCT；1.00 表示它就是最好的 |
| 实例（B 段） | `instance.py` 的一个进程，监听 7700 端口；一次只算一个请求，先到先算。实例预设 `lecture11`：h1b 15%、h3a 30%、h4a 60% 个核；`lecture11x`：h2a 60%、h3b 15%、h4b 30% |
| 请求（B 段） | 先上传输入，再做一段计算。`upload`：输入 1 MB、计算 20 ms；`compute`：输入 10 kB、计算 150 ms；`mixed`：两者交替。计算量是 CPU 时间，不是墙上时间 |
| 四段时间（B 段） | 传输：发出 → 实例收齐输入；排队：收齐 → 开始计算；计算：开始 → 算完；返回：算完 → 客户端收到结果 |
| 批完成（B 段） | 最后一个请求完成的时刻减第一个请求发出的时刻；默认一批 12 个请求，每 100 ms 发出一个 |
| rate（B 段） | 算力画像里的数：工作量（CPU 时间）÷ 计算用的墙上时间；1.0 相当于一个不受限的核 |

作业结果写入 `/tmp/lab06-results/<label>.json`（`jobrun.py` 沿用 Lab 6 的结果目录），画像默认写入 `/tmp/lab04-results/`，`evaluate.py` 的汇总写入 `/tmp/lab07-results/`。B 段的两张画像与每批请求的结果（`steer-<label>.json`）也写入 `/tmp/lab07-results/`；实例的状态登记在 `/run/lab07`，cgroup 在 `/sys/fs/cgroup/lab07`。作业结果与评估汇总的**同名文件会被覆盖**；`checkup.py` 则相反，发现同名的画像或原始输出目录已经存在时会拒绝运行，重测时换一个 `--out` 文件名，或先删掉旧的 `.json` 与 `.raw`。重启主机可能清除 `/tmp`，需要留存时另外复制。

**画像只代表测量时的网络**。换了场景要重新测；`evaluate.py` 发现画像里记录的场景与实验床当前的场景不一致时会提示。

### 3.3 骨架与测试

```bash
# 1. 进入 Lab 7 目录（压缩包解压后的目录，路径换成你自己的），准备路由守护进程的 Python 环境
cd ~/lab07
uv sync --frozen

# 2. 离线测试：骨架原样应为 36 个测试中 4 个通过、32 个报错
python3 -m unittest 2>&1 | tail -1
```

```output
FAILED (errors=32)
```

通过的 4 个是给定部分的测试（候选数目、两种不看画像的放置策略、三种给定的分发策略）。TODO 对应的测试：`tests.test_cost.RoundCases` 是 TODO 1，`tests.test_strategy.RankCases` 是 TODO 2，`tests.test_cost.SharedTimeCases` 与 `SharedRoundCases` 是 TODO 3，`tests.test_steering.EstimateCases` 是 TODO 4，`tests.test_steering.JointCases` 是 TODO 5。本实验的工具只用 Python 标准库，直接用系统 `python3` 运行。

---

## 四、实验步骤

### A 段：第 10 讲后

#### 任务 1：测一张画像，跑两种不看画像的放置（基础）

```bash
# 3. 清理课堂网络与 Lab 3 网络（节点重名），搭建完整实验床并自检
sudo bash lab3_classroom.sh down
sudo bash lab3_topo.sh down
sudo bash lab4_topo.sh up
sudo bash lab4_topo.sh check

# 4. 加载场景：机架 2 的两条上联、两个方向都降到 10 Mbit/s
sudo bash lab4_topo.sh scenario rack2-slow

# 5. 快速画像，约 2.5 分钟：56 个有向对各测 1 次吞吐，28 个无序对各 20 个 ping
sudo python3 checkup.py --tput-repeats 1 --tput-seconds 1 --tput-omit 1 --out /tmp/lab04-results/profile-rack2-slow.json
```

**实测样例**（节选：只保留吞吐矩阵和最后一行）：

```output
吞吐中位数（Mbit/s）（行＝源，列＝目的）
             h1a     h1b     h2a     h2b     h3a     h3b     h4a     h4b
     h1a       ·    95.1     9.4     9.4    95.0    95.1    94.9    94.8
     h1b    95.6       ·     8.8     9.4    94.9    95.0    94.8    95.0
     h2a     9.4     9.4       ·    95.0     9.4     9.4     9.4     8.8
     h2b     8.8    10.5    95.1       ·     9.4     9.4     8.8     8.8
     h3a    95.9    96.0     9.4     9.4       ·    95.4    95.6    95.0
     h3b    94.9    94.9     8.8     9.4    95.0       ·    95.0    95.0
     h4a    95.0    95.3     9.4     9.4    95.1    95.0       ·    95.1
     h4b    95.8    94.7     9.4     9.4    95.8    95.0    95.3       ·

[完成] 用时 2.4 分钟；画像 /tmp/lab04-results/profile-rack2-slow.json；原始输出 /tmp/lab04-results/profile-rack2-slow.raw/
```

```bash
# 6. 两种不看画像的放置
python3 place.py rack
python3 place.py random --seed 2

# 7. 各运行一次，排成表
sudo python3 jobrun.py --label t1-rack $(python3 place.py rack)
sudo python3 jobrun.py --label t1-rand $(python3 place.py random --seed 2)
python3 place.py report t1-rack t1-rand
```

**实测样例**：

```output
--ps h1a --workers h1b,h2a,h2b,h3a
--ps h1a --workers h4b,h4a,h2a,h1b
[t1-rack] ps N=4 模型 1 MB 10 轮 cubic：JCT = 27.575 s，结果 /tmp/lab06-results/t1-rack.json
[t1-rand] ps N=4 模型 1 MB 10 轮 cubic：JCT = 19.017 s，结果 /tmp/lab06-results/t1-rand.json
标签        PS   worker                   JCT s     每轮ms  最慢上传            最慢下发            
t1-rack     h1a  h1b,h2a,h2b,h3a         27.575   2757.5  h2b 855.2 ms        h2a 1696.1 ms
t1-rand     h1a  h4b,h4a,h2a,h1b         19.017   1901.7  h2a 851.0 ms        h2a 850.2 ms
```

**要回答的问题**：

1. 从矩阵里读出哪里慢。依据是哪些行、哪些列，以及哪两个格子说明“不是主机本身慢”？
2. 两种放置各用了机架 2 的几台主机？“最慢上传”“最慢下发”指向谁，用时与画像里的哪个数对应？
3. 你的 `t1-rack` 落在第 10 讲 3.3 节三档读数的哪一档？只凭这一次运行，能不能说同机架优先“就是这么慢”？

#### 任务 2：把代价模型写成函数（基础，TODO 1）

完成 [`sched/cost.py`](sched/cost.py) 的 `predict_round`（`shared=False` 的部分）。先读 [`sched/model.py`](sched/model.py)：`table.tput[(src, dst)]` 是画像里的吞吐，`table.capacity_in(ps)` 与 `table.capacity_out(ps)` 是 PS 接入链路两个方向的能力，`job.megabits` 是一份梯度的大小。模型就是第 10 讲 3.1 节的三项。

```bash
# 8. TODO 1 的离线测试
python3 -m unittest tests.test_cost.RoundCases 2>&1 | tail -1

# 9. 预测三种放置：避开机架 2 的、同机架优先的、任务 1 的随机放置
python3 place.py predict --profile /tmp/lab04-results/profile-rack2-slow.json --ps h1a --workers h1b,h3a,h3b,h4a
python3 place.py predict --profile /tmp/lab04-results/profile-rack2-slow.json $(python3 place.py rack)
python3 place.py predict --profile /tmp/lab04-results/profile-rack2-slow.json $(python3 place.py random --seed 2)

# 10. 把避开机架 2 的放置也跑一次，三次作业排在一起
sudo python3 jobrun.py --label t2-fast --ps h1a --workers h1b,h3a,h3b,h4a
python3 place.py report t2-fast t1-rack t1-rand
```

**实测样例**：

```output
OK
--ps h1a --workers h1b,h3a,h3b,h4a
每轮 870.2 ms = 计算 200.0 + 上传 333.8 + 下发 336.4；10 轮预测 JCT 8.70 s
--ps h1a --workers h1b,h2a,h2b,h3a
每轮 1957.3 ms = 计算 200.0 + 上传 908.1 + 下发 849.3；10 轮预测 JCT 19.57 s
--ps h1a --workers h4b,h4a,h2a,h1b
每轮 1898.5 ms = 计算 200.0 + 上传 849.3 + 下发 849.3；10 轮预测 JCT 18.99 s
[t2-fast] ps N=4 模型 1 MB 10 轮 cubic：JCT = 8.660 s，结果 /tmp/lab06-results/t2-fast.json
标签        PS   worker                   JCT s     每轮ms  最慢上传            最慢下发            
t2-fast     h1a  h1b,h3a,h3b,h4a          8.660    866.0  h3a 332.0 ms        h3b 334.4 ms
t1-rack     h1a  h1b,h2a,h2b,h3a         27.575   2757.5  h2b 855.2 ms        h2a 1696.1 ms
t1-rand     h1a  h4b,h4a,h2a,h1b         19.017   1901.7  h2a 851.0 ms        h2a 850.2 ms
```

**要提交的对账表**（用你自己的数据）：

| 放置 | 预测每轮（ms） | 预测 JCT（s） | 实测 JCT（s） | 误差 |
| :--- | :--- | :--- | :--- | :--- |
| 避开机架 2 | | | | |
| 同机架优先 | | | | |
| 随机（种子 2） | | | | |

**要回答的问题**：

1. 三种放置里哪些预测与实测对得上，哪些对不上？对不上的那种，实测的“最慢上传”或“最慢下发”是预测值的几倍？
2. 模型里 `capacity / N` 这一项在哪种放置里起作用，在哪种放置里不起作用？
3. 画像里同一个方向的 9.4 与 8.8 这样的差别，会让预测变化多少？这个差别可信吗？（提示：快速画像每对只测了 1 次。）

#### 任务 3：在全部候选里找最好的放置（基础，TODO 2）

完成 [`sched/strategy.py`](sched/strategy.py) 的 `rank_placements`：给全部 280 种放置打分并排序。

```bash
# 11. TODO 2 的离线测试
python3 -m unittest tests.test_strategy 2>&1 | tail -1

# 12. 按画像打分：第一行是选出的放置，后面是前 5 名
python3 place.py score --profile /tmp/lab04-results/profile-rack2-slow.json

# 13. 评估：同机架优先、3 个随机种子、按画像打分，各跑 2 次，约 5 分钟
sudo python3 evaluate.py --profile /tmp/lab04-results/profile-rack2-slow.json --tag rack2
```

**实测样例**：

```output
OK
--ps h3a --workers h1a,h1b,h3b,h4a
# 候选 280 种；预测最好 8.68 s，最差 20.12 s；与最好相差 2% 以内的有 30 种
#  1     8.68 s  --ps h3a --workers h1a,h1b,h3b,h4a
#  2     8.68 s  --ps h3a --workers h1a,h1b,h3b,h4b
#  3     8.68 s  --ps h3a --workers h1a,h1b,h4a,h4b
#  4     8.68 s  --ps h3a --workers h1a,h3b,h4a,h4b
#  5     8.68 s  --ps h3a --workers h1b,h3b,h4a,h4b
[运行] rack         --ps h1a --workers h1b,h2a,h2b,h3a
[运行] random-1     --ps h2a --workers h3a,h1a,h4b,h3b
[运行] random-2     --ps h1a --workers h4b,h4a,h2a,h1b
[运行] random-3     --ps h2b --workers h3a,h4a,h1b,h2a
[运行] score        --ps h3a --workers h1a,h1b,h3b,h4a

策略         PS  worker              预测 共享预测   实测          平均 后悔值
rack         h1a h1b,h2a,h2b,h3a    19.57        -  27.56  27.43  27.50   3.17
random-1     h2a h3a,h1a,h4b,h3b    20.12        -  45.19  44.15  44.67   5.16
random-2     h1a h4b,h4a,h2a,h1b    18.99        -  19.03  19.07  19.05   2.20
random-3     h2b h3a,h4a,h1b,h2a    19.56        -  44.35  35.91  40.13   4.63
score        h3a h1a,h1b,h3b,h4a     8.68        -   8.66   8.67   8.66   1.00

[完成] 结果 /tmp/lab07-results/rack2.json；每次作业的时间戳在 /tmp/lab06-results/rack2-*.json
```

“共享预测”一列现在是 `-`，要到任务 4 完成 TODO 3 后才有数。表里的实测保留两位小数；想再看这张表不必重跑，执行 `python3 evaluate.py --show rack2` 即可。

```bash
# 14. 换一个场景再评估一次：先加载场景、重新画像（约 2.5 分钟），再评估（约 5 分钟）
sudo bash lab4_topo.sh scenario lecture10
sudo python3 checkup.py --tput-repeats 1 --tput-seconds 1 --tput-omit 1 --out /tmp/lab04-results/profile-lecture10.json
sudo python3 evaluate.py --profile /tmp/lab04-results/profile-lecture10.json --tag l10
```

**实测样例**（节选：省略画像的输出）：

```output
[*] 场景 lecture10 已加载。结束后执行 lab4_topo.sh scenario clear，再用 lab4_topo.sh status 核对。
[运行] rack         --ps h1a --workers h1b,h2a,h2b,h3a
[运行] random-1     --ps h2a --workers h3a,h1a,h4b,h3b
[运行] random-2     --ps h1a --workers h4b,h4a,h2a,h1b
[运行] random-3     --ps h2b --workers h3a,h4a,h1b,h2a
[运行] score        --ps h2b --workers h1b,h2a,h4a,h4b

策略         PS  worker              预测 共享预测   实测          平均 后悔值
rack         h1a h1b,h2a,h2b,h3a    35.09        -  35.46  35.53  35.49   4.09
random-1     h2a h3a,h1a,h4b,h3b    20.14        -  19.09  27.44  23.26   2.68
random-2     h1a h4b,h4a,h2a,h1b    35.09        -  35.32  35.53  35.43   4.08
random-3     h2b h3a,h4a,h1b,h2a    19.61        -  19.06  19.01  19.03   2.19
score        h2b h1b,h2a,h4a,h4b     8.69        -   8.67   8.68   8.67   1.00

[完成] 结果 /tmp/lab07-results/l10.json；每次作业的时间戳在 /tmp/lab06-results/l10-*.json
```

**要回答的问题**：

1. 两个场景里，按画像打分选出的放置后悔值各是多少？同机架优先呢？
2. `place.py score` 说“与最好相差 2% 以内的有若干种”。这些放置有什么共同点？调度器在它们之间怎么选，有没有实际差别？
3. 哪些随机放置的实测明显大于预测？它们的 PS 或 worker 在哪里？先写下你的猜测，任务 4 再检验。
4. 280 种放置全部打分用了多久（可以用 `time python3 place.py score …` 量一下）？如果是 100 台主机里选 1 个 PS、16 个 worker，候选有多少种？还能穷举吗？

#### 任务 4：给共享上联做修正（进阶，TODO 3）

第 10 讲 3.4 节说过：画像是一对一对测的，看不见两条流挤在同一条上联的情况。完成 [`sched/cost.py`](sched/cost.py) 的 `expected_shared_time`，并让 `predict_round` 支持 `shared=True`：与 PS 不同机架、且同一机架里有两个以上 worker 时，这几条流的用时改用“随机选上联”的期望值。

```bash
# 15. TODO 1、3 的离线测试
python3 -m unittest tests.test_cost 2>&1 | tail -1

# 16. 回到 rack2-slow；同机架优先的放置，修正前后的预测
sudo bash lab4_topo.sh scenario rack2-slow
python3 place.py predict --profile /tmp/lab04-results/profile-rack2-slow.json $(python3 place.py rack)
python3 place.py predict --profile /tmp/lab04-results/profile-rack2-slow.json $(python3 place.py rack) --shared

# 17. 再评估一次，每种放置跑 3 次，约 8 分钟
sudo python3 evaluate.py --profile /tmp/lab04-results/profile-rack2-slow.json --tag rack2-shared --repeats 3
```

**实测样例**：

```output
OK
[*] 场景 rack2-slow 已加载。结束后执行 lab4_topo.sh scenario clear，再用 lab4_topo.sh status 核对。
--ps h1a --workers h1b,h2a,h2b,h3a
每轮 1957.3 ms = 计算 200.0 + 上传 908.1 + 下发 849.3；10 轮预测 JCT 19.57 s
--ps h1a --workers h1b,h2a,h2b,h3a
每轮 2836.0 ms = 计算 200.0 + 上传 1362.1 + 下发 1273.9；10 轮预测 JCT 28.36 s（含共享上联修正）
[提示] 做共享上联修正后选出的放置与 score 相同，不重复运行。
[运行] rack         --ps h1a --workers h1b,h2a,h2b,h3a
[运行] random-1     --ps h2a --workers h3a,h1a,h4b,h3b
[运行] random-2     --ps h1a --workers h4b,h4a,h2a,h1b
[运行] random-3     --ps h2b --workers h3a,h4a,h1b,h2a
[运行] score        --ps h3a --workers h1a,h1b,h3b,h4a

策略         PS  worker              预测 共享预测   实测                 平均 后悔值
rack         h1a h1b,h2a,h2b,h3a    19.57    28.36  27.47  27.44  27.60  27.50   3.18
random-1     h2a h3a,h1a,h4b,h3b    20.12    28.30  35.98  45.27  44.27  41.84   4.83
random-2     h1a h4b,h4a,h2a,h1b    18.99    18.99  18.97  18.99  19.00  18.99   2.19
random-3     h2b h3a,h4a,h1b,h2a    19.56    19.56  37.88  29.04  52.84  39.92   4.61
score        h3a h1a,h1b,h3b,h4a     8.68     8.68   8.66   8.66   8.67   8.66   1.00

[完成] 结果 /tmp/lab07-results/rack2-shared.json；每次作业的时间戳在 /tmp/lab06-results/rack2-shared-*.json
```

**要回答的问题**：

1. 同机架优先的放置，修正前后的预测各是多少？哪个更接近你 3 次实测的平均值？单次实测为什么仍然可能离预测很远？
2. 修正之后，按画像打分选出的放置变了吗？为什么？
3. 表里还有哪种放置的实测远大于“共享预测”？画出它的流量经过哪些上联，说明这次修正漏掉了什么。（提示：本任务只修正了 worker 一侧。PS 在慢机架里时，谁的流量要经过 PS 所在机架的上联？）
4. 修正用到了“每个机架有 2 条上联”和“哪些主机在同一个机架”两条拓扑知识。如果只有画像、没有机架标签，还能做这个修正吗？

#### 任务 5：未知网络里的闭环（挑战）

```bash
# 18. 注入隐藏条件（把 7 换成你学号的后三位），重新画像，评估；做完再看答案
sudo bash lab4_topo.sh blind --seed 7
sudo python3 checkup.py --tput-repeats 1 --tput-seconds 1 --tput-omit 1 --out /tmp/lab04-results/profile-blind.json
sudo python3 evaluate.py --profile /tmp/lab04-results/profile-blind.json --tag blind
sudo bash lab4_topo.sh blind reveal
```

隐藏条件可能是限速，也可能是延迟或丢包，后两者在吞吐矩阵里不一定明显。这一项没有样例输出，结果因种子而异。隐藏条件也可能对这个作业没有影响：备课时种子 7 注入的是“h3a 的发送出口限速 40 Mbit/s”，五种放置的实测都在 8.66–8.70 秒。遇到这种情况，在报告里用代价模型解释为什么没有影响，再换一个种子。

**要做的事**（选一项深入做）：

- **改进模型**：从任务 3、4 里挑一类预测明显偏离实测的放置（例如 PS 在慢机架里），改进 `predict_round`，用至少两个场景的数据说明改进之后排序是否更准。
- **换作业**：把模型改成 1 KB、每轮计算 20 ms（`--model-mb 0.001 --compute-ms 20`），此时吞吐几乎不起作用。给代价模型加上往返时间一项（`profile.rtt(src, dst)`），在一个带延迟的场景下检验。
- **少测一些**：只测 16 个“机架对”而不是 56 个主机对（第 10 讲 4.4 节），用它生成一张近似的画像，比较两张画像选出的放置。

报告里写清楚：你的预测、实测、后悔值，以及改进前后的对比。预测被推翻同样有价值。

#### A 段的清理

```bash
# 19. 恢复基线并核对
sudo bash lab4_topo.sh scenario clear
sudo bash lab4_topo.sh status

# 20. 留存结果（同名文件再次运行会被覆盖）
mkdir -p "$HOME/lab07-results" && cp -r /tmp/lab06-results /tmp/lab04-results /tmp/lab07-results "$HOME/lab07-results/"

# 21. 不接着做 B 段的话，拆实验床（幂等）
sudo bash lab4_topo.sh down
```

**实测样例**：

```output
[*] 已恢复基线：全部端口 HTB + fq、档位不变，钉路已取消。
[档位] leaf–spine 100 Mbit/s；host 接入 100 Mbit/s。场景：无。
[基线] 32 个限速端口均为 HTB + fq，速率与 burst 为基线值。
[基线] r1–r4 没有额外策略路由（自然 ECMP）。
[*] 实验床已拆除；路由日志保留在 /tmp/lab04-results。
```

### B 段：第 11 讲后

A 段默认每台主机算得一样快。B 段让主机的算力也不一样，工作负载换成请求与响应：客户端 h1a 把请求发给三个服务实例中的一个，实例先收输入、再计算、最后返回结果。要决定的是每个请求发给谁。背景、两类请求和四段时间的定义见[第 11 讲](../../docs/computing_aware_steering.md)模块一，3.2 节的表里也有。

#### 任务 6：两张画像，三种现成的策略（基础）

```bash
# 23. 实验床已经拆掉的话重新搭建（接着 A 段做、实验床还在时，这一步什么也不做）
sudo bash lab4_topo.sh status >/dev/null 2>&1 || sudo bash lab4_topo.sh up

# 24. 加载网络场景，启动三个实例（h1b 15%、h3a 30%、h4a 60% 个核）
sudo bash lab4_topo.sh scenario lecture11
sudo bash edge.sh up
sudo bash edge.sh status

# 25. 两张画像：客户端 h1a 到三个实例的网络（约 10 秒），三个实例的算力（约 6 秒）
sudo rm -rf /tmp/lab07-results/net-profile.json /tmp/lab07-results/net-profile.raw
sudo python3 checkup.py --src h1a --dst h1b,h3a,h4a --tput-repeats 1 --tput-seconds 1 --tput-omit 1 --out /tmp/lab07-results/net-profile.json
sudo python3 cpuprof.py
```

**实测样例**（节选：省略了 `[计划]` 行和网络画像的两张矩阵）：

```output
[*] 场景 lecture11 已加载。结束后执行 lab4_topo.sh scenario clear，再用 lab4_topo.sh status 核对。
[*] 预设 lecture11：实例已启动，端口 7700。查看限额用 edge.sh status；结束后执行 edge.sh down。
[预设] lecture11
[实例] h1b  cpu.max 1500 10000（15% 个核）  计算进程 167965 
[实例] h3a  cpu.max 3000 10000（30% 个核）  计算进程 167974 
[实例] h4a  cpu.max 6000 10000（60% 个核）  计算进程 167976 
[RTT]  h1a ⇄ h1b  p50 0.098 ms  p90 0.107 ms  丢 0/20
[RTT]  h1a ⇄ h3a  p50 0.143 ms  p90 0.201 ms  丢 0/20
[RTT]  h1a ⇄ h4a  p50 0.145 ms  p90 0.209 ms  丢 0/20
[吞吐] h1a → h1b  95.0 Mbit/s（95.0–95.0，n=1）
[吞吐] h1a → h3a  28.3 Mbit/s（28.3–28.3，n=1）
[吞吐] h1a → h4a  9.4 Mbit/s（9.4–9.4，n=1）
[完成] 用时 0.2 分钟；画像 /tmp/lab07-results/net-profile.json；原始输出 /tmp/lab07-results/net-profile.raw/
[算力] h1b  100 ms 的计算用了 657.2 ms（656.4–658.8，n=5）  rate 0.152
[算力] h3a  100 ms 的计算用了 326.3 ms（325.6–327.1，n=5）  rate 0.306
[算力] h4a  100 ms 的计算用了 157.4 ms（156.7–158.1，n=5）  rate 0.635
[完成] 算力画像 /tmp/lab07-results/cpu-profile.json
```

```bash
# 26. 三类负载 × 三种现成的策略，各一批（12 个请求，每 100 ms 一个），共 9 次，约 45 秒
for w in compute upload mixed; do
  for p in nearest:near strongest:strong least:least; do
    sudo python3 steer.py run --policy ${p%%:*} --workload $w --label ${w:0:1}-${p##*:}
  done
done

# 27. 排成表
python3 steer.py report c-near c-strong c-least u-near u-strong u-least m-near m-strong m-least
```

**实测样例**（节选：省略了每次运行打印的一行摘要）：

```output
标签     策略          负载    批完成s p50ms p95ms 传输 排队 计算  各实例请求数
c-near   nearest       compute  12.023  5503 10923    2 4956 1000  h1b×12
c-strong strongest     compute   3.014  1010  1914    7  828  249  h4a×12
c-least  least         compute   4.000   699  3000    4  436  581  h1b×4 h3a×4 h4a×4
u-near   nearest       upload    1.724   385   624   86  186  135  h1b×12
u-strong strongest     upload    6.767  5485  6046 4570    5   27  h4a×12
u-least  least         upload    1.968   341   868  331    7   87  h1b×6 h3a×4 h4a×2
m-near   nearest       mixed     6.913  2992  5813   44 2398  565  h1b×12
m-strong strongest     mixed     2.773   591  2024  927   72  138  h4a×12
m-least  least         mixed     2.157   758  1058  205  206  312  h1b×4 h3a×5 h4a×3
```

**要回答的问题**：

1. 两张画像各说明了什么？三个实例里，谁离客户端最近、谁算得最快？
2. 三类负载各是哪种策略最好？有没有一种策略在三类负载上都不差？
3. `c-least` 把 12 个请求平分给了三个实例，为什么反而比全部发给 h4a 的 `c-strong` 慢？用 `python3 steer.py show c-least` 的明细说明。
4. `c-strong` 的“排队”一列为什么不是 0？它的批完成时间怎样用“一个请求算多久”估出来？

#### 任务 7：把三项的估计写成函数（基础，TODO 4）

完成 [`sched/steering.py`](sched/steering.py) 的 `estimate`：把一个请求现在发给某个实例，估计它的传输、排队、计算各要多久，什么时候做完。式子就是第 11 讲 3.1 节的三项。

```bash
# 28. TODO 4 的离线测试
python3 -m unittest tests.test_steering.EstimateCases 2>&1 | tail -1

# 29. 用两张画像估计两类请求在各实例上的完成时间（实例空闲时）
python3 steer.py estimate --workload mixed

# 30. 实测对账：两类请求各给三个实例发 1 个
for h in h1b h3a h4a; do
  sudo python3 steer.py run --policy only:$h --workload upload --requests 1 --label u1-$h
  sudo python3 steer.py run --policy only:$h --workload compute --requests 1 --label c1-$h
done
python3 steer.py report u1-h1b u1-h3a u1-h4a c1-h1b c1-h3a c1-h4a
```

**实测样例**（节选：省略了第 30 步每次运行打印的一行摘要）：

```output
OK
输入kB    计算ms  实例   吞吐Mbit/s   rate   传输ms   计算ms   完成ms   （实例空闲、只发这一个请求时的估计）
1000          20  h1b          95.0  0.152     84.3    131.4    215.8
1000          20  h3a          28.3  0.306    283.2     65.3    348.5
1000          20  h4a           9.4  0.635    848.5     31.5    880.0
10           150  h1b          95.0  0.152      0.9    985.5    986.5
10           150  h3a          28.3  0.306      3.0    489.4    492.4
10           150  h4a           9.4  0.635      8.6    236.1    244.8
标签     策略          负载    批完成s p50ms p95ms 传输 排队 计算  各实例请求数
u1-h1b   only:h1b      upload    0.217   217   217   89    0  126  h1b×1
u1-h3a   only:h3a      upload    0.337   337   337  284    0   52  h3a×1
u1-h4a   only:h4a      upload    0.871   871   871  840    0   29  h4a×1
c1-h1b   only:h1b      compute   0.994   994   994    8    1  985  h1b×1
c1-h3a   only:h3a      compute   0.503   503   503   10    0  492  h3a×1
c1-h4a   only:h4a      compute   0.254   254   254   11    0  242  h4a×1
```

**要提交的对账表**（用你自己的数据）：6 行，每行是一类请求在一个实例上的估计完成时间、实测完成时间与误差。

**要回答的问题**：

1. 6 个估计里误差最大的是哪个？偏大还是偏小？可能漏掉了什么？
2. 对 `upload` 和 `compute`，估计最快的实例各是谁？与任务 6 里“哪种策略最好”对得上吗？
3. `estimate` 里的 `wait` 一项，在这一步的对账里用上了吗？它什么时候才不是 0？

#### 任务 8：联合代价分发器（基础，TODO 5）

完成 [`sched/steering.py`](sched/steering.py) 的 `Joint.choose`：每个请求发给预计最早做完的实例，并记下这个实例要忙到什么时候。第 11 讲 3.5 节手工推演过前 4 个请求。

```bash
# 31. TODO 4、5 的离线测试
python3 -m unittest tests.test_steering 2>&1 | tail -1

# 32. 联合代价：三类负载各一批
for w in compute upload mixed; do
  sudo python3 steer.py run --policy joint --workload $w --label ${w:0:1}-joint
done

# 33. 与任务 6 的 9 次排在一起；再看混合负载下它把请求发给了谁
python3 steer.py report c-near c-strong c-least c-joint u-near u-strong u-least u-joint m-near m-strong m-least m-joint
python3 steer.py show m-joint
```

**实测样例**（节选：省略了第 32 步每次运行打印的一行摘要）：

```output
OK
标签     策略          负载    批完成s p50ms p95ms 传输 排队 计算  各实例请求数
c-near   nearest       compute  12.023  5503 10923    2 4956 1000  h1b×12
c-strong strongest     compute   3.014  1010  1914    7  828  249  h4a×12
c-least  least         compute   4.000   699  3000    4  436  581  h1b×4 h3a×4 h4a×4
c-joint  joint         compute   2.090   653  1004    6  296  372  h1b×1 h3a×3 h4a×8
u-near   nearest       upload    1.724   385   624   86  186  135  h1b×12
u-strong strongest     upload    6.767  5485  6046 4570    5   27  h4a×12
u-least  least         upload    1.968   341   868  331    7   87  h1b×6 h3a×4 h4a×2
u-joint  joint         upload    1.425   316   355  132   53  121  h1b×10 h3a×2
m-near   nearest       mixed     6.913  2992  5813   44 2398  565  h1b×12
m-strong strongest     mixed     2.773   591  2024  927   72  138  h4a×12
m-least  least         mixed     2.157   758  1058  205  206  312  h1b×4 h3a×5 h4a×3
m-joint  joint         mixed     1.607   212   507   46   62  184  h1b×6 h4a×6
实例     请求数    传输    排队    计算    返回    完成   （各段是该实例上请求的平均值，ms）
h1b           6    85.4     1.0   119.2     0.7   206.3
h4a           6     7.3   123.8   249.4     1.1   381.6
```

**要回答的问题**：

1. 以每类负载里最小的批完成时间为基准，算出四种策略的后悔值。联合代价在三类负载上各是多少？
2. `c-joint` 给三个实例各发了几个请求？这个比例与三个实例的 rate 之比接近吗？为什么不是全给 h4a，也不是平分？
3. `m-joint` 把哪类请求发给了谁？h3a 用上了吗？把请求间隔从 100 ms 改成 50 ms 再跑一次（`--gap-ms 50`），分配有什么变化？
4. 联合代价的分发器靠自己的记录知道每个实例要忙到什么时候。这份记录在什么情况下会不准？

#### 任务 9：实例的状态隔一会儿才知道（进阶）

联合代价的分发器是唯一的客户端，所以它自己的记录够用。更一般的情况是：分发器靠实例**上报**的状态决策，而上报是有间隔的（第 11 讲 4.2 节）。`--policy reported` 模拟这种情况：每隔 `--report-ms` 毫秒向各实例查询一次“还有多少工作没算完”，两次查询之间只按上一次查到的数来估计。它用到 TODO 4 的 `estimate`。

```bash
# 34. 更密的一批：24 个重计算请求，每 50 ms 一个；联合代价作基线
sudo python3 steer.py run --policy joint --workload compute --requests 24 --gap-ms 50 --label r-joint

# 35. 按上报的状态决策：每个请求之前都查询（0）、每 300 ms、每 1000 ms 查询一次
for ms in 0 300 1000; do
  sudo python3 steer.py run --policy reported --report-ms $ms --workload compute --requests 24 --gap-ms 50 --label r-$ms
done

# 36. 排成表；再看间隔 300 ms 时各实例的明细
python3 steer.py report r-joint r-0 r-300 r-1000
python3 steer.py show r-300
```

**实测样例**（节选：省略了每次运行打印的一行摘要与 `[上报]` 行）：

```output
标签     策略          负载    批完成s p50ms p95ms 传输 排队 计算  各实例请求数
r-joint  joint         compute   3.592  1492  2441    5 1024  416  h1b×3 h3a×7 h4a×14
r-0      reported      compute   3.760  1456  2460    5 1058  384  h1b×2 h3a×7 h4a×15
r-300    reported      compute   4.596  1357  2892    5 1107  436  h1b×4 h3a×6 h4a×14
r-1000   reported      compute   5.012  1851  3866    6 1698  291  h3a×4 h4a×20
实例     请求数    传输    排队    计算    返回    完成   （各段是该实例上请求的平均值，ms）
h1b           4     1.6  1419.1   996.4     1.2  2418.2
h3a           6     3.4  1115.2   497.1     0.9  1616.7
h4a          14     6.7  1015.0   249.6     1.6  1273.0
```

**要回答的问题**：

1. 上报间隔为 0 时，结果与联合代价接近吗？它们用的信息有什么不同？
2. 间隔 300 ms 与 1000 ms 时，各实例收到的请求数怎样变化？哪个实例被“挤爆”了？用“两次上报之间，分发器看到的状态不变”解释。
3. 批完成时间随间隔单调变差吗？你的数据如果不是单调的，可能是什么原因？（提示：一次查询之后的这一段时间里，所有请求都去了同一个实例；这个实例碰巧是谁，取决于查询的那一刻。）
4. 不缩短上报间隔，分发器自己可以做什么来减轻这个问题？至少提出一种做法，说明它用到了什么额外的信息。

#### 任务 10：换一组条件，完成闭环（挑战）

```bash
# 37. 换一组条件：实例的位置、算力与到它们的网络都变了；重测两张画像，再比较四种策略
sudo bash lab4_topo.sh scenario lecture11x
sudo bash edge.sh up lecture11x
sudo rm -rf /tmp/lab07-results/net-profile.json /tmp/lab07-results/net-profile.raw
sudo python3 checkup.py --src h1a --dst h2a,h3b,h4b --tput-repeats 1 --tput-seconds 1 --tput-omit 1 --out /tmp/lab07-results/net-profile.json
sudo python3 cpuprof.py
for p in nearest:near strongest:strong least:least joint:joint; do
  sudo python3 steer.py run --policy ${p%%:*} --workload mixed --label x-${p##*:}
done
python3 steer.py report x-near x-strong x-least x-joint
```

这一项没有样例输出。先完成上面的闭环，再**选一项深入做**：

- **两个分发器**：在 h1a 和另一台主机上（`--client h2b`，网络画像要另测这台主机到各实例的三对）同时各运行一个联合代价分发器，它们互相不知道对方发了什么。批完成时间比单个分发器发同样多的请求差多少？怎样改进？
- **改进上报**：给 `reported` 加一种修正（例如把自己在上一次查询之后发出的请求也算进去），用任务 9 的三个间隔检验。
- **拆开来做**：第 11 讲 6.2 节第 4 题。先在近的实例上做轻的一步、把输入变小，再送去强的实例做重的一步，估计并实测。

报告里写清楚：你的预测、实测、后悔值，以及改进前后的对比。

#### B 段的清理

```bash
# 38. 停实例、删 cgroup，恢复网络基线并核对
sudo bash edge.sh down
sudo bash lab4_topo.sh scenario clear
sudo bash lab4_topo.sh status

# 39. 留存结果（同名文件再次运行会被覆盖）
mkdir -p "$HOME/lab07-results" && cp -r /tmp/lab07-results "$HOME/lab07-results/"

# 40. 拆实验床（幂等）
sudo bash lab4_topo.sh down
```

**实测样例**：

```output
[*] 实例已停止，cgroup 已删除。
[*] 已恢复基线：全部端口 HTB + fq、档位不变，钉路已取消。
[档位] leaf–spine 100 Mbit/s；host 接入 100 Mbit/s。场景：无。
[基线] 32 个限速端口均为 HTB + fq，速率与 burst 为基线值。
[基线] r1–r4 没有额外策略路由（自然 ECMP）。
[*] 实验床已拆除；路由日志保留在 /tmp/lab04-results。
```

`edge.sh down` 会结束实例的两个进程并删除 `/sys/fs/cgroup/lab07`，重复执行不报错。要先停实例，再拆实验床。

---

## 五、故障排查

| 现象 | 先看什么 | 常见原因 |
| :--- | :--- | :--- |
| `jobrun.py`、`checkup.py` 报实验床尚未搭建或没有 namespace | `ls /run/lab04` | 没有执行 `lab4_topo.sh up`，或搭的是 Lab 3 或课堂网络 |
| `place.py score`、`predict` 或 `evaluate.py` 提示“需要先完成 TODO n” | 对应的 TODO | `score` 需要 TODO 1、2；`--shared` 需要 TODO 3；`rack`、`random`、`report` 不需要 |
| `checkup.py` 报“已存在：换一个 --out” | `ls /tmp/lab04-results` | 同名的画像或 `.raw` 目录已经存在；换一个文件名，或删掉旧的 `.json` 与 `.raw` 后重测 |
| `读不了画像` | 画像文件路径；`checkup.py` 是否跑完 | 路径写错；画像没有测全部主机对（用了 `--src` 等选项）；测量中途被打断 |
| `evaluate.py` 提示画像的场景与当前场景不同 | `sudo bash lab4_topo.sh status` 的第一行 | 换了场景没有重新画像，或忘了加载场景 |
| 预测与实测整体对不上 | 画像是否是当前场景下测的；机器上有没有别的负载（`top`） | 画像过期；画像期间有别的作业在跑 |
| 同一种放置两次实测差一倍 | `place.py report` 的“最慢上传”“最慢下发” | 两个 worker 撞上同一条上联（第 10 讲 3.3 节），属于正常现象，多跑几次看分布 |
| `checkup.py` 很慢或卡住 | `sudo python3 checkup.py --dry-run` 看计划 | 用了默认参数（每对 3 次，共十几分钟）；本实验用 `--tput-repeats 1 --tput-seconds 1 --tput-omit 1` |
| JCT 比样例长很多 | `sudo bash lab4_topo.sh status` | 端口偏离基线（上一个场景没有恢复），或加载了别的场景 |
| 实验中断后状态不明 | `sudo bash lab4_topo.sh status` | 执行 `lab4_topo.sh scenario clear` 恢复；再不行就 `lab4_topo.sh down` 后重新 `up` |
| `edge.sh up` 报需要 cgroup v2 或没有 cpu 控制器 | `cat /sys/fs/cgroup/cgroup.controllers` | 系统用的是 cgroup v1，或在不允许写 cgroup 的容器里；换一台标准的 Ubuntu 虚拟机 |
| `edge.sh up` 报实例没有起来 | `cat /run/lab07/<主机>.log` | 实验床没搭；7700 端口被上一次没停干净的实例占着，先 `edge.sh down` |
| `steer.py`、`cpuprof.py` 报没有在运行的实例或连接被拒 | `sudo bash edge.sh status` | 没有执行 `edge.sh up`；或者实验床重搭过，实例随旧的 namespace 一起没了 |
| `steer.py run` 报网络画像里没有某一对主机 | 画像是为哪几个实例测的 | 换了预设没有重测；按任务 6 第 25 步重测，`--dst` 写当前的三个实例 |
| 算力画像的 rate 与限额差很多，或两次差别大 | `top`；`sudo bash edge.sh status` | 机器上有别的负载在抢 CPU；三个实例的限额加起来超过了机器空闲的核数 |
| `steer.py` 提示需要先完成 TODO | 对应的 TODO | `estimate` 子命令和 `reported` 需要 TODO 4；`joint` 需要 TODO 4、5；`nearest`、`strongest`、`least`、`only:`、`split:` 不需要 |
| 同一种策略两次的批完成时间差不少 | `python3 steer.py show 标签` 的“传输”一列 | 大输入的请求要过两条限速的上联，多条连接怎样分到两条上每次不同（第 11 讲 3.3 节的边界） |

---

## 六、思考题

1. **PS 的位置与 worker 的位置**：同样是“放错了一台”，把 PS 放进慢机架和把一个 worker 放进慢机架，哪个代价更大？用任务 3 的数据说明。
2. **画像的代价**：快速画像用了约 2.5 分钟，期间每条链路都被 iperf3 占满过。如果集群里有作业在跑，画像会给它们带来什么影响，它们又会怎样影响画像？
3. **预测值并列时**：30 种放置的预测值只差 2%。真实的调度器在并列的候选之间通常还会考虑什么？（提示：机器上已经在跑的作业、故障域、公平。）
4. **接到第 11 讲**：A 段假设每台主机算得一样快。如果 h3a 的 CPU 只有别人的四分之一，而它的网络最好，A 段的代价模型应该怎么改？
5. **两个模型合起来**：A 段的代价模型有“共享上联”，B 段的估计有“排队”。它们描述的是同一类现象吗？各自的“共享资源”是什么？
6. **度量的单位**：B 段的 rate 是用一种纯 CPU 的计算量出来的。如果服务的计算主要耗在读写内存或使用 GPU 上，这张算力画像还能用吗？应该怎样测？

---

## 七、提交要求

**截止时间**：2026-12-28。

| 层次 | 提交内容 | 分值 |
| :--- | :--- | :--- |
| A 段 任务 1（基础） | 画像矩阵；两种放置的运行结果；三个问题的解答 | 5 |
| A 段 任务 2（基础） | `predict_round`（`RoundCases` 全部通过）；三种放置的对账表；三个问题的解答 | 15 |
| A 段 任务 3（基础） | `rank_placements`（`RankCases` 全部通过）；两个场景的评估表；四个问题的解答 | 15 |
| A 段 任务 4（进阶） | `expected_shared_time` 与 `predict_round(shared=True)`（`test_cost` 全部通过）；修正前后的预测与 3 次实测；四个问题的解答 | 10 |
| A 段 任务 5（挑战） | 盲测场景的画像、评估表与揭晓结果；所选一项的改进、数据与对比 | 5 |
| B 段 任务 6（基础） | 两张画像；9 次运行的对照表；四个问题的解答 | 10 |
| B 段 任务 7（基础） | `estimate`（`EstimateCases` 全部通过）；6 行的估计与实测对账表；三个问题的解答 | 15 |
| B 段 任务 8（基础） | `Joint.choose`（`test_steering` 全部通过）；12 次运行的对照表与后悔值；四个问题的解答 | 15 |
| B 段 任务 9（进阶） | 四次运行的对照表与间隔 300 ms 的明细；四个问题的解答 | 5 |
| B 段 任务 10（挑战） | 新条件下的两张画像与四种策略的对照表；所选一项的做法、数据与对比 | 5 |

报告建议 A 段 3–4 页，B 段 3–4 页。每项都要有预测、证据、解释：预测被推翻同样有价值，评分看证据是否充分、解释是否不超出数据。

提交 `sched/` 目录、报告和结果文件。不提交 `.venv/` 与 `__pycache__/`。

```bash
# 41. 打包代码与第 20、39 步留存的结果
tar --exclude=__pycache__ -czf "$HOME/lab07-submission.tgz" sched -C "$HOME/lab07-results" .
tar -tzf "$HOME/lab07-submission.tgz" | head
```

### 维护与验证

本文样例的来源与验证范围：

| 项目 | 内容 |
| :--- | :--- |
| 状态 | A 段（2026-11-15）与 B 段（2026-11-15）均已编写 |
| 环境 | 2026-11-15，备课虚拟机：Ubuntu 26.04.1、Linux `7.0.0-43-generic`、x86_64、2 核 2.8 GB；iperf3 3.20；实验床使用 Lab 2 参考路由。这台机器的系统默认拥塞控制是 `bbr`，工具都显式指定 `cubic` |
| 离线测试 | 骨架原样 36 个测试：4 个通过、32 个报错；补全 TODO 的参考实现 36 个全部通过。`tests/fixtures/` 的两份画像是 2026-11-14 在同一台虚拟机上实测的 |
| 实验床 | 2026-11-15 把本目录复制到仓库外（`~/lab07`），按本文原样、按顺序运行了 A 段的全部步骤（第 1–21 步与打包）：步骤 1–7 用骨架原样，步骤 8–14 用只补全 TODO 1、2 的临时副本，步骤 15 起用补全 A 段全部 TODO 的临时副本；A 段的实测样例均来自这次运行。B 段（第 23–41 步）同日另行运行：第 23–27 步用骨架原样，第 28 步起用补全全部 TODO 的临时副本，B 段的实测样例均来自这次运行；清理后 `/sys/fs/cgroup/lab07` 与 namespace 都不存在。任务 10 的第 37 步实测为 `nearest` 6.919、`strongest` 3.601、`least` 2.308、联合代价 1.606 秒。同机架优先的放置在这次运行里 6 次都落在约 27.5 秒一档（上传或下发有一个方向撞车）；第 10 讲备课时的 5 次是 36、35、27、27、19 秒。任务 5 的盲测路径用种子 7 跑通。清理后没有残留进程和 namespace。评估表的排版在这次运行之后改窄了：本文任务 3、4 的三张表是用 `evaluate.py --show` 从同一批结果文件重新打印的，新格式另用一次短的实跑（1 个随机种子、各 1 次）确认过。参考实现不入库 |
| 单独运行 | 本目录复制到仓库外（`~/lab07`）后按本文原样运行，脚本只依赖本目录的文件 |
| Ubuntu 24.04 | 2026-11-15 在 Ubuntu 24.04.5 用户态容器（iproute2 6.1.0、Python 3.12.3、iperf3 3.16；宿主内核 Linux 7.3、4 vCPU）中，把本目录复制到仓库外，按同样的三段方式原样运行了 A 段的全部步骤，全部通过。读数与本文样例一致：按画像打分的放置 8.64–8.67 秒（后悔值 1.00）；`lecture10` 下同机架优先 35.31、35.52 秒；`rack2-slow` 下同机架优先 5 次为 19.13、19.10、27.43、27.42、35.84 秒，三档都出现了。这只说明用户态是 24.04，内核不是学生环境的内核。B 段：这个容器默认不允许给子 cgroup 开启 `cpu` 控制器，`edge.sh up` 直接运行会报错退出（已确认它不改动容器的 cgroup 状态）。2026-11-15 另起了一个同镜像的临时容器，先把容器里的进程移进一个子 cgroup、再给容器的 cgroup 根开启 `cpu` 控制器，然后把本目录复制到仓库外，按原样运行了 B 段的全部步骤（第 23–27 步用骨架，第 28 步起用补全全部 TODO 的临时副本），全部通过，读数与本文样例一致：算力画像 0.152、0.305、0.632；`compute` 的四种策略 11.998、3.005、4.004、2.080 秒；`mixed` 的联合代价 1.601 秒；任务 9 的四次 3.589、3.755、4.590、5.011 秒。同一容器里离线测试的结果与上文相同。**没有验证到的**：学生在标准虚拟机上不需要“先移进程”这一步，`edge.sh` 在真正的 24.04 根 cgroup 上自动开启控制器的那条路径只在备课虚拟机（26.04）上验证过 |
