"""第 08 讲阅读版配图：与 Markdown 中的 Mermaid 源图按摘要一一绑定；图意以 Markdown 为准。"""

import hashlib
from html import escape
import json
from pathlib import Path

from network_measurement_figures import arrow, box, router, text

SOURCE_SHA = json.loads(Path(__file__).with_name("communication_cost_figure_sources.json").read_text())

# 只补充配图样式；字体、主题变量、正文与打印设置继续复用讲义模板。
FIGURE_CSS = """
.fig-body:focus-visible { outline:2px solid var(--l3); outline-offset:4px; }
@media screen { .fig svg.lec08 { min-width:700px; } }
svg.lec08 text { font-size:13px; }
svg.lec08 .t-mono { font-size:12.5px; }
svg.lec08 .slow { fill:var(--warn-bg); stroke:var(--warn); stroke-width:1.4; }
svg.lec08 .t-warn { fill:var(--warn); }
svg.lec08 .t-drop { fill:var(--drop); }
svg.lec08 .frame { fill:none; stroke:var(--rule-2); stroke-width:1.2; stroke-dasharray:5 4; }
svg.lec08 .life { stroke:var(--rule-2); stroke-width:1.2; stroke-dasharray:3 4; }
svg.lec08 .hotlink { stroke:var(--drop); stroke-width:4; fill:none; }
svg.lec08 .ps { fill:var(--drop-bg); stroke:var(--drop); stroke-width:1.6; }
svg.lec08 .active { fill:var(--l4-bg); stroke:var(--l4); stroke-width:1.4; }
.fig-scroll-hint { display:none; }
@media screen and (max-width:740px) {
  .fig-scroll-hint { display:block; margin:0 0 8px; color:var(--ink-2); font-size:12px; }
}
@media print { .fig svg.lec08 { min-width:0; width:100%; } .fig-scroll-hint { display:none; } }
"""

RACKS = (115, 295, 475, 655)
SPINES = (295, 475)
ALL_WORKERS = {"h1b", "h2a", "h2b", "h3a", "h3b", "h4a", "h4b"}


def _bar(x0, x1, y, label, cls):
    return box(x0, y, x1 - x0, 36, [(label, "")], cls)


def round_(key):
    """1.3 节：一轮的四段，barrier 对齐两个 worker。"""
    p = [text(18, 60, "worker 1", "t-b", "start"), text(18, 120, "worker 2", "t-b", "start"),
         text(18, 180, "PS", "t-b", "start")]
    p += [_bar(130, 230, 42, "计算", "n-host"), _bar(230, 360, 42, "上传", "n-l4"),
          _bar(360, 470, 42, "等待", "slow"), _bar(470, 690, 42, "下载", "n-l4")]
    p += [_bar(130, 350, 102, "计算（更久）", "n-host"), _bar(350, 470, 102, "上传", "n-l4"),
          _bar(470, 690, 102, "下载", "n-l4")]
    p += [_bar(230, 470, 162, "接收梯度，收齐后聚合", "n-host"), _bar(470, 690, 162, "下发模型", "n-l4")]
    p += ['<path d="M 470 30 V 212" class="life"/>', text(470, 22, "barrier：PS 收齐全部梯度并聚合完", "t-sm t-warn")]
    p += [text(690, 232, "一轮结束", "t-sm t-2", "end"),
          text(130, 232, "时间 →（不按比例）", "t-sm t-2", "start")]
    return 244, "".join(p)


def _host_class(name, active, has_ps):
    if has_ps and name == "h1a":
        return "ps"
    return "active" if name in active else "n-host"


