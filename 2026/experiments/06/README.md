# Lab 6　分布式作业的时间花在哪，以及怎么省

> 对应第 08、09 讲　｜　建议用时 2 周　｜　A 段（第 08 讲后）约 3 小时；B 段（第 09 讲后）约 4 小时　｜　截止：2026-12-07　｜　产出：一份能闭合的 JCT 拆账、一个能和实测对账的预测模型；B 段再做一次“只改通信方式、计算不变、作业变快”的实证

第 08 讲的课上，你手算了一轮的四段时间，用两个样本估了 $\alpha$、$\beta$，又预测了几个配置。本实验把这些手算写成程序，让它们能处理整个作业，再用更多配置检验模型，并解释模型错在哪里。

本实验分两段：**A 段**（任务 1–4）对应第 08 讲，人人完成；**B 段**（任务 5–8）对应第 09 讲，实现 Ring AllReduce，比较放置与环序，并研究 straggler，其中任务 5 人人完成，任务 6、7 是进阶，任务 8 是挑战。计分见第七节。

---

## 一、实验目标

1. 把作业的 JCT 拆成计算、上传、等待、下载，并用“四段之和等于总时间”检验自己的拆账。
2. 用最小二乘拟合 $T(m)=\alpha+\beta m$，说明 $\alpha$、$\beta$ 各自的含义与可信度。
3. 预测参数服务器作业的 JCT，在多个配置上和实测对账，解释偏差最大的一项。
4. （B 段）实现 Ring AllReduce，实测通信量并与理论值对照；比较随机环序与拓扑感知环序；研究 straggler 如何被 barrier 放大。

---

## 二、预备知识与工具

**先读**：

- [第 08 讲](../../docs/communication_cost.md)模块一到模块三：四段的计时口径、`timeline.py` 的读法、α-β 模型；4.2 节：上联收窄时的 ECMP 现象。
- 第 09 讲：Ring AllReduce 与环序（B 段）。算法也写在本文 B 段的开头，够你动手实现。
- [Lab 3 指导书](../03/README.md) 3.2 节：节点、接口与地址约定。Lab 3 没有做完也可以做本实验，实验床用给定的完整版。

**环境**：Linux（`sudo`）、`iproute2`、`iputils-ping`、Python 3.10 及以上与 `uv`；内核支持 namespace、veth、bridge、HTB、fq 与 netem。

**约定**：以下命令都**从仓库根目录执行**，需要 root 的步骤显式写了 `sudo`。所有工具都显式指定拥塞控制算法，默认 `cubic`，不依赖系统默认值。

---

## 三、目录与资源

### 3.1 文件

| 文件 | 说明 |
| :--- | :--- |
| `jobrun.py` | 作业入口（给定）：在各 namespace 启动 PS 和 worker，合并时间戳，写结果文件，打印 JCT |
| `job.py` | PS 与 worker 的进程（给定，建议读一遍） |
| `timeline.py` | 打印某一轮的原始时间戳（给定），只读文件 |
| `curve.py` | 测传输时间与数据量的关系（给定），接收端回执后才停表 |
| `decompose.py` | 打印拆账表（给定），调用 TODO 1、2 |
| `fit.py` | 拟合并预测（给定），调用 TODO 3、4、6 |
| `compare.py` | 把多次作业排成表（给定），只读文件，不依赖 TODO；`--steps` 看环上每一步的用时，`--slow` 数变慢的轮 |
| `jobkit/wire.py`、`compute.py` | 报文格式、时间戳、本地计算（给定） |
| `jobkit/decompose.py` | **TODO 1、2**：拆一轮，汇总整个作业 |
| `jobkit/alphabeta.py` | **TODO 3、4、6**：最小二乘拟合，预测参数服务器与 Ring 的一轮 |
| `jobkit/ring.py` | **TODO 5、7**：Ring AllReduce，拓扑感知环序 |
| `tests/` | 离线测试，不需要 root，也不需要实验床 |

### 3.2 实验床与测量口径

实验床是 [`04/topo.sh`](../04/topo.sh)，与第 06、07、08 讲相同：2 spine（`r5`、`r6`）× 4 leaf（`r1`–`r4`）× 8 host（`h1a`–`h4b`），host 接入口与 leaf–spine 链路都是 100 Mbit/s。PS 固定在 h1a，`--n N` 取 h3a、h2a、h4a、h1b、h2b、h3b、h4b 的前 N 台作为 worker。Ring 没有 PS，`--workers all` 表示全部 8 台。

