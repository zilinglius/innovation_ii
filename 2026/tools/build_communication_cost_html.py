"""从第 08 讲 Markdown 重建单文件阅读版，并核对代码、配图、链接与外部依赖。

版式复用 link_state_router.html 的公共 CSS、字体、目录与打印行为；页面结构对照 datacenter_network.html
（导读、课堂安排提示、学习目标、本讲路线、时间安排、各模块）。正文以 Markdown 为唯一来源。
"""

import argparse
from collections import Counter
from datetime import date
import hashlib
import html
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from latex2mathml.converter import convert
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from communication_cost_figures import FIGURE_CSS, figure
from reading_common import Page, check_leftovers, check_links, highlight, html_token, upright_greek

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "2026/docs/communication_cost.md"
TEMPLATE = ROOT / "2026/docs/link_state_router.html"
NUMERALS = "一二三四五六七八九"
# 每个模块的语义色（data-layer）与标签：计时与传输模型属于四层，流量形状与瓶颈看三层。
MODULE_TAGS = {
    1: ("", "", "方法 · 同步模型", "同步"),
    2: ("l4", "l4", "L4 · 时间拆账", "拆账"),
    3: ("l4", "l4", "L4 · α-β 模型", "模型"),
    4: ("l3", "l3", "L3 · 流量与瓶颈", "瓶颈"),
    5: ("l3", "l3", "动手 · 预测", "动手"),
    6: ("", "", "课后", "课后"),
}
EXTRA_CSS = """
/* 第 08 讲：长命令块打印时允许分页；导读内不再套引用样式。 */
@media print { .code { break-inside:auto; } .code.short { break-inside:avoid; } }
.module > blockquote { margin: 20px 0; padding-left: 16px; border-left: 2px solid var(--rule-2); color: var(--ink-2); }
/* 英文副标题在窄屏不做两端对齐，避免单词间出现大空隙。 */
.masthead .mast-sub { text-align: left; }
.math-wrap { overflow-x:auto; max-width:100%; }
"""


def markdown():
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    # 显示公式放进可横向滚动的容器，窄屏时不撑开整页。
    md.use(dollarmath_plugin, renderer=lambda text, options: (
        f'<div class="math-wrap">{upright_greek(convert(text, display="block"))}</div>'
        if options["display_mode"] else upright_greek(convert(text, display="inline"))))

    def fence(tokens, idx, options, env):
        token = tokens[idx]
        language = token.info.strip()
        short = " short" if token.content.count("\n") <= 14 else ""
        if language == "bash":
            return (f'<div class="code cmd{short}"><span class="code-tag">bash</span>'
                    f'<pre><code>{highlight(token.content)}</code></pre></div>\n')
        if language == "output":
            return (f'<div class="code out{short}"><span class="code-tag">实测样例</span>'
                    f'<pre><code>{html.escape(token.content)}</code></pre></div>\n')
        raise ValueError(f"未处理的代码类型 {language!r}：先补充对应渲染规则")

    def link_open(tokens, idx, options, env):
        token = tokens[idx]
        href = token.attrGet("href")
        url = urlsplit(href)
        if url.scheme:
            token.attrSet("class", "ext")
        else:
            token.attrSet("class", "xref")
            target = SOURCE.parent / unquote(url.path)
            # 有同名阅读版时链接到 HTML；没有时保留 Markdown 链接。片段锚点在 check() 中逐一核对。
            if target.suffix == ".md" and target.with_suffix(".html").exists():
                token.attrSet("href", href.replace(url.path, url.path[:-3] + ".html", 1))
        return md.renderer.renderToken(tokens, idx, options, env)

    md.renderer.rules["fence"] = fence
    md.renderer.rules["link_open"] = link_open
    md.renderer.rules["table_open"] = lambda *args: (
        '<div class="table-wrap" tabindex="0" role="region" aria-label="表格，可横向滚动"><table>\n')
    md.renderer.rules["table_close"] = lambda *args: "</table></div>\n"
    return md


