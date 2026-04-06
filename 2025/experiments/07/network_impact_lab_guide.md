# 分布式框架网络影响模拟实验指导书

> 背景阅读：`docs/network_impact_distributed_frameworks.md`（关注延迟/带宽模型、拓扑耦合、PS 与 AllReduce 公式）。本实验不要求部署 Spark/Flink/PS 集群，而是用命名空间 + `tc netem` + Python 模拟脚本在单机上重现网络瓶颈对作业的放大效应。

---

## 1. 实验目标
- 在 Driver + Parameter Server + 多 Worker 的星型桥接拓扑上，通过 `tc netem` 控制延迟/带宽/抖动，获得可量化的网络参数（RTT、吞吐）。
- 将实测 RTT、吞吐带入 `experiments/07/framework_network_sim.py`，对比 Shuffle、Parameter Server、Ring AllReduce 三类通信模式的迭代时间，感受网络参数如何放大到作业完成时间。
- 验证教材中的 $T_\text{comm} \approx L + D/B$ 与长尾放大现象，形成“网络参数 → 作业时间”的可重复闭环，帮助学生理解“测得的链路特性就是模型的输入”。

## 2. 预备知识与工具
- 熟悉 Bash、`ip netns`、`tc netem`、`iperf3`、`ping`。
- 需安装：`python3`, `iperf3`, `tcpdump`（可选）。

## 3. 目录与资源
```
docs/network_impact_distributed_frameworks.md    # 背景阅读
experiments/07/ns_framework_topo.sh              # Driver + PS + 3 Worker 拓扑
experiments/07/framework_network_sim.py          # 作业时间模拟器（ps/allreduce/shuffle）
experiments/07/network_impact_lab_guide.md       # 本指导书
```

## 4. 环境准备
1. **拉起拓扑**（创建 Driver/PS/Worker 命名空间与桥）
   ```bash
   sudo bash experiments/07/ns_framework_topo.sh
   ip netns list
   ```
   看到 `drv/ps/w1/w2/w3` 即为成功。
2. **准备日志目录**（集中保存 ping/iperf 输出，便于后续对比）
   ```bash
   mkdir -p logs
   ```
3. **接口速览**（示例，确保地址分配符合预期）  
   `ps: vps_ns (10.10.0.20/24)` ← Root 侧 `vps` 接入桥 `brfw`  
   `drv: vdrv_ns (10.10.0.10/24)`；`w1/w2/w3` 依次为 `vw1_ns/vw2_ns/vw3_ns` (10.10.0.11/12/13)。
4. **连通性检查**（验证命名空间与 IP 是否可达）
   ```bash
   ip netns exec drv ping -c 4 10.10.0.20   # Driver -> PS
   ip netns exec w1 ping -c 4 10.10.0.13    # Worker1 -> Worker3
   ```
5. **记录基础状态**（基线配置快照，为后续“前后对比”）
   ```bash
   ip netns exec ps sysctl net.ipv4.ip_forward
   ip netns exec ps tc qdisc show
   tc qdisc show dev vps   # root 侧 PS 接口，后续在此注入（ns_framework_topo.sh 已创建）
   ```

## 5. 基线测量（无干预）
1. **带宽**（以 PS 为中心测链路能力）
   ```bash
   ip netns exec ps iperf3 -s -D
   ip netns exec w1 iperf3 -c 10.10.0.20 -t 15 -i 3   # Worker -> PS
   ```
   记下平均带宽（Gbps），后续填入模拟器 `--bandwidth-gbps`。
2. **延迟**（Driver 到 Worker 的 RTT）
   ```bash
   ip netns exec drv ping -c 50 -i 0.2 10.10.0.12 > logs/ping_baseline.txt
   ```
   计算 p50/p90/p99 RTT（p50 可作为 `--latency-ms` 输入）。
3. **清理基线服务**
   ```bash
   ip netns exec ps pkill iperf3 || true
   ```

## 6. 场景一：拓扑敏感的 Shuffle/Barrier
1. **在“热点节点（PS/汇聚层）”链路注入瓶颈**（对 root 侧 `vps` 施加 netem，模拟 ToR 上行受限；等同于 PS 变成拥塞点）
   ```bash
   tc qdisc add dev vps root netem delay 3ms 1ms 15% rate 500mbit
   tc qdisc show dev vps
   ```
