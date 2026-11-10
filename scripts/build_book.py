# -*- coding: utf-8 -*-
"""合并成书：所有章节 → 单文件 HTML，地图 SVG 内联到占位框位置。

用法
----
    python build_book.py <项目目录> [--no-check]

输入：<项目目录>/book.toml + 各章 .html + figs/*.svg
输出：<项目目录>/<book.out_html>

和旧版（海南 scripts/build_book.py）的区别
------------------------------------------
1. 章节顺序、图 id、图注、宽度全部读 book.toml，不再有 CHAPTERS 常量。
2. 占位框用深度匹配找闭合 div，内层有 div 也不会被截断（历史坑 #1）。
3. 图注统一由配置生成并自动编号，不再靠占位框里的「地图位置：」前缀
   （历史坑 #2：13 张图只有 12 条图注）。
4. 支持 [[part]]：给一组章节加真正的上级 h1，章标题降为 h2.chap，
   目录里的「第二章 六天行程」不再凭空消失（历史坑 #10）。
"""
from __future__ import annotations

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as CFG  # noqa: E402

# 目录里 assets/book.css 优先；没有就用这份内置兜底（两者应保持一致）
FALLBACK_CSS = """
  @page{size:A4;margin:22mm 24mm}
  *{box-sizing:border-box}
  body{font-family:"Songti SC","SimSun","宋体",serif;background:#fff;color:#000;
       line-height:1.7;font-size:10.5pt;max-width:820px;margin:0 auto;padding:36px 46px 64px}
  .chapter{page-break-after:always}
  h1{font-size:15pt;font-weight:700;text-align:center;margin:0 0 4px}
  h1.part{font-size:19pt;letter-spacing:6px;text-align:center;margin:0;padding:180px 0 0}
  h2.chap{font-size:15pt;font-weight:700;text-align:center;border:0;
          margin:0 0 4px;padding:0;line-height:normal}
  .sub{font-size:10pt;text-align:center;color:#333;margin:0 0 26px}
  h2{font-size:12pt;font-weight:700;margin:26px 0 10px;padding-bottom:4px;border-bottom:1px solid #999}
  h3{font-size:11pt;font-weight:700;margin:18px 0 6px}
  p{margin:7px 0}
  table{width:100%;border-collapse:collapse;margin:10px 0 14px;font-size:10pt}
  th{border:1px solid #808080;padding:5px 7px;background:#f2f2f2;font-weight:700;text-align:left}
  td{border:1px solid #808080;padding:5px 7px;vertical-align:top}
  td.n{text-align:right;white-space:nowrap}
  td.c{text-align:center}
  .meta{border:1px solid #999;padding:10px 14px;background:#fcfcfc;margin:14px 0;font-size:10pt}
  .meta p{margin:3px 0}
  .advice{border:1px solid #bbb;border-left:6px solid #666;padding:12px 16px;background:#fafafa;margin:14px 0}
  .advice .tag{font-weight:700;display:block;margin-bottom:4px}
  .advice p{margin:5px 0}
  .warn{border:1px solid #666;padding:12px 16px;background:#f7f7f7;margin:14px 0}
  .warn .tag{font-weight:700;display:block;margin-bottom:4px}
  .imgph{border:1px solid #999;background:#fafafa;padding:14px 16px;margin:14px 0;font-size:9.5pt;color:#333}
  .imgph b{display:block;margin-bottom:4px}
  .fig{border:1px solid #999;padding:8px;margin:16px 0;background:#fff;page-break-inside:avoid}
  .fig svg{display:block;width:100%;height:auto}
  .figcap{font-size:9.5pt;text-align:center;margin-top:6px;color:#222}
  ul,ol{margin:7px 0 7px 0;padding-left:22px}
  li{margin:3px 0}
  .foot{margin-top:40px;border-top:1px solid #000;padding-top:10px;font-size:9pt;display:flex;justify-content:space-between}
  .note{font-size:9pt;color:#333}
  .cover{text-align:center;padding:120px 0 90px;border-bottom:1px solid #000;margin-bottom:30px}
  .cover .t1{font-size:30pt;font-weight:700;letter-spacing:10px;margin:0 0 18px}
  .cover .t2{font-size:12pt;color:#333;margin:0 0 8px}
  .cover .t3{font-size:10.5pt;color:#333;margin:26px 0 0}
  .cover .t4{font-size:9.5pt;color:#333;margin-top:60px}
"""


