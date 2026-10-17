"""第 06 讲阅读版配图：与 Markdown 中的 Mermaid 源图按摘要一一绑定；图意以 Markdown 为准。"""

import hashlib
from html import escape
import json
from pathlib import Path

SOURCE_SHA = json.loads(Path(__file__).with_name("network_measurement_figure_sources.json").read_text())

# 只补充配图样式；字体、主题变量、正文与打印设置继续复用讲义模板。
FIGURE_CSS = """
.fig-body:focus-visible { outline:2px solid var(--l3); outline-offset:4px; }
@media screen { .fig svg.lec06 { min-width:700px; } }
svg.lec06 text { font-size:13px; }
svg.lec06 .t-mono { font-size:12.5px; }
svg.lec06 .cand { fill:var(--warn-bg); stroke:var(--warn); stroke-width:1.4; }
svg.lec06 .t-warn { fill:var(--warn); }
svg.lec06 .alt { fill:var(--bg); stroke:var(--l4); stroke-width:1.4; stroke-dasharray:6 4; }
svg.lec06 .frame { fill:none; stroke:var(--rule-2); stroke-width:1.2; stroke-dasharray:5 4; }
.fig-scroll-hint { display:none; }
@media screen and (max-width:740px) {
  .fig-scroll-hint { display:block; margin:0 0 8px; color:var(--ink-2); font-size:12px; }
}
@media print { .fig svg.lec06 { min-width:0; width:100%; } .fig-scroll-hint { display:none; } }
"""


def text(x, y, value, cls="", anchor="middle"):
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}">{escape(value)}</text>'


def box(x, y, w, h, lines, cls="n-host"):
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" class="{cls}"/>'
    first = y + h / 2 + 5 - 9 * (len(lines) - 1)
    for i, (value, style) in enumerate(lines):
        out += text(x + w / 2, first + 18 * i, value, style)
    return out


def router(x, y, name, rx=36, ry=21):
    return f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" class="n-l3"/>' + text(x, y + 5, name, "t-mono t-b t-l3")


def arrow(d, key, cls="ar", marker="ink"):
    return f'<path d="{d}" class="{cls}" marker-end="url(#{key}-{marker})"/>'


def badge(x, y, number):
    return f'<circle cx="{x}" cy="{y}" r="11" class="cand"/>' + text(x, y + 4.5, number, "t-b t-warn")


def qdisc(key):
    """2.2 节：一个端口发送方向上的 qdisc 结构；只替换叶子，限速不变。"""
    p = [
        f'<rect x="8" y="34" width="744" height="252" rx="8" class="frame"/>',
        text(22, 26, "一个限速端口的发送方向（egress）", "t-sm t-2", "start"),
        text(330, 62, "HTB 根与类：决定容量（每秒最多发多少）", "t-sm t-l3"),
        text(555, 62, "叶子：决定排队方式", "t-sm t-l4"),
        box(20, 82, 110, 56, [("报文离开接口", "")]),
        arrow("M 130 110 H 158", key),
        box(162, 82, 120, 56, [("根 qdisc", ""), ("htb 1:", "t-mono t-l3")], "n-l3"),
        arrow("M 282 110 H 310", key),
        box(314, 82, 140, 56, [("类 1:10", ""), ("rate = ceil = 档位", "t-mono t-l3")], "n-l3"),
        arrow("M 454 110 H 482", key),
        box(486, 82, 136, 56, [("叶子 qdisc 10:", ""), ("基线为 fq", "t-mono t-l4")], "n-l4"),
        arrow("M 622 110 H 650", key),
        box(654, 82, 90, 56, [("veth 对端", "")]),
        arrow("M 554 138 V 206", key, "ar ar-l4 dash", "l4"),
        text(564, 180, "本讲替换为", "t-sm t-l4", "start"),
        f'<rect x="420" y="210" width="324" height="64" rx="5" class="alt"/>',
        text(582, 236, "netem：加延迟／抖动／丢包", "t-mono"),
        text(582, 258, "pfifo：单一先进先出队列", "t-mono"),
        text(20, 220, "只替换叶子，HTB 的限速保持不变", "t-sm t-2", "start"),
        text(20, 244, "所有配置只作用于该接口的发送方向", "t-sm t-2", "start"),
    ]
    return 300, "".join(p)


