"""阅读版的共用主题：把“旧版结构”的页面套进新的页面外壳与组件，并维护各页内嵌的主题。

共用的样式、脚本与字体放在 reading_theme/（theme.css、theme.js、head.js、fonts.css），版式规范见
仓库根目录的 html_guidelines.md。讲义、课堂回顾、参考答案与实验指导书四类页面共用这一套主题。两个入口：

    restyle(html, page, kind=…)   生成器在最后一步调用：把按旧版结构拼出的整页换成新版页面。
    retheme                       主题改动后，刷新手工维护的页面里内嵌的样式与脚本
                                  （python reading_theme.py retheme 2026/docs/network.html …）。

正文（段落、表格、公式、SVG、代码文本）逐字沿用输入页；这里只换外壳，并调整代码块、预测卡片、
思考提示等组件的包裹结构。带 .ui 的元素是页面附加的界面文字，不属于正文。
"""

import argparse
import html as htmllib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
THEME = Path(__file__).resolve().parent / "reading_theme"

# 讲次、配套实验与课堂回顾的对应关系，用于页尾的“接下来”。与 2026/README.md 的大纲表保持一致。
LECTURES = [
    # 页面名                 讲次  实验  实验卡片的小标题      回顾页
    ("network",                  "01", "01", "配套实验",            "network_review"),
    ("switching_routing",        "02", "01", "配套实验",            "switching_routing_review"),
    ("routing_protocol",         "03", "02", "配套实验",            "routing_protocol_review"),
    ("link_state_router",        "04", "02", "配套实验",            "link_state_router_review"),
    ("datacenter_network",       "05", "03", "配套实验",            "datacenter_network_review"),
    ("network_measurement",      "06", "04", "配套实验（选做）",    "network_measurement_review"),
    ("tail_latency",             "07", "05", "配套实验",            None),
    ("communication_cost",       "08", "06", "配套实验 · A 段",     None),
    ("collective_communication", "09", "06", "配套实验 · B 段",     None),
    ("topology_aware_scheduling", "10", "07", "配套实验 · A 段",    None),
    ("computing_aware_steering", "11", "07", "配套实验 · B 段",     None),
]

# 页面的四个种类。讲义按 LECTURES 登记；回顾与参考答案挂在对应讲义的“回顾页”一栏；实验页的 page 写成 lab03 这样。
KINDS = {"lecture": "讲义", "review": "回顾", "answers": "回顾 · 参考答案", "lab": "实验指导书"}
NUMERAL_HEAD = re.compile(r"^[一二三四五六七八九十]+、")


def page_info(page, kind):
    """返回（编号，目录与页眉用的名称，顶栏上的短标签，仓库 2026/ 目录的相对路径）。"""
    assert kind in KINDS, kind
    if kind == "lecture":
        _, row = lecture_info(page)
        return row[1], f"第 {row[1]} 讲", row[1], "../"
    if kind == "lab":
        number = _one(r"^lab(\d\d)$", page, what="实验页的 page 应写成 lab03 这样").group(1)
        return number, f"Lab {int(number)}", f"LAB {number}", "../../"
    stem = page.removesuffix("_answers")
    assert (kind == "answers") == page.endswith("_answers"), page
    rows = [row for row in LECTURES if row[4] == stem]
    assert rows, f"LECTURES 里没有回顾页 {stem}"
    number = rows[0][1]
    return number, f"第 {number} 讲回顾" + (" · 参考答案" if kind == "answers" else ""), ("答案 " if kind == "answers" else "回顾 ") + number, "../"


