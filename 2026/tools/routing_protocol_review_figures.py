"""第三讲回顾的语义配图；与 Markdown Mermaid 摘要一一绑定。"""

import hashlib
from html import escape
import json
from pathlib import Path
import re

SOURCE_SHA = json.loads(Path(__file__).with_name("routing_protocol_review_figure_sources.json").read_text())
FIGURE_CSS = """
@media screen { .fig svg { min-width:700px; } }
.fig-body:focus-visible { outline:2px solid var(--l3); outline-offset:3px; }
svg .review-label { paint-order:stroke; stroke:var(--bg); stroke-width:5px; stroke-linejoin:round; }
@media print { .fig svg { min-width:0; } }
"""


def text(x, y, lines, cls="", size=14):
    if isinstance(lines, str):
        lines = lines.split("\n")
    return (f'<text x="{x}" y="{y}" text-anchor="middle" class="{cls}" style="font-size:{size}px">'
            + "".join(f'<tspan x="{x}" dy="{0 if i == 0 else 20}">{escape(line)}</tspan>' for i, line in enumerate(lines))
            + '</text>')


def box(x, y, w, h, label, cls="n-host", size=14):
    lines = label.split("\n")
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" class="{cls}"/>'
            + text(x + w / 2, y + h / 2 + 5 - 10 * (len(lines) - 1), lines, size=size))


def router(x, y, label, rx=42, ry=28, size=15):
    lines = label.split("\n")
    return (f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" class="n-l3"/>'
            + text(x, y + 5 - 10 * (len(lines) - 1), lines, "t-b", size))


def line(d, cls="wire"):
    return f'<path d="{d}" class="{cls}"/>'


def arrow(d, key, dashed=False):
    return f'<path d="{d}" class="ar ar-l3 {"dash" if dashed else ""}" marker-end="url(#{key}-arrow)"/>'


def topology(key):
    p = [box(15, 45, 150, 62, "h1a\n10.0.1.11", size=13),
         box(595, 45, 150, 62, "h2a\n10.0.2.11", size=13),
         box(190, 45, 125, 62, "br1\n10.0.1.1", "n-l2", 13),
         box(445, 45, 125, 62, "br2\n10.0.2.1", "n-l2", 13),
         line('M 165 76 H 190 M 570 76 H 595 M 252 107 V 165 M 508 107 V 165'),
         router(252, 195, "r1"), router(508, 195, "r2"), router(380, 337, "r3"),
         line('M 294 195 H 466 M 270 220 L 359 313 M 490 220 L 401 313'),
         text(380, 156, "10.0.12.0/30\nr1=.1 / r2=.2", "t-mono", 12),
         text(170, 275, "10.0.13.0/30\nr1=.1 / r3=.2", "t-mono", 12),
         text(590, 275, "10.0.23.0/30\nr2=.1 / r3=.2", "t-mono", 12),
         text(380, 387, "r3 仅中转；所有接口名沿用 本端-对端", "t-muted", 12)]
    return 408, ''.join(p)


def dv_chain(key):
    p = [box(15, 48, 100, 54, "LAN1"), box(645, 48, 100, 54, "LAN3"),
         box(330, 165, 100, 54, "LAN2"), router(210, 75, "r1"),
         router(380, 75, "r2"), router(550, 75, "r3"),
         line('M 115 75 H 168 M 252 75 H 338 M 422 75 H 508 M 592 75 H 645 M 380 103 V 165'),
         text(295, 62, '1', 't-l3'), text(465, 62, '1', 't-l3'),
         text(150, 144, '直连 LAN 距离为 1', 't-muted', 12),
         text(595, 185, '每轮只用上一轮邻居向量', 't-muted', 12)]
    return 240, ''.join(p)


def dv_loop(key):
    p = [box(50, 12, 240, 50, 'LAN1 · 已断开', 'n-drop'),
         line('M 170 62 V 132', 'wire dash'), text(170, 101, '×', 't-drop', 24),
         router(170, 175, 'r1\nLAN1=16', 122, 42),
         router(570, 175, 'r2\nLAN1=2 via r1', 132, 42),
         arrow('M 570 133 V 93 H 320 V 175 H 295', key),
         text(480, 71, '旧消息：我到 LAN1 是 2', 't-l3', 13),
         arrow('M 170 217 V 270 H 570 V 220', key, True),
         text(375, 257, 'r1 采纳后，将向 r2 宣告多少？', 't-l3', 13)]
    return 296, ''.join(p)