def prepare(tokens, md, module, figures, subtoc):
    """h3 加编号与锚点；Mermaid 与紧随其后的图注合成一幅可访问 SVG。"""
    out = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token.type == "heading_open" and token.tag == "h3":
            inline = tokens[idx + 1].content
            number, title = re.match(r"^(\d+\.\d+) (.+)$", inline).groups()
            anchor = f"s{number.replace('.', '-')}"
            assert anchor == f"s{module}-{len(subtoc) + 1}", f"小节编号不连续：{number}"
            rendered = md.renderInline(title)
            out.append(html_token(f'<h3 id="{anchor}"><span class="sec-no">{number}</span>{rendered}</h3>\n'))
            subtoc.append(f'<li><a href="#{anchor}">{number}　{rendered}</a></li>')
            idx += 3
            continue
        if token.type == "fence" and token.info.strip() == "mermaid":
            kinds = [t.type for t in tokens[idx + 1:idx + 4]]
            assert kinds == ["paragraph_open", "inline", "paragraph_close"], "配图后缺少图注"
            caption = tokens[idx + 2].content
            match = re.fullmatch(r"\*图示说明：(.+)\*", caption, re.S)
            assert match, "图注应以 *图示说明：…* 书写"
            key = re.search(r"%% lecture08:(\w+)", token.content)[1]
            figures.append(key)
            plain = re.sub(r"[*`]", "", match[1])
            out.append(html_token(figure(key, token.content, len(figures), md.renderInline(match[1]), plain)))
            idx += 4
            continue
        out.append(token)
        idx += 1
    return out


def check(source, output):
    page = Page()
    page.feed(output)
    fences = [t for t in markdown().parse(source) if t.type == "fence"]
    blocks = [t.content for t in fences if t.info.strip() != "mermaid"]
    assert blocks == page.blocks, "命令／输出块与源文不一致"
    mermaid = sum(t.info.strip() == "mermaid" for t in fences)
    assert page.figures == mermaid, f"配图数量 {page.figures} 与源图 {mermaid} 不符"
    numbers = [int(n) for n in re.findall(r"<figcaption><b>图 (\d+)</b>", output)]
    assert numbers == list(range(1, mermaid + 1)), f"图号不连续：{numbers}"
    duplicated = [key for key, count in Counter(page.ids).items() if count > 1]
    assert not duplicated, f"ID 重复：{duplicated}"
    assert not page.resources, f"存在外部资源依赖：{page.resources}"
    assert hashlib.sha256(source.encode()).hexdigest() in output, "源文摘要不匹配"
    check_leftovers(page, output)
    assert not re.search(r"第 ?04 ?讲|链路状态路由器|LECTURE 04|lecture-04", output), "有第 04 讲模板残留"
    check_links(page, SOURCE.parent)
    math = output.count("<math")
    print(f"PASS：{len(blocks)} 个命令／输出块逐字一致；{page.figures} 幅配图；{math} 个 MathML；"
          f"{len(page.links)} 个链接、ID、摘要与外部依赖检查通过。")


def build(updated):
    source = SOURCE.read_text()
    template = TEMPLATE.read_text()
    md = markdown()
    css = re.search(r"<style>(.*?)</style>", template, re.S)[1]
    css = css.replace("云网融合创新实践 · 第 04 讲", "云网融合创新实践 · 第 08 讲")
    css = css.replace('"动手实现一个链路状态路由器"', '"分布式作业的通信代价"')
    css = css.replace("代码讲义的附加样式（第 04 讲起", "代码讲义的附加样式（模板自带")
    css += EXTRA_CSS + FIGURE_CSS
    script = re.search(r"<script>(.*?)</script>", template, re.S)[1]

    title = source.splitlines()[0].removeprefix("# ")
    lecture, topic = re.match(r"^第 (\d+) 讲 (.+)$", title).groups()
    head, subhead = topic.split("：", 1)
    chunks = re.split(r"^## (.+)\n", source, flags=re.M)

    # 导读：引用块进 lead，其余段落进“课堂安排与准备”提示框。
    intro_tokens = md.parse(chunks[0].split("\n", 1)[1].replace("\n---\n", "\n"))
    quote_end = next(i for i, t in enumerate(intro_tokens) if t.type == "blockquote_close")
    lead_inline = intro_tokens[2]
    lead_inline.content = lead_inline.content.removeprefix("**课程导读**：")
    lead_inline.children = md.parseInline(lead_inline.content, {})[0].children
    lead = md.renderer.render(intro_tokens[1:quote_end], md.options, {})
    note = md.renderer.render(intro_tokens[quote_end + 1:], md.options, {})

    sections, toc, hops, figures = [], [], [], []
    goals = schedule = ""
    for idx in range(1, len(chunks), 2):
        heading, body = chunks[idx], chunks[idx + 1].replace("\n---\n", "\n")
        if heading == "学习目标":
            tokens = md.parse(body)
            end = next(i for i, t in enumerate(tokens) if t.type == "ordered_list_close" and t.level == 0)
            goals = md.renderer.render(tokens[:end + 1], md.options, {})
            schedule = md.renderer.render(tokens[end + 1:], md.options, {})
            continue
        number, name = re.match(r"^模块([一二三四五六七八九])：(.+)$", heading).groups()
        module = NUMERALS.index(number) + 1
        layer, tag_class, tag, hop_tag = MODULE_TAGS[module]
        subtoc = []
        tokens = prepare(md.parse(body), md, module, figures, subtoc)
        rendered_name = md.renderInline(name)
        layer_attr = f' data-layer="{layer}"' if layer else ""
        sections.append(
            f'<section class="module" id="m{module}"{layer_attr}><header class="module-head">'
            f'<div class="module-eyebrow"><span class="module-no">模块{number}</span>'
            f'<span class="tag {tag_class}">{tag}</span></div><h2>{rendered_name}</h2></header>\n'
            + md.renderer.render(tokens, md.options, {}) + "</section>\n")
        toc.append(f'<li data-layer="{layer}" data-target="m{module}"><a href="#m{module}">'
                   f'<span class="n">{module:02}</span><span>{rendered_name}</span></a>'
                   f'<ol class="toc-sub">{"".join(subtoc)}</ol></li>')
        hops.append(f'<li><a href="#m{module}"><span class="hop-n">{module}</span><span class="hop-m">模块{number}</span>'
                    f'<span class="hop-t">{rendered_name}</span><span class="tag {tag_class}">{hop_tag}</span></a></li>')

    sha = hashlib.sha256(source.encode()).hexdigest()
    pathstrip = (
        '<svg viewBox="0 0 300 40" role="img" aria-label="多个 worker 的数据都要经过参数服务器的接入链路">'
        '<rect x="2" y="1" width="46" height="10" rx="2" class="n-host"/>'
        '<rect x="2" y="15" width="46" height="10" rx="2" class="n-host"/>'
        '<rect x="2" y="29" width="46" height="10" rx="2" class="n-host"/>'
        '<path d="M 48 6 L 150 20 M 48 20 L 150 20 M 48 34 L 150 20" class="wire"/>'
        '<rect x="150" y="16" width="90" height="8" rx="2" class="n-l4"/>'
        '<rect x="240" y="10" width="56" height="20" rx="3" class="n-l3"/>'
        '</svg>')
    output = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="2026/tools/build_communication_cost_html.py；源文 sha256 {sha}；更新 {updated}">
