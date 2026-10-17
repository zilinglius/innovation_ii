# 2026 阅读版维护工具

目前提供 **Lab 3 阅读版**和**第二、三讲回顾阅读版**的生成入口，不是全仓库通用转换器。教师使用，不属于学生实验依赖；学生 Lab 3 仍只用 Python 标准库。

## Lab 3 阅读版

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

## 第二讲回顾与参考答案阅读版

先修改 `2026/docs/switching_routing_review.md`，再从仓库根目录执行：

```bash
# 1. 按本目录锁文件准备依赖（与 Lab 3 生成器共用）
uv sync --project 2026/tools --frozen

# 2. 生成第二讲回顾；日期填写本次内容更新日期
uv run --project 2026/tools --frozen python 2026/tools/build_switching_routing_review_html.py --date 2026-10-11

# 3. 修改对应的参考答案 Markdown 后，生成答案阅读版
uv run --project 2026/tools --frozen python 2026/tools/build_switching_routing_review_html.py --answers --date 2026-10-11
```

- 默认输出 `switching_routing_review.html`；加 `--answers` 时从 `switching_routing_review_answers.md` 生成同名 HTML。各自以 Markdown 为唯一正文源，保留源文链接、SHA-256 与更新日期。
- 复用 `link_state_router.html` 的 CSS、内嵌字体、A4 打印样式及目录行为；公式预转 MathML，目录由标题生成。
- 生成前核对两份材料的 34 个题号逐一对应、命令／输出逐字一致、唯一 ID、目录与题目锚点、本地链接与页面外部资源引用。
- 答案中的两幅图由 `switching_routing_review_figures.py` 转为 SVG，图注来自 Markdown；其中的源图摘要防止 Mermaid 改动后仍使用旧图。修改源图时须先核对节点、路径、接口及简化条件，再更新 SVG 与摘要。
- 自动检查不覆盖浏览器显示；生成后仍须核验桌面、约 390 px 手机、浅色／深色和打印显示。本入口不重建第一讲回顾或原第二讲讲义。

## 第三讲回顾与参考答案阅读版

先修改 `2026/docs/routing_protocol_review.md` 与 `routing_protocol_review_answers.md`，再从仓库根目录执行：

```bash
# 1. 按本目录锁文件准备依赖
uv sync --project 2026/tools --frozen

# 2. 生成第三讲回顾，日期填写本次内容更新日期
uv run --project 2026/tools --frozen python 2026/tools/build_routing_protocol_review_html.py --date 2026-10-11

# 3. 生成逐题参考答案
uv run --project 2026/tools --frozen python 2026/tools/build_routing_protocol_review_html.py --answers --date 2026-10-11
```

- 输出同目录、同名 HTML；正文以 Markdown 为唯一源，沿用 `link_state_router.html` 的公共样式、字体、目录及打印行为。生成信息保留 SHA-256 与日期，公式预转 MathML。
- 题单 9 幅、答案 11 幅图由 `routing_protocol_review_figures.py` 绘制为内嵌 SVG；图注来自 Markdown，源图摘要保存在 `routing_protocol_review_figure_sources.json`。修改 Mermaid 后，应先同步并核对 SVG 的节点、方向、字段、数值和简化条件，再更新对应摘要；不要只刷新摘要掩盖旧图。
- 生成器核对两份材料 36 个题号、连续图号、命令／输出文本、唯一标识、本地链接、源文摘要与外部资源依赖；它是第三讲专用入口，不重建原讲义或其他讲次。
- 图示以约 760 单位宽度绘制，手机局部滚动，打印按可用宽度缩放。生成后仍需实际查看桌面、390 px 手机、浅色／深色与打印显示，自动检查不能替代显示验收。
- 本次材料引用第三讲已有 FRR 8.4.4 输出并增加纸面推演，没有新增 Linux 实测；协议状态、RIB/FIB 与业务证据分别解释，不能把排版检查视为实验验证。