def sequence(key, answered):
    rows = ([('ab', 'Hello · 列表含 r2'), ('ba', 'Hello · 列表含 r1'),
             ('note', '确认双向；点到点邻接继续同步'), ('ab', 'DBD · LSA 摘要'),
             ('ba', 'DBD · LSA 摘要'), ('ba', 'LS Request · 请求缺少或较新的 LSA'),
             ('ab', 'LS Update · 完整 LSA'), ('back', 'LS Ack · 确认'), ('note', '同步完成后 Full')]
            if answered else [('ab', 'Hello · 邻居列表为空'), ('ba', 'Hello · 邻居列表为空'),
                              ('ab', 'Hello · 邻居列表含 2.2.2.2'), ('note', '下一阶段还需完成什么？')])
    h = 95 + len(rows) * 49
    p = [box(93, 12, 174, 44, 'r1 · 1.1.1.1' if not answered else 'r1', 'n-l3'),
         box(493, 12, 174, 44, 'r2 · 2.2.2.2' if not answered else 'r2', 'n-l3'),
         line(f'M 180 56 V {h-20} M 580 56 V {h-20}', 'life off')]
    for i, (direction, label) in enumerate(rows):
        y = 98 + i * 49
        if direction == 'note':
            p.append(box(95, y - 22, 570, 34, label, 'zone', 13))
        else:
            p.append(arrow(f'M {180 if direction == "ab" else 580} {y} H {578 if direction == "ab" else 182}', key, direction == 'back'))
            p.append(text(380, y-10, label, 't-l3 review-label', 13))
    return h, ''.join(p)


def flood_question(key):
    p = [router(140, 65, 'r1'), router(620, 65, 'r2'), router(380, 265, 'r3'),
         arrow('M 182 65 H 578', key), text(380, 48, 'LSA K · 版本 v', 't-l3'),
         arrow('M 164 90 L 352 243', key), arrow('M 596 90 L 408 243', key),
         text(190, 168, '同一版本 · 先到', 't-l3 review-label', 13),
         text(574, 168, '同一版本 · 后到', 't-l3 review-label', 13),
         text(380, 322, 'r3 是否还需要把第二份再次扩散？', 't-b', 14)]
    return 345, ''.join(p)


def costs(key, answered):
    p = []
    for offset, changed in [(0, False), (260, True)]:
        title = ('两端直连接口 cost=20' if changed else '基线：互联出接口 cost=10')
        p.append(box(12, 8+offset, 736, 246, '', 'zone'))
        p.append(text(380, 34+offset, title, 't-b', 15))
        for x, y, label in [(140, 100, 'r1'), (450, 100, 'r2'), (295, 196, 'r3')]:
            p.append(router(x, y+offset, label, 36, 24))
        p.append(box(605, 76+offset, 120, 48, 'LAN2'))
        paths = [(f'M 176 {100+offset} H 414', False),
                 (f'M 164 {119+offset} L 265 {177+offset}', not changed),
                 (f'M 325 {177+offset} L 426 {119+offset}', not changed),
                 (f'M 486 {100+offset} H 603', False)]
        for d, unselected in paths:
            p.append(arrow(d, key, unselected) if answered else line(d))
        p += [text(295, 87+offset, '20' if changed else '10', 't-l3'),
              text(184, 157+offset, '10', 't-l3 review-label'),
              text(406, 157+offset, '10', 't-l3 review-label'),
              text(546, 87+offset, '10', 't-l3')]
        if answered:
            p.append(text(570, 182+offset, '直达 30 = 绕行 30\n两个等价首跳' if changed else '直达 20 < 绕行 30\n只选 r2 为首跳', 't-b', 14))
        else:
            p.append(text(565, 190+offset, '请计算到 LAN2 的总 cost', 't-muted', 12))
    return 522, ''.join(p)


def planes_question(key):
    labels = ['ospfd\n协议计算', '____\n汇总与选优', '内核 FIB', '转发业务包']
    p = []
    for i, label in enumerate(labels):
        x = 12+i*192
        p.append(box(x, 62, 155, 66, label, 'n-l3' if i in (0, 2) else 'n-host'))
        if i < 3:
            p.append(arrow(f'M {x+155} 95 H {x+188}', key))
    p.append(text(380, 34, '____ · 内核接口', 't-l3', 13))
    return 160, ''.join(p)


def faults(key):
    p = []
    for offset, title, subtitle in [(0, 'A · 接口 down', '内核产生链路事件'),
                                     (215, 'B · 静默故障', '载波仍在；INPUT / FORWARD 丢弃')]:
        p.append(box(12, 8+offset, 736, 201, '', 'zone'))
        p += [text(172, 35+offset, title, 't-b', 15), text(488, 35+offset, subtitle, 't-muted', 13),
              router(180, 91+offset, 'r1'), router(580, 91+offset, 'r2'), router(380, 172+offset, 'r3'),
              line(f'M 222 {91+offset} H 367 M 393 {91+offset} H 538', 'wire dash'),
              text(380, 77+offset, 'r1–r2 不可用', 't-drop', 14),
              line(f'M 210 {112+offset} L 345 {158+offset} M 415 {158+offset} L 550 {112+offset}'),
              text(380, 99+offset, '×', 't-drop', 22),
              text(180, 178+offset, '备用链路可用', 't-muted', 12), text(580, 178+offset, '备用链路可用', 't-muted', 12)]
    return 430, ''.join(p)


