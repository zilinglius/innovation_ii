(function () {
  var d = document, root = d.documentElement, PAGE = (d.body.getAttribute("data-page") || "page");
  function $(s, c) { return (c || d).querySelector(s); }
  function $$(s, c) { return Array.prototype.slice.call((c || d).querySelectorAll(s)); }
  // 本地存储：外观、先想后看两项偏好，以及本页的打勾进度和写下的预测。读写失败时页面照常工作。
  function load(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } }
  function save(k, v) { try { window.localStorage.setItem(k, v); } catch (e) {} }
  function loadObj(k) { try { return JSON.parse(load(k) || "{}") || {}; } catch (e) { return {}; } }
  function say(t) { var r = $("#live"); if (r) { r.textContent = ""; window.setTimeout(function () { r.textContent = t; }, 30); } }
  function el(tag, cls, html) { var e = d.createElement(tag); if (cls) e.className = cls; if (html) e.innerHTML = html; return e; }
  function typing(e) { var t = e.target; return t && (t.tagName === "TEXTAREA" || t.tagName === "INPUT" || t.isContentEditable); }
  var ICON = {
    copy: '<svg class="i-cp" viewBox="0 0 20 20" aria-hidden="true"><rect x="7" y="7" width="9.5" height="9.5" rx="1.6"/><path d="M12.5 4.5v-.4A1.6 1.6 0 0 0 10.9 2.5H5.1A1.6 1.6 0 0 0 3.5 4.1v5.8a1.6 1.6 0 0 0 1.6 1.6h.4"/></svg><svg class="i-ok" viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 10.5l3.6 3.6 7.4-8"/></svg>',
    check: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 10.5l3.2 3.2L15 6.5"/></svg>',
    zoom: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 8V3.5H8M12 3.5h4.5V8M16.5 12v4.5H12M8 16.5H3.5V12"/></svg>'
  };

  // ---------- 打印 ----------
  $$(".js-print").forEach(function (b) { b.addEventListener("click", function () { window.print(); }); });

  // ---------- 外观：跟随系统 → 浅色 → 深色 ----------
  var THEMES = ["auto", "light", "dark"], THEME_T = { auto: "跟随系统", light: "浅色", dark: "深色" };
  var theme = load("iilec-theme"); if (THEMES.indexOf(theme) < 0) theme = "auto";
  function applyTheme() {
    if (theme === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", theme);
    $$(".js-theme").forEach(function (b) {
      b.setAttribute("data-mode", theme); b.setAttribute("aria-label", "外观：" + THEME_T[theme] + "，点击切换");
      var l = $(".js-theme-t", b); if (l) l.textContent = THEME_T[theme];
    });
  }
  $$(".js-theme").forEach(function (b) {
    b.addEventListener("click", function () { theme = THEMES[(THEMES.indexOf(theme) + 1) % 3]; save("iilec-theme", theme); applyTheme(); say("外观：" + THEME_T[theme]); });
  });
  applyTheme();

  // ---------- 紧凑版面（窄屏或投影）与抽屉目录 ----------
  var toc = $("#toc"), scrim = $(".scrim"), doc = $(".doc"), opener = null, narrowMq = window.matchMedia("(max-width: 67.99em)");
  function compact() { return root.classList.contains("compact"); }
  function setDrawer(open) {
    if (!toc) return;
    toc.classList.toggle("open", open); if (scrim) scrim.classList.toggle("open", open);
    if (doc) doc.inert = open;                              // 抽屉打开时，键盘焦点不落到被遮住的正文
    $$(".js-toc-open").forEach(function (b) { b.setAttribute("aria-expanded", open ? "true" : "false"); });
    if (open) {
      var cur = $(".subs li.cur > a", toc) || $(".stops > li.active > a", toc);
      if (cur) { cur.scrollIntoView({ block: "center" }); cur.focus({ preventScroll: true }); }
    } else if (opener) { opener.focus({ preventScroll: true }); opener = null; }
  }
  function drawerOpen() { return toc && toc.classList.contains("open"); }
  function syncCompact() {
    var want = narrowMq.matches || root.classList.contains("present");
    if (!want && drawerOpen()) { opener = null; setDrawer(false); }
    root.classList.toggle("compact", want);
  }
  narrowMq.addEventListener("change", syncCompact);
  $$(".js-toc-open").forEach(function (b) { b.addEventListener("click", function () { opener = b; setDrawer(!drawerOpen()); }); });
  $$(".js-toc-close").forEach(function (b) { b.addEventListener("click", function () { setDrawer(false); }); });
  if (scrim) scrim.addEventListener("click", function () { setDrawer(false); });
  if (toc) toc.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("a[href^='#']") && compact()) { opener = null; setDrawer(false); }
  });

  // ---------- 位置：当前模块、小节、实验步骤；线路上的站点状态 ----------
  var marks = [], stopLi = {}, subLi = {}, order = [];
  $$(".stops > li[data-target]").forEach(function (li) { stopLi[li.getAttribute("data-target")] = li; order.push(li.getAttribute("data-target")); });
  $$(".subs a[href^='#']").forEach(function (a) { subLi[a.getAttribute("href").slice(1)] = a.parentNode; });
  (function collect() {
    var hero = $(".hero"), first = $(".stops > li[data-target='top'] a");
    if (hero) marks.push({ el: hero, mod: "top", sub: null, step: null, text: first ? first.textContent : "导读" });
    $$(".module").forEach(function (m) {
      var no = $(".module-no", m), h2 = $("h2", m), base = (no ? no.textContent : "") + " · ";
      marks.push({ el: m, mod: m.id, sub: null, step: null, text: base + (h2 ? h2.textContent : "") });
      var sub = null;
      // 实验页的任务层级（header.tier）当作小节，任务标题（header.task-head）当作步骤
      $$("h3[id], h4[id], header.tier[id], header.task-head[id]", m).forEach(function (h) {
        if (h.tagName === "HEADER") {
          var t = $("h3, h4", h), no = $(".task-no", h), tier = h.classList.contains("tier");
          if (tier) sub = h.id;
          marks.push({ el: h, mod: m.id, sub: sub, step: tier ? null : h.id, text: base + (no ? no.textContent + " " : "") + (t ? t.textContent : "") });
        } else if (h.tagName === "H3") {
          sub = h.id; var n = $(".sec-no", h), t = h.textContent;
          marks.push({ el: h, mod: m.id, sub: sub, step: null, text: base + (n ? n.textContent + " " + t.slice(n.textContent.length) : t) });
        } else marks.push({ el: h, mod: m.id, sub: sub, step: h.id, text: base + h.textContent });
      });
    });
  })();
  var locEl = $(".js-loc"), mini = $$(".mini i"), last = {};
  function current() {
    var line = Math.max(90, window.innerHeight * 0.22), cur = marks[0], i, top;
    for (i = 0; i < marks.length; i++) {
      top = marks[i].el.getBoundingClientRect().top;
      if (top <= line) cur = marks[i]; else if (top > window.innerHeight) break;
    }
    return cur;
  }
  function spy() {
    var cur = current(); if (!cur) return;
    if (cur.mod !== last.mod) {
      var at = order.indexOf(cur.mod);
      order.forEach(function (k, i) { stopLi[k].classList.toggle("active", i === at); stopLi[k].classList.toggle("done", i < at); });
      mini.forEach(function (m) { var i = order.indexOf(m.getAttribute("data-target")); m.classList.toggle("active", i === at); m.classList.toggle("done", i < at); });
    }
    if (cur.sub !== last.sub || cur.step !== last.step)
      Object.keys(subLi).forEach(function (k) { subLi[k].classList.toggle("cur", k === cur.sub || k === cur.step); });
    if (cur !== last.cur) {
      if (locEl) locEl.textContent = cur.text;
      if (toc && !compact() && toc.scrollHeight > toc.clientHeight) {
        var a = (cur.step && subLi[cur.step]) || (cur.sub && subLi[cur.sub]) || stopLi[cur.mod];
        if (a) { var r = a.getBoundingClientRect(); if (r.top < 60 || r.bottom > window.innerHeight - 220) toc.scrollTop += r.top - window.innerHeight * 0.35; }
      }
    }
    last = { mod: cur.mod, sub: cur.sub, step: cur.step, cur: cur };
  }
  var ticking = false;
  function onScroll() { if (!ticking) { ticking = true; window.requestAnimationFrame(function () { ticking = false; spy(); }); } }
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);

  // ---------- 投影模式：放大字号，收起侧栏，左右方向键按段翻 ----------
  function barH() { var b = $(".topbar"); return b && compact() ? b.offsetHeight : 0; }
  function setPresent(on) {
    var keep = current();
    root.classList.toggle("present", on); syncCompact(); fitTables(); fitMath();
    $$(".js-present").forEach(function (b) { b.setAttribute("aria-pressed", on ? "true" : "false"); });
    if (keep && keep.mod !== "top") window.requestAnimationFrame(function () {
      window.scrollTo({ top: keep.el.getBoundingClientRect().top + window.scrollY - barH() - 16, behavior: "instant" });
    });
    say(on ? "投影模式已开启：左右方向键按段翻页，Esc 退出" : "投影模式已关闭");
    var t = $("#toast"); if (t) { t.classList.toggle("show", on); window.clearTimeout(t._t); if (on) t._t = window.setTimeout(function () { t.classList.remove("show"); }, 4200); }
  }
  $$(".js-present").forEach(function (b) { b.addEventListener("click", function () { setPresent(!root.classList.contains("present")); }); });
  function step(dir) {
    var y = window.scrollY, vh = window.innerHeight, page = vh * 0.85, target;
    var tops = $$(".opener, h3[id], h4[id], .tier, .task-head, .fig, .pme, .questions > li, .qs > li, .module > ol:not(.qs) > li[id^='q']").map(function (e) {
      return Math.round(e.getBoundingClientRect().top + y - barH() - 16 - (e.closest(".labzone") ? 52 : 0));
    }).sort(function (a, b) { return a - b; });
    if (dir > 0) { target = tops.filter(function (t) { return t > y + 4; })[0]; if (target === undefined || target > y + page) target = y + page; }
    else { var prev = tops.filter(function (t) { return t < y - 4; }); target = prev.length ? prev[prev.length - 1] : 0; if (target < y - page) target = y - page; }
    window.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
  }

  // ---------- 图：放大到整屏 ----------
  var zoomed = null, holder = null;
  function setZoom(f, on) {
    if (zoomed && zoomed !== f) setZoom(zoomed, false);
    var b = $(".zoom-btn", f);
    if (on) {
      holder = el("div", "fig-holder"); holder.style.height = f.offsetHeight + "px"; holder.style.margin = window.getComputedStyle(f).margin;
      f.parentNode.insertBefore(holder, f); f.classList.add("zoom"); root.classList.add("zooming"); zoomed = f;
    } else {
      f.classList.remove("zoom"); root.classList.remove("zooming"); zoomed = null;
      if (holder && holder.parentNode) holder.parentNode.removeChild(holder); holder = null;
    }
    if (b) { $("span", b).textContent = on ? "关闭" : "放大"; b.setAttribute("aria-pressed", on ? "true" : "false"); b.focus({ preventScroll: true }); }
  }
  $$(".fig").forEach(function (f) {
    var cap = $("figcaption b", f), b = el("button", "zoom-btn no-print", ICON.zoom + "<span>放大</span>");
    b.type = "button"; b.setAttribute("aria-pressed", "false"); b.setAttribute("aria-label", "放大" + (cap ? cap.textContent : "这幅图") + "到整屏");
    b.addEventListener("click", function () { setZoom(f, !f.classList.contains("zoom")); });
    f.insertBefore(b, f.firstChild);
  });

  // ---------- 键盘 ----------
  d.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      if (zoomed) setZoom(zoomed, false); else if (drawerOpen()) setDrawer(false); else if (root.classList.contains("present")) setPresent(false);
      return;
    }
    if (!root.classList.contains("present") || zoomed || drawerOpen() || typing(e) || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === "ArrowRight") { e.preventDefault(); step(1); } else if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
  });

  // ---------- 命令：逐步复制 ----------
  function copyText(t) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(t);
    return new Promise(function (ok, fail) {
      var ta = d.createElement("textarea"); ta.value = t; ta.setAttribute("readonly", "");
      ta.style.cssText = "position:fixed;top:0;left:0;opacity:0"; d.body.appendChild(ta); ta.select();
      try { d.execCommand("copy") ? ok() : fail(); } catch (e) { fail(e); } finally { d.body.removeChild(ta); }
    });
  }
  $$(".code.cmd .grp").forEach(function (g) {
    var cmds = $$(".ln.x", g).map(function (l) { return l.textContent.replace(/\n$/, ""); });
    if (!cmds.length) return;
    var n = g.getAttribute("data-step"), what = n ? "第 " + n + " 步的命令" : "这组命令";
    var b = el("button", "cp no-print", ICON.copy); b.type = "button";
    b.setAttribute("aria-label", "复制" + what); b.title = "复制" + what + "（不含注释行）";
    b.addEventListener("click", function () {
      copyText(cmds.join("\n")).then(function () {
        b.classList.add("ok"); say("已复制" + what);
        window.clearTimeout(b._t); b._t = window.setTimeout(function () { b.classList.remove("ok"); }, 1600);
      }, function () { say("复制失败，请手动选中命令复制"); });
    });
    g.appendChild(b);
  });

  // ---------- 实验步骤：打勾与进度 ----------
  var KEY_STEPS = "iilec:" + PAGE + ":steps", done = loadObj(KEY_STEPS), ticks = [], progEls = $$(".js-prog");
  function showProgress() {
    var n = ticks.filter(function (t) { return t.getAttribute("aria-checked") === "true"; }).length;
    progEls.forEach(function (p) { p.textContent = n + " / " + ticks.length; });
    $$(".nav-prog").forEach(function (p) { p.classList.toggle("on", ticks.length > 0 && !$(".bench")); });
  }
  function setTick(t, on) { t.setAttribute("aria-checked", on ? "true" : "false"); t.parentNode.classList.toggle("is-done", on); }
  // 有实验区（.labzone）的页只在实验区内打勾；其余页所有带序号的步骤都可以打勾。按出现顺序记录。
  $$(($(".labzone") ? ".labzone " : "") + ".code.cmd .grp[data-step]").forEach(function (g, k) {
    var n = g.getAttribute("data-step"), t = el("button", "tick no-print", ICON.check);
    t.type = "button"; t.setAttribute("role", "checkbox"); t.setAttribute("aria-label", "第 " + n + " 步已完成");
    g.classList.add("has-tick"); g.insertBefore(t, g.firstChild); setTick(t, !!done[k]); ticks.push(t);
    t.addEventListener("click", function () {
      var on = t.getAttribute("aria-checked") !== "true"; setTick(t, on);
      if (on) done[k] = 1; else delete done[k];
      save(KEY_STEPS, JSON.stringify(done)); showProgress();
    });
  });
  showProgress();
  $$(".js-reset").forEach(function (b) {
    b.addEventListener("click", function () { done = {}; save(KEY_STEPS, "{}"); ticks.forEach(function (t) { setTick(t, false); }); showProgress(); say("进度已清零"); });
  });

  // ---------- 我的预测：写下来再测量 ----------
  var KEY_MINE = "iilec:" + PAGE + ":predict", mine = loadObj(KEY_MINE), saveTimer = 0;
  $$(".pme").forEach(function (card, i) {
    var body = $(".pme-step .pme-body", card); if (!body) return;
    var wrap = el("label", "mine ui", "<span>我的预测<i>（只保存在这台电脑的浏览器里）</i></span>"), ta = d.createElement("textarea");
    ta.rows = 2; ta.placeholder = "先写下你的预测，再往下看。"; ta.value = mine[i] || "";
    ta.addEventListener("input", function () {
      if (ta.value) mine[i] = ta.value; else delete mine[i];
      window.clearTimeout(saveTimer); saveTimer = window.setTimeout(function () { save(KEY_MINE, JSON.stringify(mine)); }, 300);
    });
    wrap.appendChild(ta); body.appendChild(wrap);
  });

  // ---------- “先想后看”：样例输出与思考提示先收起 ----------
  var reveals = $$(".reveal").map(function (r, i) {
    var body = $(".reveal-body", r), kind = r.getAttribute("data-kind"), hint = kind === "hint", open = false;
    var what = kind === "ans" ? "解读" : "样例输出与解读";
    var btn = el("button", "reveal-btn no-print", '<span class="rv-t"></span><span class="rv-s"></span>'); btn.type = "button";
    body.id = body.id || "rv-" + (i + 1); btn.setAttribute("aria-controls", body.id);
    body.parentNode.insertBefore(btn, body);
    function set(v) {
      open = v; r.classList.toggle("is-open", v); btn.setAttribute("aria-expanded", v ? "true" : "false");
      if (v) body.removeAttribute("hidden"); else body.setAttribute("hidden", "until-found");
      $(".rv-t", btn).textContent = v ? (hint ? "收起提示" : "收起" + what) : (hint ? "看思考提示" : "展开" + what);
      $(".rv-s", btn).textContent = v || hint ? "" : (kind === "ans" ? "先写下预测，再对照" : "先自己运行一遍，再对照");
    }
    btn.addEventListener("click", function () { set(!open); });
    body.addEventListener("beforematch", function () { set(true); });       // 页内查找命中收起的内容时自动展开
    return { set: set, isOpen: function () { return open; } };
  });
  var think = load("iilec-think") !== "off";
  function applyThink() {
    root.classList.toggle("think", think);
    reveals.forEach(function (r) { r.set(!think); });
    $$(".js-think").forEach(function (b) { b.setAttribute("aria-checked", think ? "true" : "false"); });
  }
  $$(".js-think").forEach(function (b) {
    if (!reveals.length) b.hidden = true;                    // 没有可收起内容的页（多数回顾页）不显示这个开关
    b.addEventListener("click", function () {
      think = !think; save("iilec-think", think ? "on" : "off"); applyThink();
      say(think ? "先想后看已开启：样例输出与思考提示先收起" : "先想后看已关闭：全部内容展开");
    });
  });
  applyThink();
  var before = null;
  window.addEventListener("beforeprint", function () {
    if (zoomed) setZoom(zoomed, false);
    before = reveals.map(function (r) { return r.isOpen(); }); reveals.forEach(function (r) { r.set(true); });
  });
  window.addEventListener("afterprint", function () { if (before) reveals.forEach(function (r, i) { r.set(before[i]); }); before = null; });

  // ---------- 表格：比栏宽还宽的在自己的框里横向滚动，其余表头吸顶 ----------
  function fitTables() {
    $$(".table-wrap").forEach(function (w) {
      var t = $("table", w); if (!t) return;
      w.classList.remove("is-wide"); w.classList.toggle("is-wide", t.scrollWidth > w.clientWidth + 1);
    });
  }
  window.addEventListener("resize", fitTables);
  window.addEventListener("load", fitTables);
  if (d.fonts && d.fonts.ready) d.fonts.ready.then(fitTables);      // 内嵌字体生效后列宽会变，重新量一次

  // ---------- 行内公式：窄屏上比栏还宽的那几个，改成可以在自己的框里横向滚动 ----------
  function fitMath() {
    if (!doc) return;
    var right = doc.getBoundingClientRect().right + 1;
    $$(".math.inline").forEach(function (m) {
      m.classList.remove("is-wide");
      if (m.getBoundingClientRect().right > right) m.classList.add("is-wide");
    });
  }
  window.addEventListener("resize", fitMath);
  window.addEventListener("load", fitMath);

  syncCompact(); fitTables(); fitMath(); spy();
  if (window.location.hash.length > 1) {      // 带 #锚点 打开：收起内容后版面高度变了，重新对齐一次
    var target = d.getElementById(decodeURIComponent(window.location.hash.slice(1)));
    if (target) window.requestAnimationFrame(function () { target.scrollIntoView(); });
  }
})();
