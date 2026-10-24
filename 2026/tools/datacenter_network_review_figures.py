"""第五讲回顾的语义配图；与 Markdown Mermaid 摘要一一绑定。"""

import hashlib
from html import escape
import json
from pathlib import Path
import re

SOURCE_SHA = json.loads(Path(__file__).with_name("datacenter_network_review_figure_sources.json").read_text())
FIGURE_CSS = """
@media screen { .fig svg { min-width:700px; } }
.fig-body:focus-visible { outline:2px solid var(--l3); outline-offset:3px; }
svg .review-label { paint-order:stroke; stroke:var(--bg); stroke-width:5px; stroke-linejoin:round; }
svg .ar-muted { stroke:var(--ink-3); }
svg .mk-muted { fill:var(--ink-3); }
svg .bar-drop { fill:var(--drop-bg); stroke:var(--drop); stroke-width:1.2; }
svg .bar-l3 { fill:var(--l3-bg); stroke:var(--l3); stroke-width:1.2; }
svg .bar-l4 { fill:var(--l4-bg); stroke:var(--l4); stroke-width:1.2; }
svg .dot-l4 { fill:var(--l4); }
svg .tick { stroke:var(--rule-2); stroke-width:1; fill:none; }
svg .cut { stroke:var(--drop); stroke-width:2.2; }
@media print { .fig svg { min-width:0; } }
"""
LEAF_X = (95, 285, 475, 665)


def text(x, y, lines, cls="", size=14, anchor="middle"):
    if isinstance(lines, str):
        lines = lines.split("\n")
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}" style="font-size:{size}px">'
            + "".join(f'<tspan x="{x}" dy="{0 if i == 0 else 18}">{escape(line)}</tspan>' for i, line in enumerate(lines))
            + '</text>')


def box(x, y, w, h, label, cls="n-host", size=13):
    lines = label.split("\n") if label else []
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" class="{cls}"/>'
            + (text(x + w / 2, y + h / 2 + 5 - 9 * (len(lines) - 1), lines, size=size) if lines else ""))


def router(x, y, label, rx=34, ry=22, size=13):
    lines = label.split("\n")
    return (f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" class="n-l3"/>'
            + text(x, y + 5 - 9 * (len(lines) - 1), lines, "t-b", size))


def line(d, cls="wire"):
    return f'<path d="{d}" class="{cls}"/>'


def arrow(d, key, kind="l3", dashed=False):
    return f'<path d="{d}" class="ar ar-{kind}{" dash" if dashed else ""}" marker-end="url(#{key}-arrow-{kind})"/>'


def bar(x, y, w, h, cls):
    return f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}" class="{cls}"/>'


def cross(x, y, r=7):
    return line(f'M {x - r} {y - r} L {x + r} {y + r} M {x - r} {y + r} L {x + r} {y - r}', 'cut')


def topology(key):
    p = []
    for i, cx in enumerate(LEAF_X, 1):
        p.append(f'<rect x="{cx - 93}" y="160" width="186" height="226" rx="6" class="zone"/>')
        p.append(text(cx, 378, f"机架 {i} · 10.0.{i}.0/24", "t-muted", 11))
    for s, sx in ((5, 190), (6, 570)):
        for i, cx in enumerate(LEAF_X, 1):
            p.append(line(f'M {sx} 74 L {cx} 168', 'wire' + (' dash' if s == 6 else '')))
    p += [router(190, 50, "r5 · spine", 62, 24), router(570, 50, "r6 · spine", 62, 24)]
    for i, cx in enumerate(LEAF_X, 1):
        k = 2 * (i - 1)
        p += [router(cx, 190, f"r{i} · leaf", 50, 22),
              line(f'M {cx} 212 V 262 M {cx} 298 L {cx - 47} 322 M {cx} 298 L {cx + 47} 322'),
              text(cx, 234, f"10.1.{k}.0/30 → r5", "t-mono t-l3 review-label", 10.5),
              text(cx, 250, f"10.1.{k + 1}.0/30 → r6", "t-mono t-l3 review-label", 10.5),
              box(cx - 62, 262, 124, 36, f"br{i} · 10.0.{i}.1", "n-l2", 12),
              box(cx - 90, 322, 86, 36, f"h{i}a .11", "n-host", 12),
              box(cx + 4, 322, 86, 36, f"h{i}b .12", "n-host", 12)]
    p.append(text(380, 410, "实线连 r5，虚线连 r6 · 主机接入 100 Mbit/s · leaf–spine 100 或 50 Mbit/s", "t-muted", 12))
    return 424, ''.join(p)


