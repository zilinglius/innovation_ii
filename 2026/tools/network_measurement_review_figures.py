"""第 06 讲回顾的语义配图；与 Markdown Mermaid 摘要一一绑定。数据图按比例绘制。"""

import hashlib
from html import escape
import json
from pathlib import Path
import re

from datacenter_network_review_figures import FIGURE_CSS as BASE_CSS
from datacenter_network_review_figures import arrow, box, line, text, topology

SOURCE_SHA = json.loads(Path(__file__).with_name("network_measurement_review_figure_sources.json").read_text())
FIGURE_CSS = BASE_CSS + """
svg .hot { fill:var(--drop-bg); stroke:var(--drop); stroke-width:1.5; }
svg .pkt { fill:var(--l4-bg); stroke:var(--l4); stroke-width:1; }
svg .pkt-ping { fill:var(--drop-bg); stroke:var(--drop); stroke-width:1.2; }
svg .dot-a { fill:var(--l4); }
svg .mark { stroke:var(--drop); stroke-width:1.8; }
svg .span { stroke:var(--l3); stroke-width:3; }
svg .span-mid { stroke:var(--warn); stroke-width:3; }
svg .frame { fill:none; stroke:var(--rule-2); stroke-width:1.2; stroke-dasharray:5 4; }
.math-wrap { overflow-x:auto; max-width:100%; }
"""


def _axis(x0, x1, y, top, ticks, unit, scale):
    out = [line(f"M {x0} {y} H {x1}")]
    for tick in ticks:
        x = scale(tick)
        out.append(f'<path d="M {x} {y} V {y + 5}" class="tick"/>')
        out.append(text(x, y + 20, f"{tick:g}", "t-muted", 12))
        out.append(f'<path d="M {x} {top} V {y}" class="tick" style="stroke-dasharray:2 5"/>')
    out.append(text(x1, y + 38, unit, "t-muted", 12, "end"))
    return "".join(out)


def queues(key):
    """题 18：同样的发送端和限速，只换队列。"""
    p = ['<rect x="6" y="6" width="368" height="266" rx="8" class="frame"/>',
         '<rect x="386" y="6" width="368" height="266" rx="8" class="frame"/>',
         text(190, 30, "fq：按流排队，轮流发送", "t-b", 14), text(570, 30, "pfifo：所有报文排同一个队", "t-b", 14)]
    # 左：fq
    p += [box(18, 62, 84, 42, "h1b 大流", "n-host", 13), box(18, 178, 84, 42, "h1a ping", "n-host", 13)]
    p.append('<rect x="124" y="62" width="130" height="42" rx="4" class="n-l4"/>')
    p += [f'<rect x="{132 + i * 13}" y="72" width="9" height="22" rx="1" class="pkt"/>' for i in range(9)]
    p.append(text(189, 122, "大流的队列：最多 100 个包", "t-sm t-2", 12))
    p.append('<rect x="124" y="178" width="130" height="42" rx="4" class="n-l4"/>')
    p.append('<rect x="132" y="188" width="9" height="22" rx="1" class="pkt-ping"/>')
    p.append(text(189, 238, "ping 的队列：几乎为空", "t-sm t-2", 12))
    p += [box(278, 112, 84, 58, "r3→h3a\n50 Mbit/s", "n-l3", 12)]
    p += [arrow("M 102 83 H 122", key, "muted"), arrow("M 102 199 H 122", key, "muted"),
          arrow("M 254 83 L 276 122", key, "muted"), arrow("M 254 199 L 276 160", key, "muted")]
    # 右：pfifo
    p += [box(398, 62, 84, 42, "h1b 大流", "n-host", 13), box(398, 178, 84, 42, "h1a ping", "n-host", 13)]
    p.append('<rect x="500" y="118" width="134" height="46" rx="4" class="hot"/>')
    p += [f'<rect x="{506 + i * 13}" y="130" width="9" height="22" rx="1" class="pkt"/>' for i in range(9)]
    p.append('<rect x="623" y="130" width="9" height="22" rx="1" class="pkt-ping"/>')
    p.append(text(600, 186, "同一个队列：最多 1000 个包", "t-sm t-2", 12))
    p.append(text(600, 204, "ping 排在大流后面", "t-sm t-2", 12))
    p += [box(656, 112, 90, 58, "r3→h3a\n50 Mbit/s", "n-l3", 12)]
    p += [arrow("M 482 83 L 498 128", key, "muted"), arrow("M 482 199 L 498 156", key, "muted"),
          arrow("M 634 141 H 654", key, "muted")]
    return 280, "".join(p)


