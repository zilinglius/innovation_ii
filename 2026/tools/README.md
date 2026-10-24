# 2026 阅读版维护工具

目前提供 **Lab 3、Lab 4 阅读版**、**第二、三、四、五讲回顾阅读版**和**第 06 讲讲义阅读版**的生成入口，不是全仓库通用转换器。第 06 讲与 Lab 4 的生成器共用 `reading_common.py`（命令行内高亮、生成页结构检查、链接与锚点核对、残留标记检查）。教师使用，不属于学生实验依赖；学生 Lab 3 仍只用 Python 标准库。

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

## 第四讲回顾与参考答案阅读版

先修改 `2026/docs/link_state_router_review.md` 与 `link_state_router_review_answers.md`，再从仓库根目录执行：

```bash
# 1. 按本目录锁文件准备依赖
uv sync --project 2026/tools --frozen

# 2. 生成第四讲回顾，日期填写本次内容更新日期
uv run --project 2026/tools --frozen python 2026/tools/build_link_state_router_review_html.py --date 2026-10-18

# 3. 生成逐题参考答案
uv run --project 2026/tools --frozen python 2026/tools/build_link_state_router_review_html.py --answers --date 2026-10-18
```

- 结构与第三讲回顾生成器相同：输出同目录、同名 HTML，公共样式、字体、目录与打印行为取自 `link_state_router.html`，打印页眉改为“第 04 讲回顾”。代码块支持 `bash`、`text` 与 `python` 三类，只做转义、不加高亮，复制文本与源文一致。
- 题单与答案各 6 幅图，由 `link_state_router_review_figures.py` 绘制为内嵌 SVG；Mermaid 源图以 `%% lsr-review:<key>` 标识，摘要保存在 `link_state_router_review_figure_sources.json`。图注取自源图下方的 `*图 N：…*`，阅读版中图号与说明分列。答案中的计时图（图 1、4、5）在阅读版里按时间比例绘制，图 4 的放大段在图内注明不按比例。修改 Mermaid 后先核对 SVG 的节点、方向、数值与简化条件，再更新摘要。
- 生成器核对：32 个题号逐一对应、连续图号、代码／输出逐字一致、唯一 ID、本地链接与跨页锚点、源文摘要、外部资源依赖，以及其他讲次模板与未转换 Mermaid 的残留。显示仍须在浏览器中检查桌面、约 390 px 手机、浅色／深色与导出 PDF 的分页；打印时题单的“使用说明”与第一、二、三、五、十节，答案的第一、三、七、八、十一节与“讲评时的核对入口”允许接续上一页，其余模块另起一页。
- 第八节题 29、30 引用 2026-10-18 在备课虚拟机上用 `02/reference/lsrd` 补测的重启场景，复现命令写在答案题 30；其余数字沿用第四讲模块六的原记录。排版检查不代表实验验证。

## 第五讲回顾与参考答案阅读版

先修改 `2026/docs/datacenter_network_review.md` 与 `datacenter_network_review_answers.md`，再从仓库根目录执行：

```bash
# 1. 按本目录锁文件准备依赖
uv sync --project 2026/tools --frozen

# 2. 生成第五讲回顾，日期填写本次内容更新日期
uv run --project 2026/tools --frozen python 2026/tools/build_datacenter_network_review_html.py --date 2026-10-24

# 3. 生成逐题参考答案
uv run --project 2026/tools --frozen python 2026/tools/build_datacenter_network_review_html.py --answers --date 2026-10-24
```

