"""从 Lab 7 指导书 Markdown 重建单文件阅读版，并核对代码、链接与外部依赖。

正文以 Markdown 为唯一来源。本脚本先按“旧版结构”（实验导读、按“一、二、……”分节、目录列出各级小节）拼出整页，
最后交给 reading_theme.restyle() 套上共用主题（2026/tools/reading_theme/），换成新版页面；版式规范见 html_guidelines.md。
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
from reading_theme import restyle
from reading_common import Page, check_leftovers, check_links, highlight, html_token, upright_greek

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "2026/experiments/07/README.md"
NUMERALS = "一二三四五六七八九十"

def markdown():
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    md.use(dollarmath_plugin, renderer=lambda text, options: upright_greek(convert(
        text, display="block" if options["display_mode"] else "inline")))

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
    """各级小节加锚点并收进目录。"""
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
        out.append(token)
        idx += 1
    return out


def check(source, output, figures):
    page = Page()
    page.feed(output)
    fences = [t for t in markdown().parse(source) if t.type == "fence"]
    blocks = [t.content for t in fences]
    assert blocks == page.blocks, "命令／输出块与源文不一致"
    assert page.figures == 0, f"本实验不应有配图：{page.figures}"
    duplicated = [key for key, count in Counter(page.ids).items() if count > 1]
    assert not duplicated, f"ID 重复：{duplicated}"
    assert not page.resources, f"存在外部资源依赖：{page.resources}"
    assert hashlib.sha256(source.encode()).hexdigest() in output, "源文摘要不匹配"
    check_leftovers(page, output)
    assert not re.search(r"masthead|module-head|toc-mods|pathstrip", output), "有旧版结构残留"
    check_links(page, SOURCE.parent)
    print(f"PASS：{len(blocks)} 个命令／输出块逐字一致；{output.count('<math')} 个 MathML；"
          f"{len(page.links)} 个链接、ID、摘要与外部依赖检查通过。")


def build(updated):
    source = SOURCE.read_text()
    md = markdown()
    css, script = "", ""          # 共用样式与脚本由 restyle() 嵌入；这里只带本页配图的专属样式

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
<meta name="generator" content="2026/tools/build_lab7_html.py；源文 sha256 {sha}；更新 {updated}">
<title>Lab {lab} · {html.escape(topic)}</title><style>{css}</style></head><body><div class="layout">
<nav class="toc no-print" aria-label="目录"><div class="toc-course">云网融合创新实践 · LAB {int(lab):02}<b>{html.escape(topic)}</b></div>
<ol class="toc-mods"><li data-target="top"><a href="#top"><span class="n">00</span><span>实验导读</span></a></li>{"".join(toc)}</ol>
<div class="toc-foot"><button class="btn-print js-print" type="button">打印 / 存为 PDF</button><p class="print-hint">版式按 A4 纵向设计，自带页眉与页码；打印对话框里请关掉浏览器自己的“页眉和页脚”。</p></div></nav>
<main class="doc" id="top"><header class="masthead"><div class="mast-eyebrow"><span>上海交通大学 · 云网融合创新实践</span><span class="lec">2026 · LAB {int(lab):02}</span></div><h1>算网协同调度</h1><p class="mast-sub">Compute–Network Co-Scheduling</p><div class="legend"><span><i class="k-l3"></i>三层 · 路径与机架上联</span><span><i class="k-l4"></i>四层 · 吞吐与作业流量</span></div><div class="lead"><span class="lead-label">实验导读</span>{intro}</div></header>
{"".join(sections)}
<footer class="colophon"><span>上海交通大学 · 云网融合创新实践 · Lab {lab}</span><span>由 <a href="README.md">README.md</a> 生成 · sha256 {sha[:12]} · {updated}</span></footer>
</main></div><script>{script}</script></body></html>
'''
    output = restyle(output, "lab07", kind="lab", page_css=css, base=SOURCE.parent)
    check(source, output, figures)
    target = SOURCE.with_suffix(".html")
    target.write_text(output)
    print(f"已生成 {target.relative_to(ROOT)}；浏览器显示检查须另行完成。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", required=True, type=date.fromisoformat, help="本次内容更新日期，YYYY-MM-DD")
    build(parser.parse_args().date)
