# OSPF-Like 路由协议实验指导书

## 实验目标
- 理解链路状态型路由协议的关键阶段：邻居发现、LSA 泛洪、最短路径计算、转发表安装。
- 掌握如何在 Linux network namespace 环境下调试分布式路由器进程。
- 学会使用提供的框架代码与工具脚本，实现一个精简版的 OSPF 类协议。

## 背景知识
1. **OSPF 工作原理概览**  
   OSPF 属于链路状态协议（Link State Protocol），所有路由器维护对整个拓扑一致的视图。每个节点采集自身链路代价并向全网泛洪，所有节点据此独立运行 SPF（Shortest Path First）算法生成最优路由，最终达到“每台路由器计算出的全网拓扑一致”的目标。这种分布式模式减少了环路并加快收敛，适用于中大型自治系统。
2. **工作流程分解**  
   - *邻居发现*：接口周期性发送 Hello 数据包，匹配 Area ID、Hello/Dead 定时器等协商字段。双方互相出现在对方的邻居列表后，状态由 Down→Init→Two-Way，满足条件的邻接对继续升迁至 Full。  
   - *邻接建立*：双方互换 Database Description（DD）报文以同步 LSDB 摘要，缺失条目通过 Link State Request（LSR）/Link State Update（LSU）补齐，完成后发送 Link State Ack（LSAck）确认。  
   - *LSA 泛洪*：任何链路变化都会生成新的 LSA（内含序列号、Age、Checksum），沿邻接关系全网传播。路由器在 LSDB 中比较序列号，只接受更新鲜的 LSA，并在必要时继续泛洪。  
   - *SPF 计算与转发表安装*：LSDB 更新后触发 SPF 计时器，运行 Dijkstra 获得到各节点的最短路径与下一跳，再写入路由表或内部 FIB 结构。  
   - *DR/BDR 机制*：在广播网络上，通过指定 DR/BDR 降低邻接数量，减少泛洪开销（本实验可视需求实现或忽略）。
3. **实验中的简化**  
   - 不考虑 Area/ABR/ASBR，仅实现单域。
   - 使用自定义 LSA 结构，字段与 OSPF 类似但更精简。
   - 仅支持 IPv4 前缀，忽略多播/认证等高级特性。
4. **Linux network namespace 复习**  
   前置脚本 `experiments/01/ns.sh` 和 `experiments/01/ns_bridge.sh` 可快速创建用于测试的五节点拓扑或桥接拓扑。通过 `sudo bash <script>` 启动，`sudo bash <script> down` 清理。必要时使用：
   ```bash
   ip netns list
   ip -n <ns> addr
   ```

## 实验环境
- 操作系统：推荐使用支持 network namespace 的 Linux。
- Python 3.10+（框架默认语言）。
- 需要 `sudo` 权限运行 namespace 脚本。

## 目录结构
```
experiments/03/
├── ns.sh
├── ns_bridge.sh
├── ns_setup_guide.md
├── ospf_lab_guide.md         ← 本指导书
└── ospf_lab/                 ← 框架代码与工具
    ├── README.md             ← 起步说明
    ├── main.py               ← 协议入口
    ├── topo.sample.yaml      ← 示例拓扑描述
    ├── ospf/
    │   ├── __init__.py
    │   ├── adjacency.py
    │   ├── cli.py
    │   ├── events.py
    │   ├── lsdb.py
    │   ├── message.py
    │   ├── router.py
    │   └── timers.py
    └── tools/
        └── capture.sh        ← 辅助抓包脚本
```

## 实验任务拆解
1. **阅读框架代码**  
   先通读 `README.md` 与 `main.py`，了解 CLI 参数及组件分工，再阅读 `ospf/` 目录下各模块的注释与 TODO。
2. **实现邻居发现**  
   - 在 `adjacency.py` 的 `process_hello` 与 `build_hello` 中填充逻辑。  
   - 维护邻居状态机（Down → Init → 2-Way → Full）。
3. **完成 LSA 流程**  
   - 在 `message.py` 定义 LSA 序列号、校验与泛洪逻辑。  
   - 在 `lsdb.py` 中实现 LSDB 插入、老化与一致性校验。
4. **最短路径计算**  
   - 在 `router.py` 里实现 `run_spf`，对 LSDB 运行 Dijkstra，生成转发表。  
   - 更新本地路由（可以写入 namespace 的 `ip route`，或在框架内维护虚拟转发表）。
5. **事件与定时器**  
   - `events.py` 提供事件循环骨架；补齐发动 Hello、LSA 重传、超时检测的调度逻辑。  
   - `timers.py` 提供默认时间常量，可根据实际调试调整。
6. **命令行与调试**  
   - `cli.py` 暴露实时查看邻居、LSDB、路由表的命令，需补齐输出。  
   - 使用 `tools/capture.sh` 配合 `tcpdump` 抓包观察协议消息。

## 实验步骤建议
1. **准备拓扑**  
   选择 `ns.sh` 或 `ns_bridge.sh` 创建 namespace 环境，并记录每个 namespace 绑定的接口与 IP。
2. **运行路由器实例**  
   在每个 namespace 内执行：
   ```bash
   sudo ip netns exec <ns> python experiments/01/ospf_lab/main.py \
     --router <router-id> \
     --config experiments/01/ospf_lab/topo.sample.yaml \
     --log-level debug
   ```
   也可在单机多进程模式下测试（README 中说明）。
3. **验证邻居关系**  
   使用 CLI 命令（例如 `show neighbors`）或观察日志，确认邻居成功从 Down 到 Full。
4. **验证 LSDB 与路由表**  
   - 运行 `show lsdb` 比对每个节点的 LSA 集。  
   - 使用 `show routes` 或 `ip -n <ns> route` 查看转发表是否一致。
5. **连通性测试**  
   使用 `ping` 或 `traceroute` 验证任意两端主机连通性。必要时配合 `capture.sh` 抓包定位问题。
6. **撰写实验报告**  
   至少包含：邻居建立日志截屏、LSDB 输出、路由表验证、最短路径推导、测试命令列表、问题及解决过程。

## 实验提示
- 尽量先在单进程模式调通逻辑，再搬到 namespace 环境。
- 关注定时器取值，Hello/Dead 间隔失衡会导致邻居频繁抖动。
- 使用 `shellcheck` 检查新增的 shell 脚本；Python 部分可选用 `python -m compileall` 快速语法检查。
- 遇到协议死锁时，可开启 `--log-level trace`（需自行实现细粒度日志输出）。

## 拓展思考
- 为 LSA 加入广播域成本，尝试生成多条等价路径。
- 加入简单认证字段验证邻居合法性。
- 将路由表同步到 Linux 内核，结合 `ip netns exec <ns> ip route` 直接验证转发。

祝调试顺利，玩得开心！