def bgp_question(key):
    p = [box(20, 30, 225, 70, 'AS 65001\n203.0.113.0/24'),
         box(310, 30, 140, 70, 'AS 65002'), box(570, 30, 150, 70, 'AS 65003'),
         arrow('M 245 65 H 307', key), arrow('M 450 65 H 567', key),
         text(277, 48, '65001', 't-l3 review-label', 11),
         text(510, 48, '65002 65001', 't-l3 review-label', 11),
         arrow('M 645 100 V 179 H 132 V 103', key),
         text(380, 165, '65003 65002 65001', 't-l3', 14),
         text(380, 220, '通告回到发起 AS：如何判定是否接受？', 't-b', 14)]
    return 248, ''.join(p)


def planes_answer(key):
    p = [box(30, 25, 195, 62, 'ospfd\n协议与 SPF', 'n-l3'),
         box(283, 25, 195, 62, 'zebra\nRIB 选优'),
         box(545, 25, 185, 62, '内核 FIB', 'n-l3'),
         arrow('M 225 56 H 280', key), arrow('M 478 56 H 542', key),
         text(510, 111, 'netlink 安装', 't-l3', 12),
         box(30, 174, 195, 62, '业务 IP 包'),
         box(500, 174, 230, 62, '内核查表并转发', 'n-l3'),
         arrow('M 225 205 H 497', key), arrow('M 638 87 V 171', key, True),
         text(690, 140, '供查询', 't-l3', 12),
         text(335, 191, '数据平面', 't-muted', 13)]
    return 263, ''.join(p)


def dv_rounds(key):
    labels = ['第 0 轮 · r3\nLAN3=1', '第 1 轮 · r2\nLAN3=2', '第 2 轮 · r1\nLAN3=3']
    p = []
    for i, label in enumerate(labels):
        x = 20+i*265
        p.append(box(x, 44, 190, 76, label, 'n-l3'))
        if i < 2:
            p.append(arrow(f'M {x+190} 82 H {x+262}', key))
            p.append(text(x+227,  60, '加 1', 't-l3', 13))
    return 153, ''.join(p)


def poison_answer(key):
    p = [router(170, 148, 'r1\nLAN1 的来源', 126, 42),
         router(585, 148, 'r2\nLAN1=2 via r1', 138, 42),
         arrow('M 170 106 V 45 H 585 V 103', key), text(380, 31, '原始通告：LAN1=1', 't-l3'),
         arrow('M 447 148 H 299', key, True), text(370, 135, '省略 LAN1', 't-l3', 12),
         text(380, 180, '水平分割', 't-muted', 12),
         arrow('M 585 190 V 244 H 170 V 193', key, True), text(380, 230, '毒性逆转：LAN1=16', 't-l3')]
    return 277, ''.join(p)


def flood_answer(key):
    p = [box(160, 15, 440, 56, '接收合法 LSA · 识别身份并比较版本', 'n-l3')]
    branches = [(15, '本地没有／收到更新版本', '装入 LSDB\n按规则泛洪\n安排 SPF'),
                (270, '与本地版本相同', '不重复扩散\n按规则处理确认'),
                (525, '收到较旧版本', '按规则用本地\n较新副本纠正对方')]
    for x, state, action in branches:
        center = x+110
        p += [arrow(f'M 380 71 V 96 H {center} V 122', key),
              box(x, 125, 220, 52, state, 'n-host', 13),
              arrow(f'M {center} 177 V 217', key),
              box(x, 220, 220, 94, action, 'n-l3', 14)]
    return 340, ''.join(p)


def metrics_answer(key):
    p = []
    for offset, label, value, paths in [(0, '基线', '110 / 20', '一个下一跳'), (120, '改 cost 后', '110 / 30', '两个下一跳')]:
        p += [text(82, 72+offset, label, 't-b', 14),
              box(160, 28+offset, 210,  70, 'RIB\n'+value, 'n-l3'),
              arrow(f'M 370 {63+offset} H 449', key),
              box(452, 28+offset, 280, 70, 'FIB · metric 20\n'+paths)]
    p += [text(265, 265, '管理距离 / 协议 cost', 't-muted', 13), text(590, 265, '内核 metric 的含义不同', 't-muted', 13)]
    return 289, ''.join(p)


