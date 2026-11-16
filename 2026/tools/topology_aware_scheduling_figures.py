"""第 10 讲阅读版的三幅配图：两种放置、共享上联的两种情况、一次放置的决策过程。"""

import hashlib
from html import escape
import json
from pathlib import Path

from communication_cost_figures import RACKS, SPINES
from network_measurement_figures import arrow, box, router, text

SOURCE_SHA = json.loads(Path(__file__).with_name("topology_aware_scheduling_figure_sources.json").read_text())

# 只补充配图样式；字体、主题变量、正文与打印设置来自共用主题。类名避开主题已有的名字。
FIGURE_CSS = """
.fig-body:focus-visible { outline:2px solid var(--l3); outline-offset:4px; }
@media screen { .fig svg.lec10 { min-width:700px; } }
svg.lec10 text { font-size:13px; }
svg.lec10 .t-mono { font-size:12.5px; }
svg.lec10 .t-warn { fill:var(--warn); }
svg.lec10 .t-l4c { fill:var(--l4); }
svg.lec10 .pane { fill:none; stroke:var(--rule-2); stroke-width:1.2; stroke-dasharray:5 4; }
svg.lec10 .slowlink { stroke:var(--warn); stroke-width:4.5; fill:none; }
svg.lec10 .psbox { fill:var(--drop-bg); stroke:var(--drop); stroke-width:1.6; }
svg.lec10 .worker { fill:var(--l4-bg); stroke:var(--l4); stroke-width:1.4; }
svg.lec10 .unused { fill:var(--bg); stroke:var(--rule-2); stroke-width:1.2; stroke-dasharray:4 3; }
svg.lec10 .flow { fill:none; stroke:var(--l4); stroke-width:2.6; }
svg.lec10 .loop { fill:none; stroke:var(--ink-3); stroke-width:1.5; stroke-dasharray:6 4; }
.fig-scroll-hint { display:none; }
@media screen and (max-width:740px) {
  .fig-scroll-hint { display:block; margin:0 0 8px; color:var(--ink-2); font-size:12px; }
}
@media print { .fig svg.lec10 { min-width:0; width:100%; } .fig-scroll-hint { display:none; } }
"""


def _pane(x, y, width, height, title, detail=""):
    out = (f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="6" class="pane"/>'
           + text(x + 12, y + 21, title, "t-b", "start"))
    if detail:
        out += text(x + width - 12, y + 21, detail, "t-sm t-2", "end")
    return out


def _fabric(y, ps, workers, slow_rack):
    """与第 08、09 讲相同的节点位置：2 台 spine、4 台 leaf、8 台 host；slow_rack 的上联画成琥珀色粗线。"""
    p = []
    spine_y, leaf_y, host_y = y + 52, y + 106, y + 140
    for sx in SPINES:
        for rack, lx in enumerate(RACKS, start=1):
            cls = "slowlink" if rack == slow_rack else "wire"
            p.append(f'<path d="M {sx} {spine_y} L {lx} {leaf_y}" class="{cls}"/>')
    for sx, name in zip(SPINES, ("r5", "r6")):
        p.append(router(sx, spine_y, name, 28, 16))
    for rack, lx in enumerate(RACKS, start=1):
        for side in (-41, 41):
            p.append(f'<path d="M {lx} {leaf_y} L {lx + side} {host_y}" class="wire"/>')
        p.append(router(lx, leaf_y, f"r{rack}", 28, 16))
        for side, suffix in ((-41, "a"), (41, "b")):
            name = f"h{rack}{suffix}"
            cls = "psbox" if name == ps else "worker" if name in workers else "unused"
            label = f"{name} PS" if name == ps else name
            style = "t-mono t-b" if cls != "unused" else "t-mono t-muted"
            p.append(box(lx + side - 36, host_y, 72, 30, [(label, style)], cls))
    return p


def placements(key):
    """1.3 节：场景 rack2-slow 下的两种放置，节点位置相同，只有一台 worker 不同。"""
    p = [_pane(8, 8, 744, 184, "放置甲：worker 是 h1b、h3a、h3b、h4a", "4 个 worker 都不经过机架 2 的上联")]
    p += _fabric(8, "h1a", {"h1b", "h3a", "h3b", "h4a"}, 2)
    p += [_pane(8, 204, 744, 184, "放置乙：h3b 换成 h2a", "h2a 的上传和下发都要经过机架 2 的一条上联")]
    p += _fabric(204, "h1a", {"h1b", "h2a", "h3a", "h4a"}, 2)
    p += [text(380, 410, "琥珀色粗线：机架 2 的两条上联，两个方向都限速 10 Mbit/s；其余链路 100 Mbit/s", "t-sm t-2"),
          text(380, 428, "红框：参数服务器；紫框：worker；虚线框：这次作业没有用到的主机", "t-sm t-2")]
    return 440, "".join(p)


