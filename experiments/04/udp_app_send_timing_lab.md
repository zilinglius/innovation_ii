# UDP 应用层发包时间实验指导（SO\_TXTIME + ETF）

> 背景阅读：`docs/udp_app_send_timing.md`（重点关注 §1–§7）。本指导书给出可以直接复制编译的示例代码，并串联 `ns_bridge.sh` 拓扑、`tcpdump`/`ptp4l`/`SO_TIMESTAMPING` 等工具，帮助学生按 tcpdump 时间戳复现 UDP 发包节奏并量化误差。

---

## 0. 实验目标
- 在 Linux 网络命名空间拓扑中复现真实 capture（pcap）中的 UDP 报文节奏。
- 对比“用户态绝对定时（方案 A）”与“SO\_TXTIME + ETF（方案 B）”的抖动。
- 使用 `SO_TIMESTAMPING`、`tcpdump`、Python 统计脚本收集 Δt 误差分布，验证 `docs/udp_app_send_timing.md` 中的链路开销拆解与优化建议。

---

## 1. 拓扑与资源

| 组件 | 作用 |
| --- | --- |
| `exeriments/04/ns_2_nodes.sh` | 构建多命名空间桥接拓扑（ns1a→ns3a 为本实验的 Sender→Receiver）。 |
| `experiments/04/udp_txtime_replay.c` | 读取 PCAP，设置 `SCM_TXTIME`，由 ETF qdisc 精确定时发送。 |
| `experiments/04/udp_rx_timestamp.c` | 软件时间戳接收端，输出 CSV（seq, wire_len, payload_len, kernel_realtime_ns, mono_raw_ns）。 |
| 辅助工具 | `gcc`, `libpcap-dev`, `linuxptp` (`ptp4l`, `phc2sys`), `tcpdump`, `python3`。 |

拓扑选择 `ns_2_nodes.sh`或`ns_3_nodes.sh`，以 `ns1a` 为 Sender、`ns2a`或`ns3a` 为 Receiver，其间经过 `ns1` ↔ `ns2` ↔ `ns3` 的三层链路，可观察队列/转发对抖动的影响。

---

## 2. 环境准备

1. **依赖安装（Ubuntu/Debian 示例）**
   ```bash
   sudo apt update
   sudo apt install -y build-essential libpcap-dev linuxptp tcpdump python3-pip
   ```
2. **参考环境检查**：按 `exeriments/01/ns_setup_guide.md` 确认 `veth`、`bridge` 模块和 sudo 权限。
3. **拉起拓扑**
   ```bash
   cd /path/to/repo
   sudo bash exeriments/04/ns_2_nodes.sh
   ip netns list
   ```
4. **命名空间基线快照**（供实验记录）
   ```bash
   ip netns list
   ip -n ns1 addr
   ip -n ns2 addr
   ```

---

## 3. 编译教学用示例程序

> 所有源码位于 `experiments/04/`，保持与 lab 说明同路径，方便抄写与版本控制。

```bash
# 1) SO_TXTIME 发送端（依赖 libpcap）
gcc -O2 -Wall -Wextra -o experiments/04/udp_txtime_replay \
  experiments/04/udp_txtime_replay.c -lpcap

# 2) SO_TIMESTAMPING 接收端
gcc -O2 -Wall -Wextra -o experiments/04/udp_rx_timestamp \
  experiments/04/udp_rx_timestamp.c
```

编译完成后，可用 `file experiments/04/udp_txtime_replay` 检查二进制是否生成。

---

## 4. 步骤总览

1. 生成或获取一个包含 UDP 报文的 `pcap`（可用 `tcpdump -i <if> -w trace.pcap udp` 实地录制）。  
2. 在 `ns2` 启动 `udp_rx_timestamp` 并记录 CSV。  
3. 在 `ns1` 配置 `ETF qdisc + SO_TXTIME`；运行 `udp_txtime_replay`，按 capture 节奏发送。  
4. 并行使用 `tcpdump` 抓 Sender、转发器、Receiver 的时间戳。  
5. 用 Python 对照 `pcap` 原始 Δt，与接收 CSV 计算误差直方图。  
6. 调整 `ethtool -C`, `taskset`, `SCHED_FIFO` 等参数，验证 `docs/udp_app_send_timing.md` §1/§6 的优化点。  
7. 记录发现，最后 `sudo bash exeriments/04/ns_2_nodes.sh down` 清理实验环境。

以下章节给出详细指令。

---

## 5. Sender/Receiver 命名空间配置

