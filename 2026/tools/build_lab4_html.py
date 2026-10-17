"""从 Lab 4 指导书 Markdown 重建单文件阅读版，并核对代码、配图、链接与外部依赖。

版式复用 link_state_router.html 的公共 CSS、字体、目录与打印行为；页面结构与 Lab 3 阅读版一致
（实验导读、按“一、二、……”分节、目录列出各级小节）。正文以 Markdown 为唯一来源。
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
from lab4_figures import FIGURE_CSS, figure
from reading_common import Page, check_leftovers, check_links, highlight, html_token

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "2026/experiments/04/README.md"
TEMPLATE = ROOT / "2026/docs/link_state_router.html"
NUMERALS = "一二三四五六七八九十"
FLOW_MARK = "checkup.py ──▶ measure.ping()"
EXTRA_CSS = """
/* Lab 4：长命令块打印时允许分页；导读中的引用块只作为实验信息行显示。 */
@media print { .code { break-inside:auto; } .code.short { break-inside:avoid; } }
.lead blockquote { margin:0 0 14px; padding:0; border:0; color:var(--ink-2); font-size:.94em; }
.lead blockquote p { margin:0; text-align:left; }
.masthead .mast-sub { text-align: left; }
.masthead > .legend { margin: 0 0 36px; }
/* 目录中任务（h4）缩进在“基础／进阶／挑战”之下。 */
.toc-sub li.toc-h4 a { padding-left: 3.35em; font-size: 12px; }
"""


def markdown():
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    md.use(dollarmath_plugin, renderer=lambda text, options: convert(
        text, display="block" if options["display_mode"] else "inline"))

    def fence(tokens, idx, options, env):
        token = tokens[idx]
        language = token.info.strip()
        short = " short" if token.content.count("\n") <= 14 else ""
        if language == "bash":
            return (f'<div class="code cmd{short}"><span class="code-tag">bash</span>'
                    f'<pre><code>{highlight(token.content)}</code></pre></div>\n')
        if language in ("output", ""):
            tag = "实测样例" if language == "output" else "示意"
            return (f'<div class="code out{short}"><span class="code-tag">{tag}</span>'
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
    """各级小节加锚点并收进目录；字符数据流图与紧随其后的图注合成一幅可访问 SVG。"""
    out = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token.type == "heading_open":
            anchor = f"m{module}-s{len(subtoc) + 1}"
            rendered = md.renderInline(tokens[idx + 1].content)
            level = token.tag
            out.append(html_token(f'<{level} id="{anchor}">{rendered}</{level}>\n'))
            cls = ' class="toc-h4"' if level == "h4" else ""
            subtoc.append(f'<li{cls}><a href="#{anchor}">{rendered}</a></li>')
            idx += 3
            continue
        if token.type == "fence" and FLOW_MARK in token.content:
            kinds = [t.type for t in tokens[idx + 1:idx + 4]]
            assert kinds == ["paragraph_open", "inline", "paragraph_close"], "数据流图后缺少图注"
            match = re.fullmatch(r"\*图 (\d+)：(.+)\*", tokens[idx + 2].content, re.S)
            assert match, "图注应写成 *图 N：…*"
            figures.append("dataflow")
            assert int(match[1]) == len(figures), f"图号不连续：{match[1]}"
            plain = re.sub(r"[*`]", "", match[2])
            out.append(html_token(figure("dataflow", token.content, len(figures), md.renderInline(match[2]), plain)))
            idx += 4
            continue
        out.append(token)
        idx += 1
    return out


def check(source, output, figures):
    page = Page()
    page.feed(output)
    fences = [t for t in markdown().parse(source) if t.type == "fence"]
    blocks = [t.content for t in fences if FLOW_MARK not in t.content]
    assert blocks == page.blocks, "命令／输出块与源文不一致"
    assert page.figures == len(figures) == 1, f"配图数量不符：{page.figures}"
    numbers = [int(n) for n in re.findall(r"<figcaption><b>图 (\d+)</b>", output)]
    assert numbers == list(range(1, len(figures) + 1)), f"图号不连续：{numbers}"
    duplicated = [key for key, count in Counter(page.ids).items() if count > 1]
    assert not duplicated, f"ID 重复：{duplicated}"
    assert not page.resources, f"存在外部资源依赖：{page.resources}"
    assert hashlib.sha256(source.encode()).hexdigest() in output, "源文摘要不匹配"
    check_leftovers(page, output)
    assert not re.search(r"第 ?04 ?讲|链路状态路由器|LECTURE 04", output), "有第 04 讲模板残留"
    check_links(page, SOURCE.parent)
    print(f"PASS：{len(blocks)} 个命令／输出块逐字一致；{page.figures} 幅配图；{output.count('<math')} 个 MathML；"
          f"{len(page.links)} 个链接、ID、摘要与外部依赖检查通过。")


def build(updated):
    source = SOURCE.read_text()
    template = TEMPLATE.read_text()
    md = markdown()
    css = re.search(r"<style>(.*?)</style>", template, re.S)[1]
    css = css.replace("云网融合创新实践 · 第 04 讲", "云网融合创新实践 · Lab 4")
    css = css.replace('"动手实现一个链路状态路由器"', '"给网络做体检"')
    css = css.replace("代码讲义的附加样式（第 04 讲起", "代码讲义的附加样式（模板自带")
    css += EXTRA_CSS + FIGURE_CSS
    script = re.search(r"<script>(.*?)</script>", template, re.S)[1]

    title = source.splitlines()[0].removeprefix("# ")
    lab, topic = re.match(r"^Lab (\d+)\s+(.+)$", title).groups()
    chunks = re.split(r"^## (.+)\n", source, flags=re.M)
    intro = md.render(chunks[0].split("\n", 1)[1].replace("\n---\n", "\n"))

    sections, toc, figures = [], [], []
    for idx in range(1, len(chunks), 2):
        heading, body = chunks[idx], chunks[idx + 1].replace("\n---\n", "\n")
        numeral, name = re.match(r"^([一二三四五六七八九十]+)、(.+)$", heading).groups()
        module = NUMERALS.index(numeral) + 1
        subtoc = []
        tokens = prepare(md.parse(body), md, module, figures, subtoc)
        rendered_name = md.renderInline(name)
        sections.append(
            f'<section class="module" id="m{module}"><header class="module-head">'
            f'<div class="module-eyebrow"><span class="module-no">{module:02}</span><span class="tag">LAB {lab}</span></div>'
            f'<h2>{rendered_name}</h2></header>\n' + md.renderer.render(tokens, md.options, {}) + "</section>\n")
        toc.append(f'<li data-target="m{module}"><a href="#m{module}"><span class="n">{module:02}</span>'
                   f'<span>{rendered_name}</span></a><ol class="toc-sub">{"".join(subtoc)}</ol></li>')

    sha = hashlib.sha256(source.encode()).hexdigest()
    output = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="2026/tools/build_lab4_html.py；源文 sha256 {sha}；更新 {updated}">
<title>Lab {lab} · {html.escape(topic)}</title><style>{css}</style></head><body><div class="layout">
<nav class="toc no-print" aria-label="目录"><div class="toc-course">云网融合创新实践 · LAB {int(lab):02}<b>{html.escape(topic)}</b></div>
<ol class="toc-mods"><li data-target="top"><a href="#top"><span class="n">00</span><span>实验导读</span></a></li>{"".join(toc)}</ol>
<div class="toc-foot"><button class="btn-print js-print" type="button">打印 / 存为 PDF</button><p class="print-hint">版式按 A4 纵向设计，自带页眉与页码；打印对话框里请关掉浏览器自己的“页眉和页脚”。</p></div></nav>
<main class="doc" id="top"><header class="masthead"><div class="mast-eyebrow"><span>上海交通大学 · 云网融合创新实践</span><span class="lec">2026 · LAB {int(lab):02}</span></div><h1>给网络<br>做体检</h1><p class="mast-sub">Network Check-up: Profiling Latency &amp; Throughput</p><div class="legend"><span><i class="k-l3"></i>三层 · 往返时间、单向延迟与丢包</span><span><i class="k-l4"></i>四层 · 连接与吞吐</span></div><div class="lead"><span class="lead-label">实验导读</span>{intro}</div></header>
{"".join(sections)}
<footer class="colophon"><span>上海交通大学 · 云网融合创新实践 · Lab {lab}</span><span>由 <a href="README.md">README.md</a> 生成 · sha256 {sha[:12]} · {updated}</span></footer>
</main></div><script>{script}</script></body></html>
'''
    check(source, output, figures)
    target = SOURCE.with_suffix(".html")
    target.write_text(output)
    print(f"已生成 {target.relative_to(ROOT)}；浏览器显示检查须另行完成。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", required=True, type=date.fromisoformat, help="本次内容更新日期，YYYY-MM-DD")
    build(parser.parse_args().date)