def matrix_question(key):
    p = [f'<rect x="16" y="24" width="240" height="210" rx="6" class="zone"/>',
         text(136, 46, "机架 1", "t-muted", 12),
         f'<rect x="500" y="14" width="244" height="96" rx="6" class="zone"/>',
         text(512, 34, "机架 2", "t-muted", 12, "start"),
         f'<rect x="500" y="146" width="244" height="96" rx="6" class="zone"/>',
         text(512, 234, "机架 3", "t-muted", 12, "start"),
         box(66, 58, 140, 44, "h1a"), box(66, 168, 140, 44, "h1b"),
         box(572, 34, 120, 44, "h2a"), box(572, 166, 120, 44, "h3a"),
         arrow('M 206 72 L 568 56', key, 'l4'), text(386, 52, "50 MB", "t-l4 review-label", 13),
         arrow('M 206 92 L 568 184', key, 'l4'), text(440, 164, "50 MB", "t-l4 review-label", 13),
         arrow('M 206 182 L 568 70', key, 'l4'), text(470, 104, "50 MB", "t-l4 review-label", 13),
         arrow('M 120 168 V 106', key, 'l4'), text(88, 142, "30 MB", "t-l4 review-label", 13),
         arrow('M 632 166 V 82', key, 'l4'), text(668, 128, "40 MB", "t-l4 review-label", 13),
         text(380, 266, "箭头为本阶段的通信需求，不表示物理链路或已选路径", "t-muted", 12)]
    return 282, ''.join(p)


def incast_question(key):
    p = [f'<rect x="10" y="14" width="270" height="128" rx="6" class="zone"/>',
         f'<rect x="10" y="156" width="270" height="128" rx="6" class="zone"/>',
         text(232, 38, "机架 1", "t-muted", 12), text(232, 180, "机架 2", "t-muted", 12)]
    hosts = [("h1a · 30 MB", 26), ("h1b · 30 MB", 90), ("h2a · 30 MB", 168), ("h2b · 30 MB", 232)]
    for i, (label, y) in enumerate(hosts):
        leaf_y = 78 if i < 2 else 220
        p += [box(22, y, 118, 40, label, "n-host", 12), line(f'M 140 {y + 20} L 198 {leaf_y}')]
    for leaf, y in (("r1", 78), ("r2", 220)):
        for sy in (78, 220):
            p.append(line(f'M 266 {y} L 374 {sy}'))
        p.append(router(232, y, leaf))
    for spine, y in (("r5", 78), ("r6", 220)):
        p += [line(f'M 434 {y} L 534 149'), router(404, y, spine)]
    p += [router(566, 150, "r3"), arrow('M 600 150 H 636', key, 'l4'),
          box(640, 128, 110, 44, "h3a\n接收 120 MB", "n-host", 12),
          text(618, 194, "r3-h3a", "t-mono t-l4", 11),
          text(380, 306, "未指定哪条流经过哪个 spine · 主机接入 100 Mbit/s", "t-muted", 12)]
    return 322, ''.join(p)


VX_LAYERS = [("外层 Ethernet", "14", "n-l2"), ("外层 IPv4", "20", "n-l3"), ("UDP", "8", "n-l4"),
             ("VXLAN", "8", "n-l4"), ("内层 Ethernet", "14", "n-l2"), ("内层 IPv4", "20", "n-l3"),
             ("ICMP", "8", "n-l3"), ("数据", "32", "n-host")]


