"""Lab 3 阅读版的静态内容核验；不代替真实浏览器显示检查。"""
from collections import Counter
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'2026/experiments/03/README'


class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.links=[];self.pre=False;self.parts=[];self.blocks=[];self.resources=[];self.svg=0;self.math=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='a':self.links.append(a.get('href',''))
        if tag in ('script','img','iframe','link'):
            ref=a.get('src',a.get('href',''))
            if ref and not ref.startswith('data:'):self.resources.append(ref)
        if tag=='pre':self.pre=True;self.parts=[]
        if tag=='svg':self.svg+=1
        if tag=='math':self.math+=1
    def handle_endtag(self,tag):
        if tag=='pre':self.pre=False;self.blocks.append(''.join(self.parts))
    def handle_data(self,text):
        if self.pre:self.parts.append(text)


def check():
    md=BASE.with_suffix('.md').read_text();html=BASE.with_suffix('.html').read_text();page=Page();page.feed(html)
    assert hashlib.sha256(md.encode()).hexdigest() in html,'源文摘要不一致'
    blocks=[body for lang,body in re.findall(r'^```([^\n]*)\n(.*?)^```',md,re.M|re.S) if lang!='mermaid' and '┌─ h1a' not in body]
    assert blocks==page.blocks,'代码或输出内容／顺序不一致'
    assert not [key for key,n in Counter(page.ids).items() if n>1],'ID 重复'
    assert page.svg==4 and page.math>0,'SVG 或 MathML 缺失'
    assert not page.resources,f'正文存在外部依赖 {page.resources}'
    for link in page.links:
        url=urlsplit(link)
        if url.scheme:
            assert url.scheme in ('http','https','mailto'),f'异常协议 {link}'
            continue
        target=BASE.with_suffix('.html') if not url.path else (BASE.parent/unquote(url.path)).resolve()
        assert target.exists(),f'目标文件缺失 {link}'
        if url.fragment and target.suffix=='.html':
            other=Page();other.feed(target.read_text())
            assert unquote(url.fragment) in other.ids,f'锚点不存在 {link}'
    for number in range(1,5):
        assert f'图 {number}：' in html,f'缺少图注 {number}'
    print(f'PASS: {len(blocks)} 个代码／输出块逐字一致；4 幅 SVG；{page.math} 个 MathML；摘要、锚点与本地链接通过。')
    print('显示检查未由本工具覆盖。')


if __name__=='__main__':check()
