"""第 09 讲阅读版配图：与 Markdown 中的 Mermaid 源图按摘要一一绑定；图意以 Markdown 为准。"""

import hashlib
from html import escape
import json
from pathlib import Path

from communication_cost_figures import ALL_WORKERS, RACKS, _fabric, _panel
from network_measurement_figures import arrow, box, router, text

SOURCE_SHA = json.loads(Path(__file__).with_name("collective_communication_figure_sources.json").read_text())

# 只补充配图样式；字体、主题变量、正文与打印设置继续复用讲义模板。前半段与第 08 讲相同，换成本讲的类名。
FIGURE_CSS = """
.fig-body:focus-visible { outline:2px solid var(--l3); outline-offset:4px; }
@media screen { .fig svg.lec09 { min-width:700px; } }
svg.lec09 text { font-size:13px; }
svg.lec09 .t-mono { font-size:12.5px; }
svg.lec09 .t-warn { fill:var(--warn); }
svg.lec09 .t-drop { fill:var(--drop); }
svg.lec09 .t-l4c { fill:var(--l4); }
svg.lec09 .frame { fill:none; stroke:var(--rule-2); stroke-width:1.2; stroke-dasharray:5 4; }
svg.lec09 .hotlink { stroke:var(--drop); stroke-width:4; fill:none; }
svg.lec09 .ps { fill:var(--drop-bg); stroke:var(--drop); stroke-width:1.6; }
svg.lec09 .active { fill:var(--l4-bg); stroke:var(--l4); stroke-width:1.4; }
svg.lec09 .done { fill:var(--l4-bg); stroke:var(--l4); stroke-width:1.6; }
svg.lec09 .part { fill:none; stroke:var(--rule-2); stroke-width:1.2; stroke-dasharray:4 3; }
svg.lec09 .alpha { fill:var(--warn-bg); stroke:var(--warn); stroke-width:1.2; }
svg.lec09 .ring { fill:none; stroke:var(--l4); stroke-width:1.6; }
svg.lec09 .ring-x { fill:none; stroke:var(--warn); stroke-width:2.2; }
svg.lec09 .uplink { stroke:var(--l3); stroke-width:2.4; fill:none; }
.fig-scroll-hint { display:none; }
@media screen and (max-width:740px) {
  .fig-scroll-hint { display:block; margin:0 0 8px; color:var(--ink-2); font-size:12px; }
}
@media print { .fig svg.lec09 { min-width:0; width:100%; } .fig-scroll-hint { display:none; } }
"""


def allreduce(key):
    """1.2 节：N=3 的 AllReduce = Reduce-Scatter + Allgather；“全”表示合并了全部 3 个节点。"""
    columns = (
        (20, "开始", "每个节点有自己的 3 块", [(), (), ()]),
        (275, "Reduce-Scatter 之后", "每个节点有 1 块合并完的", [(1,), (2,), (0,)]),
        (530, "Allgather 之后", "每个节点都有全部 3 块", [(0, 1, 2)] * 3),
    )
    p = []
    for x, title, detail, done in columns:
        p.append(f'<rect x="{x - 8}" y="10" width="226" height="212" rx="6" class="frame"/>')
        p.append(text(x + 105, 32, title, "t-b"))
        p.append(text(x + 105, 50, detail, "t-sm t-2"))
        for node in range(3):
            y = 70 + node * 50
            p.append(text(x + 4, y + 22, f"节点 {node}", "t-sm", "start"))
            for chunk in range(3):
                complete = chunk in done[node]
                if not done[node]:
                    cls, label = "n-host", f"c{chunk}"
                else:
                    cls, label = ("done", f"c{chunk} 全") if complete else ("part", "")
                p.append(box(x + 54 + chunk * 52, y, 48, 32, [(label, "t-mono")], cls))
    p += [arrow("M 240 136 H 265", key, "ar ar-l4", "l4"), arrow("M 495 136 H 520", key, "ar ar-l4", "l4"),
          text(252, 244, "N−1 步，边传边合并", "t-sm t-l4c"), text(507, 244, "N−1 步，只传不算", "t-sm t-l4c"),
          text(20, 270, "紫框“全”：这一块已经合并了全部 3 个节点的贡献；虚线框：还没合并完、之后会被覆盖的块",
               "t-sm t-2", "start")]
    return 282, "".join(p)


