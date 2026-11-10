# -*- coding: utf-8 -*-
"""
htmltree —— 极简 HTML → 树 → 飞书 DocxXML 的解析层（全书唯一实现）

为什么不用正则套正则
--------------------
书稿里有嵌套结构（目录的 <ul> 里挂 6 个 Day）。`re.split(r'<div.*?</div>')`
这类非贪婪写法会在第一个 `</div>` 就截断，导致占位框只换掉一半、
列表层级错位。这里的做法是：

1. `parse()` 用一个栈把 HTML 建成一棵树；
2. `balanced_divs()` 用深度计数找完整的 div 区间（处理占位框）；
3. 渲染时递归遍历树，嵌套结构天然正确。

节点结构
--------
    ("text", "纯文本")
    ("el", tag, {attrs}, [子节点...])
"""
import re

__all__ = [
    "ENTITY", "esc", "parse_attrs", "balanced_divs", "parse", "inline",
    "substitute_imgph", "walk", "iter_blocks", "text_of",
]

VOID = {"br", "img", "hr", "col", "meta", "link", "input", "imgfig"}

ENTITY = {
    "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
    "&quot;": '"', "&#39;": "'", "&mdash;": "\u2014", "&hellip;": "\u2026",
}

# 全角空格 U+3000 必须保留：它承担"标签 / 副题"之间的视觉间距。
# 普通的 \s+ 会把它一起吃掉，导致「前言　我为什么做这本路书」变成「前言 我为什么…」
_WS = r"[^\S\u3000]+"


def esc(t):
    """转义成 XML 文本。只转 & < >，引号在文本节点里不需要转。"""
    t = re.sub(_WS, " ", t)
    t = t.replace("&nbsp;", " ")
    t = t.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")
    return t


def parse_attrs(s):
    return {k: v for k, v in re.findall(r'([\w:-]+)\s*=\s*"([^"]*)"', s or "")}


def balanced_divs(html, cls):
    """返回所有 class 含 `cls` 的 div 的 (start, end) 完整区间。

    用 `<div` / `</div>` 的深度计数，嵌套几层都不会截断。
    """
    res = []
    for m in re.finditer(r'<div\b[^>]*class="[^"]*\b' + re.escape(cls) + r'\b[^"]*"', html):
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


def parse(body):
    """HTML → 树。容错：闭合标签对不上时向上找最近的同名标签，找不到就忽略。"""
    root = ("el", "root", {}, [])
    stack = [root]
    pos = 0
    for m in re.finditer(r"<(\w+)([^>]*?)(/?)>|</(\w+)>", body):
        if m.start() > pos:
            stack[-1][3].append(("text", body[pos:m.start()]))
        pos = m.end()
        if m.group(4):                       # 闭合标签
            tag = m.group(4).lower()
            for k in range(len(stack) - 1, 0, -1):
                if stack[k][1] == tag:
                    del stack[k:]
                    break
            continue
        tag = m.group(1).lower()
        node = ("el", tag, parse_attrs(m.group(2)), [])
        stack[-1][3].append(node)
        if tag not in VOID and m.group(3) != "/":
            stack.append(node)
    if pos < len(body):
        stack[-1][3].append(("text", body[pos:]))
    return root[3]


def inline(nodes):
    """行内渲染。只保留 <b> 与 <br/>，其余标签剥掉但保留文字。"""
    out = []
    for n in nodes:
        if n[0] == "text":
            t = n[1]
            for k, v in ENTITY.items():
                t = t.replace(k, v)
            t = re.sub(_WS, " ", t)
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
    s = re.sub(_WS, " ", s)
    s = re.sub(r"[ \t]*<br/>[ \t]*", "<br/>", s)
    return s.strip()


def substitute_imgph(body, mapping=None, tag="imgfig"):
    """把占位框换成 <imgfig idx="N"/> 或 <imgfig id="fig-xxx"/>。

    mapping 三种写法：
      None                → 只按出现顺序编号 0,1,2…
      {"fig-a": 0, ...}   → 显式 id，占位框需写 data-fig="fig-a"
      [0, 1, ...]         → 旧式序号

    返回 (新 body, 占位框数量, 未能匹配的 id 列表)。
    """
    out, pos, idx = [], 0, 0
    missing = []
    for s, e in balanced_divs(body, "imgph"):
        seg = body[s:e]
        m = re.search(r'data-fig\s*=\s*"([^"]+)"', seg)
        out.append(body[pos:s])
        if m and mapping is not None and not isinstance(mapping, list):
            fid = m.group(1)
            if fid in mapping:
                out.append(f'<{tag} id="{fid}"/>')
            else:
                missing.append(fid)
                out.append(seg)
        else:
            out.append(f'<{tag} idx="{idx}"/>')
        idx += 1
        pos = e
    out.append(body[pos:])
    return "".join(out), idx, missing


def walk(nodes, fn, parent=None):
    """深度优先遍历，fn(node, parent) 返回 False 可剪枝。"""
    for n in nodes:
        if fn(n, parent) is False:
            continue
        if n[0] == "el":
            walk(n[3], fn, n)


def iter_blocks(nodes):
    """只产出块级节点（text 里的纯空白丢掉）。"""
    for n in nodes:
        if n[0] == "text":
            if n[1].strip():
                yield n
        else:
            yield n


def text_of(node):
    """把一个节点的全部文字拼起来，用于校验/计数。"""
    if node[0] == "text":
        return node[1]
    return "".join(text_of(c) for c in node[3])
