"""第四讲回顾的语义配图；与 Markdown Mermaid 摘要一一绑定。"""

import hashlib
from html import escape
import json
from pathlib import Path
import re

SOURCE_SHA = json.loads(Path(__file__).with_name("link_state_router_review_figure_sources.json").read_text())
FIGURE_CSS = """
@media screen { .fig svg { min-width:700px; } }
.fig-body:focus-visible { outline:2px solid var(--l3); outline-offset:3px; }
svg .review-label { paint-order:stroke; stroke:var(--bg); stroke-width:5px; stroke-linejoin:round; }
svg .ar-muted { stroke:var(--ink-3); }
svg .mk-muted { fill:var(--ink-3); }
svg .bar-drop { fill:var(--drop-bg); stroke:var(--drop); stroke-width:1.2; }
svg .bar-l3 { fill:var(--l3-bg); stroke:var(--l3); stroke-width:1.2; }
svg .tick { stroke:var(--rule-2); stroke-width:1; }
@media print { .fig svg { min-width:0; } }
"""


def text(x, y, lines, cls="", size=14, anchor="middle"):
    if isinstance(lines, str):
        lines = lines.split("\n")
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}" style="font-size:{size}px">'
            + "".join(f'<tspan x="{x}" dy="{0 if i == 0 else 20}">{escape(line)}</tspan>' for i, line in enumerate(lines))
            + '</text>')


def box(x, y, w, h, label, cls="n-host", size=14):
    lines = label.split("\n") if label else []
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" class="{cls}"/>'
            + (text(x + w / 2, y + h / 2 + 5 - 10 * (len(lines) - 1), lines, size=size) if lines else ""))


def router(x, y, label, rx=42, ry=28, size=15):
    lines = label.split("\n")
    return (f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" class="n-l3"/>'
            + text(x, y + 5 - 10 * (len(lines) - 1), lines, "t-b", size))


def line(d, cls="wire"):
    return f'<path d="{d}" class="{cls}"/>'


def arrow(d, key, dashed=False, kind="l3"):
    marker = f"{key}-arrow" if kind == "l3" else f"{key}-arrow-{kind}"
    return f'<path d="{d}" class="ar ar-{kind} {"dash" if dashed else ""}" marker-end="url(#{marker})"/>'


def topology(key):
    p = [box(15, 45, 150, 62, "h1a\n10.0.1.11", size=13),
         box(595, 45, 150, 62, "h2a\n10.0.2.11", size=13),
         box(190, 45, 125, 62, "br1 · passive\n10.0.1.1", "n-l2", 13),
         box(445, 45, 125, 62, "br2 · passive\n10.0.2.1", "n-l2", 13),
         line('M 165 76 H 190 M 570 76 H 595 M 252 107 V 165 M 508 107 V 165'),
         router(252, 195, "r1\nrid 1", 44, 30, 14), router(508, 195, "r2\nrid 2", 44, 30, 14),
         router(380, 337, "r3\nrid 3", 44, 30, 14),
         line('M 296 195 H 464 M 272 222 L 358 310 M 488 222 L 402 310'),
         text(380, 156, "10.0.12.0/30\nr1-r2=.1 / r2-r1=.2", "t-mono", 12),
         text(165, 268, "10.0.13.0/30\nr1-r3=.1 / r3-r1=.2", "t-mono", 12),
         text(595, 268, "10.0.23.0/30\nr2-r3=.1 / r3-r2=.2", "t-mono", 12),
         text(380, 393, "互联接口 cost 10 · Hello 2 s / Dead 8 s · UDP 5200", "t-muted", 12)]
    return 412, ''.join(p)


def sequence(key, rows, left, right):
    h = 95 + len(rows) * 49
    p = [box(93, 12, 174, 44, left, 'n-l3'), box(493, 12, 174, 44, right, 'n-l3'),
         line(f'M 180 56 V {h - 20} M 580 56 V {h - 20}', 'life off')]
    for i, (kind, label) in enumerate(rows):
        y = 98 + i * 49
        if kind == 'note':
            p.append(box(95, y - 22, 570, 34, label, 'zone', 13))
        elif kind == 'noteA':
            p.append(box(30, y - 22, 330, 34, label, 'zone', 13))
        elif kind == 'noteB':
            p.append(box(430, y - 22, 300, 34, label, 'zone', 13))
        else:
            ab = kind == 'ab'
            p.append(arrow(f'M {180 if ab else 580} {y} H {578 if ab else 182}', key))
            p.append(text(380, y - 10, label, 't-l3 review-label', 13))
    return h, ''.join(p)