HOST_X = {f"h{rack}{side}": x + d for rack, x in enumerate(RACKS, start=1) for side, d in (("a", -41), ("b", 41))}


def _ring_edges(order, y, cross_of):
    """环上的逻辑边画成主机下方的弧线；跨机架的边用琥珀色。"""
    p = []
    for src, dst in zip(order, order[1:] + order[:1]):
        x0, x1 = HOST_X[src] + 12, HOST_X[dst] - 12
        depth = 30 if abs(x1 - x0) < 200 else 66
        cls, marker = ("ring-x", "warn") if cross_of(src, dst) else ("ring", "l4")
        p.append(f'<path d="M {x0} {y} C {x0} {y + depth}, {x1} {y + depth}, {x1} {y + 3}" '
                 f'class="{cls}" marker-end="url(#KEY-{marker})"/>')
    return p


def traffic(key):
    """2.3 节：同一组 worker 的两种通信方式，节点位置相同。"""
    order = ["h1b", "h2a", "h2b", "h3a", "h3b", "h4a", "h4b"]
    p = [_panel(8, 186, "参数服务器：h1a 接入链路每轮进 7S、出 7S", "红线是共同瓶颈"),
         _fabric(34, ALL_WORKERS, hot_access=True),
         _panel(204, 240, "Ring：每条接入链路每轮进、出各 12S/7", "按机架顺序，4 条跨机架边（琥珀色）"),
         _fabric(230, ALL_WORKERS, has_ps=False)]
    edges = _ring_edges(order, 372, lambda a, b: a[1] != b[1])
    p += [edge.replace("KEY", key) for edge in edges]
    p += [text(380, 438, "弧线是逻辑收发关系（h1b→h2a→…→h4b→h1b），实际报文都经过 leaf，跨机架的还经过 spine；Ring 不用 h1a",
               "t-sm t-2")]
    return 452, "".join(p)


def _mini_fabric(y, order, title, detail, key):
    """3.2 节用：r5、r6 两台 spine，r1、r2 两个 leaf，各 2 台 host；上联标 50 Mbit/s。"""
    spines, leaves = (250, 510), (200, 560)
    hosts = {"h1a": 140, "h1b": 260, "h2a": 500, "h2b": 620}
    p = [f'<rect x="8" y="{y}" width="744" height="236" rx="6" class="frame"/>',
         text(20, y + 22, title, "t-b", "start"), text(740, y + 22, detail, "t-sm t-2", "end")]
    sy, ly, hy = y + 52, y + 112, y + 146
    for sx in spines:
        for lx in leaves:
            p.append(f'<path d="M {sx} {sy} L {lx} {ly}" class="uplink"/>')
    p.append(text(20, y + 88, "蓝线：上联，每条 50 Mbit/s", "t-sm t-l3", "start"))
    for sx, name in zip(spines, ("r5", "r6")):
        p.append(router(sx, sy, name, 28, 16))
    for lx, name, members in ((leaves[0], "r1", ("h1a", "h1b")), (leaves[1], "r2", ("h2a", "h2b"))):
        for member in members:
            p.append(f'<path d="M {lx} {ly} L {hosts[member]} {hy}" class="wire"/>')
        p.append(router(lx, ly, name, 28, 16))
    for name, hx in hosts.items():
        p.append(box(hx - 36, hy, 72, 30, [(name, "t-mono t-b")], "active"))
    for index, (src, dst) in enumerate(zip(order, order[1:] + order[:1])):
        x0, x1 = hosts[src] + 14, hosts[dst] - 14
        cross = src[1] != dst[1]
        depth = 26 + 18 * index
        cls, marker = ("ring-x", "warn") if cross else ("ring", "l4")
        p.append(f'<path d="M {x0} {hy + 30} C {x0} {hy + 30 + depth}, {x1} {hy + 30 + depth}, '
                 f'{x1} {hy + 33}" class="{cls}" marker-end="url(#{key}-{marker})"/>')
    return p