def _fabric(y, active=frozenset(), hot_access=False, hot_uplinks=False, has_ps=True):
    """相同的节点位置：上层 2 台 spine，中层 4 台 leaf，下层 8 台 host。"""
    p = []
    spine_y, leaf_y, host_y = y + 22, y + 76, y + 110
    for sx in SPINES:
        for rack, lx in enumerate(RACKS):
            cls = "hotlink" if hot_uplinks else "wire"
            p.append(f'<path d="M {sx} {spine_y} L {lx} {leaf_y}" class="{cls}"/>')
    for sx, name in zip(SPINES, ("r5", "r6")):
        p.append(router(sx, spine_y, name, 28, 16))
    for index, lx in enumerate(RACKS, start=1):
        for side, suffix in ((-41, "a"), (41, "b")):
            hot = hot_access and index == 1 and suffix == "a"
            p.append(f'<path d="M {lx} {leaf_y} L {lx + side} {host_y}" class="{"hotlink" if hot else "wire"}"/>')
        p.append(router(lx, leaf_y, f"r{index}", 28, 16))
        for side, suffix in ((-41, "a"), (41, "b")):
            name = f"h{index}{suffix}"
            label = "h1a PS" if has_ps and name == "h1a" else name
            p.append(box(lx + side - 36, host_y, 72, 30, [(label, "t-mono t-b")], _host_class(name, active, has_ps)))
    return "".join(p)


def _panel(y, height, title, detail):
    return (f'<rect x="8" y="{y}" width="744" height="{height}" rx="6" class="frame"/>'
            + text(20, y + 20, title, "t-b", "start") + text(740, y + 20, detail, "t-sm t-2", "end"))


def ps(key):
    """2.1 节：物理拓扑，PS 模式的瓶颈在 h1a 接入链路。"""
    p = [_fabric(26, ALL_WORKERS, hot_access=True)]
    p += [text(20, 42, "spine", "t-sm t-2", "start"), text(20, 106, "leaf", "t-sm t-2", "start"),
          text(380, 190, "红线：r1 与 h1a 之间的接入链路，每轮上传 N×S 字节、下载 N×S 字节，是共同的瓶颈", "t-sm t-drop"),
          text(380, 210, "host 接入与 leaf–spine 均 100 Mbit/s；紫框：worker，图中没有画出具体的 ECMP 路径", "t-sm t-2")]
    return 224, "".join(p)


def patterns(key):
    """4.1 节：两种通信模式，相同节点位置，瓶颈位置不同。"""
    p = [_panel(8, 186, "参数服务器：所有流量汇向一台 host", "瓶颈在 h1a 接入，7S = 56 Mbit，0.56 s"),
         _fabric(34, ALL_WORKERS, hot_access=True),
         _panel(204, 186, "Shuffle：每台 host 发给其他所有 host", "上联 50 Mbit/s 时瓶颈在机架上联：12s = 96 Mbit，0.96 s"),
         _fabric(230, ALL_WORKERS | {"h1a"}, hot_uplinks=True, has_ps=False)]
    return 400, "".join(p)


def scenes(key):
    """5.1 节：三次实验，节点位置相同，只有 worker 数不同。"""
    cases = (
        ("N=1", {"h3a"}, "每个 worker 算 1400 ms，一轮通信 2×1×S"),
        ("N=3", {"h3a", "h2a", "h4a"}, "每个 worker 算 467 ms，一轮通信 2×3×S"),
        ("N=7", ALL_WORKERS, "每个 worker 算 200 ms，一轮通信 2×7×S"),
    )
    p = []
    for index, (name, active, detail) in enumerate(cases):
        y = 8 + index * 190
        p += [_panel(y, 182, name, detail), _fabric(y + 26, active, hot_access=True)]
    return 582, "".join(p)


DRAW = {"round": round_, "ps": ps, "patterns": patterns, "scenes": scenes}


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
            f'<svg class="lec08" viewBox="0 0 760 {height}" role="img" aria-labelledby="{key}-title {key}-desc" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{key}-title">图 {number}</title><desc id="{key}-desc">{escape(caption_text)}</desc>'
            f'<defs>{markers}</defs>{body}</svg></div>'
            f'<figcaption><b>图 {number}</b><span>{caption_html}</span></figcaption></figure>\n')