BIMODAL = [18.9, 18.9, 18.9, 95.6, 95.2, 18.8, 18.8, 18.8, 18.8, 95.6, 18.8, 18.9]


def _scale_tput(value):
    return 50 + value * 6.6


def _dots(values, y, cls="dot-a"):
    """按读数画点；相同取值附近的点往上叠，便于数个数。"""
    out = []
    levels = {}
    for value in sorted(values):
        slot = round(value / 2)
        level = levels.get(slot, 0)
        levels[slot] = level + 1
        out.append(f'<circle cx="{_scale_tput(value):.1f}" cy="{y - 8 - level * 13}" r="5" class="{cls}"/>')
    return "".join(out)


def bimodal_question(key):
    """题 28：12 次读数的分布。"""
    ticks = (0, 20, 40, 60, 80, 100)
    p = [_axis(50, 710, 150, 16, ticks, "接收速率（Mbit/s）", _scale_tput), _dots(BIMODAL, 150)]
    p.append(text(_scale_tput(18.9) + 22, 60, "9 次", "t-sm t-2", 13, "start"))
    p.append(text(_scale_tput(95.5) - 18, 90, "3 次", "t-sm t-2", 13, "end"))
    return 196, "".join(p)


def position(key):
    """题 30：同一条路径，netem 挂在不同端口。"""
    names = [("h1a TCP", 16, 90), ("h1a eth0", 150, 130), ("r1、spine", 324, 100), ("r3-h3a", 468, 130), ("h3a", 642, 100)]

    def row(y, title, hot):
        out = [f'<rect x="6" y="{y}" width="748" height="92" rx="8" class="frame"/>', text(20, y + 22, title, "t-b", 13, "start")]
        for index, (name, x, w) in enumerate(names):
            if index == hot:
                out.append(box(x, y + 34, w, 46, f"{name}\nnetem delay 10ms", "hot", 12))
            else:
                out.append(box(x, y + 34, w, 46, f"{name}\nHTB + fq" if index in (1, 3) else name, "n-host", 12))
        for (_, x, w), (_, nx, _) in zip(names, names[1:]):
            out.append(arrow(f"M {x + w} {y + 57} H {nx - 2}", key, "muted"))
        return "".join(out)

    return 214, row(6, "netem 放在路由器端口", 3) + row(112, "netem 放在发送主机自己的出口", 1)


WILSON = [("原讲义 3/200", 1.5, 0.51, 4.32, False), ("原讲义 1/200", 0.5, 0.09, 2.78, False),
          ("原讲义 3/200", 1.5, 0.51, 4.32, False), ("原讲义合并 7/600", 1.17, 0.57, 2.39, True),
          ("补测 38/2000", 1.9, 1.39, 2.60, False), ("补测 36/2000", 1.8, 1.30, 2.48, False),
          ("补测 40/2000", 2.0, 1.47, 2.71, False), ("补测合并 114/6000", 1.9, 1.58, 2.28, True)]


