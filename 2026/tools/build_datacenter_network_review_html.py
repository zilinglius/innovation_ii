"""从第五讲回顾或参考答案 Markdown 重建阅读版，检查代码、题号、图形与链接。"""

import argparse
from collections import Counter
from datetime import date
import hashlib
import html
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from latex2mathml.converter import convert
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from datacenter_network_review_figures import FIGURE_CSS, figure

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "2026/docs/datacenter_network_review.md"
ANSWERS = ROOT / "2026/docs/datacenter_network_review_answers.md"
TEMPLATE = ROOT / "2026/docs/link_state_router.html"
QUESTIONS = 32
FIGURES = {False: 5, True: 6}
FENCES = {"bash": ("cmd", "BASH"), "text": ("out", "OUTPUT"), "": ("out", "OUTPUT")}


def markdown():
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    md.use(dollarmath_plugin, renderer=lambda text, options: convert(
        text, display="block" if options["display_mode"] else "inline"))

    def fence(tokens, idx, options, env):
        token = tokens[idx]
        if token.info.strip() not in FENCES:
            raise ValueError("新增图形或其他代码类型时，先补充对应渲染规则")
        kind, label = FENCES[token.info.strip()]
        return (f'<div class="code {kind} short"><span class="code-tag">{label}</span>'
                f'<pre><code>{html.escape(token.content)}</code></pre></div>\n')

    md.renderer.rules["fence"] = fence
    md.renderer.rules["table_open"] = lambda *args: '<div class="table-wrap" tabindex="0" role="region" aria-label="表格，可横向滚动"><table>\n'
    md.renderer.rules["table_close"] = lambda *args: '</table></div>\n'
    return md


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links, self.resources, self.blocks = [], [], [], []
        self.in_pre = False
        self.parts = []
        self.svg_count = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if tag == "svg":
            self.svg_count += 1
        if tag in ("script", "img", "iframe", "link"):
            ref = attrs.get("src", attrs.get("href", ""))
            if ref and not ref.startswith("data:"):
                self.resources.append(ref)
        if tag == "pre":
            self.in_pre, self.parts = True, []

    def handle_endtag(self, tag):
        if tag == "pre":
            self.in_pre = False
            self.blocks.append("".join(self.parts))

    def handle_data(self, value):
        if self.in_pre:
            self.parts.append(value)


def check(source, output, source_path, answers):
    page = Page()
    page.feed(output)
    tokens = markdown().parse(source)
    blocks = [t.content for t in tokens if t.type == "fence" and t.info != "mermaid"]
    assert blocks == page.blocks, "命令／输出与源文不一致"
    questions = [int(n) for n in re.findall(r"^(\d+)\. ", source, re.M)]
    expected = [int(n) for n in re.findall(r"^(\d+)\. ●", SOURCE.read_text(), re.M)]
    assert questions == expected == list(range(1, QUESTIONS + 1)), "题号未与题单逐一对应"
    assert all(f"q{n}" in page.ids for n in questions), "缺少题目锚点"
    assert page.svg_count == FIGURES[answers], "配图数量不符"
    captions = [int(n) for n in re.findall(r"^\s*\*图 (\d+)：", source, re.M)]
    assert captions == list(range(1, page.svg_count + 1)), "图号不连续"
    assert not re.search(r"第 0[12346] 讲回顾|REVIEW 0[12346]|Link-State Router|链路状态路由器|```|%% dc-review", output), "有旧模板残留或未转换的源码"
    assert not re.search(r"file://|/Users/|/root/", output), "出现本机绝对路径"
    assert not [key for key, count in Counter(page.ids).items() if count > 1], "ID 重复"
    assert not page.resources, f"存在外部资源依赖：{page.resources}"
    assert hashlib.sha256(source.encode()).hexdigest() in output, "摘要不匹配"
    assert not re.search(r'<span class="math inline"><math[^>]+display="block"', output), "行内公式误排成块级公式"
    for link in page.links:
        url = urlsplit(link)
        if url.scheme:
            assert url.scheme in ("https", "http", "mailto"), f"异常链接：{link}"
            continue
        target = source_path.with_suffix(".html") if not url.path else source_path.parent / unquote(url.path)
        if not url.path:
            assert unquote(url.fragment) in page.ids, f"内部锚点不存在：{link}"
        else:
            assert target.exists(), f"本地链接不存在：{link}"
            if target.suffix == ".html" and url.fragment:
                other = Page()
                other.feed(target.read_text())
                assert unquote(url.fragment) in other.ids, f"跨页锚点不存在：{link}"
    print(f"PASS：{len(questions)} 道题题号连续，{len(blocks)} 个代码／输出块逐字一致，"
          f"{page.svg_count} 幅图图号连续；摘要、ID 与链接通过。")