def vxlan_stack(key, answered):
    widths = [92, 86, 70, 76, 98, 86, 70, 76]
    x, p, edges = 10, [], []
    for (name, size, cls), w in zip(VX_LAYERS, widths):
        shown = size if answered or name in ("外层 Ethernet", "内层 IPv4", "ICMP", "数据") else "?"
        p.append(box(x, 40, w - 4, 56, f"{name}\n{shown} B", cls, 12))
        edges.append(x)
        x += w
    edges.append(x)

    def brace(a, b, y, label, cls):
        x1, x2 = edges[a], edges[b] - 4
        return (line(f'M {x1} {y - 8} V {y} H {x2} V {y - 8}', 'tick')
                + text((x1 + x2) / 2, y + 18, label, cls, 12))

    p.append(brace(5, 8, 118, "内层 IP 总长 60 B", "t-l3"))
    p.append(brace(1, 8, 156, "外层 IP 总长：tcpdump 显示 length 110" if not answered
                   else "外层 IP 总长 20 + 8 + 8 + 14 + 60 = 110 B", "t-l3"))
    if answered:
        p.append(brace(0, 8, 194, "经典 Ethernet 格式抓到的帧 124 B", "t-muted"))
    p.append(text(380, 24, "报文中的先后顺序：左 → 右 · 宽度不按比例", "t-muted", 12))
    return (230 if answered else 192), ''.join(p)


def vxlan_question(key):
    return vxlan_stack(key, False)


def vxlan_answer(key):
    return vxlan_stack(key, True)


def failure_question(key):
    p = []
    for off, title, failed in ((0, "故障前：固定分路，上联 100 Mbit/s", False),
                               (206, "关闭 r6-r1 并收敛后：只剩 r1-r5", True)):
        y5, y6, y1 = 70 + off, 156 + off, 113 + off
        p += [f'<rect x="8" y="{8 + off}" width="744" height="190" rx="6" class="zone"/>',
              text(380, 32 + off, title, "t-b", 14),
              box(18, y5 - 20, 108, 38, "h1a · 30 MB", "n-host", 12),
              box(18, y6 - 20, 108, 38, "h1b · 30 MB", "n-host", 12),
              router(222, y1, "r1"), router(392, y5, "r5"), router(392, y6, "r6"),
              router(560, y5, "r3"), router(560, y6, "r4"),
              box(640, y5 - 19, 104, 38, "h3a", "n-host", 12), box(640, y6 - 19, 104, 38, "h4a", "n-host", 12),
              arrow(f'M 126 {y5} L 190 {y1 - 10}', key, 'l4'),
              arrow(f'M 126 {y6} L 190 {y1 + 10}', key, 'l4', True),
              arrow(f'M 594 {y5} H 636', key, 'l4'),
              arrow(f'M 594 {y6} H 636', key, 'l4', True)]
        if not failed:
            p += [arrow(f'M 254 {y1 - 12} L 360 {y5 + 8}', key, 'l4'),
                  arrow(f'M 254 {y1 + 12} L 360 {y6 - 8}', key, 'l4', True),
                  text(290, y5 + 8, "r1-r5", "t-mono t-l3 review-label", 11),
                  text(290, y6 - 2, "r1-r6", "t-mono t-l3 review-label", 11),
                  arrow(f'M 426 {y5} H 524', key, 'l4'), arrow(f'M 426 {y6} H 524', key, 'l4', True)]
        else:
            p += [arrow(f'M 254 {y1 - 16} L 360 {y5 + 2}', key, 'l4'),
                  arrow(f'M 256 {y1 - 6} L 362 {y5 + 12}', key, 'l4', True),
                  text(286, y5 - 4, "r1-r5：两流共享", "t-mono t-l3 review-label", 11),
                  line(f'M 254 {y1 + 12} L 360 {y6 - 8}', 'wire dash'), cross(307, y1 + 28),
                  text(300, y6 + 6, "r6-r1 已关闭", "t-drop review-label", 11),
                  arrow(f'M 426 {y5} H 524', key, 'l4'),
                  arrow(f'M 420 {y5 + 14} L 528 {y6 - 10}', key, 'l4', True)]
    p.append(text(380, 428, "实线为 h1a → h3a，虚线为 h1b → h4a；各 30 MB，主机接入 100 Mbit/s", "t-muted", 12))
    return 442, ''.join(p)


