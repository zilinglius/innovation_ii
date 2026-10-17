"""阅读版生成器的共用部分：命令高亮、生成页的结构检查。第 06 讲与 Lab 4 的生成器共用。"""

import html
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from markdown_it.token import Token


def highlight(code):
    """只加行内高亮，不加块级行容器：复制出来的文本与源文逐字相同。"""
    lines = []
    for line in code.split("\n"):
        step = re.match(r"^(\s*)(# \d+\.)(.*)$", line)
        if step:
            lines.append(f'{step[1]}<span class="c step"><span class="step-n">{html.escape(step[2])}</span>'
                         f'{html.escape(step[3])}</span>')
            continue
        if line.lstrip().startswith("#"):
            lines.append(f'<span class="c">{html.escape(line)}</span>')
            continue
        escaped = html.escape(line)
        escaped = re.sub(r"(?<![\w-])sudo(?![\w-])", '<span class="su">sudo</span>', escaped)
        escaped = re.sub(r"(ip netns exec |ip -n )(&quot;\$\w+&quot;|[\w-]+)", r'\1<span class="ns">\2</span>', escaped)
        lines.append(escaped)
    return "\n".join(lines)


def html_token(content):
    token = Token("html_block", "", 0)
    token.content = content
    return token


class Page(HTMLParser):
    """收集生成页中的 ID、链接、外部资源、<pre> 文本、配图数与正文可见文字。"""

    def __init__(self):
        super().__init__()
        self.ids, self.links, self.resources, self.blocks = [], [], [], []
        self.depth = {"pre": 0, "code": 0, "math": 0, "script": 0, "style": 0, "svg": 0}
        self.parts, self.visible = [], []
        self.figures = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if tag == "figure":
            self.figures += 1
        if tag in ("script", "img", "iframe", "link", "source", "video", "audio"):
            ref = attrs.get("src", attrs.get("href", ""))
            if ref and not ref.startswith("data:"):
                self.resources.append(ref)
        if tag in self.depth:
            self.depth[tag] += 1
        if tag == "pre":
            self.parts = []

    def handle_endtag(self, tag):
        if tag in self.depth:
            self.depth[tag] -= 1
        if tag == "pre":
            self.blocks.append("".join(self.parts))

    def handle_data(self, value):
        if self.depth["pre"]:
            self.parts.append(value)
        elif not any(self.depth[k] for k in ("code", "math", "script", "style", "svg")):
            self.visible.append(value)


def check_links(page, base):
    """页内锚点、本地文件与跨页 HTML 锚点必须存在；外部链接只允许 http(s)。base 为生成页所在目录。"""
    for link in page.links:
        url = urlsplit(link)
        if url.scheme:
            assert url.scheme in ("https", "http"), f"异常链接：{link}"
            continue
        if not url.path:
            assert unquote(url.fragment) in page.ids, f"页内锚点不存在：{link}"
            continue
        target = Path(base) / unquote(url.path)
        assert target.exists(), f"本地链接不存在：{link}"
        if target.suffix == ".html" and url.fragment:
            other = Page()
            other.feed(target.read_text())
            assert unquote(url.fragment) in other.ids, f"跨页锚点不存在：{link}"


def check_leftovers(page, output):
    """正文中不应残留未解析的 Markdown／Mermaid 标记、占位符或本机绝对路径。"""
    visible = "".join(page.visible)
    for leftover in ("**", "```", "$$", "%%", "flowchart", "⟦"):
        assert leftover not in visible, f"正文残留未解析标记：{leftover}"
    assert not re.search(r"file://|/Users/|/root/", output), "出现本机绝对路径"