| 量 | 定义 |
| :--- | :--- |
| 模型大小 $S$ | `--model-mb` 给定，1 MB 等于 $10^6$ 字节；梯度与模型一样大 |
| 计算时间 | `--compute-ms`（每个 worker 相同）或 `--compute-total-ms`（总量平分给 N 个 worker）；默认占位计算 `time.sleep`，不占 CPU |
| 上传 | 从 `compute_end` 到 PS 收到该 worker 梯度的最后一个字节，**不是** `sendall` 返回的时刻 |
| 等待 | 从 PS 收齐该 worker 的梯度，到 PS 收齐全部梯度并聚合完（barrier） |
| 下载 | 从 barrier 到该 worker 收到模型的最后一个字节 |
| JCT | 最晚的 `model_last` 减最早的 `compute_start` |
| $T(m)$ | `curve.py` 测得：发送方开始发送到收到接收方回执，包含一个方向的传输和一次回执 |
| Ring 的通信 | 从 `compute_end` 到 `ring_end`。没有 PS，也没有显式 barrier，节点靠等左邻居的数据自然同步，等待包含在通信里 |
| 发送/S | 平均每个 worker 每轮在应用层发出的字节数，以 $S$ 为单位；Ring 的理论值是 $2(N-1)/N$ |
| 最忙发送 | 8 台 host 的 `eth0` 里发送字节最多的一台，包含报文头和 ACK |

时间戳都用 `time.monotonic()`。所有 namespace 跑在同一台机器上，共用一个单调时钟，跨进程可以直接相减；换到真实集群，这张表需要先做时钟同步。

结果写入 `/tmp/lab06-results/<label>.json`，**同名标签会被覆盖**，重启主机可能清除 `/tmp`，需要留存时另外复制。作业进程运行完就退出，不留后台进程。

**为什么默认不用真实计算**：所有 namespace 共用同一台机器的 CPU，真实计算会互相抢 CPU，JCT 的差别就不只来自通信了。任务 2 的选做部分让你亲眼看到这一点。

### 3.3 骨架与测试

```bash
# 1. 准备 Python 环境（路由器复用 Lab 2 的环境；本实验的环境含 numpy）
uv sync --project 2026/experiments/02 --frozen
uv sync --project 2026/experiments/06 --frozen

# 2. 离线测试：骨架原样应为 24 个测试中 1 个通过、4 个失败、19 个报错
(cd 2026/experiments/06 && uv run --frozen python -m unittest 2>&1 | tail -1)
```

```output
FAILED (failures=4, errors=19)
```

通过的 1 个是给定的切块函数的测试。TODO 对应的测试分别在 `tests.test_decompose`（TODO 1、2）、`tests.test_alphabeta`（`FitCases` 是 TODO 3，`PredictCases` 是 TODO 4）与 `tests.test_ring`（`RingCases` 是 TODO 5，`RingPredictCases` 是 TODO 6，`OrderCases` 是 TODO 7）。

---

## 四、实验步骤

### A 段：基础任务（第 08 讲后）

#### 任务 1：跑通基线，手算一轮

**预测**：N=7，模型 1 MB，每轮计算 200 ms，10 轮。课上的结果还记得吗？这次预计的 JCT 是多少？

```bash
# 3. 清理其他实验的网络（节点重名），搭完整实验床并自检
sudo bash 2026/experiments/03/classroom.sh down
sudo bash 2026/experiments/03/topo.sh down
sudo bash 2026/experiments/04/topo.sh up
sudo bash 2026/experiments/04/topo.sh check

# 4. 基线作业与第 5 轮的原始时间戳
sudo python3 2026/experiments/06/jobrun.py --label t1-base
python3 2026/experiments/06/timeline.py /tmp/lab06-results/t1-base.json --round 5
```

**实测样例**：

```output
[t1-base] N=7 模型 1 MB 10 轮 cubic：JCT = 13.695 s，结果 /tmp/lab06-results/t1-base.json
作业 t1-base：N=7，模型 1 MB，第 5 轮（从 0 数），单位 ms
worker           计算开始         计算结束    sendall返回         PS收齐      barrier         模型收齐
h1b              12.4        212.5        391.0        794.6        800.0       1380.4
h2a               7.4        207.5        405.4        796.6        800.0       1366.2
h2b               0.0        200.1        399.8        796.1        800.0       1385.1
h3a              16.2        216.3        404.0        798.7        800.0       1386.3
h3b               8.6        208.7        510.1        798.0        800.0       1379.1
h4a              13.0        213.1        416.1        799.9        800.0       1362.1
h4b               5.8        205.9        400.1        793.7        800.0       1384.3
```

**要写进报告的**：选自己结果里的**两个** worker，手算四段时间，验证四段之和等于这一轮的总长。这两个数字就是任务 2 的验算依据。

#### 任务 2：把拆账写成程序（TODO 1、2）

打开 [`jobkit/decompose.py`](jobkit/decompose.py)，按注释完成 `round_breakdown()` 与 `job_breakdown()`。上传段的终点要用 PS 一侧的 `grad_last`，不要用 `local_send_done`。

```bash
# 5. 测试通过后输出 OK
(cd 2026/experiments/06 && uv run --frozen python -m unittest tests.test_decompose 2>&1 | tail -1)

# 6. 打印整个作业的拆账（只读文件，不需要 root）
python3 2026/experiments/06/decompose.py /tmp/lab06-results/t1-base.json

# 7. 让 h3a 的计算时间变成 4 倍，看等待段出现在谁身上
sudo python3 2026/experiments/06/jobrun.py --label t2-strag --straggler h3a:4
python3 2026/experiments/06/decompose.py /tmp/lab06-results/t2-strag.json
```