ECMP_ROWS = [("补测 · 策略 0", "46.95 Mbit/s", (0, 0.00), (8, 30.41)),
             ("补测 · 策略 1", "92.44 Mbit/s", (1, 28.70), (7, 29.36)),
             ("原讲义 · 策略 1", "93.52 Mbit/s", (3, 29.10), (5, 29.49))]


def ecmp_answer(key):
    p = [text(250, 20, "按 SYN 路径分组的接收应用数据", "t-muted", 12, "start"),
         text(560, 20, "连接数", "t-muted", 12, "start")]
    for i, (title, rate, a, b) in enumerate(ECMP_ROWS):
        y0 = 36 + i * 100
        p += [f'<rect x="8" y="{y0}" width="744" height="88" rx="6" class="zone"/>',
              text(20, y0 + 36, title, "t-b", 13, "start"), text(20, y0 + 58, f"八流 {rate}", "t-muted", 12, "start")]
        for j, (spine, (flows, mb)) in enumerate((("r5", a), ("r6", b))):
            y = y0 + 14 + j * 36
            p += [text(232, y + 16, spine, "t-mono t-l3", 12, "end"),
                  bar(250, y, max(mb * 7, 1.5), 22, "bar-l3"),
                  text(256 + mb * 7, y + 16, f"{mb:.2f} MB", "t-mono", 11, "start")]
            p += [f'<circle cx="{566 + k * 16}" cy="{y + 11}" r="5" class="dot-l4"/>' for k in range(flows)]
            p.append(text(566 + max(flows, 1) * 16 + 6, y + 15, f"{flows} 条", "t-l4", 12, "start"))
    p.append(text(380, 350, "每条上联 50 Mbit/s，由经过它的连接分享；单条连接约 47.6 Mbit/s", "t-muted", 12))
    return 364, ''.join(p)


INCAST_ROWS = [("发送端接入", "各 30 MB", 2.4, 2.4), ("源 leaf 上联", "均衡时各 30 MB", 2.4, 4.8),
               ("spine → r3", "均衡时各 60 MB", 4.8, 9.6), ("r3 → h3a", "120 MB", 9.6, 9.6)]


def incast_answer(key):
    x0, scale = 250, 40
    p = [bar(250, 14, 16, 12, "bar-l3"), text(272, 25, "leaf–spine 100 Mbit/s", "t-muted", 12, "start"),
         bar(450, 14, 16, 12, "bar-l4"), text(472, 25, "leaf–spine 50 Mbit/s", "t-muted", 12, "start")]
    for i, (name, load, t100, t50) in enumerate(INCAST_ROWS):
        y = 46 + i * 58
        p += [text(20, y + 18, name, "t-b", 13, "start"), text(20, y + 36, load, "t-muted", 11, "start")]
        for j, (t, cls) in enumerate(((t100, "bar-l3"), (t50, "bar-l4"))):
            yy = y + j * 22
            p += [bar(x0, yy, t * scale, 18, cls), text(x0 + t * scale + 6, yy + 14, f"{t} s", "t-mono", 11, "start")]
    p += [line(f'M {x0 + 9.6 * scale} 38 V 280', 'tick dash'),
          text(x0 + 9.6 * scale, 298, "下界 9.6 s", "t-b", 12),
          text(380, 322, "按 8D/C 计算，忽略首部与启动开销；任何不均衡都会让 50 档的 fabric 超过 9.6 s", "t-muted", 12)]
    return 336, ''.join(p)


