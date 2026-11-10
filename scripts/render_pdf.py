# -*- coding: utf-8 -*-
"""HTML 成书 → A4 PDF。

用法：
    python render_pdf.py <书目录> [--out 文件名.pdf]

要点：
- 用 print 媒体渲染，@page{size:A4} 由 CSS 决定（prefer_css_page_size）
- 打印时去掉 body 的 max-width 与内边距，否则正文只剩一半宽
- 内联 SVG 走矢量，放大不糊；不需要先跑 png 步骤
- 页脚只放「当前页 / 总页」，不写中文（页脚字体不可控，中文易缺字）

依赖 playwright 的 python 环境（可用 ROADBOOK_PYTHON 指定），浏览器探测顺序：
ROADBOOK_BROWSER → ms-playwright/chromium-* → Edge → Chrome
"""
import os
import re
import sys
import glob
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PRINT_CSS = """
/* 打印专用：@page 负责页边距，body 自己不再留白 */
body{max-width:none !important;margin:0 !important;padding:0 !important}
h1,h2,h3{break-after:avoid;page-break-after:avoid}
h1.part, h2.chap, .chapter{break-before:auto}
tr,li{break-inside:avoid;page-break-inside:avoid}
.fig,.meta,.advice,.warn{break-inside:avoid;page-break-inside:avoid}
table{break-inside:auto}
thead{display:table-header-group}
a{color:#000;text-decoration:none}
svg{max-width:100%}
"""

FOOTER = ('<div style="width:100%;font-size:8.5pt;color:#666;text-align:center;'
          'font-family:Arial,Helvetica,sans-serif">'
          '<span class="pageNumber"></span> / <span class="totalPages"></span></div>')


def find_browser():
    env = os.environ.get("ROADBOOK_BROWSER")
    if env and os.path.exists(env):
        return env
    pats = [
        os.path.expanduser(r"~\AppData\Local\ms-playwright\chromium-*\chrome-win64\chrome.exe"),
        os.path.expanduser(r"~/Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"),
        os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"),
    ]
    cand = []
    for p in pats:
        cand += sorted(glob.glob(p), reverse=True)
    cand += [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ]
    for c in cand:
        if os.path.exists(c):
            return c
    return None


def count_pages(pdf):
    """优先用 pymupdf；没有就数 /Type /Page 对象。

    注意不能读 /Count：Chromium 的页树是嵌套的，第一个 /Count 往往是子树
    的页数（实测 114 页的书，第一个 /Count 是 8），会严重低报。
    """
    try:
        import fitz
        with fitz.open(pdf) as d:
            return d.page_count
    except Exception:
        pass
    data = open(pdf, "rb").read()
    return len(re.findall(rb"/Type\s*/Page[^s]", data))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = os.path.abspath(sys.argv[1])
    import config as CFG

    book = CFG.load(root)
    src = book.path(book.out_html)
    if not os.path.exists(src):
        print(f"[pdf] 找不到 {src}，先跑 build")
        return 1

    out = os.path.join(root, "book.pdf")
    if "--out" in sys.argv:
        out = os.path.join(root, sys.argv[sys.argv.index("--out") + 1])

    from playwright.sync_api import sync_playwright

    exe = find_browser()
    url = "file:///" + src.replace("\\", "/")
    print(f"[pdf] 渲染 {os.path.basename(src)} → {os.path.basename(out)}")
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        pg = b.new_page(viewport={"width": 900, "height": 1280})
        pg.goto(url, wait_until="load")
        pg.emulate_media(media="print")
        pg.add_style_tag(content=PRINT_CSS)
        pg.wait_for_timeout(300)
        pg.pdf(path=out, format="A4", print_background=True,
               prefer_css_page_size=True, display_header_footer=True,
               header_template="<div></div>", footer_template=FOOTER)
        b.close()

    size = os.path.getsize(out)
    n = count_pages(out)
    verts = sum(open(p, encoding="utf-8").read().count("<svg")
                for p in [src])
    print(f"[pdf] {out}")
    print(f"[pdf] {n} 页 · {size/1024:.0f} KB · 内联 SVG {verts} 张（矢量，可放大）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
