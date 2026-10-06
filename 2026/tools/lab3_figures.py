"""Lab 3 教学配图：统一坐标、节点与语义色；图意以 Markdown 为准。"""
from html import escape


# 仅补充配图样式，字体、主题变量、正文与打印设置继续复用讲义模板。
FIGURE_CSS = """
.fig-body { max-width:100%; border-radius:8px; }
.fig-body:focus-visible { outline:2px solid var(--l3); outline-offset:4px; }
.fig .lab-diagram { min-width:700px; }
.lab-diagram text { font-size:13px; }
.lab-diagram .d-title { font-size:16px; font-weight:600; }
.lab-diagram .d-label { font-size:14px; font-weight:600; }
.lab-diagram .d-small { font-size:12px; fill:var(--ink-2); }
.lab-diagram .d-mono { font-family:var(--font-mono); font-size:13px; }
.lab-diagram .d-panel { fill:var(--bg); stroke:var(--rule-2); stroke-width:1; }
.lab-diagram .d-band { fill:var(--l3-bg); }
.lab-diagram .d-rule { stroke:var(--rule); stroke-width:1; }
.lab-diagram .d-link { fill:none; stroke:var(--l3); stroke-width:1.7; }
.lab-diagram .d-candidate { fill:none; stroke:var(--l3-line); stroke-width:2; }
.lab-diagram .d-halo { fill:none; stroke:var(--bg); stroke-width:6; }
.lab-diagram .d-flow { fill:none; stroke:var(--l4); stroke-width:2.6; }
.lab-diagram .d-tenant { fill:none; stroke:var(--l2); stroke-width:2.6; }
.lab-diagram .d-dash { stroke-dasharray:7 5; }
.lab-diagram .d-idle { fill:var(--surface); stroke:var(--rule-2); stroke-width:1.2; stroke-dasharray:4 4; }
.lab-diagram .d-namespace { fill:none; stroke:var(--rule-2); stroke-width:1.2; stroke-dasharray:5 4; }
.fig-scroll-hint { display:none; }
@media screen and (max-width:740px) {
  .fig-scroll-hint { display:block; margin:0 0 8px; color:var(--ink-2); font-size:12px; }
}
@media print {
  .fig .lab-diagram { min-width:0; width:100%; }
  .fig-scroll-hint { display:none; }
}
"""


def text(x, y, value, cls="", anchor="middle"):
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" '
            f'class="{cls}">{escape(value)}</text>')


def rect(x, y, width, height, cls, radius=6):
    return (f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
            f'rx="{radius}" class="{cls}"/>')


def path(d, cls="d-link", marker=None):
    end = f' marker-end="url(#{marker})"' if marker else ""
    return f'<path d="{d}" class="{cls}"{end}/>'


def line(x1, y1, x2, y2, cls="d-link", marker=None):
    return path(f'M{x1},{y1} L{x2},{y2}', cls, marker)


def host(x, y, lines, width=108, idle=False):
    height = 28 + 17 * (len(lines) - 1)
    out = rect(x - width/2, y - height/2, width, height,
               "d-idle" if idle else "n-host")
    first = y + 5 - 8.5 * (len(lines) - 1)
    for i, value in enumerate(lines):
        out += text(x, first + 17*i, value, "d-mono t-b" if i == 0 else "d-small")
    return out


def router(x, y, name, rx=27, ry=20):
    return (f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" class="n-l3"/>'
            + text(x, y+5, name, "d-mono t-b t-l3"))


def panel(top, height, letter, title, note):
    return (rect(8, top+8, 744, height-16, "d-panel", 8)
            + rect(24, top+24, 28, 28, "n-l3", 5)
            + text(38, top+43, letter, "d-label t-l3")
            + text(65, top+44, title, "d-title", "start")
            + text(728, top+43, note, "d-small", "end"))


