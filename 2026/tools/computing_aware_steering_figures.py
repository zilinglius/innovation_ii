"""第 11 讲阅读版的三幅配图：一个请求的四段时间、两张画像合在一起、CATS 框架示意。"""

import hashlib
from html import escape
import json
from pathlib import Path

from network_measurement_figures import arrow, box, text

SOURCE_SHA = json.loads(Path(__file__).with_name("computing_aware_steering_figure_sources.json").read_text())

# 只补充配图样式；字体、主题变量、正文与打印设置来自共用主题。类名避开主题已有的名字。
FIGURE_CSS = """
.fig-body:focus-visible { outline:2px solid var(--l3); outline-offset:4px; }
@media screen { .fig svg.lec11 { min-width:700px; } }
svg.lec11 text { font-size:13px; }
svg.lec11 .t-mono { font-size:12.5px; }
svg.lec11 .t-warn { fill:var(--warn); }
svg.lec11 .waitseg { fill:var(--warn-bg); stroke:var(--warn); stroke-width:1.4; }
svg.lec11 .mark { stroke:var(--ink-2); stroke-width:1.4; }
svg.lec11 .path-a { fill:none; stroke:var(--l3); stroke-width:7; }
svg.lec11 .path-b { fill:none; stroke:var(--l3); stroke-width:3.5; }
svg.lec11 .path-c { fill:none; stroke:var(--l3); stroke-width:1.6; }
svg.lec11 .cpu-all { fill:var(--bg); stroke:var(--ink-3); stroke-width:1; }
svg.lec11 .cpu-own { fill:var(--l4); stroke:none; }
svg.lec11 .feed { fill:none; stroke:var(--ink-3); stroke-width:1.5; stroke-dasharray:6 4; }
.fig-scroll-hint { display:none; }
@media screen and (max-width:740px) {
  .fig-scroll-hint { display:block; margin:0 0 8px; color:var(--ink-2); font-size:12px; }
}
@media print { .fig svg.lec11 { min-width:0; width:100%; } .fig-scroll-hint { display:none; } }
"""


def stages(key):
    """1.1 节：一个请求的四段时间，长度不按比例。"""
    y = 62
    segments = ((40, 250, "n-l3", "传输", "上传输入，取决于网络"), (250, 430, "waitseg", "排队", "等前面的请求算完"),
                (430, 650, "n-l4", "计算", "取决于实例的算力"), (650, 720, "n-host", "返回", ""))
    p = []
    for x0, x1, cls, name, note in segments:
        p.append(f'<rect x="{x0}" y="{y}" width="{x1 - x0}" height="40" class="{cls}"/>')
        p.append(text((x0 + x1) / 2, y + 25, name, "t-b"))
        if note:
            p.append(text((x0 + x1) / 2, y + 60, note, "t-sm t-2"))
    marks = ((40, "客户端发出请求", 30, "start"), (250, "实例收齐输入", 48, "middle"), (430, "开始计算", 30, "middle"),
             (650, "算完", 48, "middle"), (720, "客户端收到结果", 30, "end"))
    for x, label, ty, anchor in marks:
        p.append(f'<path d="M {x} {ty + 6} L {x} {y + 40}" class="mark"/>')
        p.append(text(x, ty, label, "t-sm", anchor))
    p.append(text(685, y + 60, "结果很小", "t-sm t-2"))
    p.append(text(380, 150, "四段首尾相接，加起来是这个请求的完成时间；图中各段的长度不按比例", "t-sm t-2"))
    return 162, "".join(p)


def instances(key):
    """2.3 节：客户端到三个实例的吞吐（线的粗细）与各实例的算力（紫色条的长度）。"""
    rows = (("h1b", "同机架", "95.7 Mbit/s", 0.152, "path-a", 34), ("h3a", "机架 3", "28.2 Mbit/s", 0.307, "path-b", 104),
            ("h4a", "机架 4", "9.4 Mbit/s", 0.634, "path-c", 174))
    p = [box(24, 100, 120, 48, [("客户端", "t-b"), ("h1a", "t-mono")])]
    for name, where, mbps, rate, cls, y in rows:
        p.append(f'<path d="M 144 124 L 470 {y + 26}" class="{cls}"/>')
        p.append(text(330, {34: 68, 104: 116, 174: 194}[y], mbps, "t-mono t-l3"))
        p.append(box(470, y, 266, 52, [], "n-host"))
        p.append(text(484, y + 21, f"{name}（{where}）", "t-b", "start"))
        p.append(text(484, y + 41, f"rate {rate:.3f}", "t-mono", "start"))
        p.append(f'<rect x="590" y="{y + 30}" width="130" height="12" class="cpu-all"/>')
        p.append(f'<rect x="590" y="{y + 30}" width="{130 * rate:.1f}" height="12" class="cpu-own"/>')
    p.append(text(380, 252, "蓝线越粗，客户端到这个实例的吞吐越大；紫色条越长，这个实例分到的 CPU 越多（整条是一个不受限的核）", "t-sm t-2"))
    return 264, "".join(p)


def cats(key):
    """4.2 节：RFC 10053 的 CATS 框架，教学用的简化。"""
    p = [box(20, 132, 96, 48, [("客户端", "t-b")]),
         box(150, 132, 176, 48, [("入口 CATS-Forwarder", "t-b"), ("含 C-TC：识别服务流量", "t-sm t-2")]),
         box(396, 132, 150, 48, [("出口 CATS-Forwarder", "t-b")]),
         box(610, 132, 130, 48, [("服务联系实例", "t-b")]),
         box(150, 30, 176, 48, [("C-PS", "t-b t-l3"), ("选出口与实例", "t-sm t-2")], "n-l3"),
         box(396, 30, 150, 48, [("C-NMA", "t-b t-l2"), ("收集网络状态", "t-sm t-2")], "n-l2"),
         box(610, 30, 130, 48, [("C-SMA", "t-b t-l4"), ("收集算力状态", "t-sm t-2")], "n-l4"),
         arrow("M 116 156 L 148 156", key), arrow("M 326 156 L 394 156", key), arrow("M 546 156 L 608 156", key),
         text(361, 148, "底层网络", "t-sm t-2"),
         arrow("M 396 54 L 328 54", key), arrow("M 675 30 L 675 12 L 238 12 L 238 28", key),
         arrow("M 238 78 L 238 130", key), text(246, 108, "选路结果", "t-sm t-2", "start"),
         f'<path d="M 471 132 L 471 80" class="feed" marker-end="url(#{key}-ink)"/>',
         f'<path d="M 675 132 L 675 80" class="feed" marker-end="url(#{key}-ink)"/>',
         text(380, 206, "实线箭头：一条服务请求的通路，以及度量和选路结果的流向；虚线箭头：状态被采集的方向", "t-sm t-2"),
         text(380, 224, "组件可以合在同一台设备上，也可以分开部署；图中省略了多个站点、多个实例", "t-sm t-2")]
    return 236, "".join(p)


DRAW = {"stages": stages, "instances": instances, "cats": cats}


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
            f'<svg class="lec11" viewBox="0 0 760 {height}" role="img" aria-labelledby="{key}-title {key}-desc" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{key}-title">图 {number}</title><desc id="{key}-desc">{escape(caption_text)}</desc>'
            f'<defs>{markers}</defs>{body}</svg></div>'
            f'<figcaption><b>图 {number}</b><span>{caption_html}</span></figcaption></figure>\n')