### 5.1 命名空间别名
```bash
SENDER_NS=ns1
RECEIVER_NS=ns3
SENDER_IF=veth12a   # 可通过 ip -n ns1 link show 查看实际名称
RECEIVER_IF=veth12b
SENDER_IP="10.0.12.1"
RECERVER_IP="10.0.12.2"
```

### 5.2 开启 PTP/时钟同步（可选但推荐）
若宿主机网卡具备 PHC，可在 host 或 namespace 中运行：
```bash
# 以 host 环境为例，使用 CLOCK_TAI 作为统一时间源，eno1为网卡名字
sudo ptp4l -2 -i eno1 -m &
sudo phc2sys -a -r -n 0 &
```
在没有 PHC 的 veth 拓扑中，可跳过此步，默认 `CLOCK_TAI` 仍然存在，只是与真实 UTC 偏移固定。

### 5.3 绑定 CPU / 设定调度策略
```bash
ip netns exec $SENDER_NS chrt -f 80 taskset -c 2 \
  ./experiments/04/udp_txtime_replay --help  # 确认指令可运行
```
（`docs/udp_app_send_timing.md` §1.2 建议：绑核、SCHED\_FIFO、mlockall。可用 `sudo sysctl kernel.sched_rt_runtime_us=-1` 放宽 RT 额度。）

---

## 6. ETF qdisc 与 SO_TXTIME 配置

1. **查看命名空间中的链路**
   ```bash
   ip -n $SENDER_NS link show $SENDER_IF
   ```
2. **配置 ETF**（clock 需与程序的 `--clock` 参数一致；示例使用 `CLOCK_TAI`）
   ```bash
   ip netns exec $SENDER_NS tc qdisc replace dev $SENDER_IF \
     root etf clockid CLOCK_TAI delta 50000 offload
   ```
   - `delta 50000`：允许内核提前 50 μs 排队，可按 `docs/udp_app_send_timing.md` §4 建议微调。
3. **可选：启用 XPS、固定频率**
   ```bash
   ip netns exec ns1 ethtool -C lgw0 tx-usecs 4 rx-usecs 4
   sudo cpupower frequency-set -g performance
   ```

---

## 7. 准备参考 PCAP

1. **生成教学用 trace（以 `ns1` 为例）**
   ```bash
   ip netns exec $SENDER_NS tcpdump -i $SENDER_IF -nn -tt udp \
     -w /tmp/udp_base_trace.pcap &
   ```
2. **在同一命名空间发若干 UDP 报文**（使用 `netcat` 或已有应用）。
3. **停止 tcpdump**，并复制 `pcap` 到 `experiments/04/traces/`，供后续复现：
   ```bash
   mkdir -p experiments/04/traces
   cp /tmp/udp_base_trace.pcap experiments/04/traces/demo_trace.pcap
   ```

---

## 8. 启动接收端采样器

```bash
ip netns exec $RECEIVER_NS ./experiments/04/udp_rx_timestamp \
  --bind-ip $RECEIVER_IP --port 5500 --count 0 \
  > /tmp/rx_ns2.csv
```
- `--count 0` 表示持续记录直到手动停止。
- 输出字段解释：`seq`（报文序号）、`wire_len`（估算含头部大小）、`payload_len`、`kernel_realtime_ns`（`SO_TIMESTAMPING` 提供的 `CLOCK_REALTIME`）、`mono_raw_ns`（本地 `CLOCK_MONOTONIC_RAW`）。

可并行运行第二个 `tcpdump` 以获取接收端参考：
```bash
ip netns exec $RECEIVER_NS tcpdump -i $RECEIVER_IF -tt -nn udp port 5500 \
  -w /tmp/rx_side.pcapng
```

---

## 9. 运行 SO_TXTIME 发送程序

```bash
ip netns exec $SENDER_NS chrt -f 80 taskset -c 3 \
  ./experiments/04/udp_txtime_replay \
    --pcap experiments/04/traces/demo_trace.pcap \
    --bind-ip $SENDER_IP --bind-port 5500 \
    --dst-ip $RECEIVER_IP --dst-port 5500 \
    --lead-us 200 --clock CLOCK_TAI
```

- 程序会输出 `[*] Replaying N packets ...`。
- `--lead-us` 决定“提前写入 qdisc 的 guard 时间”，需要与 ETF `delta` 配合，典型 100–300 μs。
- 若需要方案 A（纯用户态定时），可将 `tc qdisc` 替换为 `fq`，并将 `--clock CLOCK_MONOTONIC`，在代码中使用 `clock_nanosleep`（详见 `docs/udp_app_send_timing.md` §4 方案 A）。