def failure_answer(key):
    t0, x0, scale = 5.5, 70, 80          # 上排：每秒 80 单位

    def tx(t):
        return x0 + (t - t0) * scale

    p = []
    for s in range(6, 14):
        p += [line(f'M {tx(s)} 34 V 160', 'tick'), text(tx(s), 26, f"{s:02d}", "t-mono", 11)]
    p += [text(14, 26, "07:25:xx", "t-muted", 11, "start"),
          text(14, 62, "路由", "t-b", 12, "start"),
          bar(tx(6.546), 46, (12.784 - 6.546) * scale, 26, "bar-l3"),
          text((tx(6.546) + tx(12.784)) / 2, 64, "检测：r6 判 Down 用 6.238 s", "t-l3", 12),
          bar(tx(12.784), 46, (12.959 - 12.784) * scale, 26, "n-l3"),
          text(14, 104, "F3 去程", "t-b", 12, "start"),
          bar(tx(6.546), 88, 6.410 * scale, 24, "bar-drop"),
          text((tx(6.546) + tx(12.956)) / 2, 105, "中断 6410 ms，丢在 r1", "t-drop", 12),
          text(14, 142, "R1 回程", "t-b", 12, "start"),
          bar(tx(6.546), 126, 6.390 * scale, 24, "bar-drop"),
          text((tx(6.546) + tx(12.936)) / 2, 143, "中断 6390 ms，丢在 r6", "t-drop", 12)]
    z0, z1, zx0, zx1 = 12.75, 13.0, 70, 730

    def zx(t):
        return zx0 + (t - z0) * (zx1 - zx0) / (z1 - z0)

    p += [line(f'M {tx(z0)} 160 L {zx0} 196 M {tx(z1)} 160 L {zx1} 196', 'wire dash'),
          f'<rect x="{zx0}" y="196" width="{zx1 - zx0}" height="34" class="zone"/>']
    events = [(12.784, "r6 判 Down", 0), (12.795, "r6 发 LSA", 1), (12.892, "r1 判 Down", 0),
              (12.934, "r6 改装", 1), (12.943, "r3 改路由", 2), (12.959, "r1 改路由", 0)]
    for t, label, row in events:
        p += [line(f'M {zx(t):.1f} 196 V 230', 'ar ar-l3'), text(round(zx(t), 1), 250 + row * 17, label, "t-l3", 11)]
    p += [text(zx0 + 4, 225, "12.75", "t-mono t-muted", 10, "start"), text(zx1 - 4, 225, "13.00", "t-mono t-muted", 10, "end"),
          line(f'M {zx(12.784):.1f} 290 V 298 H {zx(12.959):.1f} V 290', 'tick'),
          text(round((zx(12.784) + zx(12.959)) / 2, 1), 316, "从 r6 判 Down 到 r1 改好路由约 175 ms", "t-l3", 12),
          text(380, 346, "下排放大 12.75–13.00 s（每 0.05 s 约 132 单位），上排按时间比例", "t-muted", 12)]
    return 360, ''.join(p)


CAP_ROWS = [("故障前 · 100 档", "收敛比 1:1", ("100", "100"), 2.622, 2.602),
            ("故障后 · 100 档", "收敛比 2:1", ("100", None), 5.125, 2.611),
            ("不故障 · 50 档", "收敛比 2:1", ("50", "50"), 5.113, 5.119)]