def orders(key):
    """3.2 节：两种环序，节点位置与上联相同；琥珀色是跨机架边。"""
    p = _mini_fabric(8, ["h1a", "h1b", "h2a", "h2b"], "环序 A：h1a → h1b → h2a → h2b → h1a",
                     "2 条跨机架边，每个方向 1 条流", key)
    p += _mini_fabric(254, ["h1a", "h2a", "h1b", "h2b"], "环序 B：h1a → h2a → h1b → h2b → h1a",
                      "4 条跨机架边，每个方向 2 条流", key)
    p += [text(380, 512, "琥珀色弧线：跨机架的边，要过 leaf 上联；紫色弧线：同机架的边。B 中同方向的 2 条流由 ECMP 各自选上联，可能落在同一条上",
               "t-sm t-2")]
    return 524, "".join(p)


def _segments(x, y, count, beta_width, label_alpha, label_beta, max_width):
    """一段传输画成“α 框 + β 条”；count 段首尾相接。"""
    p, alpha_width = [], 22
    step = (alpha_width + beta_width + 6)
    for index in range(count):
        sx = x + index * step
        if sx + step > x + max_width:
            p.append(text(sx + 8, y + 22, "…", "t-b"))
            break
        p.append(f'<rect x="{sx}" y="{y}" width="{alpha_width}" height="32" rx="3" class="alpha"/>')
        p.append(f'<rect x="{sx + alpha_width}" y="{y}" width="{beta_width}" height="32" rx="3" class="n-l4"/>')
    p.append(text(x, y + 52, label_alpha, "t-sm t-warn", "start"))
    p.append(text(x + 200, y + 52, label_beta, "t-sm t-l4c", "start"))
    return p


def scenes(key):
    """5.1 节：一轮通信的时间结构，教学示意，长度不按比例。"""
    p = [_panel(8, 132, "参数服务器：每轮 2 次串行传输，每次过 h1a 接入链路 7S 字节", "改变的只有 S 与同步方式"),
         text(20, 62, "上传", "t-sm", "start"), text(300, 62, "下载", "t-sm", "start")]
    p += _segments(20, 70, 2, 250, "琥珀：α（每次传输的固定开销）", "紫：7Sβ（传 7S 字节的时间）", 720)
    p += [_panel(152, 132, "Ring：每轮 12 步串行，每步每条边 S/7 字节", "Reduce-Scatter 6 步 + Allgather 6 步")]
    p += _segments(20, 192, 12, 26, "琥珀：α，每步都要付一次", "紫：Sβ/7（每步只传 S/7）", 720)
    p += [text(380, 300, "长度不按比例：S 小时 α 占主导，Ring 付 12 次、参数服务器付 2 次；S 大时紫色占主导，参数服务器每次传 7S",
               "t-sm t-2")]
    return 312, "".join(p)


DRAW = {"allreduce": allreduce, "traffic": traffic, "orders": orders, "scenes": scenes}


def figure(key, code, number, caption_html, caption_text):
    if SOURCE_SHA.get(key) != hashlib.sha256(code.encode()).hexdigest():
        raise ValueError(f"{key} 源图已变；先核对 SVG 的节点、方向、标签与简化条件，再更新图源摘要")
    height, body = DRAW[key](key)
    markers = "".join(
        f'<marker id="{key}-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
        f'orient="auto"><path d="M 0 0 L 10 5 L 0 10 Z" class="mk-{name}"/></marker>'
        for name in ("ink", "l4", "warn", "drop"))
    return (f'<figure class="fig" id="fig-{key}">'
            '<p class="fig-scroll-hint">左右滑动查看全图；键盘可聚焦图框后横向滚动。</p>'
            f'<div class="fig-body" tabindex="0" role="region" aria-label="图 {number}，可横向滚动">'
            f'<svg class="lec09" viewBox="0 0 760 {height}" role="img" aria-labelledby="{key}-title {key}-desc" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{key}-title">图 {number}</title><desc id="{key}-desc">{escape(caption_text)}</desc>'
            f'<defs>{markers}</defs>{body}</svg></div>'
            f'<figcaption><b>图 {number}</b><span>{caption_html}</span></figcaption></figure>\n')