def wrapper(key, height, title, description, body):
    markers = ""
    for kind in ("l2", "l3", "l4"):
        markers += (f'<marker id="{key}-{kind}" viewBox="0 0 10 10" refX="9" refY="5" '
                    'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
                    f'<path d="M0 0 L10 5 L0 10 Z" class="mk-{kind}"/></marker>')
    return (f'<svg class="lab-diagram" viewBox="0 0 760 {height}" role="img" '
            f'aria-labelledby="{key}-title {key}-desc" xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{key}-title">{escape(title)}</title>'
            f'<desc id="{key}-desc">{escape(description)}</desc>'
            '<defs>'+markers+'</defs>'+body+'</svg>')


def topology():
    """八条独立 fabric 链路；机架区域与 namespace 边界明确分开。"""
    body = text(24, 26, '2 SPINE  /  4 LEAF  /  8 HOST', "d-label", "start")
    body += text(736, 26, '接线图 · 连线交叉处不相连', "d-small", "end")
    centers = (95, 285, 475, 665)
    for i, x in enumerate(centers, 1):
        body += rect(x-83, 224, 166, 282, "zone", 8)
        body += text(x, 408, f'机架 {i}', "d-label")
        body += rect(x-71, 260, 142, 126, "d-namespace")
    # 用不同端点与线型区分两台 spine 的四条独立连接，不画共享总线。
    for spine, sx in ((5, 255), (6, 505)):
        for i, x in enumerate(centers):
            source_x = sx + (i-1.5)*12
            target_x = x + (-12 if spine == 5 else 12)
            d = f'M{source_x},107 C{source_x},163 {target_x},185 {target_x},294'
            body += path(d, "d-halo")
            body += path(d, "d-link" + (" d-dash" if spine == 6 else ""))
    for spine, x in ((5, 255), (6, 505)):
        body += rect(x-66, 52, 132, 70, "d-namespace")
        body += text(x, 69, f'spine namespace r{spine}', "d-small")
        body += router(x, 92, f'r{spine}', rx=35, ry=17)
    for i, x in enumerate(centers, 1):
        body += router(x, 313, f'r{i}', rx=34)
        body += line(x, 333, x, 345, "wire ar-l2")
        body += rect(x-32, 345, 64, 27, "n-l2", 4)
        body += text(x, 364, f'br{i}', "d-mono t-b t-l2")
        for suffix, hx, port in (("a", x-40, x-14), ("b", x+40, x+14)):
            body += path(f'M{port},372 V398 H{hx} V422', "wire ar-l2")
            body += host(hx, 444, [f'h{i}{suffix}', '.11' if suffix == 'a' else '.12'], 70)
        body += text(x, 488, f'10.0.{i}.0/24', "d-mono")
    body += text(24, 539, '上联：8 条点到点链路 · 双向 100 / 50 Mbit/s', "d-small", "start")
    body += text(24, 562, '接入：每台 host 双向固定 100 Mbit/s；host 各有独立 namespace', "d-small", "start")
    body += line(26, 588, 61, 588)
    body += text(69, 592, '连接 r5', "d-small", "start")
    body += line(180, 588, 215, 588, "d-link d-dash")
    body += text(223, 592, '连接 r6', "d-small", "start")
    body += rect(354, 580, 16, 16, "n-l2", 3)
    body += text(380, 592, '机架内 bridge', "d-small", "start")
    body += rect(550, 580, 24, 16, "d-namespace", 2)
    body += text(584, 592, 'namespace 边界', "d-small", "start")
    return wrapper('topology', 612, 'Lab 3 实验床：从 spine 到独立主机',
                   '两台 spine 分别用四条独立链路连接四台 leaf。每个机架的 leaf 与 bridge '
                   '共用一个 namespace，两个 host 各有独立 namespace。实线连接 r5，虚线连接 r6；'
                   '交叉处不相连。主机接入双向固定 100 Mbit/s，上联双向可切换 100 与 50 Mbit/s。', body)


