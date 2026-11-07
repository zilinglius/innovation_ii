"""第 07 讲阅读版配图：与 Markdown 中的 Mermaid 源图按摘要一一绑定；图意以 Markdown 为准。"""

import hashlib
from html import escape
import json
from pathlib import Path

from network_measurement_figures import arrow, box, text

SOURCE_SHA = json.loads(Path(__file__).with_name("tail_latency_figure_sources.json").read_text())

# 只补充配图样式；字体、主题变量、正文与打印设置继续复用讲义模板。
FIGURE_CSS = """
.fig-body:focus-visible { outline:2px solid var(--l3); outline-offset:4px; }
@media screen { .fig svg.lec07 { min-width:700px; } }
svg.lec07 text { font-size:13px; }
svg.lec07 .t-mono { font-size:12.5px; }
svg.lec07 .slow { fill:var(--warn-bg); stroke:var(--warn); stroke-width:1.4; }
svg.lec07 .hot { fill:var(--drop-bg); stroke:var(--drop); stroke-width:1.6; }
svg.lec07 .t-warn { fill:var(--warn); }
svg.lec07 .t-drop { fill:var(--drop); }
svg.lec07 .frame { fill:none; stroke:var(--rule-2); stroke-width:1.2; stroke-dasharray:5 4; }
svg.lec07 .life { stroke:var(--rule-2); stroke-width:1.2; stroke-dasharray:3 4; }
svg.lec07 .ar-drop { stroke:var(--drop); stroke-width:2; }
.fig-scroll-hint { display:none; }
@media screen and (max-width:740px) {
  .fig-scroll-hint { display:block; margin:0 0 8px; color:var(--ink-2); font-size:12px; }
}
@media print { .fig svg.lec07 { min-width:0; width:100%; } .fig-scroll-hint { display:none; } }
"""


def pipe(key):
    """1.1 节：cwnd 超过 BDP 的部分只能排队。"""
    p = [
        box(14, 56, 130, 62, [("发送方", "t-b"), ("在途 = cwnd", "t-sm t-2")]),
        arrow("M 144 87 H 196", key),
        '<rect x="198" y="56" width="196" height="62" rx="5" class="n-l4"/>',
    ]
    for i in range(9):
        p.append(f'<rect x="{212 + i * 19}" y="66" width="13" height="16" rx="2" class="slow"/>')
    p += [
        text(296, 104, "瓶颈队列：排队 ≈ cwnd − BDP", "t-sm t-l4"),
        arrow("M 394 87 H 436", key),
        '<rect x="438" y="66" width="172" height="42" rx="21" class="n-l3"/>',
        text(524, 92, "链路：最多容纳 BDP", "t-sm t-l3"),
        arrow("M 610 87 H 646", key),
        box(648, 56, 98, 62, [("接收方", "t-b")]),
        text(296, 40, "放不下的报文排在这里", "t-sm t-warn"),
        text(524, 40, "这部分不增加延迟", "t-sm t-2"),
        text(380, 150, "cwnd ≤ BDP：几乎不排队；cwnd ≫ BDP：多出来的全部变成排队时延", "t-sm t-2"),
    ]
    return 166, "".join(p)


def fanout(key):
    """3.1 节：一轮要等全部分片。"""
    rows = [("分片 1", "6 ms", False), ("分片 2", "6 ms", False), ("分片 3", "106 ms（慢）", True), ("分片 N", "6 ms", False)]
    p = [box(20, 122, 110, 60, [("前端", "t-b"), ("同时发出 N 个", "t-sm t-2")])]
    for i, (name, ms, slow) in enumerate(rows):
        y = 22 + i * 68
        cls = "slow" if slow else "n-host"
        p.append(arrow(f"M 130 152 L 278 {y + 22}", key))
        p.append(box(280, y, 190, 44, [(f"{name}：{ms}", "t-b t-warn" if slow else "")], cls))
        p.append(arrow(f"M 470 {y + 22} L 588 152", key, "ar ar-warn" if slow else "ar", "warn" if slow else "ink"))
    p.append(text(375, 219, "⋮", "t-muted"))
    p.append(box(590, 112, 150, 80, [("等全部回来", "t-b"), ("本轮 106 ms", "t-b t-warn"), ("由最慢的决定", "t-sm t-2")]))
    return 306, "".join(p)


def hedge(key):
    """4.2 节：对冲请求的时序；只画主副本变慢的情况。"""
    xs = {"前端": 130, "主副本": 400, "备份副本": 640}
    p = []
    for name, x in xs.items():
        p.append(box(x - 60, 12, 120, 34, [(name, "t-b")]))
        p.append(f'<line x1="{x}" y1="46" x2="{x}" y2="306" class="life"/>')
    p += [
        arrow("M 130 80 H 398", key),
        text(265, 72, "请求", "t-sm"),
        '<rect x="392" y="84" width="16" height="200" rx="3" class="slow"/>',
        text(470, 118, "主副本变慢", "t-sm t-warn"),
        f'<path d="M 110 80 V 150" class="ar ar-warn dash" marker-end="url(#{key}-warn)"/>',
        text(100, 120, "等 d 毫秒，", "t-sm t-warn", "end"),
        text(100, 138, "主副本没回来", "t-sm t-warn", "end"),
        arrow("M 130 150 H 638", key),
        text(320, 142, "备份请求", "t-sm"),
        '<rect x="632" y="154" width="16" height="36" rx="3" class="n-host"/>',
        arrow("M 632 194 H 132", key, "ar ar-l4", "l4"),
        text(320, 186, "响应：先到，采用", "t-sm t-l4"),
        arrow("M 130 236 H 390", key, "ar dash"),
        text(265, 228, "取消", "t-sm"),
        text(520, 262, "主副本的结果不再需要", "t-sm t-2"),
    ]
    return 318, "".join(p)


