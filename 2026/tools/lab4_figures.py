"""Lab 4 阅读版配图：与 Markdown 中的字符图按摘要绑定；图意以 Markdown 为准。"""

import hashlib
from html import escape
import json
from pathlib import Path

SOURCE_SHA = json.loads(Path(__file__).with_name("lab4_figure_sources.json").read_text())

# 只补充配图样式；字体、主题变量、正文与打印设置继续复用讲义模板。
FIGURE_CSS = """
.fig-body:focus-visible { outline:2px solid var(--l3); outline-offset:4px; }
@media screen { .fig svg.lab4 { min-width:700px; } }
svg.lab4 text { font-size:12.5px; }
svg.lab4 .t-mono { font-size:11.5px; }
svg.lab4 .badge { fill:var(--warn-bg); stroke:var(--warn); stroke-width:1.2; }
svg.lab4 .t-warn { fill:var(--warn); font-size:10.5px; font-weight:600; }
svg.lab4 .t-tiny { font-size:10px; }
svg.lab4 .raw { fill:var(--bg); stroke:var(--ink-3); stroke-width:1.2; stroke-dasharray:5 4; }
.fig-scroll-hint { display:none; }
@media screen and (max-width:740px) {
  .fig-scroll-hint { display:block; margin:0 0 8px; color:var(--ink-2); font-size:12px; }
}
@media print { .fig svg.lab4 { min-width:0; width:100%; } .fig-scroll-hint { display:none; } }
"""


def text(x, y, value, cls="", anchor="middle"):
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}">{escape(value)}</text>'


def box(x, y, w, h, lines, cls="n-host", todo=None):
    """lines 为 (文字, 样式) 列表，自上而下排在框内；todo 给出右上角的 TODO 标签。"""
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" class="{cls}"/>'
    first = y + h / 2 + 4.5 - 8.5 * (len(lines) - 1)
    for i, (value, style) in enumerate(lines):
        out += text(x + w / 2, first + 17 * i, value, style)
    if todo:
        # 标签骑在框的上边线上，不压住框内第一行文字
        out += (f'<rect x="{x + w - 58}" y="{y - 11}" width="54" height="16" rx="4" class="badge"/>'
                + text(x + w - 31, y + 1, todo, "t-warn"))
    return out


def arrow(d, key, cls="ar", marker="ink"):
    return f'<path d="{d}" class="{cls}" marker-end="url(#{key}-{marker})"/>'


def dataflow(key):
    """3.3 节：一对主机从测量到画像记录的数据流。"""
    small, mono = "t-xs t-2", "t-mono t-b"
    p = [
        box(10, 40, 90, 155, [("checkup.py", mono), ("调度", small)]),
        # 往返时间一路（第 1 行）
        box(126, 45, 128, 50, [("measure.py", small), ("ping()", mono)], "n-l3"),
        box(300, 45, 110, 50, [("parse.py", small), ("parse_ping()", mono)], "n-l3", "TODO 1"),
        box(455, 45, 160, 50, [("summary.py", small), ("summarize_rtt()", mono)], "n-l3", "TODO 3"),
        arrow("M 100 70 H 123", key),
        arrow("M 254 70 H 297", key), text(276, 61, "原始文本", "t-tiny t-2"),
        arrow("M 410 70 H 452", key),
        arrow("M 615 70 H 637", key),
        # 吞吐一路（第 2 行）
        box(126, 135, 128, 60, [("measure.py", small), ("throughput_runs()", mono), ("每次 iperf3_once()", small)],
            "n-l4", "TODO 5"),
        box(300, 140, 110, 50, [("parse.py", small), ("parse_iperf3()", mono)], "n-l4", "TODO 2"),
        box(455, 135, 160, 60, [("summary.py", small), ("summarize_throughput()", mono), ("多次读数 → 中位数、区间", small)],
            "n-l4", "TODO 4"),
        arrow("M 100 165 H 123", key),
        arrow("M 254 165 H 297", key), text(276, 156, "JSON", "t-xs t-2"),
        arrow("M 410 165 H 452", key),
        arrow("M 615 165 H 637", key),
        # 可信度标记（第 3 行）
        box(455, 230, 160, 60, [("summary.py", small), ("flags()", mono), ("依据 rtt 与各次读数", small)], "n-host", "TODO 6"),
        arrow("M 615 260 H 637", key),
        # 合成一条记录，写成画像；原始输出另存
        text(697, 30, "一条 pairs[] 记录", "t-sm t-b"),
        f'<rect x="640" y="40" width="115" height="260" rx="5" class="n-host"/>',
        text(697, 74, "rtt_ms", "t-mono t-l3"),
        text(697, 169, "throughput_mbps", "t-mono t-l4"),
        text(697, 264, "flags", "t-mono"),
        arrow("M 697 300 V 337", key),
        text(686, 323, "schema.validate()", "t-mono", "end"),
        box(640, 340, 115, 40, [("profile.json", mono)]),
        arrow("M 190 195 V 337", key, "ar dash"),
        text(200, 270, "每次的 JSON", "t-xs t-2", "start"),
        f'<rect x="130" y="340" width="120" height="40" rx="5" class="raw"/>',
        text(190, 356, "profile.raw/", mono),
        text(190, 373, "ping 文本与 iperf3 JSON", "t-xs t-2"),
        text(10, 412, "蓝框：往返时间一路　紫框：吞吐一路　带 TODO 标签的函数由你补全，其余给定", "t-xs t-2", "start"),
    ]
    return 425, "".join(p)


DRAW = {"dataflow": dataflow}


def figure(key, code, number, caption_html, caption_text):
    if SOURCE_SHA.get(key) != hashlib.sha256(code.encode()).hexdigest():
        raise ValueError(f"{key} 源图已变；先核对 SVG 的节点、方向、标签与简化条件，再更新图源摘要")
    height, body = DRAW[key](key)
    marker = (f'<marker id="{key}-ink" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
              'orient="auto"><path d="M 0 0 L 10 5 L 0 10 Z" class="mk-ink"/></marker>')
    return (f'<figure class="fig" id="fig-{key}">'
            '<p class="fig-scroll-hint">左右滑动查看全图；键盘可聚焦图框后横向滚动。</p>'
            f'<div class="fig-body" tabindex="0" role="region" aria-label="图 {number}，可横向滚动">'
            f'<svg class="lab4" viewBox="0 0 760 {height}" role="img" aria-labelledby="{key}-title {key}-desc" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{key}-title">图 {number}</title><desc id="{key}-desc">{escape(caption_text)}</desc>'
            f'<defs>{marker}</defs>{body}</svg></div>'
            f'<figcaption><b>图 {number}</b><span>{caption_html}</span></figcaption></figure>\n')