def capacity():
    """按同一组流展开路径；蓝色区域定位唯一改变的链路。"""
    body = ""
    flows = [('h1a', 'r1', 'r5', 'r3', 'h3a'),
             ('h1b', 'r1', 'r6', 'r3', 'h3b'),
             ('h2a', 'r2', 'r5', 'r4', 'h4a'),
             ('h2b', 'r2', 'r6', 'r4', 'h4b')]
    for n, rate in enumerate((100, 50)):
        top = n*300
        body += panel(top, 292, 'AB'[n], f'上联 {rate} Mbit/s', '固定：四条流各 30 MB')
        body += rect(183, top+60, 372, 212, "d-band")
        body += text(94, top+80, '发送端', "d-small")
        body += text(369, top+80, f'FABRIC · 每段 {rate} Mbit/s', "d-label t-l3")
        body += text(666, top+80, '接收端', "d-small")
        for row, names in enumerate(flows):
            y = top+111+row*46
            body += text(29, y+5, f'F{row+1}', "d-small")
            xs = (97, 220, 369, 520, 664)
            for col in range(4):
                left = xs[col] + (45 if col == 0 else 27)
                right = xs[col+1] - (45 if col == 3 else 27)
                body += line(left, y, right, y, marker='capacity-l3')
            body += host(xs[0], y, [names[0]], 90)
            body += host(xs[4], y, [names[4]], 90)
            for col in (1, 2, 3):
                body += router(xs[col], y, names[col], ry=17)
    body += text(380, 622, '不变：接入 100 Mbit/s、发送与接收映射、路径、总量 120 MB', "d-small")
    body += text(380, 645, '改变：全部 leaf–spine 链路两端的容量档位', "d-label t-l3")
    return wrapper('capacity', 664, '容量对照：相同路径，只改变 fabric 容量',
                   '上下两种条件的四行分别为 F1 到 F4，各传 30 MB。h1a 经 r1-r5-r3 到 h3a，'
                   'h1b 经 r1-r6-r3 到 h3b，h2a 经 r2-r5-r4 到 h4a，h2b 经 r2-r6-r4 到 h4b。'
                   '蓝色 fabric 区域由每段 100 改为 50 Mbit/s，接入始终为 100 Mbit/s。'
                   '同名路由器在不同行表示同一设备。', body)


def collision():
    """连接 F1/F2 保持线型；同路的两条轨迹共享同一物理出口。"""
    body = ""
    for n in range(2):
        top = n*302
        mid = top+168
        ys = (top+118, top+224)
        body += panel(top, 294, 'AB'[n], '同路示例' if n == 0 else '分路示例',
                      '固定：两条流各 30 MB；上联 50 Mbit/s')
        for y in ys:
            body += line(247, mid, 353, y, 'd-candidate')
            body += line(407, y, 513, mid, 'd-candidate')
        for flow in range(2):
            y = ys[flow]
            sy = ys[0] if n == 0 else y
            offset = -6 if flow == 0 else 6
            cls = 'd-flow' + (' d-dash' if flow else '')
            # 端点在节点边界，线型在整条路径上保持一致。
            body += line(135, y, 193, mid+offset, cls, 'collision-l4')
            body += line(247, mid+offset, 353, sy+offset, cls, 'collision-l4')
            body += line(407, sy+offset, 513, mid+offset, cls, 'collision-l4')
            body += line(567, mid+offset, 625, y, cls, 'collision-l4')
        for flow in range(2):
            body += host(81, ys[flow], [f'h1{"ab"[flow]}', f'F{flow+1} · 30 MB'])
            body += host(679, ys[flow], [f'h3{"ab"[flow]}', f'接收 F{flow+1}'])
        body += router(220, mid, 'r1') + router(540, mid, 'r3')
        body += router(380, ys[0], 'r5') + router(380, ys[1], 'r6')
        body += text(380, top+81, '共享：F1 + F2 = 60 MB' if n == 0 else 'F1：30 MB', 'd-label t-l4')
        body += text(380, top+266, 'r6 本轮无目标流' if n == 0 else 'F2：30 MB', 'd-small')
    body += line(24, 626, 64, 626, 'd-flow')
    body += text(75, 630, 'F1 · TCP 流', 'd-small', 'start')
    body += line(230, 626, 270, 626, 'd-flow d-dash')
    body += text(281, 630, 'F2 · TCP 流', 'd-small', 'start')
    body += line(460, 626, 500, 626, 'd-candidate')
    body += text(511, 630, '候选路径 · 每条 50 Mbit/s', 'd-small', 'start')
    body += text(380, 658, '两幅图是自然 ECMP 的分类示例；所有 host 接入保持 100 Mbit/s', 'd-small')
    return wrapper('collision', 678, 'ECMP：跟踪两条流，看是否共享同一上联',
                   '上图 F1 与 F2 都经 r5，共享一条 50 Mbit/s 上联，合计 60 MB；'
                   '下图 F1 经 r5、F2 经 r6，各承载 30 MB。节点位置完全相同。'
                   '紫色实线为 F1，紫色虚线为 F2；细蓝线是候选路径。', body)