def capacity_answer(key):
    x0, scale = 390, 56
    p = [text(250, 22, "r1 的上联（Mbit/s）", "t-muted", 12),
         bar(390, 12, 16, 12, "bar-l3"), text(412, 23, "两流 60 MB", "t-muted", 12, "start"),
         bar(540, 12, 16, 12, "bar-l4"), text(562, 23, "单流 30 MB", "t-muted", 12, "start")]
    for i, (title, ratio, links, pair, single) in enumerate(CAP_ROWS):
        y0 = 36 + i * 100
        cy = y0 + 44
        p += [f'<rect x="8" y="{y0}" width="744" height="88" rx="6" class="zone"/>',
              text(20, cy - 4, title, "t-b", 13, "start"), text(20, cy + 16, ratio, "t-muted", 12, "start"),
              router(200, cy, "r1", 24, 17, 12), router(310, y0 + 20, "r5", 24, 15, 11), router(310, y0 + 68, "r6", 24, 15, 11)]
        for (cap, ty) in zip(links, (y0 + 20, y0 + 68)):
            if cap:
                p += [line(f'M 222 {cy + (-8 if ty < cy else 8)} L 286 {ty}', 'wire ar-l3'),
                      text(254, (cy + ty) / 2 + (-4 if ty < cy else 14), cap, "t-mono t-l3 review-label", 11)]
            else:
                p += [line(f'M 222 {cy + 8} L 286 {ty}', 'wire dash'), cross(254, (cy + ty) / 2 + 2, 6)]
        for j, (t, cls) in enumerate(((pair, "bar-l3"), (single, "bar-l4"))):
            yy = y0 + 18 + j * 30
            p += [bar(x0, yy, t * scale, 22, cls), text(x0 + t * scale + 6, yy + 16, f"{t:.3f} s", "t-mono", 11, "start")]
    p.append(text(380, 350, "两流由上联总容量决定，单流由单条路径的容量决定；均为三轮中位数", "t-muted", 12))
    return 364, ''.join(p)


def evidence_answer(key):
    labels = [("拓扑与链路", "n-l3"), ("LSDB 与 SPF", "n-l3"), ("RIB", "n-l3"), ("FIB\n乙", "n-drop"),
              ("哈希选路\n甲", "n-drop"), ("共享容量\n丙", "n-drop"), ("完成时间", "n-l4")]
    p = []
    for i, (label, cls) in enumerate(labels):
        x = 10 + i * 107
        p.append(box(x, 34, 92, 64, label, cls, 13))
        if i < len(labels) - 1:
            p.append(arrow(f'M {x + 92} 66 H {x + 105}', key))
    p.append(text(380, 136, "红框是三个现场分别卡住的环节；上游正确不保证下游正确", "t-muted", 12))
    return 156, ''.join(p)


DRAW = {
    'topology': topology, 'matrix_question': matrix_question, 'incast_question': incast_question,
    'vxlan_question': vxlan_question, 'failure_question': failure_question,
    'ecmp_answer': ecmp_answer, 'incast_answer': incast_answer, 'vxlan_answer': vxlan_answer,
    'failure_answer': failure_answer, 'capacity_answer': capacity_answer, 'evidence_answer': evidence_answer,
}


def figure(code, number, rendered_caption, plain_caption):
    key = re.match(r'%% dc-review:(\w+)', code)[1]
    if SOURCE_SHA.get(key) != hashlib.sha256(code.encode()).hexdigest():
        raise ValueError(f'{key} 源图改变；先核对 SVG 的节点、方向、字段与条件，再更新摘要')
    height, body = DRAW[key](key)
    markers = ''.join(
        f'<marker id="{key}-arrow-{kind}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
        f'<path d="M 0 0 L 10 5 L 0 10 Z" class="mk-{kind}"/></marker>'
        for kind in ('l3', 'l4', 'muted', 'drop'))
    return (f'<figure class="fig" id="fig-{key}"><div class="fig-body" tabindex="0" role="region" aria-label="配图，可横向滚动">'
            f'<svg viewBox="0 0 760 {height}" role="img" aria-labelledby="{key}-title {key}-desc">'
            f'<title id="{key}-title">{escape(number)}</title>'
            f'<desc id="{key}-desc">{escape(plain_caption)}</desc>'
            f'<defs>{markers}</defs>'
            f'{body}</svg></div><figcaption><b>{escape(number)}</b><span>{rendered_caption}</span></figcaption></figure>')