def wilson(key):
    """题 8：Wilson 区间。"""
    scale = lambda v: 180 + v * 110
    top, row = 16, 28
    bottom = top + row * len(WILSON) + 4
    p = [_axis(180, 730, bottom, top, (0, 1, 2, 3, 4, 5), "丢包率（%）", scale)]
    p.append(f'<path d="M {scale(2)} {top - 6} V {bottom}" class="mark"/>')
    p.append(text(scale(2) + 6, top + 2, "配置值 2%", "t-sm", 12, "start"))
    for index, (label, point, low, high, merged) in enumerate(WILSON):
        y = top + row * index + 16
        p.append(text(170, y + 4, label, "t-b" if merged else "t-2", 12, "end"))
        p.append(line(f"M {scale(low):.1f} {y} H {scale(high):.1f}", "span-mid" if merged else "span"))
        p.append(f'<circle cx="{scale(point):.1f}" cy="{y}" r="4.5" class="dot-a"/>')
    return bottom + 46, "".join(p)


BURST = [("默认 1600", 0.3343, 0.1673, "0.335–0.337"), ("1 000 000", 0.1746, 0.1673, "0.175–0.177"),
         ("1 500 000", 0.0946, 0.1673, "0.168–0.170"), ("2 000 000", 0.0146, 0.1673, "0.168")]


def burst(key):
    """题 16：完成时间取两项中的较大者。"""
    scale = lambda v: 150 + v * 1000
    top, row = 12, 60
    bottom = top + row * len(BURST) + 4
    p = [_axis(150, 550, bottom, top, (0, 0.1, 0.2, 0.3, 0.4), "时间（秒）", scale)]
    for index, (label, limiter, upstream, measured) in enumerate(BURST):
        y = top + row * index + 8
        p.append(text(140, y + 19, label, "t-b", 12, "end"))
        p.append(f'<rect x="150" y="{y}" width="{limiter * 1000:.1f}" height="16" rx="2" class="bar-l3"/>')
        p.append(f'<rect x="150" y="{y + 20}" width="{upstream * 1000:.1f}" height="16" rx="2" class="bar-l4"/>')
        p.append(text(scale(limiter) + 6, y + 13, f"限速器项 {limiter:.3f}", "t-sm t-l3", 11, "start"))
        p.append(text(scale(upstream) + 6, y + 33, f"上游项 {upstream:.3f}", "t-sm t-l4", 11, "start"))
        p.append(text(748, y + 22, f"实测 {measured} s", "t-sm", 12, "end"))
    return bottom + 46, "".join(p)


QUEUE_ROWS = [("fq 每流上限", 24.2, "bar-l4"), ("fq 大流 rtt", 20.7, "bar-l3"), ("fq ping p50", 0.235, "bar-drop"),
              ("pfifo 上限", 242.2, "bar-l4"), ("pfifo 大流 rtt", 119.4, "bar-l3"), ("pfifo ping p50", 121.0, "bar-drop"),
              ("pfifo ping max", 239.0, "bar-drop")]


def queues_answer(key):
    """题 18：同样的吞吐，排队时间差几十到几百倍。"""
    scale = lambda v: 150 + v * 2.2
    top, row = 12, 28
    bottom = top + row * len(QUEUE_ROWS) + 4
    p = [_axis(150, 700, bottom, top, (0, 50, 100, 150, 200, 250), "毫秒", scale)]
    for index, (label, value, cls) in enumerate(QUEUE_ROWS):
        y = top + row * index + 5
        p.append(text(140, y + 14, label, "t-2", 12, "end"))
        p.append(f'<rect x="150" y="{y}" width="{max(value * 2.2, 1.5):.1f}" height="18" rx="2" class="{cls}"/>')
        p.append(text(scale(value) + 6, y + 14, f"{value:g} ms", "t-sm", 12, "start"))
    return bottom + 46, "".join(p)