def hello_question(key):
    rows = [('note', '双方邻居表都是空的'), ('ab', '① Hello · seen = ？'),
            ('ba', '② Hello · seen = ？'), ('ab', '③ Hello · seen = ？'),
            ('note', '每条到达后，接收方怎样记录对方？')]
    return sequence(key, rows, 'r1 · rid 1', 'r2 · rid 2')


def hello_answer(key):
    rows = [('ab', '① Hello · seen = []'), ('noteB', 'r2：新建 r1 · Init'),
            ('ba', '② Hello · seen = [1]'), ('noteA', 'r1：新建 r2 · Init，同一条里升 Full'),
            ('ab', '③ Hello · seen = [2]'), ('noteB', 'r2：r1 升 Full')]
    return sequence(key, rows, 'r1 · rid 1', 'r2 · rid 2')


def flood_question(key):
    p = [router(140, 70, 'r1'), router(620, 70, 'r2'), router(380, 280, 'r3'),
         arrow('M 182 70 H 576', key), text(380, 55, '① seq 4', 't-l3'),
         arrow('M 166 92 L 350 255', key), text(220, 190, '② seq 4', 't-l3 review-label'),
         arrow('M 592 92 L 414 249', key), text(462, 186, '③ 转发', 't-l3 review-label'),
         arrow('M 425 263 L 605 104', key), text(568, 186, '④ 转发', 't-l3 review-label'),
         text(380, 345, '③、④ 都在 r2–r3 链路上，方向相反', 't-muted', 13)]
    return 368, ''.join(p)


def halflink_question(key):
    p = [router(150, 80, 'r1\nlinks: [3]', 78, 34, 14),
         router(380, 250, 'r3\nlinks: [1, 2]', 86, 34, 14),
         router(610, 80, 'r2\nlinks: [1, 3]', 86, 34, 14),
         line('M 196 108 L 330 222 M 430 222 L 562 108'),
         arrow('M 524 80 H 232', key, True), text(380, 64, '只有 r2 仍列着 r1', 't-l3', 13),
         text(380, 320, '实线：双方互相列出 · 虚线：单方面声明', 't-muted', 12)]
    return 340, ''.join(p)


SPF_NODES = {'r1': (95, 160), 'r2': (330, 60), 'r3': (330, 260), 'r4': (565, 160)}
SPF_EDGES = [('r1', 'r2', '2', 205, 95, 'M 133 140 L 288 78'),
             ('r1', 'r3', '1', 205, 232, 'M 133 180 L 288 242'),
             ('r3', 'r2', '1', 345, 165, 'M 330 230 V 92'),
             ('r2', 'r4', '1', 455, 95, 'M 372 78 L 525 140'),
             ('r3', 'r4', '3', 455, 232, 'M 372 242 L 525 180')]


def spf_graph(key, answered):
    p = []
    for a, b, cost, lx, ly, d in SPF_EDGES:
        unused = answered and (a, b) == ('r3', 'r4')
        if not answered:
            p.append(line(d))
        else:
            p.append(arrow(d, key, unused, 'muted' if unused else 'l3'))
        p.append(text(lx, ly, '3 · 未选' if unused else cost, ('t-muted' if unused else 't-l3') + ' review-label', 14))
    if answered:
        labels = {'r1': 'r1\n0', 'r2': 'r2 · 2\n首跳 2、3', 'r3': 'r3 · 1\n首跳 3', 'r4': 'r4 · 3\n首跳 2、3'}
        for name, (x, y) in SPF_NODES.items():
            p.append(router(x, y, labels[name], 40 if name == 'r1' else 60, 30, 13))
    else:
        for name, (x, y) in SPF_NODES.items():
            p.append(router(x, y, name, 40, 28))
        p += [line('M 605 160 H 630'), box(630, 136, 120, 48, '10.0.4.0/24\ncost 10', 'n-host', 12)]
    return 300, ''.join(p)


def spf_question(key):
    return spf_graph(key, False)


