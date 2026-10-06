"""从 Lab 3 Markdown 重建单文件阅读版；复用第四讲公共 CSS 与目录行为。"""
import argparse
from datetime import date
import hashlib
import html
import json
from pathlib import Path
import re

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from latex2mathml.converter import convert
from lab3_figures import FIGURE_CSS, figure

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '2026/experiments/03/README.md'
TEMPLATE = ROOT / '2026/docs/link_state_router.html'


def math_render(content, display_mode=False):
    return convert(content, display='block' if display_mode else 'inline')


def markdown():
    md=MarkdownIt('commonmark',{'html':True}).enable('table').use(dollarmath_plugin, renderer=math_render)
    def fence(tokens,idx,options,env):
        token=tokens[idx]; language=token.info.strip();kind='cmd' if language=='bash' else 'out'
        return f'<div class="code {kind}"><span class="code-tag">{html.escape(language or "output")}</span><pre><code>{html.escape(token.content)}</code></pre></div>\n'
    md.renderer.rules['fence']=fence
    md.renderer.rules['table_open']=lambda *args:'<div class="table-wrap"><table>\n'
    md.renderer.rules['table_close']=lambda *args:'</table></div>\n'
    return md


def build(updated):
    source=SOURCE.read_text();template=TEMPLATE.read_text();md=markdown()
    css=re.search(r'<style>(.*?)</style>',template,re.S)[1]
    css=css.replace('第 04 讲','Lab 3').replace('动手实现一个链路状态路由器','搭一个迷你数据中心')
    # 保留模板字体的许可注释以及内嵌字体；新增长代码块打印允许分页。
    css+='\n@media print { .code { break-inside:auto; } .fig svg { min-width:0; } }\n'
    css += FIGURE_CSS
    script=re.search(r'<script>(.*?)</script>',template,re.S)[1]
    expected=json.loads(Path(__file__).with_name('lab3_figure_sources.json').read_text())
    seen=[]
    def diagrams(match):
        language,code,caption=match.groups()
        if language=='mermaid':
            key=re.search(r'%% lab3:(\w+)',code)[1]
        elif '┌─ h1a' in code:key='topology'
        else:return match[0]
        digest=hashlib.sha256(code.encode()).hexdigest()
        if expected.get(key)!=digest:
            raise ValueError(f'{key} 源图已变；先同步 lab3_figures.py/SVG，再更新图源摘要')
        seen.append(key)
        svg = figure(key)
        if key == 'topology':
            Path(__file__).with_name('lab3_topology.svg').write_text(svg + '\n')
        number, explanation = re.fullmatch(r'图 (\d+)：(.+)', caption).groups()
        return (f'<figure class="fig" id="fig-{key}">'
                '<p class="fig-scroll-hint">左右滑动查看全图；键盘可聚焦图框后横向滚动。</p>'
                f'<div class="fig-body" tabindex="0" role="region" aria-label="图 {number}，可横向滚动">'
                + svg + f'</div><figcaption><b>图 {number}：</b><span>'
                + md.renderInline(explanation) + '</span></figcaption></figure>\n')
    content=re.sub(r'^```([^\n]*)\n((?:(?!^```).)*?)^```\n\n\*([^\n]*图 [1-4]：[^\n]*)\*',diagrams,source,flags=re.M|re.S)
    if len(seen)!=4:raise ValueError(f'预期 4 幅语义图，实际 {seen}')
    # 标题、目录、各节从源文生成，不手写第二份正文。
    chunks=re.split(r'^## (.+)\n',content,flags=re.M)
    intro=chunks[0].split('\n',1)[1].replace('\n---\n','\n')
    sections=[];toc=['<li data-target="top"><a href="#top"><span class="n">00</span><span>实验导读</span></a></li>']
    for i in range(1,len(chunks),2):
        num=(i+1)//2;title=chunks[i];body=chunks[i+1].replace('\n---\n','\n')
        tokens=md.parse(body);subtoc=[];sub=0
        for n,t in enumerate(tokens):
            if t.type=='heading_open':
                sub+=1;anchor=f'm{num}-s{sub}';t.attrSet('id',anchor)
                # 每个任务直接可定位；h4 在目录中也保留。
                subtoc.append(f'<li><a href="#{anchor}">{html.escape(tokens[n+1].content)}</a></li>')
        label=re.sub(r'^[一二三四五六七八九十]+、','',title)
        toc.append(f'<li data-target="m{num}"><a href="#m{num}"><span class="n">{num:02}</span><span>{html.escape(label)}</span></a><ol class="toc-sub">'+''.join(subtoc)+'</ol></li>')
        sections.append(f'<section class="module" id="m{num}"><header class="module-head"><div class="module-eyebrow"><span class="module-no">{num:02}</span><span class="tag">LAB 3</span></div><h2>{html.escape(label)}</h2></header>'+md.renderer.render(tokens,md.options,{})+'</section>')
    sha=hashlib.sha256(source.encode()).hexdigest()
    page=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="2026/tools/build_lab3_html.py；源文 sha256 {sha}；更新 {updated}">
<title>Lab 3 · 搭一个迷你数据中心</title><style>{css}</style></head><body><div class="layout">
<nav class="toc no-print" aria-label="目录"><div class="toc-course">云网融合创新实践 · LAB 03<b>搭一个迷你数据中心</b></div><ol class="toc-mods">{''.join(toc)}</ol><div class="toc-foot"><button class="btn-print js-print" type="button">打印 / 存为 PDF</button><p class="print-hint">A4 纵向；请关闭浏览器自己的页眉和页脚。</p></div></nav>
<main class="doc" id="top"><header class="masthead"><div class="mast-eyebrow"><span>上海交通大学 · 云网融合创新实践</span><span class="lec">2026 · LAB 03</span></div><h1>搭一个<br>迷你数据中心</h1><p class="mast-sub">Build a Mini Data Center: Clos Fabric, ECMP &amp; VXLAN</p><div class="legend"><span><i class="k-l2"></i>二层 · 交换与隔离</span><span><i class="k-l3"></i>三层 · 路由与多路径</span><span><i class="k-l4"></i>四层 · 连接与传输</span></div><div class="lead"><span class="lead-label">实验导读</span>{md.render(intro)}</div></header>
{''.join(sections)}
<footer class="colophon"><span>上海交通大学 · 云网融合创新实践 · Lab 3</span><span>由 <a href="README.md">README.md</a> 生成 · sha256 {sha[:12]} · {updated}</span></footer></main></div><script>{script}</script></body></html>'''
    SOURCE.with_suffix('.html').write_text(page)
    print(f'{SOURCE.relative_to(ROOT)} → HTML；4 幅 SVG；sha256 {sha}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--date',default=date.today().isoformat())
    build(parser.parse_args().date)