**实测样例**（TODO 由备课用的参考实现补全）：

```output
作业 t1-base：ps，N=7，模型 1 MB，10 轮，cubic
JCT = 13.695 s
worker        计算 s      上传 s      等待 s      下载 s      合计 s
h1b          2.006     5.715     0.177     5.794    13.692
h2a          2.001     5.854     0.075     5.748    13.678
h2b          2.002     5.861     0.027     5.784    13.674
h3a          2.001     5.836     0.008     5.849    13.694
h3b          2.003     5.825     0.082     5.781    13.691
h4a          2.003     5.828     0.059     5.791    13.681
h4b          2.004     5.846     0.026     5.807    13.684
平均           2.003     5.824     0.065     5.793    13.685
占比           14.6%     42.6%      0.5%     42.3%
作业 t2-strag：ps，N=7，模型 1 MB，10 轮，cubic
JCT = 14.694 s
worker        计算 s      上传 s      等待 s      下载 s      合计 s
h1b          2.004     5.011     1.865     5.814    14.693
h2a          2.002     5.135     1.728     5.814    14.679
h2b          2.004     5.120     1.726     5.832    14.683
h3a          8.002     0.853     0.000     5.833    14.688
h3b          2.003     5.104     1.744     5.833    14.684
h4a          2.003     5.149     1.735     5.777    14.664
h4b          2.002     5.153     1.741     5.791    14.687
平均           2.860     4.504     1.506     5.813    14.683
占比           19.5%     30.7%     10.3%     39.6%
```

**要回答的问题**：

1. 拿任务 1 手算的第 5 轮，和程序里这一轮的结果对一下，一致吗？（可以临时打印 `round_breakdown` 的返回值。）
2. 每个 worker 的“合计”和 JCT 差多少？如果差得多，说明了什么？
3. 看 `t2-strag`：h3a 的计算多了 6 s，而其他 worker 的等待只多了约 1.7 s。多出来的时间到哪里去了？结合第 08 讲 4.3 节解释。

**选做：亲眼看 CPU 争用**。占位计算不占 CPU，换成真实的 numpy 梯度试试。计算量相同，看 N 变大时单个 worker 的计算时间：

```bash
# 8. 真实 numpy 计算，N=1 和 N=7，每轮 60 次梯度计算
sudo python3 2026/experiments/06/jobrun.py --label t2-np-n1 --n 1 --compute numpy --iters 60 --rounds 5
sudo python3 2026/experiments/06/jobrun.py --label t2-np-n7 --compute numpy --iters 60 --rounds 5
python3 2026/experiments/06/decompose.py /tmp/lab06-results/t2-np-n1.json /tmp/lab06-results/t2-np-n7.json
```

备课的 2 核虚拟机上，N=1 时平均计算 0.999 s，N=7 时 4.509 s，每个 worker 算同样的量却慢了 4.5 倍。你的机器核数不同，结果也会不同，这正是不能用真实计算比较通信方案的原因。

#### 任务 3：拟合 α-β（TODO 3）

打开 [`jobkit/alphabeta.py`](jobkit/alphabeta.py)，完成 `fit_alpha_beta()`。

**预测**：跨机架（h1a→h3a）和同机架（h1a→h1b）的 $\alpha$、$\beta$ 会有多大差别？

```bash
# 9. 测试通过后输出 OK
(cd 2026/experiments/06 && uv run --frozen python -m unittest tests.test_alphabeta.FitCases 2>&1 | tail -1)

# 10. 测跨机架与同机架两条曲线，共约 70 秒
sudo python3 2026/experiments/06/curve.py --label t3-cross --src h1a --dst h3a
sudo python3 2026/experiments/06/curve.py --label t3-rack --src h1a --dst h1b

# 11. 拟合。第二条命令只用不超过 100 KB 的样本
python3 2026/experiments/06/fit.py /tmp/lab06-results/t3-cross.json
python3 2026/experiments/06/fit.py /tmp/lab06-results/t3-cross.json --max-bytes 100000
python3 2026/experiments/06/fit.py /tmp/lab06-results/t3-rack.json
```

**实测样例**（TODO 由备课用的参考实现补全）：

```output
h1a→h3a cubic，6 种大小（每种取中位数）
α = 0.49 ms，β = 83.66 ns/字节，折合 95.6 Mbit/s
        字节      实测 ms      拟合 ms       偏差
      1000       0.58       0.57      -1%
     10000       1.12       1.32      18%
    100000       8.89       8.85      -0%
   1000000      84.16      84.15      -0%
   4000000     335.31     335.13      -0%
  16000000    1339.01    1339.06       0%
h1a→h3a cubic，3 种大小（每种取中位数）
α = 0.39 ms，β = 84.92 ns/字节，折合 94.2 Mbit/s
        字节      实测 ms      拟合 ms       偏差
      1000       0.58       0.47     -18%
     10000       1.12       1.24      10%
    100000       8.89       8.88      -0%
h1a→h1b cubic，6 种大小（每种取中位数）
α = 0.45 ms，β = 83.65 ns/字节，折合 95.6 Mbit/s
        字节      实测 ms      拟合 ms       偏差
      1000       0.42       0.53      25%
     10000       1.02       1.28      26%
    100000       8.70       8.81       1%
   1000000      83.83      84.10       0%
   4000000     336.04     335.06      -0%
  16000000    1338.69    1338.92       0%
```