**故障排查**
- `sendmsg: Invalid argument` → ETF 未配置/clock 不一致。
- `EAGAIN` → 报文提交晚于 `txtime`；增大 `--lead-us` 或减小系统负载。
- `pcap` 中含非 UDP 报文 → 程序会跳过，注意输入 trace。

---

## 10. 数据采集与分析

1. **停止接收端程序与 tcpdump**
   ```bash
   pkill -f udp_rx_timestamp
   pkill -f tcpdump
   ```
2. **提取发送侧 txtime 序列**  
   发送程序的基准是 `pcap` 本身，可用 Python 读取：
   ```bash
   python3 -m pip install --user dpkt numpy matplotlib
   ```
   ```python
   # experiments/04/tools/pcap_deltas.py（可粘贴到临时脚本）
   import dpkt, sys
   import statistics as st

   ts=[]
   with open(sys.argv[1],'rb') as f:
       for t,_ in dpkt.pcap.Reader(f):
           ts.append(t)
   pcap_gaps=[ts[i+1]-ts[i] for i in range(len(ts)-1)]
   print("pcap median us", st.median(pcap_gaps)*1e6,
         "p99 us", sorted(pcap_gaps)[int(0.99*len(pcap_gaps))]*1e6)
   ```
3. **分析接收 CSV**：计算 `Δt_recv` 与 `Δt_pcap` 差异。
   ```python
   import csv, statistics as st
   import numpy as np

   rx=[]
   with open("/tmp/rx_ns2.csv") as f:
       reader=csv.DictReader(f)
       for row in reader:
           rx.append(int(row["kernel_realtime_ns"]))
   recv_gaps=[(rx[i+1]-rx[i]) for i in range(len(rx)-1)]
   # 以 microseconds 为单位
   gaps_us=[g/1e3 for g in recv_gaps]
   print("recv median us", st.median(gaps_us))
   print("recv p99 us", np.percentile(gaps_us, 99))
   ```
4. **误差直方图（Δt\_recv - Δt\_pcap）**
   ```python
   import numpy as np
   import matplotlib.pyplot as plt
   errors=[recv_gaps[i]-pcap_gaps[i] for i in range(len(pcap_gaps))]
   plt.hist(errors, bins=50)
   plt.xlabel("Δt error (ns)")
   plt.ylabel("count")
   plt.title("SO_TXTIME replay jitter")
   plt.show()
   ```
5. **记录系统状态**  
   - `ip -n ns1a exec ethtool -c $SENDER_IF` → 中断合并参数。  
   - `taskset -pc <PID>`、`chrt -p <PID>` → 佐证绑核/调度策略。  
   - `ip netns exec ns1a sysctl net.core.wmem_max` → 缓冲调优。

---

## 11. 进阶实验（可选）

1. **压力扰动**：在 `ns1` 或宿主机上运行 `stress-ng --cpu 2 --timeout 60s`，观察 `p99` 抖动变化。  
2. **中断合并扫描**：在 `ns1` 中反复调整 `ethtool -C $SENDER_IF tx-usecs 4/16/64`，记录接收 CSV 中的尾部延迟。  
3. **方案 C 预研**：若实验环境有 DPDK，可对照 `docs/udp_app_send_timing.md` §4 方案 C，尝试将 `ns1` 绑定 HugeTLB + DPDK，比较 jitter。  
4. **GRO 调整**：在 `ns2` 执行 `ethtool -K $RECEIVER_IF gro off`，观察 `udp_rx_timestamp` 报文间隔。

---

## 12. 清理

实验结束后释放命名空间与临时文件：
```bash
sudo bash exeriments/04/ns_2_nodes.sh down
rm -f /tmp/udp_base_trace.pcap /tmp/rx_ns2.csv /tmp/rx_side.pcapng
```

---

## 13. 实验记录要求

1. 一段摘要：说明 `SO_TXTIME + ETF` 是否达到微秒级精度，引用 `docs/udp_app_send_timing.md` §9 takeaway。  
2. 命令清单：`sudo bash exeriments/04/ns_2_nodes.sh`, `ip netns exec ... udp_txtime_replay`, `tcpdump`, `python` 分析脚本。  
3. 数据附件：`/tmp/rx_ns2.csv`、`/tmp/rx_side.pcapng`、关键 `ip`/`ethtool` 输出。  
4. 故障或调优记录：例如“增大 `--lead-us` 从 200 → 400 可消除 EAGAIN”。

