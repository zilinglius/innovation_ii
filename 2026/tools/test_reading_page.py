"""新版阅读版的显示与交互测试：在无头 Chrome 里打开页面，核对对齐与溢出、“先想后看”、选中复制、
复制按钮、打勾、预测保存、目录跟随、图放大、投影模式、手机抽屉、深色、打印展开与无脚本回退。

    uv run --with playwright python 2026/tools/test_reading_page.py 2026/docs/network.html [更多页面 …]

需要本机装有 Chrome（脚本用 playwright 驱动系统里的 Chrome，不另外下载浏览器）。源文取同名的 .md。
这是显示层的检查，不代替内容核对（生成器自带的 check）与看截图、看导出的 PDF。
"""
import os, re, subprocess, sys
from playwright.sync_api import sync_playwright

if len(sys.argv) > 2:                      # 多个页面：逐个另起进程，互不影响
    codes = [subprocess.call([sys.executable, __file__, page]) for page in sys.argv[1:]]
    sys.exit(max(codes))
page_path = os.path.abspath(sys.argv[1])
md_path = page_path[:-len(".html")] + ".md"
md = re.sub(r"^> ?", "", open(md_path, encoding="utf-8").read(), flags=re.M)
fences = [m.group(2) for m in re.finditer(r"^```(\w*)\n(.*?)^```\s*$", md, re.S | re.M)]
url = "file://" + page_path
fails, passed = [], 0


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
    else:
        fails.append(f"{name} {detail}")