**要回答的问题**：

1. 全量拟合的 $\alpha$ 可信吗？备课时另一次同样的命令得到 $\alpha=0.08$ ms。最小二乘的截距为什么这么不稳定？
2. 跨机架和同机架的差别，能从数字里看出来吗？如果看不出来，为什么？（提示：这张网很小，算一算往返时间和传 1 字节的时间谁大。）
3. 把 $\beta$ 换算成带宽，解释它为什么不等于配置的 100 Mbit/s。

#### 任务 4：预测 JCT 并对账（TODO 4）

完成 `predict_ps_round()`。在下面 6 个配置上用任务 3 的 $\alpha$、$\beta$ 预测，再实测对比。**先把预测写下来，再运行。**

```bash
# 12. 测试通过后输出 OK
(cd 2026/experiments/06 && uv run --frozen python -m unittest tests.test_alphabeta.PredictCases 2>&1 | tail -1)

# 13. 另外 5 个配置，共约 45 秒；N=7、1 MB 用任务 1 的 t1-base
for n in 1 2 4; do
  sudo python3 2026/experiments/06/jobrun.py --label t4-n"$n" --n "$n"
done
sudo python3 2026/experiments/06/jobrun.py --label t4-s025 --model-mb 0.25
sudo python3 2026/experiments/06/jobrun.py --label t4-s4 --model-mb 4 --rounds 5

# 14. 用 α、β 预测并和实测对账
python3 2026/experiments/06/fit.py /tmp/lab06-results/t3-cross.json --predict /tmp/lab06-results/t4-n1.json /tmp/lab06-results/t4-n2.json /tmp/lab06-results/t4-n4.json /tmp/lab06-results/t1-base.json /tmp/lab06-results/t4-s025.json /tmp/lab06-results/t4-s4.json
```

**实测样例**（节选，省略了与任务 3 相同的拟合表）：

```output
作业                N    预测 JCT s    实测 JCT s      偏差
t4-n1             1       3.683       3.691   -0.2%
t4-n2             2       5.356       5.355    0.0%
t4-n4             4       8.703       8.919   -2.4%
t1-base           7      13.722      13.695    0.2%
t4-s025           7       4.938       4.918    0.4%
t4-s4             7      24.430      24.495   -0.3%
```

**要回答的问题**：

1. 偏差最大的是哪一项？用第 08 讲的方法（`timeline.py`、`decompose.py`）找证据，说明它为什么偏了。证据不够时，说清楚还需要测什么，**不要编造唯一的原因**。
2. 模型用了哪些假设？列出来，每条说明这次实验怎么保证了它。
3. 如果把 `curve.py` 测出来的 $\alpha$ 直接用在高时延的路径上，预测会偏高还是偏低？（第 08 讲 3.3 节，$\alpha$ 里含一个完整的往返。）

A 段做完可以先清理（重复执行应成功），B 段开始时重新搭建：

```bash
# 15. 核对端口基线；需要留存结果就先复制；然后拆实验床
sudo bash 2026/experiments/04/topo.sh status
mkdir -p "$HOME/lab06-results" && cp -r /tmp/lab06-results/. "$HOME/lab06-results/"
sudo bash 2026/experiments/04/topo.sh down
```

### B 段：第 09 讲后

**Ring AllReduce 怎么工作**。参数服务器让所有数据都过一条链路。Ring AllReduce 不要 PS：$N$ 个节点排成环，每个节点只向右邻居发、从左邻居收，把向量切成 $N$ 块，分两个阶段走完：

- **Reduce-Scatter**（$N-1$ 步）：每块沿环走一圈，边走边合并。结束时每个节点手里有一块已经合并完的结果。
- **Allgather**（$N-1$ 步）：把合并好的块沿环传开，结束时每个节点都有完整结果。

每一步每个节点发 $S/N$ 字节，一共 $2(N-1)$ 步，所以**每个节点发送 $2(N-1)/N\cdot S$ 字节**。下面是 $N=3$ 的手工推演，$c_j$ 是第 $j$ 块，方括号里是已经合并进来的节点：