ICO = {
    "menu": '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 5.5h13M3.5 10h13M3.5 14.5h8"/></svg>',
    "close": '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15"/></svg>',
    "print": '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M6 7V3.5h8V7M6 14H4.5A1.5 1.5 0 0 1 3 12.5v-4A1.5 1.5 0 0 1 4.5 7h11A1.5 1.5 0 0 1 17 8.5v4a1.5 1.5 0 0 1-1.5 1.5H14"/><path d="M6 11.5h8v5H6z"/></svg>',
    "present": '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="2.5" y="3.5" width="15" height="10" rx="1.5"/><path d="M10 13.5v3M6.5 16.5h7"/></svg>',
    "theme": ('<svg class="i-auto" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6.5"/><path d="M10 3.5v13M10 6.5l4.6-1.6M10 10l6.3-1.6M10 13.5l5.6-.4"/></svg>'
              '<svg class="i-light" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="3.4"/><path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M4.7 15.3l1.4-1.4M13.9 6.1l1.4-1.4"/></svg>'
              '<svg class="i-dark" viewBox="0 0 20 20" aria-hidden="true"><path d="M16.2 11.9A6.6 6.6 0 0 1 8.1 3.8a6.6 6.6 0 1 0 8.1 8.1z"/></svg>'),
}
PRINT_FONT = '"IBM Plex Sans", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif'
MAINTAIN = """<!--
  维护说明（版式规范见仓库根目录 html_guidelines.md；内容以同名 Markdown 为准）
  · id 为 theme、theme-head、theme-js 的样式与脚本块是共用主题（2026/tools/reading_theme/），不要在页面里直接改；
    主题改动后用 2026/tools/reading_theme.py retheme 刷新。本页专属的样式写在 id 为 page 的样式块里。
  · 带 .ui 的元素是页面附加的界面文字（开章大号数字、“预测 / 测量 / 解释”标签、“接下来”导航等），不属于讲义正文。
  · 代码块的每一行是一个 <span class="ln">，行末换行符写在 span 里面（空行也是），选中复制出的文本与源文逐字相同。
  · 命令块：<span class="grp" data-step="N"> 为一步；.ln.cm 是注释行，.ln.x 是命令行，续行另加 .cont
    （$ 与 > 提示符、打勾与复制按钮由样式和脚本生成）；两步之间的空行写成 .ln.gap。
  · “预测、测量、解释”：<div class="pme"> 内依次是预测（p.predict）、命令块、.reveal-body（样例输出与解读）。
    收起区的范围：每个命令块之后，到下一个命令块、标题或预测之前。打印与无脚本时全部展开。
  · 模块的 data-layer（l2 / l3 / l4 / mix / 空）决定开章色带、目录站点与强调色。
  · 新增小节时，同步目录（.stops）里的条目。
-->"""


def _one(pattern, text, flags=re.S, what=None):
    m = re.search(pattern, text, flags)
    assert m, f"旧版页面里找不到：{what or pattern[:60]}"
    return m


def strip_tags(s):
    return htmllib.unescape(re.sub(r"<[^>]+>", "", s))


# ------------------------------------------------------------------ 主题
def theme_css():
    css = (THEME / "theme.css").read_text(encoding="utf-8")
    assert css.count("/*__FONTS__*/") == 1
    return css.replace("/*__FONTS__*/", (THEME / "fonts.css").read_text(encoding="utf-8").rstrip("\n"))


def theme_blocks():
    return {
        "theme": ("style", "\n" + theme_css().rstrip("\n") + "\n"),
        "theme-head": ("script", (THEME / "head.js").read_text(encoding="utf-8").strip()),
        "theme-js": ("script", "\n" + (THEME / "theme.js").read_text(encoding="utf-8").rstrip("\n") + "\n"),
    }


def retheme(page_html):
    """刷新新版页面里内嵌的共用主题，其余内容不动。"""
    for key, (tag, content) in theme_blocks().items():
        pattern = re.compile(rf'(<{tag} id="{key}">).*?(</{tag}>)', re.S)
        assert len(pattern.findall(page_html)) == 1, f"页面里应恰有一个 <{tag} id=\"{key}\">"
        page_html = pattern.sub(lambda m: m.group(1) + content + m.group(2), page_html)
    return page_html


def page_rule(left, right):
    """@page：纸张、页边距与页眉（讲次、标题）；首页不印页眉。"""
    font = f"font: 8pt {PRINT_FONT}; color: #6f7178;"
    return ("@page {\n  size: A4; margin: 17mm 18mm 18mm;\n"
            f'  @top-left {{ content: "{left}"; {font} }}\n'
            f'  @top-right {{ content: "{right}"; {font} }}\n'
            '  @bottom-center { content: counter(page) " / " counter(pages); font: 8pt "IBM Plex Mono", Menlo, Consolas, monospace; color: #6f7178; }\n'
            "}\n"
            "@page :first { @top-left { content: none; } @top-right { content: none; } }\n")      # 要写在上一条之后才生效


