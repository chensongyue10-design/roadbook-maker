# -*- coding: utf-8 -*-
"""把 figs/*.svg 渲染成 PNG（供飞书上传、也方便肉眼验收）。

用法
----
    python render_png.py <项目目录> [--scale 2] [--only fig-01 fig-02]

设计要点
--------
1. 尺寸从 SVG 的 viewBox 里读，不再维护 SIZES 手写表
   （历史坑 #5：表里 fig-12 写 640、实际 viewBox 520，多出 120px 白边）。
2. 浏览器按「环境变量 → ms-playwright 最新版 → Edge → 系统 Chrome」顺序探测
   （历史坑 #16：写死 chromium-1248，换机器必挂）。
3. 用 `<img src="file://...svg">` 而不是 set_content，避免 SVG 里的
   `<?xml?>` 声明或编码问题。
"""
from __future__ import annotations

import glob
import io
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as CFG  # noqa: E402


def find_browser() -> str | None:
    """按可靠性从高到低探测浏览器可执行文件。"""
    env = os.environ.get("ROADBOOK_BROWSER")
    if env and os.path.exists(env):
        return env
    pats = [
        os.path.expanduser(r"~\AppData\Local\ms-playwright\chromium-*\chrome-win64\chrome.exe"),
        os.path.expanduser(r"~/Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"),
        os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"),
    ]
    cands: list[str] = []
    for p in pats:
        cands += sorted(glob.glob(p), reverse=True)
    cands += [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
        shutil.which("microsoft-edge") or "",
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def viewbox_of(svg_path: str) -> tuple[int, int]:
    head = open(svg_path, encoding="utf-8", errors="ignore").read(600)
    m = re.search(r'viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)"', head)
    if not m:
        raise ValueError(f"{os.path.basename(svg_path)} 没有 viewBox，无法确定尺寸")
    return int(float(m.group(1)) + 0.5), int(float(m.group(2)) + 0.5)


def render(root=".", scale=2, only=None):
    book = CFG.load(root)
    os.makedirs(book.png_path, exist_ok=True)
    exe = find_browser()
    if not exe:
        print("找不到可用浏览器。设置环境变量 ROADBOOK_BROWSER 指向 chrome/edge 可执行文件。",
              file=sys.stderr)
        return 1
    from playwright.sync_api import sync_playwright

    svgs = []
    for fid, f in book.figures.items():
        p = os.path.join(book.fig_dir, f.svg)
        if not os.path.exists(p):
            print(f"[缺 SVG] {f.svg}", file=sys.stderr)
            continue
        if only and fid not in only:
            continue
        svgs.append((p, fid, *viewbox_of(p)))

    done = 0
    import base64
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=exe)
        for svg, fid, w, h in svgs:
            # 用 base64 data URI 内嵌 SVG：中文路径的 file:// 会加载失败
            data = base64.b64encode(open(svg, "rb").read()).decode("ascii")
            html = (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
                    f'<style>html,body{{margin:0;padding:0;background:#fff}}'
                    f'img{{display:block;width:{w}px;height:{h}px}}</style></head>'
                    f'<body><img src="data:image/svg+xml;base64,{data}"></body></html>')
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
            pg.set_content(html, wait_until="load")
            out = os.path.join(book.png_path, f"{fid}.png")
            pg.screenshot(path=out, clip={"x": 0, "y": 0, "width": w, "height": h})
            pg.close()
            done += 1
            print(f"  {fid:22s} {w}x{h} → {scale}x  {os.path.getsize(out)//1024} KB")
        b.close()
    print(f"完成 {done}/{len(book.figures)} 张，浏览器：{exe}")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = args[0] if args else "."
    scale = 2
    if "--scale" in sys.argv:
        scale = int(sys.argv[sys.argv.index("--scale") + 1])
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only") + 1
        only = set(a for a in sys.argv[i:] if not a.startswith("-"))
    sys.exit(render(root, scale, only))