def hash_answer(key):
    p = [box(12, 83, 214, 75, '连接的源/目的\n地址与端口', 'n-l4'),
         box(292, 83, 166, 75, '策略 1\n哈希选择', 'n-l3'),
         box(540, 20, 207, 70, 'via 10.0.12.2\nr1-r2', 'n-l3'),
         box(540, 178, 207, 70, 'via 10.0.13.2\nr1-r3', 'n-l3'),
         arrow('M 226 121 H 289', key), arrow('M 458 121 H 498 V 55 H 537', key),
         arrow('M 458 121 H 498 V 213 H 537', key),
         text(646, 112, '候选 A', 't-l3', 13), text(646, 163, '候选 B', 't-l3', 13),
         text(287, 219, '选一个；可能碰撞，不保证小样本均分', 't-muted', 12)]
    return 280, ''.join(p)


def timer_answer(key):
    p = [box(15, 30, 185, 68, '最后有效 Hello\ntH', 'n-l3'),
         box(287, 30, 185, 68, '故障发生\ntF', 'n-drop'),
         box(558, 30, 187, 68, 'Dead 到期\ntH + 40', 'n-l3'),
         arrow('M 200 64 H 284', key), arrow('M 472 64 H 555', key),
         text(243, 19, '已过去 δ 秒', 't-l3', 12), text(516, 19, '约 40−δ 秒', 't-l3', 12),
         arrow('M 652 98 V 164 H 541', key),
         box(200, 136, 340, 70, '传播 / SPF / 安装\n业务恢复', 'n-host'),
         text(380, 245, '故障不会重置 Dead；后续处理也需要时间', 't-muted', 13)]
    return 271, ''.join(p)


def bgp_answer(key):
    p = [box(15, 28, 285, 75, '甲 · LOCAL_PREF 200\nAS_PATH 长度 3', 'n-l3'),
         box(15, 171, 285, 75, '乙 · LOCAL_PREF 100\nAS_PATH 长度 1'),
         box(373, 97, 165, 75, '先比较\n本 AS 偏好'),
         box(591, 97, 155, 75, '选择甲\n不再比路径长短', 'n-l3', 13),
         arrow('M 300 65 H 334 V 122 H 370', key), arrow('M 300 208 H 334 V 148 H 370', key),
         arrow('M 538 135 H 588', key)]
    return 272, ''.join(p)


def evidence_answer(key):
    labels = ['邻接\n能交换吗', 'LSDB\n地图对吗', 'RIB\n选中了吗', 'FIB\n安装了吗', '业务\n真走通了吗']
    p = []
    for i, label in enumerate(labels):
        x = 12+i*150
        p.append(box(x, 30, 132,  70, label, 'n-l3' if i < 4 else 'n-l4', 13))
        if i < 4:
            p.append(arrow(f'M {x+132} 65 H {x+148}', key))
    p.append(text(380, 142, '每一层都要有自己的成功证据', 't-muted', 14))
    return 169, ''.join(p)


DRAW = {
    'topology': topology, 'dv_chain': dv_chain, 'dv_loop': dv_loop,
    'hello_question': lambda key: sequence(key, False), 'flood_question': flood_question,
    'cost_question': lambda key: costs(key, False), 'planes_question': planes_question,
    'fault_question': faults, 'bgp_question': bgp_question,
    'planes_answer': planes_answer, 'dv_rounds': dv_rounds, 'poison_answer': poison_answer,
    'hello_answer': lambda key: sequence(key, True), 'flood_answer': flood_answer,
    'cost_answer': lambda key: costs(key, True), 'metrics_answer': metrics_answer,
    'hash_answer': hash_answer, 'timer_answer': timer_answer, 'bgp_answer': bgp_answer,
    'evidence_answer': evidence_answer,
}


def figure(code, caption, rendered_caption):
    key = re.match(r'%% routing-review:(\w+)', code)[1]
    if SOURCE_SHA.get(key) != hashlib.sha256(code.encode()).hexdigest():
        raise ValueError(f'{key} 源图改变；先核对 SVG 的节点、方向、字段与条件，再更新摘要')
    height, body = DRAW[key](key)
    return (f'<figure class="fig" id="fig-{key}"><div class="fig-body" tabindex="0" role="region" aria-label="配图，可横向滚动">'
            f'<svg viewBox="0 0 760 {height}" role="img" aria-labelledby="{key}-title {key}-desc">'
            f'<title id="{key}-title">{escape(caption.split("：", 1)[0])}</title>'
            f'<desc id="{key}-desc">{escape(caption)}</desc>'
            f'<defs><marker id="{key}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 Z" class="mk-l3"/></marker></defs>'
            f'{body}</svg></div><figcaption>{rendered_caption}</figcaption></figure>')