def spf_answer(key):
    return spf_graph(key, True)


def restart_question(key):
    p = []
    for off, title, forward in [(0, '去程探针：h1a → h2a，端口 9100', True),
                                (190, '回程探针：h2a → h1a，端口 9101', False)]:
        y = 102 + off
        p += [box(12, 8 + off, 736, 176, '', 'zone'), text(380, 34 + off, title, 't-b', 14),
              box(30, 78 + off, 110, 48, 'h1a', 'n-host', 13), box(620, 78 + off, 110, 48, 'h2a', 'n-host', 13),
              router(270, y, 'r1', 40, 26), router(490, y, 'r2', 40, 26)]
        if forward:
            p += [arrow(f'M 140 {y} H 228', key), arrow(f'M 310 {y} H 448', key), arrow(f'M 530 {y} H 618', key),
                  text(270, 152 + off, '查 10.0.2.0/24', 't-l3', 12),
                  text(490, 152 + off, '直连 10.0.2.0/24', 't-muted', 12)]
        else:
            p += [arrow(f'M 620 {y} H 532', key), arrow(f'M 450 {y} H 312', key), arrow(f'M 230 {y} H 142', key),
                  text(490, 152 + off, '查 10.0.1.0/24', 't-l3', 12),
                  text(270, 152 + off, '直连 10.0.1.0/24', 't-muted', 12)]
        p.append(text(490, 172 + off, 'lsrd 在第 5 秒左右 restart', 't-muted', 11))
    return 378, ''.join(p)


def timer_answer(key):
    x0, scale = 150, 76          # T−2 位于 x0，每秒 76 单位

    def tx(t):
        return x0 + (t + 2) * scale

    p = [f'<rect x="{tx(0)}" y="22" width="{3 * scale}" height="190" class="zone"/>',
         text(tx(1.5), 40, '循环被拖住 3 s', 't-muted', 12)]
    for t, label in [(-2, 'T−2'), (0, 'T'), (2, 'T+2'), (3, 'T+3'), (4, 'T+4'), (5, 'T+5')]:
        p += [line(f'M {tx(t)} 52 V 212', 'tick'), text(tx(t), 232, label, 't-mono', 12)]
    for y, title, sends, nxt, note in [(92, 'now + interval', [0], 5, '1 条'),
                                       (162, 'when + interval', [0, 1], 4, '连发 2 条')]:
        p += [text(14, y + 5, title, 't-b', 13, 'start'), line(f'M {tx(-2)} {y} H {tx(5.6)}', 'life'),
              f'<circle cx="{tx(-2)}" cy="{y}" r="7" class="n-l3"/>']
        for k in sends:
            p.append(f'<circle cx="{tx(3) + 14 * k}" cy="{y}" r="7" class="n-l3"/>')
        p += [f'<circle cx="{tx(nxt)}" cy="{y}" r="7" class="n-l3 dash"/>',
              text(tx(nxt), y - 14, '下一条', 't-l3', 11), text(tx(3) + 7, y + 30, note, 't-l3', 12)]
    p.append(text(380, 262, '两行中对端看到的最长间隔都是 T−2 → T+3 = 5 s，距 Dead 8 s 余 3 s', 't-muted', 12))
    return 280, ''.join(p)


def converge_answer(key):
    x0, width, total = 30, 700, 7070
    det = round(width * 6959 / total)
    p = [text(380, 26, '36.495 失去载波 → 43.565 路由改好，共约 7070 ms', 't-b', 14),
         f'<rect x="{x0}" y="44" width="{det}" height="34" class="bar-l3"/>',
         f'<rect x="{x0 + det}" y="44" width="{width - det}" height="34" class="n-host"/>',
         text(x0 + det / 2, 66, '检测 6959 ms（约 98%）', 't-l3', 13),
         line(f'M {x0 + det} 78 L 100 128 M {x0 + width} 78 L 700 128', 'wire dash')]
    x = 100
    for w, label, cls in [(90, '生成 LSA\n3 ms', 'n-host'), (420, '合并与 SPF\n约 104 ms', 'n-l3'),
                          (90, '安装\n3.8 ms', 'n-host')]:
        p.append(box(x, 128, w, 62, label, cls, 12))
        x += w
    p.append(text(380, 218, '下排放大最后约 111 ms；两个短段为可读而加宽，不按比例', 't-muted', 12))
    return 236, ''.join(p)


