# Lab 7　算网协同调度

> 对应第 10、11 讲　｜　建议用时 2 周　｜　A 段（第 10 讲后）约 4 小时；B 段（第 11 讲后）随第 11 讲补充　｜　产出：一个能读画像、给放置打分并在全部候选里选出最好放置的调度器，以及它与两种不看画像的策略的实测对照

第 10 讲的课上，你读了一张网络画像，手算了三种放置的作业完成时间，又凭观察在一个未知的网络里挑出了一种好的放置。本实验把这些手算写成程序：让它读画像文件，给任意一种放置打分，在全部 280 种放置里找出预测最好的一个，再用实测检验它比“同机架优先”和“随机”好多少。

本实验分两段：**A 段**（任务 1–5）对应第 10 讲，只考虑网络，其中任务 1–3 人人完成，任务 4 是进阶，任务 5 是挑战。**B 段**对应第 11 讲，主机的算力也不相同时，把网络和算力放在一起决策；B 段的任务随第 11 讲补充到本文。计分见第七节。

---

## 一、实验目标

1. 用体检工具测一张全部主机对的网络画像，读出网络哪里慢。
2. 把第 10 讲的三项代价模型写成函数，预测一种放置的每轮时间与作业完成时间（JCT），并与实测对账。
3. 给全部候选放置打分并排序，选出预测最好的放置；用后悔值比较“同机架优先”“随机”“按画像打分”三种策略。
4. 用机架信息给共享上联做修正，说明修正解决了什么、还剩什么没有解决。

---

## 二、预备知识与工具

**先读**：

- [第 10 讲](../../docs/topology_aware_scheduling.md)模块二：画像矩阵的读法；模块三：代价模型与共享上联；模块五：后悔值。
- [第 08 讲](../../docs/communication_cost.md)模块一：参数服务器一轮的时间结构与 barrier。
- [Lab 3 指导书](../03/README.md) 3.2 节：节点、接口与地址约定。Lab 3、Lab 4、Lab 6 没有做完也可以做本实验：实验床、画像工具和作业都是给定的完整版。

**环境**：Linux（`sudo`）、`iproute2`、`iputils-ping`、`iperf3`、Python 3.10 及以上与 `uv`；内核支持 namespace、veth、bridge、HTB、fq 与 netem。

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
| `tests/` | 离线测试；`tests/fixtures/` 是两份实测的画像 | 给定，用来检查 TODO |

### 3.2 实验床与测量口径

实验床是本目录的 [`lab4_topo.sh`](lab4_topo.sh)，与第 06–10 讲是同一张：2 spine（`r5`、`r6`）× 4 leaf（`r1`–`r4`）× 8 host（`h1a`–`h4b`），基线时 host 接入口与 leaf–spine 链路都是 100 Mbit/s。本实验用到三个场景：

| 场景 | 内容 | 用在哪里 |
| :--- | :--- | :--- |
| `rack2-slow` | 机架 2 的两条上联、两个方向都降到 10 Mbit/s | 任务 1–4 |
| `lecture10` | 第 10 讲综合动手的场景：h1a 接入两个方向 20 Mbit/s，机架 3 的上联 10 Mbit/s | 任务 3 |
| `blind --seed N` | 随机注入 1–2 项隐藏条件 | 任务 5 |

| 量 | 定义 |
| :--- | :--- |
| 作业 | 参数服务器，默认 N=4、模型 1 MB（$10^6$ 字节）、10 轮、每个 worker 每轮计算 200 ms（`time.sleep`，不占 CPU）、CUBIC |
| 放置 | PS 所在的主机，加上 N 个 worker 所在的主机；8 台主机共 $8 \times \binom{7}{4} = 280$ 种 |
| JCT | 最晚的 `model_last` 减最早的 `compute_start` |
| 画像里的吞吐 | `iperf3` 接收端速率，Mbit/s（$10^6$ bit/s）；一次只测一对主机；快速画像每对测 1 次、统计 1 秒 |
| 预测 JCT | 轮数 × 预测的每轮时间；每轮时间 = 计算 + 上传 + 下发（第 10 讲 3.1 节） |
| 后悔值 | 一种放置的平均实测 JCT ÷ 参与比较的放置中最小的平均实测 JCT；1.00 表示它就是最好的 |

作业结果写入 `/tmp/lab06-results/<label>.json`（`jobrun.py` 沿用 Lab 6 的结果目录），画像默认写入 `/tmp/lab04-results/`，`evaluate.py` 的汇总写入 `/tmp/lab07-results/`。作业结果与评估汇总的**同名文件会被覆盖**；`checkup.py` 则相反，发现同名的画像或原始输出目录已经存在时会拒绝运行，重测时换一个 `--out` 文件名，或先删掉旧的 `.json` 与 `.raw`。重启主机可能清除 `/tmp`，需要留存时另外复制。

**画像只代表测量时的网络**。换了场景要重新测；`evaluate.py` 发现画像里记录的场景与实验床当前的场景不一致时会提示。

### 3.3 骨架与测试

```bash
# 1. 进入 Lab 7 目录（压缩包解压后的目录，路径换成你自己的），准备路由守护进程的 Python 环境
cd ~/lab07
uv sync --frozen

# 2. 离线测试：骨架原样应为 23 个测试中 3 个通过、20 个报错
python3 -m unittest 2>&1 | tail -1
```

```output
FAILED (errors=20)
```