- 结构与第四讲回顾生成器相同：输出同目录、同名 HTML，公共样式、字体、目录与打印行为取自 `link_state_router.html`，打印页眉改为“第 05 讲回顾”。代码块支持 `bash` 与 `text` 两类，只做转义、不加高亮，复制文本与源文一致。链到仓库内 Markdown 时，若同目录有同名阅读版则改链到 `.html`。
- 题单 5 幅、答案 6 幅图，由 `datacenter_network_review_figures.py` 绘制为内嵌 SVG；Mermaid 源图以 `%% dc-review:<key>` 标识，摘要保存在 `datacenter_network_review_figure_sources.json`。图注取自源图下方的 `*图 N：…*`。答案中的柱状图（图 1、2、5）与时间线（图 4）按数值比例绘制，图 4 的放大段在图内注明比例。修改 Mermaid 后先核对 SVG 的节点、方向、数值与简化条件，再更新摘要。
- 生成器核对：32 个题号逐一对应、连续图号、代码／输出逐字一致、唯一 ID、本地链接与跨页锚点、源文摘要、外部资源依赖、本机绝对路径，以及其他讲次模板与未转换 Mermaid 的残留。显示仍须在浏览器中检查桌面、约 390 px 手机、浅色／深色与导出 PDF 的分页；打印时题单的“使用说明”与第一、六、十节，答案除第三、七节外的各节允许接续上一页。
- 题 10、24、27–31 引用 2026-10-24 在备课虚拟机上用课堂实验床与 `02/reference/lsrd` 补测的数据，复现命令写在答案题 30、31；其余数字沿用第五讲原记录。排版检查不代表实验验证。

## 第 06 讲讲义阅读版

先修改 `2026/docs/network_measurement.md`，再从仓库根目录执行：

```bash
# 1. 按本目录锁文件准备依赖（与其他生成器共用）
uv sync --project 2026/tools --frozen

# 2. 生成第 06 讲阅读版，日期填写本次内容更新日期
uv run --project 2026/tools --frozen python 2026/tools/build_network_measurement_html.py --date 2026-10-17
```

- 输出 `2026/docs/network_measurement.html`。CSS、字体、目录行为与打印样式取自 `link_state_router.html`；页面结构对照 `datacenter_network.html`：导读、“课堂安排与准备”提示框、学习目标、本讲路线、课堂时间安排、各模块。
- 命令块只加行内高亮（步骤注释、`sudo`、namespace 名），不加逐行的块级容器，保证复制出的文本与源文逐字一致。输出块统一标为“实测样例”；出现其他代码类型时生成器会报错，需先补渲染规则。
- 链到仓库内 Markdown 时，若同目录有同名阅读版，改链到 `.html`；否则保留 `.md` 链接。
- 两幅图由 `network_measurement_figures.py` 绘制为内嵌 SVG，与 Markdown 中带 `%% lecture06:<key>` 的 Mermaid 源图一一对应，源图摘要保存在 `network_measurement_figure_sources.json`。图注取自源图下方的 `*图示说明：…*`。修改源图后先核对 SVG 的节点、方向、标签与简化条件，再更新摘要。
- 生成器自动核对：命令／输出文本逐字一致、图数与图号、唯一 ID、页内与跨页锚点、本地链接、源文摘要、外部资源依赖、未解析的 Markdown 标记，以及第 04 讲模板残留。显示检查仍须在真实浏览器中完成：桌面、约 390 px 手机、浅色／深色、打印与导出 PDF 的分页。

## Lab 4 阅读版

先修改 `2026/experiments/04/README.md`，再从仓库根目录执行：

```bash
# 1. 按本目录锁文件准备依赖（与其他生成器共用）
uv sync --project 2026/tools --frozen

# 2. 生成 Lab 4 阅读版，日期填写本次内容更新日期
uv run --project 2026/tools --frozen python 2026/tools/build_lab4_html.py --date 2026-10-17
```

- 输出 `2026/experiments/04/README.html`。CSS、字体、目录与打印样式取自 `link_state_router.html`；页面结构与 Lab 3 阅读版一致：实验导读、按“一、二、……”分节、目录列出各级小节，任务（h4）在目录中缩进。
- `bash` 块只加行内高亮；`output` 块标为“实测样例”，无语言标记的字符块（如 3.3 节的目录树）标为“示意”。出现其他代码类型时生成器会报错。
- 3.3 节的字符数据流图由 `lab4_figures.py` 绘制为内嵌 SVG，图注取自其下方的 `*图 1：…*`；源图摘要保存在 `lab4_figure_sources.json`。修改字符图后先核对 SVG 的框、箭头、TODO 标签与说明，再更新摘要。
- 链到仓库内 Markdown 时，若同目录有同名阅读版则改链到 `.html`。生成器自动核对命令／输出文本逐字一致、图号、唯一 ID、链接与锚点、源文摘要、外部资源依赖与残留标记；浏览器显示（桌面、约 390 px 手机、浅色／深色、打印与导出 PDF）须另行检查。