2. **重新测量**（同一方法获取新 RTT/带宽，用于对比）
   ```bash
   ip netns exec ps iperf3 -s -D
   ip netns exec w1 iperf3 -c 10.10.0.20 -t 15 -i 3
   ip netns exec drv ping -c 50 -i 0.2 10.10.0.13 > logs/ping_shuffle.txt
   ```
   将 RTT（ms）与带宽（Gbps）记下。
3. **代入模拟器（Shuffle 模式）**（把“无瓶颈”和“有限瓶颈”两组测量值分别跑一遍，观察 Stage 时间的变化）
   > 将 `ping` p50 值填入 `--latency-ms`，`iperf3` 平均带宽（Gbps）填入 `--bandwidth-gbps`；若想贴合尾部，可把 `--tail-extra-ms` 设为约 `p99 - p50`。先用“无 netem”基线跑一遍，再用“有 netem”结果跑一遍作对比。
   ```bash
   python3 experiments/07/framework_network_sim.py shuffle \
     --workers 12 \
     --latency-ms <ping_p50_ms> \
     --bandwidth-gbps <iperf_avg_gbps> \
     --shuffle-mb-per-task 20 \
     --stages 4 \
     --tail-extra-ms 4
   ```
   观察 p90/p99 Stage 时间，比较“无干预”和“有瓶颈”的差异。

## 7. 场景二：Parameter Server 推拉
1. **移除或修改 netem**（可保留上一场景，或 `tc qdisc del dev vps root` 再重建，明确你要对比的链路状态）。
2. **运行模拟**
   > 用当前测得的 `ping` p50/`iperf3` 带宽替换占位符；如需模拟长尾，把 `--tail-extra-ms` 设成 `(p99 - p50)` 的量级。先记录无瓶颈，再记录限速/抖动后的结果。
   ```bash
   python3 experiments/07/framework_network_sim.py ps \
     --workers 8 \
     --latency-ms <ping_p50_ms> \
     --bandwidth-gbps <iperf_avg_gbps> \
     --grad-mb 120 --param-mb 120 \
     --rounds 20 \
     --tail-extra-ms 2
   ```
   - 将 `--workers` 增大为 16，记录迭代时间的变化，验证公式 $T_\text{iter} \approx \max T_\text{comp} + T_\text{push} + T_\text{pull}$。
   - 可将 `rate 500mbit` 改为 `rate 200mbit`，比较迭代时间的增长。

## 8. 场景三：Ring AllReduce 长尾
1. **保留 netem 抖动**，或追加轻微丢包（模拟 AllReduce 对启动延迟与丢包的敏感性）：
   ```bash
   tc qdisc change dev vps root netem delay 3ms 1ms 15% loss 0.2%
   ```
2. **模拟 AllReduce**
   > 继续使用最新的 RTT/带宽测量值填充命令；需要模拟尾部时，同样可以用 `--tail-extra-ms ≈ (p99 - p50)`。比较“无 netem vs 有 netem”的 p99 差异。
   ```bash
   python3 experiments/07/framework_network_sim.py allreduce \
     --workers 16 \
     --latency-ms <ping_p50_ms> \
     --bandwidth-gbps <iperf_avg_gbps> \
     --grad-mb 200 \
     --rounds 30 \
     --tail-extra-ms 5
   ```
   重点观察 `workers` 扩大后延迟项 `2(p-1)L` 带来的线性放大。

## 9. 观测与记录清单
- `tc qdisc show dev vps`：注入的延迟/带宽/丢包参数。
- `logs/ping_baseline.txt` / `logs/ping_shuffle.txt`：p50/p90/p99 RTT。
- `iperf3` 平均带宽与重传。
- `framework_network_sim.py` 输出的 p50/p90/p99 作业时间；至少记录“无干预 vs 有瓶颈”两组。
- 可选：`tcpdump -i vps -nn -c 50`，验证队列排队导致的延迟抖动。

## 10. 报告要求
1. 描述拓扑角色（哪条链路视作跨机架）与 `tc netem` 参数。
2. 提供两组模拟结果（无瓶颈、有限带宽/高延迟），标注输入的 RTT/带宽。
3. 结合公式 $T_\text{comm} \approx L + D/B$ 与 Ring AllReduce 延迟项，解释 p99 扩大的原因。
4. 附关键命令与输出摘要（`tc`、`ping`、`iperf3`、模拟器统计）。

## 11. 清理
```bash
tc qdisc del dev vps root || true
sudo bash experiments/07/ns_framework_topo.sh down
```