ALIGN = r"""() => {
  const doc = document.querySelector('.doc').getBoundingClientRect(), bad = [];
  for (const e of document.querySelectorAll('.hero > *, .goals, .route, .plain, .module > *, .next, .colophon')) {
    const r = e.getBoundingClientRect(); if (!r.width) continue;
    if (Math.abs(r.left - doc.left) > 1.5 || r.right > doc.right + 1.5 || (r.width < doc.width - 1.5 && !/^(P|UL|OL|H3|H4|BLOCKQUOTE)$/.test(e.tagName) && getComputedStyle(e).display !== 'inline-block' && !e.matches('.crumbs, h1, .hero-en, .tnote')))
      bad.push(e.tagName + '.' + e.className + ' ' + Math.round(r.left - doc.left) + '/' + Math.round(r.width) + ' vs ' + Math.round(doc.width));
  }
  const inner = [];
  for (const e of document.querySelectorAll('.module *')) {
    if (e.closest('svg, math, pre, .table-wrap, .fig-body, .math-wrap, .math.block, .math-block, .sr-only') ) continue;
    const r = e.getBoundingClientRect(); if (r.width && r.right > doc.right + 2) inner.push(e.tagName + '.' + e.className + ' +' + Math.round(r.right - doc.right));
  }
  return {over: document.documentElement.scrollWidth - innerWidth, bad: bad.slice(0, 5), inner: inner.slice(0, 5), doc: Math.round(doc.width),
          wide: document.querySelectorAll('.table-wrap.is-wide').length};
}"""

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--no-sandbox"])
    errors = []

    def new(w=1440, h=900, **kw):
        ctx = b.new_context(viewport={"width": w, "height": h}, **kw)
        pg = ctx.new_page()
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url)
        pg.add_style_tag(content="html{scroll-behavior:auto !important}")
        pg.wait_for_timeout(250)
        return ctx, pg

    # ---- 版面对齐与溢出
    for w in (1920, 1440, 1100, 820, 390):
        ctx, pg = new(w)
        r = pg.evaluate(ALIGN)
        check(f"{w}px 无页面横向溢出", r["over"] <= 0, str(r["over"]))
        check(f"{w}px 各块与栏对齐", not r["bad"], str(r["bad"]))
        check(f"{w}px 没有内容伸出栏外", not r["inner"], str(r["inner"]))
        if w == 1440:
            check("1440px 栏宽 768", r["doc"] == 768, str(r["doc"]))
            wide1440 = r["wide"]
        ctx.close()

    ctx, pg = new()
    info = pg.evaluate("""() => ({pme: document.querySelectorAll('.pme').length, reveal: document.querySelectorAll('.reveal').length,
      hidden: [...document.querySelectorAll('.reveal-body')].filter(e => e.hasAttribute('hidden')).length,
      ticks: document.querySelectorAll('.tick').length, grp: document.querySelectorAll('.code.cmd .grp').length, cp: document.querySelectorAll('.cp').length,
      figs: document.querySelectorAll('.fig').length, zoom: document.querySelectorAll('.zoom-btn').length, bench: !!document.querySelector('.bench'),
      navprog: getComputedStyle(document.querySelector('.nav-prog')).display, mine: document.querySelectorAll('.mine textarea').length,
      stops: document.querySelectorAll('.stops > li').length, mods: document.querySelectorAll('.module').length, pre: document.querySelectorAll('pre').length})""")
    check("先想后看：收起区默认收起", info["hidden"] == info["reveal"] and info["reveal"] > 0, str(info))
    check("每张预测卡片有“我的预测”输入框", info["mine"] == info["pme"], str(info))
    check("每幅图有放大按钮", info["zoom"] == info["figs"], str(info))
    check("目录站点 = 模块数 + 1", info["stops"] == info["mods"] + 1, str(info))
    check("命令组都有复制按钮", info["cp"] > 0 and info["cp"] <= info["grp"], str(info))
    check("进度条显示位置", (info["navprog"] == "none") == (info["bench"] or info["ticks"] == 0), str(info))

    # ---- 选中复制的文本与 Markdown 逐字相同（先全部展开，避免收起区无法选中）
    pg.evaluate("document.querySelector('.nav .js-think').click()")
    texts = pg.evaluate("""() => [...document.querySelectorAll('pre')].map(pre => { const s = getSelection(); s.removeAllRanges(); const r = document.createRange(); r.selectNodeContents(pre); s.addRange(r); return s.toString(); })""")
    k, miss = 0, 0
    for t in texts:
        while k < len(fences) and fences[k].rstrip("\n") != t.rstrip("\n"):      # 选区末尾的换行符浏览器不计入
            k += 1
        if k == len(fences):
            miss += 1; k = 0
        else:
            k += 1
    check("选中复制与 Markdown 逐字相同", miss == 0 and len(texts) == info["pre"], f"{miss}/{len(texts)} 个对不上")
    check("关闭先想后看后全部展开", pg.evaluate("[...document.querySelectorAll('.reveal-body')].every(e => !e.hasAttribute('hidden'))"))
    pg.evaluate("document.querySelector('.nav .js-think').click()")

    # ---- 展开一处收起区
    opened = pg.evaluate("""() => { const b = document.querySelector('.reveal-btn'); b.click(); const r = b.closest('.reveal'); return r.classList.contains('is-open') && !r.querySelector('.reveal-body').hasAttribute('hidden'); }""")
    check("点击展开收起区", opened)

    # ---- 复制按钮：复制的是命令行，不含注释
    cp = pg.evaluate("""() => { const g = document.querySelector('.code.cmd .grp .cp').parentNode; let got = null;
      navigator.clipboard.writeText = t => { got = t; return Promise.resolve(); };
      g.querySelector('.cp').click();
      return {got, want: [...g.querySelectorAll('.ln.x')].map(l => l.textContent.replace(/\\n$/, '')).join('\\n')}; }""")
    pg.wait_for_timeout(100)
    check("复制按钮复制命令行", cp["got"] == cp["want"] and cp["want"], str(cp)[:120])

    # ---- 打勾与进度、刷新后保留、清零
    if info["ticks"]:
        pg.evaluate("document.querySelectorAll('.tick')[0].click(); document.querySelectorAll('.tick')[document.querySelectorAll('.tick').length - 1].click()")
        prog = pg.evaluate("document.querySelector('.js-prog').textContent")
        check("打勾后进度更新", prog == f"2 / {info['ticks']}" if info["ticks"] > 1 else prog.startswith("1"), prog)
        pg.reload(); pg.wait_for_timeout(200)
        st = pg.evaluate("[...document.querySelectorAll('.tick')].map(t => t.getAttribute('aria-checked') === 'true')")
        check("刷新后打勾保留", st[0] and st[-1] and sum(st) == min(2, info["ticks"]), str(sum(st)))
        pg.evaluate("document.querySelector('.js-reset').click()")
        check("清零", pg.evaluate("document.querySelectorAll('.tick[aria-checked=true]').length") == 0)
    # ---- 我的预测保存
    if info["pme"]:
        pg.fill(".mine textarea", "我的预测 abc"); pg.wait_for_timeout(450)
        pg.reload(); pg.wait_for_timeout(200)
        check("写下的预测刷新后保留", pg.evaluate("document.querySelector('.mine textarea').value") == "我的预测 abc")
        pg.fill(".mine textarea", ""); pg.wait_for_timeout(450)

    # ---- 目录跟随
    pg.add_style_tag(content="html{scroll-behavior:auto !important}")
    pg.evaluate("window.scrollTo({top: document.querySelectorAll('.module')[2].getBoundingClientRect().top + scrollY + 200, behavior: 'instant'})")
    pg.wait_for_timeout(250)
    nav = pg.evaluate("""() => { const a = document.querySelector('.stops > li.active'); return {t: a && a.getAttribute('data-target'), done: document.querySelectorAll('.stops > li.done').length, want: document.querySelectorAll('.module')[2].id}; }""")
    check("目录跟随当前模块", nav["t"] == nav["want"] and nav["done"] == 3, str(nav))

    # ---- 图放大、Esc 关闭
    if info["figs"]:
        pg.evaluate("document.querySelector('.zoom-btn').click()")
        z = pg.evaluate("document.querySelector('.fig.zoom') !== null")
        pg.keyboard.press("Escape")
        check("图放大与 Esc 关闭", z and pg.evaluate("document.querySelector('.fig.zoom') === null"))

    # ---- 投影模式
    pg.evaluate("document.querySelector('.nav .js-present').click()"); pg.wait_for_timeout(250)
    fs = pg.evaluate("getComputedStyle(document.documentElement).fontSize")
    y0 = pg.evaluate("scrollY"); pg.keyboard.press("ArrowRight"); pg.wait_for_timeout(700); y1 = pg.evaluate("scrollY")
    r = pg.evaluate(ALIGN)
    check("投影模式放大字号并可按键翻段", fs == "22px" and y1 > y0, f"{fs} {y0}->{y1}")
    check("投影模式无溢出、对齐", r["over"] <= 0 and not r["bad"] and not r["inner"], str(r))
    pg.keyboard.press("Escape")
    check("Esc 退出投影", not pg.evaluate("document.documentElement.classList.contains('present')"))
    ctx.close()

    # ---- 手机：抽屉目录
    ctx, pg = new(390, 844)
    pg.evaluate("document.querySelector('.js-toc-open').click()"); pg.wait_for_timeout(300)
    check("手机抽屉目录可打开", pg.evaluate("document.querySelector('#toc').classList.contains('open') && document.querySelector('.doc').inert"))
    ctx.close()

    # ---- 深色
    ctx, pg = new(color_scheme="dark")
    bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    check("深色主题", bg == "rgb(18, 19, 23)", bg)
    ctx.close()

    # ---- 打印：全部展开，控件隐藏
    ctx, pg = new()
    pg.emulate_media(media="print")
    pr = pg.evaluate("""() => ({hiddenShown: [...document.querySelectorAll('.reveal-body')].every(e => getComputedStyle(e).display !== 'none' && getComputedStyle(e).contentVisibility !== 'hidden'),
      nav: getComputedStyle(document.querySelector('.nav')).display, cp: getComputedStyle(document.querySelector('.cp')).display})""")
    check("打印时全部展开、控件隐藏", pr["hiddenShown"] and pr["nav"] == "none" and pr["cp"] == "none", str(pr))
    ctx.close()

    # ---- 无脚本
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, java_script_enabled=False)
    pg = ctx.new_page(); pg.goto(url); pg.wait_for_timeout(200)
    nojs = pg.eval_on_selector_all(".reveal-body", "els => els.every(e => !e.hasAttribute('hidden') && e.getBoundingClientRect().height > 0)")
    check("无脚本时内容全部可见", nojs)
    ctx.close()
    check("控制台无报错", not errors, str(errors[:3]))
    b.close()

name = page_path.rsplit("/", 1)[1]
print(f"{name}: {passed} 项通过，{len(fails)} 项未通过；预测卡片 {info['pme']}，收起区 {info['reveal']}，可打勾步骤 {info['ticks']}，图 {info['figs']}，1440px 下需横向滚动的表 {wide1440}")
for f in fails:
    print("   ✗", f[:400])
sys.exit(1 if fails else 0)