| 阶段与步 | 节点 0 发 → 收 | 节点 1 发 → 收 | 节点 2 发 → 收 |
| :--- | :--- | :--- | :--- |
| Reduce-Scatter 第 0 步 | $c_0$ → $c_2$，得 $c_2[0,2]$ | $c_1$ → $c_0$，得 $c_0[0,1]$ | $c_2$ → $c_1$，得 $c_1[1,2]$ |
| Reduce-Scatter 第 1 步 | $c_2[0,2]$ → $c_1[1,2]$，得 $c_1$ 全 | $c_0[0,1]$ → $c_2[0,2]$，得 $c_2$ 全 | $c_1[1,2]$ → $c_0[0,1]$，得 $c_0$ 全 |
| Allgather 第 0 步 | $c_1$ 全 → $c_0$ 全 | $c_2$ 全 → $c_1$ 全 | $c_0$ 全 → $c_2$ 全 |
| Allgather 第 1 步 | $c_0$ 全 → $c_2$ 全 | $c_1$ 全 → $c_0$ 全 | $c_2$ 全 → $c_1$ 全 |

作业用异或作为合并操作，最后一轮每个节点都会核对结果的摘要，算错了 `jobrun.py` 会直接报错。

#### 任务 5：实现 Ring AllReduce（基础，TODO 5、6）

打开 [`jobkit/ring.py`](jobkit/ring.py)，完成 `ring_allreduce()`。

**预测**：同样 7 台 worker、同样的计算，只把参数服务器换成 Ring。每个 worker 发的字节是变多还是变少？JCT 呢？

```bash
# 16. 测试通过后输出 OK
(cd 2026/experiments/06 && uv run --frozen python -m unittest tests.test_ring.RingCases 2>&1 | tail -1)

# 17. 搭建实验床并测一条曲线（已经搭好的话，up 不会出错）
sudo bash 2026/experiments/04/topo.sh up
sudo bash 2026/experiments/04/topo.sh check
sudo python3 2026/experiments/06/curve.py --label t5-curve

# 18. 同样的 7 台 worker，按机架顺序排列，只换通信方式
RACK=h1b,h2a,h2b,h3a,h3b,h4a,h4b
sudo python3 2026/experiments/06/jobrun.py --label t5-ps --workers "$RACK"
sudo python3 2026/experiments/06/jobrun.py --algo ring --label t5-ring --workers "$RACK"
python3 2026/experiments/06/compare.py t5-ps t5-ring
python3 2026/experiments/06/compare.py --steps t5-ring
```

**实测样例**（TODO 由备课用的参考实现补全，省略了曲线与 JCT 行）：

```output
标签              算法    N 环序    跨机架     JCT s   计算ms   通信ms  发送/S最忙发送MB
t5-ps             ps      7 -           -    13.706    200.2   1169.3   1.000     74.8 h1a
t5-ring           ring    7 given       4     3.987    200.6    197.5   1.714     18.2 h2b
t5-ring：N=7，每步传 142857 字节，跨机架边 4，共 12 步，平均每步用时（ms）
  15.6 19.5 18.7 17.3 17.1 17.5 17.0 15.2 15.0 14.9 14.8 14.9
```

完成 [`jobkit/alphabeta.py`](jobkit/alphabeta.py) 的 `predict_ring_round()`，再改变 $N$ 和 $S$，和实测对账。**先写下预测，再运行。**

```bash
# 19. 测试通过后输出 OK
(cd 2026/experiments/06 && uv run --frozen python -m unittest tests.test_ring.RingPredictCases 2>&1 | tail -1)

# 20. 另外 4 个配置，共约 15 秒；N=7、1 MB 用上面的 t5-ring
RACK=h1b,h2a,h2b,h3a,h3b,h4a,h4b
sudo python3 2026/experiments/06/jobrun.py --algo ring --label t5-n2 --workers h2a,h2b
sudo python3 2026/experiments/06/jobrun.py --algo ring --label t5-n4 --workers h2a,h2b,h3a,h3b
sudo python3 2026/experiments/06/jobrun.py --algo ring --label t5-s025 --workers "$RACK" --model-mb 0.25
sudo python3 2026/experiments/06/jobrun.py --algo ring --label t5-s4 --workers "$RACK" --model-mb 4 --rounds 5

# 21. 用 α、β 预测并和实测对账
python3 2026/experiments/06/fit.py /tmp/lab06-results/t5-curve.json --predict /tmp/lab06-results/t5-n2.json /tmp/lab06-results/t5-n4.json /tmp/lab06-results/t5-ring.json /tmp/lab06-results/t5-s025.json /tmp/lab06-results/t5-s4.json
```

**实测样例**（节选）：

```output
作业                N    预测 JCT s    实测 JCT s      偏差
t5-n2             2       2.847       2.922   -2.6%
t5-n4             4       3.285       3.457   -5.0%
t5-ring           7       3.494       3.987  -12.4%
t5-s025           7       2.417       2.586   -6.5%
t5-s4             7       3.899       4.502  -13.4%
```

**要回答的问题**：

1. 实测的“发送/S”和 $2(N-1)/N$ 对得上吗？Ring 的 worker 比参数服务器的 worker 发得**更多**，为什么 JCT 反而只有参数服务器的约 1/3.4？用公式里的 $N$ 解释。
2. “最忙发送”从 74.8 MB 变成 18.2 MB，这说明了什么？它和 JCT 的比值接近吗？
3. Ring 的预测偏低约 12%，比参数服务器差得多。用 `compare.py --steps` 的输出找证据：Reduce-Scatter（前 6 步）和 Allgather（后 6 步）的每步用时有什么不同？这个差别随块大小怎样变？（提示：Allgather 只传不算。）`predict_ring_round` 漏掉了什么？