def load_css():
    for p in (os.path.join(HERE, "..", "assets", "book.css"),
              os.path.join(HERE, "book.css")):
        if os.path.exists(p):
            return open(p, encoding="utf-8").read()
    return FALLBACK_CSS


def body_of(path: str) -> str:
    html = open(path, encoding="utf-8").read()
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    return m.group(1) if m else html


def demote_title(body: str) -> str:
    """章标题 h1 → h2.chap（保留视觉，修正结构层级）。只动第一个 h1。"""
    def rep(m):
        attrs = m.group(1) or ""
        attrs = re.sub(r'\sclass="[^"]*"', "", attrs)
        return f'<h2 class="chap"{attrs}>'
    out, n = re.subn(r"<h1([^>]*)>", rep, body, count=1)
    if n:
        out = re.sub(r"</h1>", "</h2>", out, count=1)
    return out


def replace_placeholders(body: str, ch, book, caps) -> tuple[str, int]:
    """按占位框位置插入 SVG。返回 (新正文, 命中数)。"""
    pairs = CFG.resolve_figures(body, ch, book)
    if not pairs:
        return body, 0
    out, cursor = [], 0
    for ph, fid in pairs:
        out.append(body[cursor:ph["start"]])
        f = book.figures[fid]
        svg_path = os.path.join(book.fig_dir, f.svg)
        if not os.path.exists(svg_path):
            out.append(ph["text"])
            cursor = ph["end"]
            print(f"  [缺图] {f.svg}（保留占位框）", file=sys.stderr)
            continue
        svg = open(svg_path, encoding="utf-8").read()
        if f.width_html:
            style = f'max-width:{f.width_html}px;margin-left:auto;margin-right:auto'
            out.append(f'<div class="fig" style="{style}">{svg}'
                       f'<div class="figcap">{caps[fid]}</div></div>')
        else:
            out.append(f'<div class="fig">{svg}'
                       f'<div class="figcap">{caps[fid]}</div></div>')
        cursor = ph["end"]
    out.append(body[cursor:])
    return "".join(out), len(pairs)


def build(root=".", check=True) -> dict:
    book = CFG.load(root)
    caps = book.numbered_captions()
    css = load_css()

    head = (f'<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="UTF-8">'
            f'<title>{book.title} · {book.subtitle} {book.version}</title>\n'
            f"<style>{css}</style></head><body>\n")
    parts = [head]
    missing, stats = [], {"fg": 0, "ph_left": 0, "parts": 0}
    seen_part = set()

    for ch in book.chapters:
        path = book.path(ch.file)
        if not os.path.exists(path):
            missing.append(ch.file)
            continue
        # 部首页
        if ch.part and ch.part not in seen_part:
            seen_part.add(ch.part)
            p = book.part_of(ch)
            parts.append(f'<div class="chapter"><h1 class="part">{p.title}</h1></div>\n')
            stats["parts"] += 1
        body = body_of(path)
        if ch.part and ch.demote:
            body = demote_title(body)
        body, n = replace_placeholders(body, ch, book, caps)
        stats["fg"] += n
        parts.append(f'<div class="chapter">\n{body}\n</div>\n')

    parts.append("</body></html>")
    html = "\n".join(parts)
    out_path = book.path(book.out_html)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    stats["ph_left"] = len(CFG.scan_placeholders(html))
    print(f"章节 {len(book.chapters) - len(missing)}/{len(book.chapters)}"
          f"　部 {stats['parts']}　插图 {stats['fg']}/{len(book.figures)}"
          f"　残留占位 {stats['ph_left']}")
    if missing:
        print("缺章:", missing, file=sys.stderr)
    print("中文字数:", len(re.findall(r"[\u4e00-\u9fff]", html)))
    print("字节:", len(html.encode("utf-8")), "→", out_path)

    if check and (missing or stats["ph_left"]):
        return {**stats, "missing": missing, "ok": False}
    return {**stats, "missing": missing, "ok": True}


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    root = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "."
    r = build(root, check="--no-check" not in sys.argv)
    sys.exit(0 if r["ok"] else 1)
