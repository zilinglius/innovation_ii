"""第二讲回顾答案中的语义 SVG；源图改变时必须重新核对。"""

import hashlib
from html import escape
import re

SOURCE_SHA = {
    "diagnosis": "7553a01bb169a3a9197c75c8989a1f77f941b28ed57135b98d4dc91a270942c3",
    "bridge": "5bcb11c431b967ef1e840d1410c3f93cae09cc6f8aef2a60b191c9f84432de30",
}

FIGURE_CSS = """
@media screen { .fig svg { min-width:700px; } }
.fig-body:focus-visible { outline:2px solid var(--l3); outline-offset:3px; }
@media print { .fig svg { min-width:0; } }
"""


def text(x, y, lines, cls="", size=13):
    spans = "".join(f'<tspan x="{x}" dy="{0 if i == 0 else 18}">{escape(line)}</tspan>'
                    for i, line in enumerate(lines))
    return f'<text x="{x}" y="{y}" text-anchor="middle" class="{cls}" style="font-size:{size}px">{spans}</text>'


def rect(x, y, w, h, lines, cls="n-host", size=13):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" class="{cls}"/>'
            + text(x + w / 2, y + h / 2 + 5 - 9 * (len(lines) - 1), lines, size=size))


def arrow(points, key, dashed=False):
    return f'<path d="{points}" class="ar ar-l3 {"dash" if dashed else ""}" marker-end="url(#{key}-arrow)"/>'


def diagnosis(key):
    parts = []
    for offset, title, broken in [(0, "情况甲：r2 缺回程路由；两台路由器开启转发", False),
                                  (215, "情况乙：r2 关闭转发；路由保持完整", True)]:
        parts.append(text(380, 25 + offset, [title], "t-b", 15))
        parts.append(rect(20, 65 + offset, 130, 60, ["h1a"]))
        parts.append(rect(610, 65 + offset, 130, 60, ["h2a"]))
        for x, name in [(275, "r1"), (475, "r2")]:
            parts.append(f'<ellipse cx="{x}" cy="{95 + offset}" rx="50" ry="30" class="n-l3"/>')
            parts.append(text(x, 100 + offset, [name], "t-b"))
        for left, right in [(150, 225), (325, 425)]:
            parts.append(arrow(f'M {left} {95 + offset} H {right - 3}', key))
            parts.append(text((left + right) / 2, 82 + offset, ["请求"], "t-l3", 12))
        if broken:
            parts.append(f'<path d="M 525 {95 + offset} H 610" class="wire dash"/>')
            parts.append(text(568, 76 + offset, ["链路仍在"], "t-muted", 11))
            parts.append(text(475, 153 + offset, ["请求在 r2 停止", "转发开关为 0"], "t-drop", 13))
            parts.append(text(675, 153 + offset, ["未收到请求", "无对应回复"], "t-muted", 12))
        else:
            parts.append(arrow(f'M 525 {95 + offset} H 607', key))
            parts.append(text(568, 82 + offset, ["请求"], "t-l3", 12))
            parts.append(arrow('M 675 125 V 158 H 475 V 130', key, True))
            parts.append(text(580, 148, ["回复"], "t-l3", 12))
            parts.append(text(475, 192, ["回复在 r2 停止：无回程路由"], "t-drop", 13))
    parts.append('<path d="M 20 211 H 740" class="life"/>')
    return 420, "".join(parts)


def bridge(key):
    parts = ['<rect x="190" y="18" width="420" height="360" rx="6" class="ns-box"/>',
             text(400, 43, ["r1 的 Network Namespace"], "t-b", 15),
             rect(15, 65, 145, 55, ["h1a", "10.0.1.11/24"], size=12),
             rect(15, 165, 145, 55, ["h1b", "10.0.1.12/24"], size=12),
             rect(210, 68, 120, 50, ["r1-h1a", "桥端口 · 无 IP"], "n-l2", 12),
             rect(210, 168, 120, 50, ["r1-h1b", "桥端口 · 无 IP"], "n-l2", 12),
             '<path d="M 160 93 H 210 M 160 193 H 210" class="wire"/>',
             text(182, 79, ["veth"], "t-muted", 10),
             text(182, 179, ["veth"], "t-muted", 10),
             '<path d="M 330 93 H 360 V 143 H 390 M 330 193 H 360 V 143" class="wire"/>',
             rect(390, 113, 180, 60, ["br1", "网关 10.0.1.1/24"], "n-l2"),
             arrow('M 480 173 V 203', key, True),
             text(535, 194, ["本地投递"], "t-l3", 11),
             '<ellipse cx="480" cy="230" rx="72" ry="25" class="n-l3"/>',
             text(480, 235, ["IPv4 查表"], "t-b"),
             arrow('M 480 255 V 297', key, True),
             text(530, 284, ["三层转发"], "t-l3", 11),
             rect(390, 300, 180, 60, ["r1-r2 · 不入桥", "10.0.12.1/30"], "n-l3", 12),
             '<path d="M 570 330 H 635" class="wire"/>',
             text(605, 316, ["veth"], "t-muted", 11),
             '<ellipse cx="690" cy="330" rx="55" ry="30" class="n-l3"/>',
             text(690, 326, ["r2", "10.0.12.2/30"], size=11)]
    return 400, "".join(parts)


def figure(code, caption, rendered_caption):
    key = re.search(r"^%% review-answer:(\w+)", code)[1]
    if SOURCE_SHA.get(key) != hashlib.sha256(code.encode()).hexdigest():
        raise ValueError(f"{key} 源图改变；先核对 SVG 的节点、路径与条件，再更新摘要")
    height, body = {"diagnosis": diagnosis, "bridge": bridge}[key](key)
    return (f'<figure class="fig" id="fig-{key}"><div class="fig-body" tabindex="0" role="region" aria-label="配图，可横向滚动">'
            f'<svg viewBox="0 0 760 {height}" role="img" aria-labelledby="{key}-title {key}-desc">'
            f'<title id="{key}-title">{escape(caption.split("：", 1)[0])}</title>'
            f'<desc id="{key}-desc">{escape(caption)}</desc>'
            f'<defs><marker id="{key}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 Z" class="mk-l3"/></marker></defs>'
            f'{body}</svg></div><figcaption>{rendered_caption}</figcaption></figure>')