def _uplinks(ox, key, collide):
    """机架 2 的两台 host、leaf r2 与两台 spine；collide 为真时两条流都走 r5。"""
    hosts = {"h2a": 62, "h2b": 150}
    leaf = (ox + 178, 121)
    spines = {"r5": (ox + 292, 66), "r6": (ox + 292, 176)}
    p = []
    for name, hy in hosts.items():
        p.append(f'<path d="M {ox + 92} {hy + 15} L {leaf[0]} {leaf[1]}" class="wire"/>')
    for sx, sy in spines.values():
        p.append(f'<path d="M {leaf[0]} {leaf[1]} L {sx} {sy}" class="slowlink"/>')
    # 两条流：沿 host → r2 → spine 画，彼此错开几个单位，箭头指向机架外
    routes = (("h2a", "r5", -5), ("h2b", "r5" if collide else "r6", 5))
    for name, spine, shift in routes:
        hy = hosts[name] + 15
        sx, sy = spines[spine]
        p.append(arrow(f"M {ox + 92} {hy + shift} L {leaf[0]} {leaf[1] + shift} L {sx} {sy + shift} L {ox + 352} {sy + shift}",
                       key, "flow", "l4"))
    for name, hy in hosts.items():
        p.append(box(ox + 20, hy, 72, 30, [(name, "t-mono t-b")], "worker"))
    p.append(router(*leaf, "r2", 28, 16))
    for name, (sx, sy) in spines.items():
        p.append(router(sx, sy, name, 28, 16))
    p.append(text(ox + 214, 76, "10 Mbit/s", "t-sm t-warn"))
    p.append(text(ox + 214, 178, "10 Mbit/s", "t-sm t-warn"))
    return p


def collision(key):
    """3.4 节：机架 2 的两个 worker 向机架外上传时的两种情况。"""
    p = [_pane(8, 8, 366, 236, "不撞：各走一条上联")]
    p += _uplinks(8, key, False)
    p += [text(366, 46, "9.4", "t-mono t-l4c", "end"), text(366, 160, "9.4", "t-mono t-l4c", "end"),
          text(191, 226, "每条流约 9.4 Mbit/s，1 MB 用 0.85 秒", "t-sm t-2")]
    p += [_pane(386, 8, 366, 236, "撞车：挤在同一条上联")]
    p += _uplinks(386, key, True)
    p += [text(744, 42, "4.7 + 4.7", "t-mono t-l4c", "end"), text(744, 180, "空闲", "t-sm t-muted", "end"),
          text(569, 226, "两条流平分约 9.4 Mbit/s，2 MB 传完要 1.70 秒", "t-sm t-2")]
    p += [text(380, 266, "紫色箭头：两条上传的流，去往 r1 下面的 h1a；琥珀色粗线：限速 10 Mbit/s 的上联；流上的数字是应用层吞吐，单位 Mbit/s",
               "t-sm t-2")]
    return 278, "".join(p)


def pipeline(key):
    """4.1 节：一次放置的决策过程。"""
    p = [box(20, 26, 176, 52, [("作业", "t-b"), ("1 个 PS、4 个 worker", "t-sm t-2")]),
         box(20, 122, 176, 52, [("候选放置", "t-b"), ("8 台主机共 280 种", "t-sm t-2")]),
         box(236, 26, 176, 52, [("信息", "t-b"), ("拓扑标签、画像", "t-sm t-2")], "n-l2"),
         box(236, 122, 176, 52, [("代价模型", "t-b"), ("预测每个候选的 JCT", "t-sm t-2")], "n-l3"),
         box(452, 122, 132, 52, [("选预测值", "t-b"), ("最小的放置", "t-b")]),
         box(620, 122, 120, 52, [("运行", "t-b"), ("得到实测 JCT", "t-sm t-2")]),
         box(620, 26, 120, 52, [("对账", "t-b"), ("预测准不准", "t-sm t-2")]),
         arrow("M 108 78 L 108 120", key), arrow("M 196 148 L 234 148", key), arrow("M 324 78 L 324 120", key),
         arrow("M 412 148 L 450 148", key), arrow("M 584 148 L 618 148", key), arrow("M 680 122 L 680 80", key),
         f'<path d="M 620 52 L 414 52" class="loop" marker-end="url(#{key}-ink)"/>',
         text(516, 44, "偏差大时补充信息或修改模型", "t-sm t-2"),
         text(380, 200, "只按规则放置的调度器没有“代价模型”这一步，直接从候选里按规则取一个", "t-sm t-2")]
    return 212, "".join(p)


DRAW = {"placements": placements, "collision": collision, "pipeline": pipeline}


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
            f'<svg class="lec10" viewBox="0 0 760 {height}" role="img" aria-labelledby="{key}-title {key}-desc" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{key}-title">图 {number}</title><desc id="{key}-desc">{escape(caption_text)}</desc>'
            f'<defs>{markers}</defs>{body}</svg></div>'
            f'<figcaption><b>图 {number}</b><span>{caption_html}</span></figcaption></figure>\n')