def bimodal_answer(key):
    """题 28：统计量落在哪里。"""
    ticks = (0, 20, 40, 60, 80, 100)
    p = [_axis(50, 710, 150, 16, ticks, "接收速率（Mbit/s）", _scale_tput), _dots(BIMODAL, 150)]
    mean_x = _scale_tput(38.0)
    p.append(f'<path d="M {mean_x} 34 V 150" class="mark"/>')
    p.append(text(mean_x + 6, 42, "均值 38.0：没有一次读数在这里", "t-sm", 12, "start"))
    p.append(line(f"M {_scale_tput(16.0):.1f} 66 H {_scale_tput(60.0):.1f}", "span-mid"))
    p.append(text(_scale_tput(60.0) + 6, 70, "均值的 95% t 区间 16.0–60.0", "t-sm", 12, "start"))
    p.append(text(_scale_tput(18.9) + 22, 108, "p50 = 18.9", "t-sm t-2", 12, "start"))
    p.append(text(44, 214, "钉 r5", "t-2", 12, "end"))
    p.append(_dots([18.8, 19.2, 18.9], 222))
    p.append(line("M 50 214 H 710"))
    p.append(text(44, 258, "钉 r6", "t-2", 12, "end"))
    p.append(_dots([94.4, 95.3, 95.7], 266))
    p.append(line("M 50 258 H 710"))
    return 276, "".join(p)


LOCALIZE = [("① 源侧：h1a 出口、r1 上联", "换源 h2a→h4a 仍慢；h2a→h2b 不经过它，RTT 仍高", "排除", False),
            ("② 两台 spine 发往 r4", "换源仍慢，反向 95.7，每次连接都慢", "保留：吞吐问题在此", True),
            ("③ h4a 或 h4b 的接入", "两台主机都慢", "不太可能", False),
            ("④ 进入 h2b", "单向 h1a→h2b 为 4.386 ms", "确认：延迟问题在此", True),
            ("⑤ h2b 发出", "单向 h2b→h1a 为 0.26 ms", "排除", False),
            ("⑥ r2 经 spine 的路径", "同机架 h2a→h2b 不经过它，RTT 仍高", "排除", False)]


def localize(key):
    """题 25：候选位置与证据。"""
    p = [text(16, 22, "候选位置", "t-b", 13, "start"), text(204, 22, "证据（只改一个因素）", "t-b", 13, "start"),
         text(590, 22, "结论", "t-b", 13, "start"), line("M 8 32 H 752")]
    for index, (place, evidence, verdict, keep) in enumerate(LOCALIZE):
        y = 40 + index * 38
        if keep:
            p.append(f'<rect x="8" y="{y}" width="744" height="32" rx="4" class="hot"/>')
        p.append(text(16, y + 21, place, "t-b" if keep else "t-2", 12.5, "start"))
        p.append(text(204, y + 21, evidence, "", 12.5, "start"))
        p.append(text(590, y + 21, verdict, "t-b" if keep else "t-muted", 12.5, "start"))
    return 40 + len(LOCALIZE) * 38 + 8, "".join(p)


DRAW = {
    "topology": topology,
    "queues": queues,
    "bimodal_question": bimodal_question,
    "position": position,
    "wilson": wilson,
    "burst": burst,
    "queues_answer": queues_answer,
    "bimodal_answer": bimodal_answer,
    "localize": localize,
}


def figure(code, number, rendered_caption, plain_caption):
    key = re.match(r"%% nm-review:(\w+)", code)[1]
    if SOURCE_SHA.get(key) != hashlib.sha256(code.encode()).hexdigest():
        raise ValueError(f"{key} 源图改变；先核对 SVG 的节点、方向、字段与条件，再更新摘要")
    height, body = DRAW[key](key)
    markers = "".join(
        f'<marker id="{key}-arrow-{kind}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
        f'<path d="M 0 0 L 10 5 L 0 10 Z" class="mk-{kind}"/></marker>'
        for kind in ("l3", "l4", "muted", "drop"))
    return (f'<figure class="fig" id="fig-{key}"><div class="fig-body" tabindex="0" role="region" aria-label="配图，可横向滚动">'
            f'<svg viewBox="0 0 760 {height}" role="img" aria-labelledby="{key}-title {key}-desc">'
            f'<title id="{key}-title">{escape(number)}</title>'
            f'<desc id="{key}-desc">{escape(plain_caption)}</desc>'
            f"<defs>{markers}</defs>"
            f"{body}</svg></div><figcaption><b>{escape(number)}</b><span>{rendered_caption}</span></figcaption></figure>")