def prepare_tokens(tokens, md):
    """题号来自列表起号；Mermaid 与紧随图注转换为同一幅可访问 SVG。"""
    idx = 0
    question = None
    while idx < len(tokens):
        token = tokens[idx]
        if token.type == "ordered_list_open" and token.level == 0:
            question = int(token.attrGet("start") or 1)
        elif token.type == "list_item_open" and token.level == 1 and question is not None:
            token.attrSet("id", f"q{question}")
            question += 1
        elif token.type == "fence" and token.info == "mermaid":
            assert [t.type for t in tokens[idx + 1:idx + 4]] == ["paragraph_open", "inline", "paragraph_close"], "配图缺少图注"
            caption = tokens[idx + 2].content.strip("*")
            match = re.match(r"(图 \d+)：(.+)", caption, re.S)
            assert match, "配图图号不符"
            token.content = figure(token.content, match[1], md.renderInline(match[2]), caption)
            token.type, token.info = "html_block", ""
            del tokens[idx + 1:idx + 4]
        elif token.type == "link_open":
            # 同目录有同名阅读版时改链到 .html，保留片段锚点。
            href = urlsplit(token.attrGet("href"))
            if not href.scheme and href.path.endswith(".md"):
                html_target = (SOURCE.parent / unquote(href.path)).with_suffix(".html")
                if html_target.exists():
                    token.attrSet("href", href.path[:-3] + ".html" + (f"#{href.fragment}" if href.fragment else ""))
        if token.children:
            prepare_tokens(token.children, md)
        idx += 1
    return tokens


