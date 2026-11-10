# -*- coding: utf-8 -*-
"""
把各章 HTML 转成飞书云文档 XML（内嵌本地地图 PNG），供 lark-cli docs +create 使用。

输出：feishu-book.xml
用法：在 hainan 目录下执行  lark-cli docs +create --doc-format xml --content "@./feishu-book.xml" --as user

设计说明：
  用一个小型 HTML 解析器建树后再渲染，而不是用正则套正则。
  原因：目录里有嵌套 <ul>，正则在嵌套结构上会错位。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config as CFG

ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else \
       os.path.normpath(os.path.join(HERE, ".."))

BOOK = CFG.load(ROOT)
FIG_CAPTION = BOOK.numbered_captions()
# 章节 -> {占位序号: (图 id, 飞书显示宽度)}，序号为 None 时由 resolve_figures 兜底
CHAPTERS = [(ch.file, {i: (fid, BOOK.figures[fid].width_feishu)
                       for i, fid in enumerate(ch.figures)})
            for ch in BOOK.chapters]

VOID = {"br", "img", "hr", "col", "meta", "link", "input", "imgfig"}

ENTITY = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
          "&quot;": '"', "&#39;": "'", "&mdash;": "—", "&hellip;": "…"}


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def esc(t):
    t = re.sub(r"[^\S\u3000]+", " ", t)
    t = t.replace("&nbsp;", " ")
    t = t.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")
    return t


def parse_attrs(s):
    return {k: v for k, v in re.findall(r'([\w:-]+)\s*=\s*"([^"]*)"', s or "")}


def balanced_divs(html, cls):
    """返回所有 <div class="cls"> ... </div> 的 (start, end) 平衡区间"""
    res = []
    for m in re.finditer(r'<div\b[^>]*class="[^"]*\b' + cls + r'\b[^"]*"', html):
        i = m.start()
        depth = 0
        for t in re.finditer(r"<div\b|</div>", html[i:]):
            if t.group(0) == "</div>":
                depth -= 1
                if depth == 0:
                    res.append((i, i + t.end()))
                    break
            else:
                depth += 1
    return res


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------
def parse(body):
    """极简 HTML -> 树。节点：("text", s) 或 ("el", tag, attrs, children)"""
    root = ("el", "root", {}, [])
    stack = [root]
    pos = 0
    for m in re.finditer(r"<(\w+)([^>]*?)(/?)>|</(\w+)>", body):
        if m.start() > pos:
            stack[-1][3].append(("text", body[pos:m.start()]))
        pos = m.end()
        if m.group(4):
            tag = m.group(4)
            for k in range(len(stack) - 1, 0, -1):
                if stack[k][1] == tag:
                    del stack[k:]
                    break
            continue
        tag, attr_s = m.group(1).lower(), m.group(2)
        node = ("el", tag, parse_attrs(attr_s), [])
        stack[-1][3].append(node)
        if tag not in VOID and m.group(3) != "/":
            stack.append(node)
    if pos < len(body):
        stack[-1][3].append(("text", body[pos:]))
    return root[3]


def inline(nodes):
    out = []
    for n in nodes:
        if n[0] == "text":
            t = n[1]
            for k, v in ENTITY.items():
                t = t.replace(k, v)
            t = re.sub(r"[^\S\u3000]+", " ", t)
            if t:
                out.append(t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            continue
        tag, ch = n[1], n[3]
        if tag == "br":
            out.append("<br/>")
        elif tag in ("b", "strong"):
            c = inline(ch).strip()
            if c:
                out.append(f"<b>{c}</b>")
        else:
            out.append(inline(ch))
    s = "".join(out)
    s = re.sub(r"[^\S\u3000]+", " ", s)
    s = re.sub(r"[ \t]*<br/>[ \t]*", "<br/>", s)
    return s.strip()


# --------------------------------------------------------------------------
# 块级渲染
# --------------------------------------------------------------------------
def convert_table(children):
    rows = []
    for n in children:
        if n[0] != "el" or n[1] != "tr":
            continue
        cells = []
        for c in n[3]:
            if c[0] == "el" and c[1] in ("td", "th"):
                cells.append((c[1], inline(c[3])))
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    out = ["<table>", "<thead><tr>"]
    for _, c in rows[0]:
        out.append(f"<th><p>{c}</p></th>")
    out.append("</tr></thead><tbody>")
    for row in rows[1:]:
        out.append("<tr>")
        for _, c in row:
            out.append(f"<td><p>{c}</p></td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def convert_list(node):
    ordered = node[1] == "ol"
    tag = "ol" if ordered else "ul"
    out = [f"<{tag}>"]
    for n in node[3]:
        if n[0] != "el" or n[1] != "li":
            continue
        txt, sub = [], []
        for c in n[3]:
            if c[0] == "el" and c[1] in ("ul", "ol"):
                sub.append(convert_list(c))
            else:
                txt.append(c)
        out.append(f"<li>{inline(txt)}{''.join(sub)}</li>")
    out.append(f"</{tag}>")
    return "".join(out)


def convert_callout(cls, children):
    key = "warn" if "warn" in cls.split() else ("meta" if "meta" in cls.split() else "advice")
    emoji = {"advice": "💡", "warn": "⚠️", "meta": "📌"}[key]
    bg = {"advice": "light-gray", "warn": "light-red", "meta": "light-blue"}[key]
    bd = {"advice": "gray", "warn": "red", "meta": "blue"}[key]
    inner = []
    for n in children:
        if n[0] == "text":
            t = inline([n])
            if t:
                inner.append(f"<p>{t}</p>")
            continue
        tag, kcls, ch = n[1], n[2].get("class", ""), n[3]
        if tag == "span" and "tag" in kcls.split():
            inner.append(f"<p><b>{inline(ch)}</b></p>")
        elif tag == "p":
            inner.append(f"<p>{inline(ch)}</p>")
        elif tag in ("ul", "ol"):
            inner.append(convert_list(n))
        else:
            for x in render_blocks([n]):
                inner.append(x)
    return (f'<callout emoji="{emoji}" background-color="{bg}" border-color="{bd}">'
            + "".join(inner) + "</callout>")


def convert_foot(children):
    texts = []
    for n in children:
        if n[0] == "el":
            t = inline(n[3])
            if t:
                texts.append(t)
    line = "　".join(texts)
    return f'<hr/><p align="center">{line}</p>'


def convert_cover(children):
    out = []
    for n in children:
        if n[0] != "el":
            continue
        cls = n[2].get("class", "").split()
        if n[1] == "div":
            if "t1" in cls:
                out.append(f'<h1 align="center">{inline(n[3])}</h1>')
            else:
                out.append(f'<p align="center">{inline(n[3])}</p>')
        else:
            out.extend(render_blocks([n]))
    return "".join(out)


def img_xml(idx, mapping):
    fig, width = mapping[idx]
    cap = FIG_CAPTION.get(fig, "")
    return f'<img path="@./figs-png/{fig}.png" width="{width}" caption="{esc(cap)}"/>'


def render_blocks(nodes, mapping=None, counter=None):
    out = []
    for n in nodes:
        if n[0] == "text":
            t = inline([n])
            if t:
                out.append(f"<p>{t}</p>")
            continue
        tag, attrs, ch = n[1], n[2], n[3]
        cls = attrs.get("class", "")
        words = cls.split()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            out.append(f"<{tag}>{inline(ch)}</{tag}>")
        elif tag == "p":
            al = ' align="center"' if "sub" in words else ""
            out.append(f"<p{al}>{inline(ch)}</p>")
        elif tag == "table":
            out.append(convert_table(ch))
        elif tag in ("ul", "ol"):
            out.append(convert_list(n))
        elif tag == "hr":
            out.append("<hr/>")
        elif tag == "imgfig":
            if mapping is not None and counter is not None:
                i = counter[0]
                counter[0] += 1
                if i in mapping:
                    out.append(img_xml(i, mapping))
        elif tag == "div":
            if any(w in ("advice", "warn", "meta") for w in words):
                out.append(convert_callout(cls, ch))
            elif "foot" in words:
                out.append(convert_foot(ch))
            elif "cover" in words:
                out.append(convert_cover(ch))
            elif "imgph" in words or "focus" in words or "fig" in words:
                pass
            else:
                out.extend(render_blocks(ch, mapping, counter))
        else:
            out.extend(render_blocks(ch, mapping, counter))
    return out


# --------------------------------------------------------------------------
# 单章转换
# --------------------------------------------------------------------------
def convert_chapter(fname, mapping, demote=False):
    html = open(os.path.join(ROOT, fname), encoding="utf-8").read()
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    body = m.group(1) if m else html

    # 章标题 h1 -> h2（有上级部时），保证飞书标题层级不跳级
    if demote:
        body, n = re.subn(r"<h1([^>]*)>", r"<h2\1>", body, count=1)
        if n:
            body = re.sub(r"</h1>", "</h2>", body, count=1)

    # 占位框 -> imgfig 标记（用平衡匹配，避免嵌套 div 错位）
    out, pos, idx = [], 0, 0
    for s, e in balanced_divs(body, "imgph"):
        out.append(body[pos:s])
        out.append(f'<imgfig idx="{idx}"/>')
        idx += 1
        pos = e
    out.append(body[pos:])
    body = "".join(out)

    tree = parse(body)
    counter = [0]
    blocks = render_blocks(tree, mapping, counter)
    if counter[0] != len(mapping):
        sys.stderr.write(f"[warn] {fname}: 占位框 {counter[0]} 个，映射 {len(mapping)} 个\n")
    return "\n".join(x for x in blocks if x.strip())


def main():
    parts = [f"<title>{BOOK.title} · {BOOK.subtitle} {BOOK.version}</title>"]
    seen_part = set()
    for ch in BOOK.chapters:
        if ch.part and ch.part not in seen_part:
            seen_part.add(ch.part)
            p = BOOK.part_of(ch)
            parts.append(f'<h1 align="center">{esc(p.title)}</h1>')
        # 用 resolve_figures 建映射：同时支持 figures 顺序和 data-fig 两种写法
        html = open(os.path.join(ROOT, ch.file), encoding="utf-8").read()
        m = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
        body = m.group(1) if m else html
        pairs = CFG.resolve_figures(body, ch, BOOK)
        mapping = {i: (fid, BOOK.figures[fid].width_feishu)
                   for i, (_, fid) in enumerate(pairs)}
        parts.append(convert_chapter(ch.file, mapping, demote=bool(ch.part and ch.demote)))
    xml = "\n".join(parts)
    out = os.path.join(ROOT, BOOK.out_xml)
    open(out, "w", encoding="utf-8").write(xml)

    # ---- 自检 ----
    print("输出:", out, len(xml.encode("utf-8")), "bytes")
    print("图片引用:", xml.count("<img "))
    print("表格:", xml.count("<table>"), " 高亮块:", xml.count("<callout"))
    print("破折号:", xml.count("——") + xml.count("—") + xml.count("–"))
    for bad in ("<div", "</div>", "<span", "</span>", "class=\"", "<table><table"):
        if bad in xml:
            print("!! 残留:", bad, xml.count(bad))
    # 标题跳级检查
    lv = [int(x) for x in re.findall(r"<h([1-6])>", xml)]
    for a, b in zip(lv, lv[1:]):
        if b > a + 1:
            print(f"!! 标题跳级: h{a} -> h{b}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