def tenants():
    """分别画租户逻辑流量与共享 underlay，空闲 B 仍保留在原位。"""
    body = ""
    for n in range(2):
        top = n*330
        mid = top+173
        ys = (top+116, top+240)
        body += panel(top, 322, 'AB'[n], '基线：仅租户 A' if n == 0 else '并发：租户 A + B',
                      '固定：外层 /32 经 r5')
        body += rect(187, top+67, 386, 213, 'd-band')
        body += text(380, top+90, '共享 UNDERLAY · 总量 ' + ('60 MB' if n == 0 else '120 MB'),
                     'd-label t-l3')
        body += line(265, mid, 353, mid, 'd-candidate')
        body += line(407, mid, 495, mid, 'd-candidate')
        for tenant in range(2):
            active = tenant == 0 or n == 1
            y = ys[tenant]
            suffix = 'ab'[tenant]
            body += host(86, y, [f'{"AB"[tenant]} · t1{suffix}', f'VNI {100*(tenant+1)}',
                                  '2 × 30 MB' if active else '空闲'], 128, not active)
            body += host(674, y, [f'{"AB"[tenant]} · t3{suffix}', f'VNI {100*(tenant+1)}',
                                   '接收 60 MB' if active else '空闲'], 128, not active)
            if active:
                offset = -6 if tenant == 0 else 6
                cls = 'd-tenant' + (' d-dash' if tenant else '')
                body += line(150, y, 211, mid+offset, cls, 'tenants-l2')
                body += line(265, mid+offset, 353, mid+offset, cls, 'tenants-l2')
                body += line(407, mid+offset, 495, mid+offset, cls, 'tenants-l2')
                body += line(549, mid+offset, 610, y, cls, 'tenants-l2')
        for x, label in ((238, 'r1'), (380, 'r5'), (522, 'r3')):
            body += router(x, mid, label)
        body += text(309, top+144, '50 Mbit/s', 'd-small')
        body += text(451, top+144, '50 Mbit/s', 'd-small')
        body += text(380, top+246, 'A：60 MB  +  B：' + ('0 MB' if n == 0 else '60 MB'), 'd-label')
        body += text(380, top+304, 'A 的数据量与路径不变；只改变 B 是否同时发送', 'd-small')
    body += line(26, 682, 61, 682, 'd-tenant')
    body += text(73, 686, '租户 A 的两条流', 'd-small', 'start')
    body += line(270, 682, 305, 682, 'd-tenant d-dash')
    body += text(317, 686, '租户 B 的两条流', 'd-small', 'start')
    body += text(380, 715, 'VNI 分离逻辑网络；两组流仍使用同一份上联容量', 'd-label t-l3')
    return wrapper('tenants', 736, '租户隔离与共享带宽：B 加入后什么发生变化',
                   '上下两种条件均将外层路径固定为 r1-r5-r3，出口为 50 Mbit/s。'
                   '基线只有 A 的两条 30 MB 流，B 节点保留但空闲；并发条件下 B 也发送两条 30 MB 流。'
                   'A 使用 VNI 100，B 使用 VNI 200。青绿实线与虚线标记租户逻辑流量，'
                   '并行轨迹不代表独立物理容量。', body)


def figure(key):
    return {'topology': topology, 'capacity': capacity,
            'collision': collision, 'tenants': tenants}[key]()