# ------------------------------------------------------------------ 把一段 HTML 拆成顶层块
VOID = {"br", "hr", "img", "col", "wbr", "input", "meta", "link"}
TAG = re.compile(r"<!--.*?-->|<(/?)([A-Za-z][\w:-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.S)


def split_blocks(fragment):
    """返回 [(块的 HTML, 起始标签名, 起始标签的属性串)]；顶层元素之间的空白丢弃，顶层裸文本不允许出现。"""
    blocks, depth, start, first = [], 0, None, None
    pos = 0
    for m in TAG.finditer(fragment):
        if m.group(0).startswith("<!--"):
            continue
        closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
        selfclose = attrs.rstrip().endswith("/") or name in VOID
        if depth == 0:
            assert not closing, f"多余的结束标签 </{name}>"
            assert not fragment[pos:m.start()].strip(), f"顶层出现裸文本：{fragment[pos:m.start()].strip()[:40]!r}"
            start, first = m.start(), (name, attrs)
            if selfclose:
                blocks.append((fragment[start:m.end()], name, attrs))
                pos = m.end()
                continue
            depth = 1
            continue
        if closing:
            depth -= 1
            if depth == 0:
                blocks.append((fragment[start:m.end()], first[0], first[1]))
                pos = m.end()
        elif not selfclose:
            depth += 1
    assert depth == 0, "标签没有配平"
    assert not fragment[pos:].strip(), f"顶层出现裸文本：{fragment[pos:].strip()[:40]!r}"
    return blocks


# ------------------------------------------------------------------ 代码块
NL = "\x01"                 # 行内换行的占位符，写出前换回 \n（中间步骤按行处理时不受干扰）
LN = '<span class="ln">'


class Shell:
    """判断命令块里的一行是不是上一条命令的续行：反斜杠、here-doc、未闭合的引号、循环与函数体。"""

    def __init__(self):
        self.heredoc, self.backslash, self.quote, self.depth = None, False, None, 0

    def continuing(self):
        return bool(self.heredoc or self.backslash or self.quote or self.depth > 0)

    def feed(self, line):
        if self.heredoc:
            if line.strip() == self.heredoc:
                self.heredoc = None
            return
        bare, i, quote = [], 0, self.quote
        while i < len(line):
            ch = line[i]
            if quote == "'":
                if ch == "'":
                    quote = None
            elif quote == '"':
                if ch == "\\":
                    i += 1
                elif ch == '"':
                    quote = None
            elif ch == "\\":
                bare.append(line[i:i + 2])
                i += 1
            elif ch in "'\"":
                quote = ch
                bare.append(" ")
            elif ch == "#" and (i == 0 or line[i - 1] in " \t;"):
                break
            else:
                bare.append(ch)
            i += 1
        bare = "".join(bare)
        self.quote = quote
        self.backslash = quote is None and bare.rstrip().endswith(("\\", "|", "&&"))      # 行尾的管道、&& 也接下一行
        if quote is None:
            m = re.search(r"<<-?\s*['\"]?(\w+)", re.sub(r"<<<", "", line))
            if m:
                self.heredoc = m.group(1)
            for part in re.split(r"[;&|]+", bare):         # 保留字只在命令开头才算（ping -M do 里的 do 不算）
                words = part.split()
                if not words:
                    continue
                if words[0] in ("do", "then", "case") or words[-1].endswith("{"):
                    self.depth += 1
                if words[0] in ("done", "fi", "esac") or words[0].startswith("}"):
                    self.depth = max(0, self.depth - 1)


def code_lines(inner):
    if LN in inner:                                   # 手工维护的旧页：一行一个 span，行间没有换行符
        assert inner.startswith(LN) and inner.endswith("</span>"), inner[:80]
        lines = inner[len(LN):-len("</span>")].split("</span>" + LN)
        return ["" if ln == "&#10;" else ln for ln in lines]      # 第 05 讲的旧页把空行写成只含换行符的一行
    return (inner[:-1] if inner.endswith("\n") else inner).split("\n")


def chips(comment):
    """注释行里的“终端 N”与按键做成小标签（只动标签外的文字）。"""
    def text(m):
        s = re.sub(r"终端 \d", lambda t: f'<span class="term">{t.group(0)}</span>', m.group(0))
        return s.replace("Ctrl+C", '<span class="kbd">Ctrl+C</span>')
    return re.sub(r"(?<=>)[^<>]+(?=<)", text, comment)


def cmd_block(lines, report):
    out, cur, has_cmd, sh = [], [], False, Shell()

    def flush():
        nonlocal cur, has_cmd
        if cur:
            step = re.search(r'<span class="step-n"># (\d+)\.</span>', cur[0])
            attr = f' data-step="{step.group(1)}"' if step else ""
            out.append(f'<span class="grp"{attr}>{"".join(cur)}</span>')
        cur, has_cmd = [], False

    for ln in lines:
        text = strip_tags(ln)
        if sh.continuing():
            cur.append(f'<span class="ln x cont">{ln}{NL}</span>')
            report.append(text)
            sh.feed(text)
        elif ln == "":
            flush()
            out.append(f'<span class="ln gap">{NL}</span>')
        elif ln.lstrip().startswith('<span class="c'):
            if has_cmd:
                flush()
            cur.append(f'<span class="ln cm">{chips(ln)}{NL}</span>')
        else:
            has_cmd = True
            cur.append(f'<span class="ln x">{ln}{NL}</span>')
            sh.feed(text)
    assert not sh.continuing(), f"命令块结束时还有未闭合的续行：{strip_tags(lines[-1])[:60]!r}"
    flush()
    return "".join(out)


def plain_block(lines):
    return "".join(f'<span class="ln">{ln}{NL}</span>' if ln else f'<span class="ln e">{NL}</span>' for ln in lines)


def restyle_code(body, report):
    def one(m):
        cls, tag, inner = m.group(1), m.group(2), m.group(3)
        kind = cls.split()[1]
        lines = code_lines(inner)
        if kind == "cmd":
            inner = cmd_block(lines, report)
        else:
            assert kind in ("out", "py", "note"), f"未处理的代码块类型：{cls}"
            inner = plain_block(lines)
        return f'<div class="{cls}"><span class="code-tag">{tag}</span><pre><code>{inner}</code></pre></div>'
    body, n = re.subn(r'<div class="(code [^"]*)"><span class="code-tag">([^<]*)</span><pre><code>(.*?)</code></pre></div>', one, body, flags=re.S)
    assert n == body.count("<pre>") == body.count('<div class="code '), "有代码块没有被识别"
    return body


# ------------------------------------------------------------------ 预测卡片与思考提示
def label(n, text):
    if n:
        return f'<span class="pme-label ui"><b>{n}</b>{text}</span>'
    return f'<span class="pme-label more ui">{text}</span>'


def step(n, text, inner, reveal=None):
    if reveal:
        return (f'<div class="pme-step reveal" data-kind="{reveal}">{label(n, text)}<div class="pme-body"><div class="reveal-body">\n'
                f'{inner}\n</div></div></div>')
    return f'<div class="pme-step">{label(n, text)}<div class="pme-body">{inner}</div></div>'


def is_cmd(block):
    return block[1] == "div" and 'class="code cmd' in block[2]


def pme_cards(blocks):
    """p.predict 起、到下一个标题或下一处预测为止，做成一张“预测、测量、解释”卡片。
    命令块始终可见；每个命令块之后到下一个命令块之前的内容（样例输出与解读）收起。
    范围里没有命令块时，是“预测、解释”两步。"""
    out, i, count = [], 0, 0
    while i < len(blocks):
        block = blocks[i]
        if not (block[1] == "p" and 'class="predict"' in block[2]):
            out.append(block[0])
            i += 1
            continue
        j = i + 1
        while j < len(blocks) and not (blocks[j][1] in ("h2", "h3", "h4", "header") or 'class="predict"' in blocks[j][2]):
            j += 1
        span = blocks[i + 1:j]
        parts = [step(1, "预测", block[0])]
        cmds = [k for k, b in enumerate(span) if is_cmd(b)]
        if not cmds:
            assert span, "预测之后没有可收起的内容"
            parts.append(step(2, "解释", "\n".join(b[0] for b in span), reveal="ans"))
        else:
            first = True
            for a, k in enumerate(cmds):
                lead = span[:k] if a == 0 else []                # 第一个命令块之前的说明留在“测量”里
                end = cmds[a + 1] if a + 1 < len(cmds) else len(span)
                parts.append(step(2 if first else 0, "测量", "\n".join(b[0] for b in lead + [span[k]])))
                tail = span[k + 1:end]
                if tail:
                    parts.append(step(3 if first else 0, "解释", "\n".join(b[0] for b in tail), reveal="obs"))
                first = False
        out.append('<div class="pme">\n' + "\n".join(parts) + "\n</div>")
        count += 1
        i = j
    return out, count


def hints(body):
    """“思考提示”可收起：思考题里的列表项，以及正文里以“思考提示”开头的段落。"""
    def li(m):
        assert "<li" not in m.group(1)
        return f'<li class="hint reveal" data-kind="hint"><div class="reveal-body">{m.group(1)}</div></li>'
    body, a = re.subn(r'<li(?: class="hint")?>(<em>思考提示(?:(?!</li>).)*)</li>', li, body, flags=re.S)
    body, b = re.subn(r"<p>(<em>思考提示(?:(?!</p>).)*)</p>",
                      r'<div class="hint reveal" data-kind="hint"><div class="reveal-body"><p>\1</p></div></div>', body, flags=re.S)
    return body, a + b


# ------------------------------------------------------------------ 整页
def lecture_info(page):
    for i, row in enumerate(LECTURES):
        if row[0] == page:
            return i, row
    raise AssertionError(f"LECTURES 里没有 {page}：先登记讲次、配套实验与回顾页")


def h1_of(path):
    text = path.read_text(encoding="utf-8")
    h1 = _one(r"<h1[^>]*>(.*?)</h1>", text).group(1)
    h1 = re.sub(r'<span class="kicker">(.*?)</span>', r"\1：", h1)
    return " ".join(strip_tags(re.sub(r"<br\s*/?>", "", h1)).split())


def next_nav(page, kind, base):
    """页尾的“接下来”。讲义：配套实验、下一讲、课后自查；回顾：原讲义、参考答案、下一讲回顾；
    参考答案：题单、原讲义；实验：对应讲义、下一个实验。"""
    cards = []

    def card(href, kicker):
        assert (base / href).exists(), base / href
        cards.append((href, kicker, h1_of(base / href)))

    if kind == "lecture":
        i, (_, _, lab, lab_kicker, review) = lecture_info(page)
        if lab:
            card(f"../experiments/{lab}/README.html", lab_kicker)
        if i + 1 < len(LECTURES):
            card(f"{LECTURES[i + 1][0]}.html", f"下一讲 · 第 {LECTURES[i + 1][1]} 讲")
        if review:
            card(f"{review}.html", "课后自查")
    elif kind == "lab":
        number = page_info(page, kind)[0]
        for name, lecture, lab, *_ in LECTURES:
            if lab == number:
                card(f"../../docs/{name}.html", f"对应讲义 · 第 {lecture} 讲")
        following = f"{int(number) + 1:02d}"
        if (base / f"../{following}/README.html").exists():
            card(f"../{following}/README.html", f"下一个实验 · Lab {int(following)}")
    else:
        stem = page.removesuffix("_answers")
        i = [row[4] for row in LECTURES].index(stem)
        if kind == "review":
            card(f"{LECTURES[i][0]}.html", f"原讲义 · 第 {LECTURES[i][1]} 讲")
            card(f"{stem}_answers.html", "参考答案")
            later = [row for row in LECTURES[i + 1:] if row[4]]
            if later:
                card(f"{later[0][4]}.html", f"下一讲回顾 · 第 {later[0][1]} 讲")
        else:
            card(f"{stem}.html", "回顾题单")
            card(f"{LECTURES[i][0]}.html", f"原讲义 · 第 {LECTURES[i][1]} 讲")
    links = "\n".join(f'    <a href="{href}"><i>{kicker}</i><b>{htmllib.escape(title)}</b></a>' for href, kicker, title in cards)
    return ('<nav class="next no-print ui" aria-labelledby="next-h">\n  <h2 class="block-h" id="next-h">接下来</h2>\n'
            f'  <div class="next-grid">\n{links}\n  </div>\n</nav>\n')


def unwrap(text, opening):
    """去掉 opening 这层包裹（保留里面的内容），按标签配平找到它的结束标签。"""
    while opening in text:
        start = text.index(opening)
        depth, end = 1, None
        for m in TAG.finditer(text, start + len(opening)):
            if m.group(0).startswith("<!--") or m.group(2).lower() in VOID:
                continue
            depth += -1 if m.group(1) else 1
            if depth == 0:
                end = m
                break
        assert end, f"{opening} 没有配平"
        text = text[:start] + text[start + len(opening):end.start()] + text[end.end():]
    return text


def restyle(old, page, *, kind="lecture", page_css=None, base=None, report=None):
    """把旧版结构的整页（刊头 masthead、目录 toc、模块 module-head、colophon）换成新版页面。
    page 是页面名（讲义与回顾用不带扩展名的文件名，实验页写成 lab03），也是浏览器本地存储的键；
    kind 是页面种类（lecture / review / answers / lab）；page_css 是本页专属样式（配图等）。"""
    base = Path(base) if base else ROOT / "2026/docs"
    report = report if report is not None else {}
    assert NL not in old
    number, label, bar, up = page_info(page, kind)
    title = _one(r"<title>(.*?)</title>", old).group(1)
    generator = _one(r'<meta name="generator" content="([^"]*)"', old).group(1)
    page_css = page_css or ""

    # ---- 目录
    course_title = _one(r'<div class="toc-course">[^<]*<b>(.*?)</b></div>', old).group(1)
    toc = _one(r'<ol class="toc-mods">(.*?)</ol>\s*<div class="toc-foot">', old).group(1)
    items = re.findall(r'<li(?: data-layer="([^"]*)")? data-target="([^"]+)"><a href="#[^"]+"><span class="n">([^<]*)</span><span>(.*?)</span></a>'
                       r'(?:<ol class="toc-sub">(.*?)</ol>)?</li>', toc, re.S)
    assert len(items) == toc.count("data-target=") and items[0][1] == "top", "目录条目没有全部识别"
    top_text = items[0][3]

    # ---- 正文
    main = _one(r'<main class="doc" id="top">(.*)</main>', old).group(1)
    mast = _one(r'<header class="masthead">(.*?)</header>', main).group(0)
    eyebrow = _one(r'<div class="mast-eyebrow"><span>(.*?)</span><span class="lec">(.*?)</span></div>', mast)
    if kind == "lecture":
        assert f"LECTURE {number}" in eyebrow.group(2), (eyebrow.group(2), number)
        crumb = f"第 {number} 讲 · {eyebrow.group(2).rsplit('·', 1)[1].strip()}"
    else:
        assert number in eyebrow.group(2), (eyebrow.group(2), number)
        crumb = label if kind != "lab" else f"{label} · {KINDS[kind]}"
    h1 = _one(r"<h1>(.*?)</h1>", mast).group(1)
    sub = re.search(r'<p class="mast-sub">(.*?)</p>', mast, re.S)
    art = re.search(r'<div class="pathstrip">\s*(<svg.*?</svg>)', mast, re.S)
    legend = re.search(r'<div class="legend">(.*?)</div>', mast, re.S)
    facts = re.search(r'<ul class="facts">.*?</ul>', mast, re.S)
    lead = _one(r'<div class="lead">(.*?)</div>\s*(?:<div class="mobile-print[^>]*>.*?</div>\s*)?</header>', mast).group(1).strip()
    lead_label = re.match(r'<span class="lead-label">(.*?)</span>', lead)
    if lead_label:
        lead = lead[lead_label.end():].strip()
    hero = ['<header class="hero">',
            f'  <div class="crumbs"><a href="{up}README.md">{eyebrow.group(1)}</a><span>2026</span><span>{crumb}</span></div>',
            f"  <h1>{h1}</h1>"]
    if sub:
        hero.append(f'  <p class="hero-en">{sub.group(1)}</p>')
    if facts:
        hero.append("  " + facts.group(0))
    hero.append('  <div class="lead">' + (f'<span class="lead-label">{lead_label.group(1)}</span>' if lead_label else "") + f"{lead}\n</div>")
    if art:
        hero.append(f'  <div class="heroart"><div class="heroart-body">{art.group(1)}</div>\n'
                    f'    <div class="legend">{legend.group(1)}</div></div>')
    elif legend:
        hero.append(f'  <div class="legend">{legend.group(1)}</div>')
    hero.append("</header>\n")
    main = main.replace(mast, "\n".join(hero))
    assert "pathstrip" not in main and "mast-" not in main

    # 学习目标（讲义才有）：“标题：说明”式的条目把标题单独成行
    goals = re.search(r'<section class="plain-sec goals" id="([^"]+)"><h2>学习目标</h2>(.*?)</section>', main, re.S)
    assert goals or kind != "lecture", "讲义缺少学习目标"
    if goals:
        inner = re.sub(r"<li><strong>((?:(?!</strong>).)*)</strong>：", r'<li><strong class="g-t">\1</strong><span class="sep">：</span>', goals.group(2), flags=re.S)
        main = main.replace(goals.group(0), f'<section class="goals" id="{goals.group(1)}"><h2 class="block-h">学习目标</h2>{inner}</section>')

    # 本页路线（讲义与手工维护的回顾、实验页有）
    layer_of = {}
    hops = re.search(r'<nav class="hops" aria-label="([^"]*)">.*?<ol>(.*?)</ol>\s*</nav>', main, re.S)
    assert hops or kind != "lecture", "讲义缺少本讲路线"
    rows = []
    if hops:
        rows = re.findall(r'<li><a href="#([^"]+)"><span class="hop-n">\d+</span><span class="hop-m">(.*?)</span><span class="hop-t">(.*?)</span>'
                          r'<span class="tag ([^"]*)">(.*?)</span></a>(<ul class="hop-tasks">.*?</ul>)?</li>', hops.group(2), re.S)
        assert len(rows) == hops.group(2).count('<li><a href="#') == len(items) - 1, "路线与目录的模块数不一致"

    # 模块标题 → 开章色带。题单这类标题自带“一、”的页不再加大号序号。
    main = unwrap(main, '<div class="sec-open">')

    def opener(m):
        extra, attrs, no, tag_cls, tag, h2 = m.groups()
        mid = _one(r'id="([^"]+)"', attrs).group(1)
        layer = re.search(r'data-layer="([^"]*)"', attrs)
        layer = (layer.group(1) if layer else "") or ("mix" if tag_cls.strip() == "mix" else "")
        layer_of[mid] = layer
        n = [t for _, t, _, _, _ in items].index(mid)
        n = items[n][2].strip()
        big = n.isdigit() and not NUMERAL_HEAD.match(strip_tags(h2))
        number_html = f'<span class="opener-no ui" aria-hidden="true">{int(n):02d}</span>' if big else ""
        hide = ' sr-only' if no.strip().isdigit() else ""
        return (f'<section class="module{extra or ""}" id="{mid}" data-layer="{layer}">\n<header class="opener{"" if big else " no-num"}">'
                f'{number_html}<div class="opener-top"><span class="module-no{hide}">{no}</span>'
                f'<span class="otag">{tag}</span></div><h2>{h2}</h2></header>')
    main, n = re.subn(r'<section class="module( [\w-]+)?"([^>]*)>\s*<header class="module-head"><div class="module-eyebrow"><span class="module-no">(.*?)</span>'
                      r'<span class="tag ?([^"]*)">(.*?)</span></div>\s*<h2>(.*?)</h2></header>', opener, main, flags=re.S)
    assert n == len(items) - 1 == main.count('<section class="module'), "模块标题没有全部识别"

    def li_attr(mid):
        return f' data-layer="{layer_of[mid]}"' if layer_of[mid] else ""
    if hops:
        route = "".join(f'<li{li_attr(mid)}><a href="#{mid}"><span class="dot"></span><span class="hop-m">{no}</span>'
                        f'<span class="hop-t">{t}</span><span class="tag {cls}">{tag}</span></a>{tasks}</li>' for mid, no, t, cls, tag, tasks in rows)
        main = main.replace(hops.group(0), f'<nav class="route" aria-labelledby="route-h">\n  <h2 class="block-h ui" id="route-h">{hops.group(1)}</h2>\n  <ol>{route}</ol>\n</nav>')
    # 其它导引小节（课堂时间安排、使用说明）
    main = re.sub(r'<section class="plain-sec( [\w-]+)?"(?: style="[^"]*")?( id="[^"]+")?><h2>(.*?)</h2>', r'<section class="plain\1"\2><h2 class="block-h">\3</h2>', main)
    assert "plain-sec" not in main and "module-head" not in main and 'class="hops"' not in main

    # 代码块、思考提示、预测卡片
    report["cont"] = []
    main = restyle_code(main, report["cont"])
    main = re.sub(r"(<h3[^>]*>(?:<span class=\"sec-no\">[\d.]+</span>)?思考题</h3>\s*)<ol>", r'\1<ol class="questions">', main)
    main, report["hints"] = hints(main)
    report["pme"] = 0

    def module(m):
        head, inner = m.group(1), m.group(2)
        blocks, k = pme_cards(split_blocks(inner))
        report["pme"] += k
        return head + "\n" + "\n".join(blocks) + "\n</section>"
    main = re.sub(r'(<section class="module[^"]*"[^>]*>\n<header class="opener[^"]*">.*?</header>)(.*?)</section>(?=\s*(?:<section class="module|<footer))', module, main, flags=re.S)
    assert main.count('<p class="predict"') == report["pme"], "有预测没有做成卡片"

    # 页尾：接下来 + 版本说明
    colophon = _one(r'<footer class="colophon">.*?</footer>', main).group(0)
    main = main.replace(colophon, next_nav(page, kind, base) + colophon)

    # ---- 目录（线路）
    stops = [f'<li data-target="top"><a href="#top"><span class="dot"></span><span>{top_text}</span></a></li>']
    for _, mid, no, text, subs in items[1:]:
        subs = f'<ol class="subs">{subs}</ol>' if subs else ""
        no = f'<span class="stop-n">{no}</span>' if no.strip().isdigit() else ""
        stops.append(f'<li{li_attr(mid)} data-target="{mid}"><a href="#{mid}"><span class="dot"></span>'
                     f'<span>{no}{text}</span></a>{subs}</li>')
    mini = "".join(f'<i data-target="{mid}"{li_attr(mid)}></i>' for _, mid, _, _, _ in items[1:])
    blocks = theme_blocks()
    shell_top = f"""<body data-page="{page}" data-kind="{kind}">
<a class="skip no-print" href="#top">跳到正文</a>
<header class="topbar no-print">
  <button type="button" class="topbar-loc js-toc-open" aria-controls="toc" aria-expanded="false" title="目录">{ICO["menu"]}<span class="sr-only">目录，当前位置：</span><span class="lec">{bar}</span><span class="js-loc">{strip_tags(top_text)}</span></button>
  <span class="mini" aria-hidden="true">{mini}</span>
  <button type="button" class="ibtn js-present" aria-pressed="false" aria-label="投影模式" title="投影模式：放大字号，左右方向键按段翻页">{ICO["present"]}</button>
  <button type="button" class="ibtn js-theme" data-mode="auto" aria-label="外观：跟随系统，点击切换">{ICO["theme"]}</button>
</header>
<div class="scrim no-print"></div>
<div class="layout">
<nav class="nav no-print" id="toc" aria-label="目录">
  <div class="nav-head">
    <div class="nav-course"><a href="{up}README.md">云网融合创新实践 · 2026</a><i>{label}</i><b>{course_title}</b></div>
    <button type="button" class="ibtn nav-close js-toc-close" aria-label="关闭目录">{ICO["close"]}</button>
  </div>
  <ol class="stops">{"".join(stops)}</ol>
  <div class="nav-foot">
    <p class="nav-prog ui"><span>已完成步骤</span><b class="js-prog">0 / 0</b><button type="button" class="js-reset">清零</button></p>
    <div class="nav-tools">
      <button type="button" class="tool wide switch js-think" role="switch" aria-checked="true"><i></i><b>先想后看</b><small>样例输出与思考提示先收起</small></button>
      <button type="button" class="tool js-present" aria-pressed="false" title="放大字号，左右方向键按段翻页，Esc 退出">{ICO["present"]}投影模式</button>
      <button type="button" class="tool js-theme" data-mode="auto" aria-label="外观：跟随系统，点击切换">{ICO["theme"]}<span class="js-theme-t">跟随系统</span></button>
      <button type="button" class="tool wide js-print">{ICO["print"]}打印 / 存为 PDF</button>
    </div>
    <p class="nav-hint">打印版按 A4 纵向排，自带页眉与页码；打印对话框里请关掉浏览器自己的“页眉和页脚”。</p>
  </div>
</nav>
"""
    page_style = page_rule(f"云网融合创新实践 · {label}", strip_tags(course_title).replace('"', "”")) + (page_css.strip() + "\n" if page_css.strip() else "")
    out = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="generator" content="{generator}">
<title>{title}</title>
{MAINTAIN}
<script id="theme-head">{blocks["theme-head"][1]}</script>
<style id="theme">{blocks["theme"][1]}</style>
<style id="page">
{page_style}</style>
</head>
{shell_top}<main class="doc" id="top">{main}</main>
</div>
<div id="toast" class="toast no-print ui" role="status" aria-hidden="true">投影模式：<kbd>←</kbd><kbd>→</kbd> 按段翻页，<kbd>Esc</kbd> 退出</div>
<div id="live" class="sr-only" role="status" aria-live="polite"></div>
<script id="theme-js">{blocks["theme-js"][1]}</script>
</body>
</html>
"""
    return out.replace(NL, "\n")


def main():
    parser = argparse.ArgumentParser(description="阅读版的共用主题：刷新手工维护的页面里内嵌的样式与脚本")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ret = sub.add_parser("retheme", help="刷新新版页面里内嵌的样式与脚本")
    ret.add_argument("pages", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.pages:
        text = path.read_text(encoding="utf-8")
        new = retheme(text)
        path.write_text(new, encoding="utf-8")
        print(f"{path}：主题已刷新" if new != text else f"{path}：主题已是最新")


if __name__ == "__main__":
    main()