<title>第{lecture}讲 {html.escape(topic)}</title><style>{css}</style></head><body><div class="layout">
<nav class="toc no-print" aria-label="目录">
<div class="toc-course">云网融合创新实践 · {lecture}<b>{html.escape(head)}</b></div>
<ol class="toc-mods"><li data-target="top"><a href="#top"><span class="n">00</span><span>导读与学习目标</span></a></li>{"".join(toc)}</ol>
<div class="toc-foot"><button type="button" class="btn-print js-print">打印 / 存为 PDF</button><p class="print-hint">版式按 A4 纵向设计，自带页眉与页码；打印对话框里请关掉浏览器自己的“页眉和页脚”。</p></div>
</nav>
<main class="doc" id="top">
<header class="masthead"><div class="mast-eyebrow"><span>上海交通大学 · 云网融合创新实践</span><span class="lec">2026 · LECTURE {lecture} · 讲义</span></div><h1>{html.escape(head)}：<br>{html.escape(subhead)}</h1><p class="mast-sub">The Communication Cost of Distributed Jobs</p><div class="pathstrip">{pathstrip}<div class="legend"><span><i class="k-l4"></i>四层 · 传输时间</span><span><i class="k-l3"></i>三层 · 路径与瓶颈位置</span></div></div><div class="lead"><span class="lead-label">课程导读</span>{lead}</div></header>
<aside class="callout note long"><div class="callout-label">NOTE<span>课堂安排与准备</span></div>{note}</aside>
<section class="plain-sec goals" id="objectives"><h2>学习目标</h2>{goals}</section>
<nav class="hops" aria-label="本讲路线"><p class="hops-cmd">$ traceroute -n <b>lecture-{lecture}</b><br>traceroute to lecture-{lecture} ({html.escape(head)}), {len(hops)} hops max</p><ol>{"".join(hops)}</ol></nav>
<section class="plain-sec" style="margin-top:40px" id="schedule"><h2>课堂时间安排</h2>{schedule}</section>
{"".join(sections)}
<footer class="colophon"><span>上海交通大学 ·《云网融合创新实践》第 {lecture} 讲</span><span>由 <a href="{SOURCE.name}">2026/docs/{SOURCE.name}</a> 生成 · sha256 {sha[:10]} · {updated}</span></footer>
</main></div><script>{script}</script></body></html>
'''
    check(source, output)
    target = SOURCE.with_suffix(".html")
    target.write_text(output)
    print(f"已生成 {target.relative_to(ROOT)}；浏览器显示检查须另行完成。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", required=True, type=date.fromisoformat, help="本次内容更新日期，YYYY-MM-DD")
    build(parser.parse_args().date)