def restart_answer(key):
    t0, scale, x0 = 32.7, 210, 180

    def tx(t):
        return x0 + (t - t0) * scale

    p = []
    for t in (33, 34, 35):
        p += [line(f'M {tx(t)} 40 V 238', 'tick'), text(tx(t), 256, f'{t} s', 't-mono', 12)]
    for t, label in [(32.835, 'A 旧 r2 退出'), (33.281, 'B r1 删路由'), (35.274, 'C、D 装回')]:
        p.append(text(tx(t), 28, label, 't-muted', 11))
    rows = [(62, 'r2 缺 10.0.1.0/24', [(32.835, 35.274, 'bar-l3', '')]),
            (104, 'r1 缺 10.0.2.0/24', [(33.281, 35.277, 'bar-l3', '')]),
            (156, '去程丢在哪里', [(32.835, 33.281, 'bar-drop', 'r2 过滤 45'),
                                   (33.281, 35.277, 'bar-drop', 'r1 无路由 199')]),
            (198, '回程丢在哪里', [(32.835, 35.274, 'bar-drop', 'r2 无路由 244')])]
    for y, label, bars in rows:
        p.append(text(14, y + 19, label, 't-b', 13, 'start'))
        for a, b, cls, tag in bars:
            p.append(f'<rect x="{tx(a):.1f}" y="{y}" width="{(b - a) * scale:.1f}" height="28" class="{cls}"/>')
            if tag:
                p.append(text(round((tx(a) + tx(b)) / 2, 1), y + 19, tag, 't-drop', 12))
    p.append(text(380, 282, '补测 A；时刻取自 ip -ts monitor route，计数取自 nstat', 't-muted', 12))
    return 298, ''.join(p)


def evidence_answer(key):
    labels = [('Hello 报文', 'n-l3'), ('邻居表\n甲', 'n-drop'), ('LSDB\n乙', 'n-drop'), ('SPF 首跳\n丙', 'n-drop'),
              ('RIB', 'n-l3'), ('FIB', 'n-l3'), ('业务', 'n-l4')]
    p = []
    for i, (label, cls) in enumerate(labels):
        x = 10 + i * 107
        p.append(box(x, 34, 92, 64, label, cls, 13))
        if i < len(labels) - 1:
            p.append(arrow(f'M {x + 92} 66 H {x + 105}', key))
    p.append(text(380, 136, '红框是三个现场分别卡住的环节；上游正确不保证下游正确', 't-muted', 12))
    return 156, ''.join(p)


DRAW = {
    'topology': topology, 'hello_question': hello_question, 'flood_question': flood_question,
    'halflink_question': halflink_question, 'spf_question': spf_question, 'restart_question': restart_question,
    'timer_answer': timer_answer, 'hello_answer': hello_answer, 'spf_answer': spf_answer,
    'converge_answer': converge_answer, 'restart_answer': restart_answer, 'evidence_answer': evidence_answer,
}


def figure(code, number, rendered_caption, plain_caption):
    key = re.match(r'%% lsr-review:(\w+)', code)[1]
    if SOURCE_SHA.get(key) != hashlib.sha256(code.encode()).hexdigest():
        raise ValueError(f'{key} 源图改变；先核对 SVG 的节点、方向、字段与条件，再更新摘要')
    height, body = DRAW[key](key)
    markers = ''.join(
        f'<marker id="{key}-arrow{suffix}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
        f'<path d="M 0 0 L 10 5 L 0 10 Z" class="mk-{kind}"/></marker>'
        for suffix, kind in (('', 'l3'), ('-muted', 'muted'), ('-drop', 'drop')))
    return (f'<figure class="fig" id="fig-{key}"><div class="fig-body" tabindex="0" role="region" aria-label="配图，可横向滚动">'
            f'<svg viewBox="0 0 760 {height}" role="img" aria-labelledby="{key}-title {key}-desc">'
            f'<title id="{key}-title">{escape(number)}</title>'
            f'<desc id="{key}-desc">{escape(plain_caption)}</desc>'
            f'<defs>{markers}</defs>'
            f'{body}</svg></div><figcaption><b>{escape(number)}</b><span>{rendered_caption}</span></figcaption></figure>')