def _panel(y, title, detail):
    return (f'<rect x="8" y="{y}" width="744" height="156" rx="8" class="frame"/>'
            + text(22, y + 22, title, "t-b", "start") + text(738, y + 22, detail, "t-sm t-2", "end"))


def _hosts(y, slow=False):
    """三个场景相同的节点位置：左边前端，中间主副本，右边备份副本。"""
    cls = "slow" if slow else "n-host"
    return (box(24, y + 62, 110, 54, [("h1a", "t-mono t-b"), ("前端", "t-sm t-2")])
            + box(392, y + 36, 110, 42, [("h3a", "t-mono t-b"), ("主副本", "t-sm t-2")], cls)
            + box(392, y + 100, 110, 42, [("h3b", "t-mono t-b"), ("主副本", "t-sm t-2")], cls)
            + box(610, y + 62, 128, 54, [("h4a、h4b", "t-mono t-b"), ("备份副本", "t-sm t-2")], cls))


def scenes(key):
    """5.1 节：三场景对照，节点位置与视觉尺度相同；只改变高亮部分。"""
    p = []
    # 场景 A：后端偶发慢。
    y = 8
    p += [_panel(y, "场景 A：后端偶发慢", "变化：每个请求以 p=1% 多等 100 ms；各副本独立抽样"), _hosts(y, True)]
    p += [arrow(f"M 134 {y + 80} L 390 {y + 57}", key), arrow(f"M 134 {y + 96} L 390 {y + 121}", key)]
    p.append(f'<path d="M 134 {y + 89} H 608" class="ar dash" marker-end="url(#{key}-ink)"/>')
    p.append(text(24, y + 142, "实线：主请求；虚线：备份请求", "t-sm t-2", "start"))
    # 场景 B：一台后端的路径堵塞。
    y = 176
    p += [_panel(y, "场景 B：一台后端的路径堵塞", "变化：r3→h3a 50 Mbit/s + pfifo 300；大象流 h2a→h3a"), _hosts(y)]
    p += [f'<rect x="316" y="{y + 40}" width="70" height="34" rx="4" class="hot"/>',
          text(351, y + 55, "r3→h3a", "t-mono t-drop"), text(351, y + 69, "队列", "t-sm t-drop")]
    p += [arrow(f"M 134 {y + 80} L 314 {y + 60}", key), arrow(f"M 386 {y + 57} H 390", key),
          arrow(f"M 134 {y + 96} L 390 {y + 121}", key)]
    p.append(f'<path d="M 134 {y + 89} H 608" class="ar dash" marker-end="url(#{key}-ink)"/>')
    p.append(box(180, y + 118, 100, 32, [("h2a 大象流", "t-mono t-sm")]))
    p.append(arrow(f"M 280 {y + 122} L 336 {y + 76}", key, "ar ar-drop", "drop"))
    # 场景 C：前端自己的入口堵塞。
    y = 344
    p += [_panel(y, "场景 C：前端自己的入口堵塞", "变化：r1→h1a 50 Mbit/s + pfifo 300；大象流 h2a→h1a"), _hosts(y)]
    p += [f'<rect x="146" y="{y + 72}" width="70" height="34" rx="4" class="hot"/>',
          text(181, y + 87, "r1→h1a", "t-mono t-drop"), text(181, y + 101, "队列", "t-sm t-drop")]
    p.append(arrow(f"M 146 {y + 89} H 136", key))
    p += [arrow(f"M 390 {y + 57} L 218 {y + 82}", key), arrow(f"M 390 {y + 121} L 218 {y + 96}", key)]
    p.append(f'<path d="M 608 {y + 89} H 218" class="ar dash" marker-end="url(#{key}-ink)"/>')
    p.append(box(190, y + 118, 100, 32, [("h2a 大象流", "t-mono t-sm")]))
    p.append(arrow(f"M 210 {y + 118} L 190 {y + 108}", key, "ar ar-drop", "drop"))
    p.append(text(24, y + 44, "这里画响应方向：响应都要经过这个队列", "t-sm t-2", "start"))
    return 508, "".join(p)


DRAW = {"pipe": pipe, "fanout": fanout, "hedge": hedge, "scenes": scenes}


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
            f'<svg class="lec07" viewBox="0 0 760 {height}" role="img" aria-labelledby="{key}-title {key}-desc" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{key}-title">图 {number}</title><desc id="{key}-desc">{escape(caption_text)}</desc>'
            f'<defs>{markers}</defs>{body}</svg></div>'
            f'<figcaption><b>图 {number}</b><span>{caption_html}</span></figcaption></figure>\n')