def build(updated, answers=False):
    source_path = ANSWERS if answers else SOURCE
    source = source_path.read_text()
    template = TEMPLATE.read_text()
    md = markdown()
    title = source.splitlines()[0].removeprefix("# ")
    css = re.search(r"<style>(.*?)</style>", template, re.S)[1]
    css = css.replace('content: "云网融合创新实践 · 第 04 讲"', 'content: "云网融合创新实践 · 第 05 讲回顾"')
    css = css.replace('content: "动手实现一个链路状态路由器"',
                      'content: "数据中心网络' + (' · 参考答案"' if answers else '"'))
    css += """
/* 回顾题单：沿用正文版式，增加题间留白及小屏打印入口。 */
.module > ol > li { margin-bottom: 1em; }
.module > ol { padding-left: 2.6em; }
.masthead h1 { text-wrap:balance; }
blockquote { margin: 20px 0; padding-left: 16px; border-left: 2px solid var(--rule-2); color: var(--ink-2); }
.lead blockquote { margin: 0; border: 0; padding: 0; color: inherit; }
.pathstrip { margin-top: 20px; }
.mobile-print { display: block; margin: 20px 0; }
@media screen and (min-width:1120px) { .mobile-print { display:none; } }
@media print {
  /* 保留模块分页，允许短节接续上一节，避免只有一两题的空白页。 */
  .review #s1, .review #s2, .review #s7, .review #s11 { break-before:auto; margin-top:20pt; }
  .answers .module:not(#s3):not(#s7) { break-before:auto; margin-top:20pt; }
  .answers .module > ol > li > p { break-inside:avoid; }
  .module > ol > li { margin-bottom: .65em; }
}
"""
    css += FIGURE_CSS
    script = re.search(r"<script>(.*?)</script>", template, re.S)[1]
    chunks = re.split(r"^## (.+)\n", source, flags=re.M)
    intro = chunks[0].split("\n", 1)[1].replace("\n---\n", "\n")
    sections = []
    intro_label = "说明" if answers else "课程导读"
    toc = [f'<li data-target="top"><a href="#top"><span class="n">00</span><span>{intro_label}</span></a></li>']
    numeral = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二")
    for idx in range(1, len(chunks), 2):
        section = (idx + 1) // 2
        heading, body = chunks[idx:idx + 2]
        anchor = f"s{section}"
        tokens = prepare_tokens(md.parse(body.replace("\n---\n", "\n")), md)
        subtoc = []
        for pos, token in enumerate(tokens):
            if token.type == "heading_open":
                subanchor = f"{anchor}-{len(subtoc) + 1}"
                token.attrSet("id", subanchor)
                subtoc.append(f'<li><a href="#{subanchor}">{md.renderInline(tokens[pos + 1].content)}</a></li>')
        numbered = re.match(r"^([一二三四五六七八九十]+)、(.+)", heading)
        index = f"{numeral.index(numbered[1]) + 1:02}" if numbered else "·"
        toc_heading = numbered[2] if numbered else heading
        toc.append(f'<li data-target="{anchor}"><a href="#{anchor}"><span class="n">{index}</span>'
                   f'<span>{md.renderInline(toc_heading)}</span></a><ol class="toc-sub">{"".join(subtoc)}</ol></li>')
        section_tag = "参考答案" if answers else "课堂讨论"
        sections.append(f'<section class="module" id="{anchor}"><header class="module-head">'
                        '<div class="module-eyebrow"><span class="module-no">第 05 讲回顾</span>'
                        f'<span class="tag">{section_tag}</span></div>'
                        f'<h2>{md.renderInline(heading)}</h2></header>{md.renderer.render(tokens, md.options, {})}</section>')
    intro_html = md.renderer.render(prepare_tokens(md.parse(intro), md), md.options, {})
    sha = hashlib.sha256(source.encode()).hexdigest()
    page_kind = "answers" if answers else "review"
    page_label = "REVIEW 05 · ANSWERS" if answers else "REVIEW 05"
    subtitle = "Answers: Datacenter Networks" if answers else "Review: Datacenter Networks"
    output = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="2026/tools/build_datacenter_network_review_html.py；源文 sha256 {sha}；更新 {updated}">
<title>{html.escape(title)}</title><style>{css}</style></head><body class="{page_kind}"><div class="layout">
<nav class="toc no-print" aria-label="目录"><div class="toc-course">云网融合创新实践 · {page_label}<b>数据中心网络</b></div><ol class="toc-mods">{"".join(toc)}</ol><div class="toc-foot"><button class="btn-print js-print" type="button">打印 / 存为 PDF</button><p class="print-hint">A4 纵向；请关闭浏览器自己的页眉和页脚。</p></div></nav>
<main class="doc" id="top"><header class="masthead"><div class="mast-eyebrow"><span>上海交通大学 · 云网融合创新实践</span><span class="lec">2026 · {page_label}</span></div><h1>{html.escape(title)}</h1><p class="mast-sub">{subtitle}</p>
<div class="pathstrip"><div class="legend"><span><i class="k-l2"></i>二层 · 机架网桥</span><span><i class="k-l3"></i>三层 · 路由与上联</span><span><i class="k-l4"></i>传输 · 流量与 VXLAN 外层端口</span></div></div>
<div class="lead">{intro_html}</div><div class="mobile-print no-print"><button class="btn-print js-print" type="button">打印 / 存为 PDF</button><p class="print-hint">A4 纵向；请关闭浏览器自己的页眉和页脚。</p></div></header>
{"".join(sections)}
<footer class="colophon"><span>上海交通大学 · 云网融合创新实践 · 第 05 讲回顾</span><span>由 <a href="{source_path.name}">{source_path.name}</a> 生成 · sha256 {sha[:12]} · {updated}</span></footer>
</main></div><script>{script}</script></body></html>'''
    check(source, output, source_path, answers)
    source_path.with_suffix(".html").write_text(output)
    print(f"已生成 {source_path.with_suffix('.html').relative_to(ROOT)}；显示检查须另行完成。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, type=date.fromisoformat, help="本次内容更新日期，YYYY-MM-DD")
    parser.add_argument("--answers", action="store_true", help="生成参考答案；省略则生成题单")
    args = parser.parse_args()
    build(args.date, args.answers)
