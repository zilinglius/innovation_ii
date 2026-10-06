# 2026 阅读版维护工具

目前只提供 **Lab 3 阅读版**的生成入口，不是全仓库通用转换器。教师使用，不属于学生实验依赖；学生 Lab 3 仍只用 Python 标准库。

从仓库根目录执行：

```bash
# 1. 按锁文件安装 Markdown 与 MathML 转换依赖
uv sync --project 2026/tools --frozen

# 2. 先改 Lab 3 Markdown，再生成阅读版；日期使用本次修改日期
uv run --project 2026/tools --frozen python 2026/tools/build_lab3_html.py --date 2026-10-06

# 3. 比较代码文本、摘要、链接、锚点、图号与外部资源
uv run --project 2026/tools --frozen python 2026/tools/check_lab3_html.py
```

- 内容源为 `2026/experiments/03/README.md`，输出为同目录的 `README.html`；CSS、字体、打印样式与目录行为来自 `2026/docs/link_state_router.html`。
- 四幅图统一由 `lab3_figures.py` 绘制；生成时也更新图 1 的 SVG 源码快照 `lab3_topology.svg`。Markdown 保留拓扑与 Mermaid，HTML 内嵌 SVG，正文公式转为 MathML。
- 配图采用相同的 760 单位宽度和既有语义色。对照场景固定节点位置；ECMP 用实线 F1／虚线 F2 跟踪连接，租户图分别标出逻辑流量与共享容量。不要仅靠颜色区分流或租户。
- `FIGURE_CSS` 只补充配图样式：屏幕最小宽度为 700 px，窄屏在图框内滚动并支持键盘聚焦，打印时恢复为可打印宽度；图注的图号和说明分列。
- `lab3_figure_sources.json` 记录源图代码块的摘要。源图改变时生成器会拒绝继续；应先同步 SVG 的节点、路径、容量和简化条件，再更新这个摘要。不得仅更新摘要掩盖图形差异。
- 图注、目录标题与正文由 Markdown 生成，输出包含源文件 SHA-256 和指定日期。不依赖 CDN 或浏览器在线公式渲染。
- 自动核验只检查内容与结构。桌面、390 px 手机、浅色／深色和打印显示仍须人工或浏览器预览；不能把静态检查称为显示验收。

`datacenter_network.html` 本次仅同步相关段落，仍沿用已有文件维护方式；此工具不重建其他讲义。