def candidates(key):
    """6.3 节：筛查后的候选位置；编号是待排除的假设，不是已知答案。"""
    p = []
    # leaf–spine 接线：每个 leaf 连两个 spine；发往 r4 的两条画成指向 r4 的箭头（方向即“进入机架 4”）。
    for leaf_x in (130, 380):
        for spine_x in (300, 460):
            p.append(f'<path d="M {leaf_x} 188 L {spine_x} 82" class="wire"/>')
    p.append(arrow("M 318 88 L 606 186", key))
    p.append(arrow("M 478 88 L 612 182", key))
    p += [
        router(300, 70, "r5"), router(460, 70, "r6"),
        text(20, 75, "spine", "t-sm t-muted", "start"),
        router(130, 200, "r1"), router(380, 200, "r2"), router(630, 200, "r4"),
        text(20, 205, "leaf", "t-sm t-muted", "start"), text(20, 330, "主机", "t-sm t-muted", "start"),
        box(80, 300, 100, 50, [("h1a", "t-mono t-b"), ("筛查源", "t-sm t-2")]),
        arrow("M 130 300 V 226", key),
        box(282, 300, 84, 50, [("h2a", "t-mono t-b"), ("对照源", "t-sm t-2")]),
        '<path d="M 324 300 L 362 220" class="wire"/>',
        box(402, 300, 84, 50, [("h2b", "t-mono t-b")]),
        arrow("M 392 222 L 424 296", key),
        arrow("M 462 300 L 410 220", key),
        box(570, 300, 120, 50, [("h4a、h4b", "t-mono t-b")]),
        arrow("M 630 222 V 296", key),
        badge(112, 262, "①"), badge(196, 150, "①"),
        badge(538, 130, "②"), badge(560, 172, "②"),
        badge(652, 262, "③"),
        badge(409, 262, "④"), badge(437, 262, "⑤"),
        badge(348, 146, "⑥"), badge(412, 146, "⑥"),
        '<path d="M 8 372 H 752" class="wire" style="stroke:var(--rule)"/>',
        text(20, 398, "① 源侧：h1a 出口、r1 上联", "t-sm", "start"),
        text(20, 422, "② 进入机架 4（两台 spine 发往 r4）", "t-sm", "start"),
        text(20, 446, "③ 单台主机的接入", "t-sm", "start"),
        text(330, 398, "④ 进入 h2b", "t-sm", "start"),
        text(330, 422, "⑤ h2b 发出", "t-sm", "start"),
        text(330, 446, "⑥ r2 经 spine 的路径", "t-sm", "start"),
        text(520, 398, "发往机架 4 吞吐低：", "t-sm t-b", "start"),
        text(520, 420, "候选 ① ② ③", "t-sm t-warn", "start"),
        text(520, 446, "与 h2b 的 RTT 高：", "t-sm t-b", "start"),
        text(520, 468, "候选 ① ④ ⑤ ⑥", "t-sm t-warn", "start"),
    ]
    return 484, "".join(p)


DRAW = {"qdisc": qdisc, "candidates": candidates}


def figure(key, code, number, caption_html, caption_text):
    if SOURCE_SHA.get(key) != hashlib.sha256(code.encode()).hexdigest():
        raise ValueError(f"{key} 源图已变；先核对 SVG 的节点、方向、标签与简化条件，再更新图源摘要")
    height, body = DRAW[key](key)
    markers = "".join(
        f'<marker id="{key}-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
        f'orient="auto"><path d="M 0 0 L 10 5 L 0 10 Z" class="mk-{name}"/></marker>'
        for name in ("ink", "l4"))
    return (f'<figure class="fig" id="fig-{key}">'
            '<p class="fig-scroll-hint">左右滑动查看全图；键盘可聚焦图框后横向滚动。</p>'
            f'<div class="fig-body" tabindex="0" role="region" aria-label="图 {number}，可横向滚动">'
            f'<svg class="lec06" viewBox="0 0 760 {height}" role="img" aria-labelledby="{key}-title {key}-desc" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{key}-title">图 {number}</title><desc id="{key}-desc">{escape(caption_text)}</desc>'
            f'<defs>{markers}</defs>{body}</svg></div>'
            f'<figcaption><b>图 {number}</b><span>{caption_html}</span></figcaption></figure>\n')