通过的 3 个是给定部分的测试（候选数目与两种不看画像的策略）。TODO 对应的测试：`tests.test_cost.RoundCases` 是 TODO 1，`tests.test_strategy.RankCases` 是 TODO 2，`tests.test_cost.SharedTimeCases` 与 `SharedRoundCases` 是 TODO 3。本实验的工具只用 Python 标准库，直接用系统 `python3` 运行。

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

B 段对应第 11 讲：用 cgroup 限制 CPU，让各主机的算力不同，再实现一个请求分发器，比较“就近”“最空闲”“算力与网络联合代价”三种策略。任务与 TODO 随第 11 讲补充到本文，A 段的画像与代价模型会接着用。

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

---

## 六、思考题

1. **PS 的位置与 worker 的位置**：同样是“放错了一台”，把 PS 放进慢机架和把一个 worker 放进慢机架，哪个代价更大？用任务 3 的数据说明。
2. **画像的代价**：快速画像用了约 2.5 分钟，期间每条链路都被 iperf3 占满过。如果集群里有作业在跑，画像会给它们带来什么影响，它们又会怎样影响画像？
3. **预测值并列时**：30 种放置的预测值只差 2%。真实的调度器在并列的候选之间通常还会考虑什么？（提示：机器上已经在跑的作业、故障域、公平。）
4. **接到第 11 讲**：本实验假设每台主机算得一样快。如果 h3a 的 CPU 只有别人的四分之一，而它的网络最好，代价模型应该怎么改？

---

## 七、提交要求

**截止时间**：随 B 段一起公布。

| 层次 | 提交内容 | 分值 |
| :--- | :--- | :--- |
| A 段 任务 1（基础） | 画像矩阵；两种放置的运行结果；三个问题的解答 | 5 |
| A 段 任务 2（基础） | `predict_round`（`RoundCases` 全部通过）；三种放置的对账表；三个问题的解答 | 15 |
| A 段 任务 3（基础） | `rank_placements`（`RankCases` 全部通过）；两个场景的评估表；四个问题的解答 | 15 |
| A 段 任务 4（进阶） | `expected_shared_time` 与 `predict_round(shared=True)`（`test_cost` 全部通过）；修正前后的预测与 3 次实测；四个问题的解答 | 10 |
| A 段 任务 5（挑战） | 盲测场景的画像、评估表与揭晓结果；所选一项的改进、数据与对比 | 5 |
| B 段 | 随第 11 讲公布 | 50 |

报告建议 A 段 3–4 页。每项都要有预测、证据、解释：预测被推翻同样有价值，评分看证据是否充分、解释是否不超出数据。

提交 `sched/` 目录、报告和结果文件。不提交 `.venv/` 与 `__pycache__/`。

```bash
# 22. 打包代码与第 20 步留存的结果
tar --exclude=__pycache__ -czf "$HOME/lab07-submission.tgz" sched -C "$HOME/lab07-results" .
tar -tzf "$HOME/lab07-submission.tgz" | head
```

### 维护与验证

本文样例的来源与验证范围：

| 项目 | 内容 |
| :--- | :--- |
| 状态 | A 段已完成；B 段尚未编写，随第 11 讲补充 |
| 环境 | 2026-11-15，备课虚拟机：Ubuntu 26.04.1、Linux `7.0.0-43-generic`、x86_64、2 核 2.8 GB；iperf3 3.20；实验床使用 Lab 2 参考路由。这台机器的系统默认拥塞控制是 `bbr`，工具都显式指定 `cubic` |
| 离线测试 | 骨架原样 23 个测试：3 个通过、20 个报错；补全 TODO 的参考实现 23 个全部通过。`tests/fixtures/` 的两份画像是 2026-11-14 在同一台虚拟机上实测的 |
| 实验床 | 2026-11-15 把本目录复制到仓库外（`~/lab07`），按本文原样、按顺序运行了全部 22 个步骤：步骤 1–7 用骨架原样，步骤 8–14 用只补全 TODO 1、2 的临时副本，步骤 15–22 用补全全部 TODO 的临时副本；实测样例均来自这次运行。同机架优先的放置在这次运行里 6 次都落在约 27.5 秒一档（上传或下发有一个方向撞车）；第 10 讲备课时的 5 次是 36、35、27、27、19 秒。任务 5 的盲测路径用种子 7 跑通。清理后没有残留进程和 namespace。评估表的排版在这次运行之后改窄了：本文任务 3、4 的三张表是用 `evaluate.py --show` 从同一批结果文件重新打印的，新格式另用一次短的实跑（1 个随机种子、各 1 次）确认过。参考实现不入库 |
| 单独运行 | 本目录复制到仓库外（`~/lab07`）后按本文原样运行，脚本只依赖本目录的文件 |
| Ubuntu 24.04 | 2026-11-15 在 Ubuntu 24.04.5 用户态容器（iproute2 6.1.0、Python 3.12.3、iperf3 3.16；宿主内核 Linux 7.3、4 vCPU）中，把本目录复制到仓库外，按同样的三段方式原样运行了全部 22 个步骤，全部通过。读数与本文样例一致：按画像打分的放置 8.64–8.67 秒（后悔值 1.00）；`lecture10` 下同机架优先 35.31、35.52 秒；`rack2-slow` 下同机架优先 5 次为 19.13、19.10、27.43、27.42、35.84 秒，三档都出现了。这只说明用户态是 24.04，内核不是学生环境的内核 |