#### 任务 6：把节点放在哪里（进阶）

**预测**：上联降到 50 Mbit/s。2 个节点放在同一机架和不同机架，通信时间差多少？4 个节点分在 2 个机架和 4 个机架，差多少？

```bash
# 22. 全部上联降到 50 Mbit/s，host 接入仍是 100 Mbit/s
sudo bash 2026/experiments/04/topo.sh rate 50

# 23. 同样的节点数，只改放置，共约 16 秒
sudo python3 2026/experiments/06/jobrun.py --algo ring --label t6-2same --workers h1a,h1b
sudo python3 2026/experiments/06/jobrun.py --algo ring --label t6-2cross --workers h1a,h2a
sudo python3 2026/experiments/06/jobrun.py --algo ring --label t6-4two --workers h1a,h1b,h2a,h2b
sudo python3 2026/experiments/06/jobrun.py --algo ring --label t6-4four --workers h1a,h2a,h3a,h4a
python3 2026/experiments/06/compare.py t6-2same t6-2cross t6-4two t6-4four
```

**实测样例**：

```output
标签              算法    N 环序    跨机架     JCT s   计算ms   通信ms  发送/S最忙发送MB
t6-2same          ring    2 given       0     2.928    200.2     92.5   1.000     10.7 h1b
t6-2cross         ring    2 given       2     3.749    200.2    174.5   1.000     10.7 h2a
t6-4two           ring    4 given       2     4.419    200.3    240.3   1.500     16.0 h2b
t6-4four          ring    4 given       4     4.741    200.3    273.7   1.500     16.1 h4a
```

**要回答的问题**：

1. 把 $\beta$ 按 50 Mbit/s 换算，手算 `t6-2same` 与 `t6-2cross` 的通信时间，和实测对账。
2. `t6-4two` 只有 2 条跨机架边，`t6-4four` 有 4 条，跨机架边减半，通信时间却只差约 12%。用 `compare.py --steps` 看每一步，解释为什么。

#### 任务 7：环序（进阶，TODO 7）

完成 `topology_ring_order()`，让同一机架的节点在环上连续。

**预测**：8 个节点、上联 50 Mbit/s。拓扑感知的环序有 4 条跨机架边，随机环序大约 6–8 条。JCT 的差别和跨机架边数成比例吗？

```bash
# 24. 测试通过后输出 OK
(cd 2026/experiments/06 && uv run --frozen python -m unittest tests.test_ring.OrderCases 2>&1 | tail -1)

# 25. 拓扑感知跑 2 次，随机环序跑 3 个种子，共约 35 秒
for i in 1 2; do
  sudo python3 2026/experiments/06/jobrun.py --algo ring --label t7-topo-"$i" --workers all --order topo
done
for s in 1 2 3; do
  sudo python3 2026/experiments/06/jobrun.py --algo ring --label t7-rand-"$s" --workers all --order random --order-seed "$s"
done
python3 2026/experiments/06/compare.py t7-topo-1 t7-topo-2 t7-rand-1 t7-rand-2 t7-rand-3

# 26. 恢复 100 Mbit/s，并核对基线
sudo bash 2026/experiments/04/topo.sh rate 100
sudo bash 2026/experiments/04/topo.sh status
```

**实测样例**（节选）：

```output
标签              算法    N 环序    跨机架     JCT s   计算ms   通信ms  发送/S最忙发送MB
t7-topo-1         ring    8 topo        4     5.018    200.2    300.8   1.750     18.7 h3a
t7-topo-2         ring    8 topo        4     5.011    200.3    299.8   1.750     18.7 h1a
t7-rand-1         ring    8 random      7     7.314    200.2    527.5   1.750     18.7 h3b
t7-rand-2         ring    8 random      7     7.656    200.3    562.8   1.750     18.8 h4b
t7-rand-3         ring    8 random      8     7.758    200.2    573.5   1.750     18.8 h3b
```

**要回答的问题**：

1. 手算拓扑感知环序的通信时间，和实测对账。提示：每一步 125 KB，瓶颈是一条 50 Mbit/s 的上联。
2. 随机环序的“发送/S”没变，为什么 JCT 多了约一半？跨机架边 7 和 8 的结果差不多，说明决定速度的不是边数，那是什么？用第 08 讲 4.2 节的上联字节计数方法，给你的解释找证据。证据不够时，说清楚还需要测什么。
3. 备课时在 100 Mbit/s 档也跑过同样的对照：拓扑感知 3.99–4.08 s，随机 5.0–5.07 s。差别为什么比 50 Mbit/s 档小？

#### 任务 8：straggler（挑战）

**预测**：让 h3a 每轮多算 600 ms（固定慢节点），参数服务器和 Ring 的 JCT 各增加多少？第 07 讲的 $1-(1-p)^N$ 能不能预测随机变慢造成的 JCT 增量？

