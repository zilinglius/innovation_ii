# 精简版 OSPF 实验框架

## 背景
本框架用于在 `experiments/03` 目录下完成类似 OSPF 的链路状态路由协议实验。结构上参考 OSPF v2，保留核心阶段：邻居发现、LSA 泛洪、SPF 计算、路由安装。学生需在预置骨架中补齐关键逻辑。

## 快速开始
1. **准备拓扑**  
   使用提供的 namespace 脚本之一：
   ```bash
   sudo bash experiments/01/ns.sh
   # 或
   sudo bash experiments/01/ns_bridge.sh
   ```
   记录每个 namespace 的接口与 IP。

2. **安装依赖**  
   Python 标准库即可运行框架，如需额外工具（如 `rich` 日志），可自行添加。

3. **启动路由器进程**  
   在某个 namespace 内：
   ```bash
   sudo ip netns exec r1 python experiments/01/ospf_lab/main.py \
     --router 1.1.1.1 \
     --config experiments/01/ospf_lab/topo.sample.yaml \
     --log-level debug
   ```
   多开若干终端分别进入其余 namespace。`router` 参数建议使用 OSPF 的 dotted-decimal Router ID。

4. **观察运行状态**  
   在进程标准输入输入命令（见 `ospf/cli.py`），例如：
   ```
   > show neighbors
   > show lsdb
   > show routes
   ```

5. **清理环境**  
   完成实验后运行：
   ```bash
   sudo bash experiments/01/ns.sh down
   ```

## 代码结构
- `main.py`：解析参数，加载拓扑，初始化事件循环与路由器。
- `ospf/adjacency.py`：邻居状态机与 Hello 处理。
- `ospf/message.py`：协议数据单元编码/解码。
- `ospf/lsdb.py`：Link State Database 管理。
- `ospf/router.py`：路由器主体，协调邻居、LSDB、转发表。
- `ospf/events.py`：事件循环与定时器调度。
- `ospf/cli.py`：交互式命令行接口。
- `ospf/timers.py`：默认定时器配置。
- `topo.sample.yaml`：示例拓扑配置，描述接口、成本与初始对等体。
- `tools/capture.sh`：协助在 namespace 内抓取协议报文。

## 建议实现顺序
1. 在单进程模式下（不进入 namespace，只用 loopback）跑通逻辑。
2. 完成 Hello 与邻居状态转换，确保 `show neighbors` 输出正确。
3. 实现 LSA 生成与泛洪，能在所有节点看到相同的 LSDB。
4. 在 `run_spf` 中实现 Dijkstra，生成最短路径树并写入路由表。
5. 增强 CLI、日志与错误处理，便于调试。

## 实验要求提示
- 所有新增 shell 脚本需包含 `set -Eeuo pipefail`。
- Python 代码应保留注释中的 TODO 提示，由学生补齐。
- 保持日志与 CLI 输出清晰，方便撰写实验报告。

祝学习顺利！