```bash
# 27. 固定慢节点：h3a 的计算时间乘 4，PS 与 Ring 各跑基线和慢节点，共约 45 秒
RACK=h1b,h2a,h2b,h3a,h3b,h4a,h4b
sudo python3 2026/experiments/06/jobrun.py --label t8-ps --workers "$RACK"
sudo python3 2026/experiments/06/jobrun.py --label t8-ps-slow --workers "$RACK" --straggler h3a:4
sudo python3 2026/experiments/06/jobrun.py --algo ring --label t8-ring --workers "$RACK"
sudo python3 2026/experiments/06/jobrun.py --algo ring --label t8-ring-slow --workers "$RACK" --straggler h3a:4
python3 2026/experiments/06/compare.py t8-ps t8-ps-slow t8-ring t8-ring-slow

# 28. 随机变慢：每个 worker 每轮以 5% 的概率多等 300 ms；N=2、4、7，每组 40 轮，共约 90 秒
for n in 2 4 7; do
  w=$(echo "$RACK" | cut -d, -f1-"$n")
  sudo python3 2026/experiments/06/jobrun.py --algo ring --label t8-r"$n" --workers "$w" --rounds 40
  sudo python3 2026/experiments/06/jobrun.py --algo ring --label t8-r"$n"-slow --workers "$w" --rounds 40 --slow-prob 0.05 --slow-ms 300 --seed 1
done
python3 2026/experiments/06/compare.py --slow t8-r2 t8-r2-slow t8-r4 t8-r4-slow t8-r7 t8-r7-slow
```

**实测样例**（节选）：

```output
标签              算法    N 环序    跨机架     JCT s   计算ms   通信ms  发送/S最忙发送MB
t8-ps             ps      7 -           -    13.746    200.4   1173.2   1.000     74.8 h1a
t8-ps-slow        ps      7 -           -    14.714    286.1   1184.6   1.000     74.9 h1a
t8-ring           ring    7 given       4     3.908    200.4    190.1   1.714     18.2 h1b
t8-ring-slow      ring    7 given       4     9.842    286.0    697.7   1.714     18.3 h3a
t8-r2             ring  N=2  JCT   11.682 s   未注入变慢
t8-r2-slow        ring  N=2  JCT   12.683 s   变慢的轮 3/40
t8-r4             ring  N=4  JCT   13.879 s   未注入变慢
t8-r4-slow        ring  N=4  JCT   16.508 s   变慢的轮 9/40
t8-r7             ring  N=7  JCT   15.531 s   未注入变慢
t8-r7-slow        ring  N=7  JCT   19.694 s   变慢的轮 14/40
```

**要回答的问题**：

1. 固定慢节点时，Ring 的 JCT 增加了约 5.9 s，参数服务器只增加了约 1 s，而每轮多算的时间相同。结合第 08 讲 4.3 节解释。Ring 更快了，付出的代价是什么？
2. 用 $P=1-(1-p)^N$ 预测 40 轮里变慢的轮数和 JCT 增量，和实测对账。单次运行的轮数有抽样波动，你需要跑几次才敢下结论？
3. 备课时对参数服务器做了同样的随机变慢（N=7，20 轮）：JCT 从 27.39 s 变成 27.47 s，几乎不变。为什么？
4. 能不能像第 07 讲那样对冲？给出你的方案和它的代价，不需要实现。

全部做完后清理（重复执行应成功）：

```bash
# 29. 核对端口基线；留存结果；拆实验床
sudo bash 2026/experiments/04/topo.sh status
mkdir -p "$HOME/lab06-results" && cp -r /tmp/lab06-results/. "$HOME/lab06-results/"
sudo bash 2026/experiments/04/topo.sh down
```

---

## 五、故障排查

| 现象 | 先看什么 | 常见原因 |
| :--- | :--- | :--- |
| `jobrun.py` 报实验床尚未搭建 | `ls /run/lab04` | 没有执行 `04/topo.sh up`，或搭的是 Lab 3 或课堂网络 |
| 报错的最后一行是 `NotImplementedError: TODO n` | 对应的 TODO | `decompose.py`、`fit.py` 要先完成 TODO；`jobrun.py`、`timeline.py`、`curve.py` 不需要 |
| `--compute numpy` 报要先执行 `uv sync` | `ls 2026/experiments/06/.venv` | 没有执行 3.3 节的第 1 步 |
| `setsockopt` 报 `No such file or directory` | `sudo modprobe tcp_cubic`；`sysctl net.ipv4.tcp_available_congestion_control` | 算法模块没有加载或没有安装 |
| JCT 比样例长很多 | `sudo bash 2026/experiments/04/topo.sh status`；`top` | 端口偏离基线（上一个实验没有恢复）；机器上有其他负载 |
| 重复运行的 JCT 差别很大 | `sudo bash 2026/experiments/04/topo.sh status`，看档位 | 上联是 50 Mbit/s 时 ECMP 分配每次不同（第 08 讲 4.2 节）；基线 100 Mbit/s 时备课的多次运行大多在 13.7 s 附近，个别到 14.06 s。Ring 的 worker 没有按机架排列时，100 Mbit/s 档也会波动（备课 3 次 4.0–5.06 s），任务 7 解释原因 |
| `AllReduce 结果不正确` | `tests.test_ring.RingCases` | TODO 5 发错了块，或者覆盖、合并用反了 |
| Ring 卡住不动，最后超时 | 是否每一步恰好调用一次 `exchange` | 收发次数不匹配；`exchange` 是阻塞的，必须所有节点步调一致 |
| “合计”与 JCT 差很多 | 拆账的代码 | 上传段用错了时间戳；四段没有首尾相接 |
| 实验中断后状态不明 | `sudo bash 2026/experiments/04/topo.sh status` | 执行 `topo.sh clear` 恢复；再不行就 `topo.sh down` 后重新 `up` |

---

## 六、思考题

1. **公平分享**：7 条流同时上传，等待段接近 0。如果把 PS 的接入改成严格优先级，让一个 worker 先传完，总的上传时间会变吗？等待段会变吗？
2. **模型放大还是通信放大**：把模型从 1 MB 换成 4 MB，JCT 的增长和 N 的增长，哪个更接近线性？用任务 4 的数据回答。
3. **Ring 的代价**：Ring 把通信分摊到每个节点，但每一步都要等所有人。节点规模从 8 增加到 1000，$2(N-1)$ 步会成为什么问题？Tree AllReduce 怎样换取更少的步数？
4. **接到第 10 讲**：任务 7 里，环序只用到了“同机架”这一点拓扑信息。如果你能拿到完整的网络画像，调度器还能做什么？

---

## 七、提交要求

**截止时间**：2026-12-07。

| 层次 | 提交内容 | 分值 |
| :--- | :--- | :--- |
| A 段 任务 1 | 两个 worker 的手算过程，并验证四段之和 | 5 |
| A 段 任务 2 | `decompose.py`（`test_decompose` 全部通过）；基线与慢节点的拆账表；三个问题的解答 | 15 |
| A 段 任务 3 | `alphabeta.py` 的 `fit_alpha_beta`（`FitCases` 全部通过）；两条曲线的拟合结果；三个问题的解答 | 10 |
| A 段 任务 4 | `predict_ps_round`（`PredictCases` 全部通过）；6 个配置的预测与实测对账；偏差最大项的分析 | 15 |
| B 段 任务 5（基础） | `ring.py` 的 `ring_allreduce` 与 `predict_ring_round`（`RingCases`、`RingPredictCases` 全部通过）；PS 与 Ring 对照；5 个配置的预测与实测对账；三个问题的解答 | 30 |
| B 段 任务 6（进阶） | 放置对照表；手算对账；两个问题的解答 | 5 |
| B 段 任务 7（进阶） | `topology_ring_order`（`OrderCases` 全部通过）；环序对照表；上联字节证据；三个问题的解答 | 10 |
| B 段 任务 8（挑战） | 固定与随机慢节点的数据；预测与实测对账；四个问题的解答 | 10 |

报告建议 A 段 2–3 页，B 段 3–4 页。每项都要有预测、证据、解释：预测被推翻同样有价值，评分看证据是否充分、解释是否不超出数据。

提交 `jobkit/` 目录、报告和结果文件，全部任务打一个包。不提交 `.venv/` 与 `__pycache__/`。

```bash
# 30. 打包代码与第 29 步留存的结果
tar --exclude=__pycache__ -czf "$HOME/lab06-submission.tgz" -C 2026/experiments/06 jobkit -C "$HOME/lab06-results" .
tar -tzf "$HOME/lab06-submission.tgz" | head
```

### 维护与验证

本文样例的来源与验证范围：

| 项目 | 内容 |
| :--- | :--- |
| 环境 | 2026-11-08，备课虚拟机：Ubuntu 26.04.1、Linux `7.0.0-43-generic`、x86_64、2 核 2.8 GB；iproute2 6.19.0、Python 3.14；实验床使用 Lab 2 参考路由。这台机器的系统默认拥塞控制是 `bbr`，工具都显式指定算法 |
| 离线测试 | 骨架原样 24 个测试：1 个通过、4 个失败、19 个报错；补全 TODO 的参考实现 24 个全部通过 |
| 实验床 | 全部命令按本文原样运行，其中工具指向补全了 TODO 的临时副本，实测样例均来自这些运行。Ring 的命令在 2 核虚拟机上 CPU 占用约 55%–60%，瓶颈仍在网络，但合并计算会占用每步几毫秒。清理后没有残留进程和 namespace |
| 未覆盖 | Ubuntu 24.04；学生自己的实现；4 核以上的机器（CPU 争用和合并耗时都会不同） |

阅读版 `README.html` 由 `2026/tools/build_lab6_html.py` 从本文生成，用法见 [`tools/README.md`](../../tools/README.md)。仓库中的 TODO 保持留白；参考实现只用于备课验证，没有放进仓库。学生实现须独立验收，样例中的单次读数不作为验收标准。
