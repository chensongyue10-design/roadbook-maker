# -*- coding: utf-8 -*-
"""配置层：一份 book.toml 喂给 build_book / convert_feishu / render_png / qc_check。

设计原则
--------
1. 章节顺序、图 id、图注、显示宽度、作者署名，全部只在这里出现一次。
2. 图号按「章节顺序 + 章内顺序」自动编排，不用手工写「图 1」「图 2」。
3. 占位框的图 id 优先读 `data-fig` 属性；没写才回退到 chapter.figures 的
   顺序映射。这样中间插一张图不会让后面全部错位（历史坑 #3）。
4. book.local.toml 覆盖 book.toml，本机私有路径不进版本库。
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field

try:
    import tomllib as _toml  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    _toml = None


# ---------------------------------------------------------------------------
#  数据结构
# ---------------------------------------------------------------------------
@dataclass
class Figure:
    id: str
    caption: str = ""
    width_html: int = 760      # HTML 版最大宽度（px），0 表示不限
    width_feishu: int = 760    # 飞书 img 的 width
    kind: str = "route"        # route / point / chart / table
    number: int | None = None  # 显式图号；None 表示按章节出现顺序自动编

    @property
    def png(self) -> str:
        return f"{self.id}.png"

    @property
    def svg(self) -> str:
        return f"{self.id}.svg"


@dataclass
class Chapter:
    file: str
    figures: list[str] = field(default_factory=list)
    part: str = ""             # 所属 part 的 key，空表示不归部
    demote: bool = True        # 章内 h1 降为 h2（有 part 时必须降级）
    toc: bool = True
    title: str = ""            # 目录显示名，空则从文件里抓 h1

    @property
    def stem(self) -> str:
        return os.path.splitext(os.path.basename(self.file))[0]


@dataclass
class Part:
    key: str
    title: str


@dataclass
class Book:
    root: str
    title: str
    subtitle: str
    author: str
    version: str
    out_html: str
    out_xml: str
    figs_dir: str
    png_dir: str
    parts: list[Part]
    chapters: list[Chapter]
    figures: dict[str, Figure]
    raw: dict = field(default_factory=dict)

    # -- 路径 ---------------------------------------------------------------
    def path(self, *p) -> str:
        return os.path.join(self.root, *p)

    @property
    def fig_dir(self) -> str:
        return self.path(self.figs_dir)

    @property
    def png_path(self) -> str:
        return self.path(self.png_dir)

    # -- 图号编排 -----------------------------------------------------------
    def figure_order(self) -> list[str]:
        """按章节顺序返回图 id 序列，索引即图号-1。"""
        seen, order = set(), []
        for ch in self.chapters:
            for fid in ch.figures:
                if fid in seen:
                    raise ValueError(f"图 id 重复引用：{fid}（{ch.file}）")
                seen.add(fid)
                order.append(fid)
        return order

    def numbered_captions(self) -> dict[str, str]:
        """{fig_id: "图 N　图注"}。

        图号优先用 figure.number（显式稳定，插图不影响老图号）；
        没给就按章节出现顺序自动编。图注里已有的「图 N」前缀会被剥掉重编。
        """
        out = {}
        order = self.figure_order()
        for fid in self.figures:          # data-fig 引用的图不在章节 figures 里
            if fid not in order:
                order.append(fid)
        for i, fid in enumerate(order, 1):
            f = self.figures[fid]
            n = f.number if f.number is not None else i
            cap = re.sub(r"^\s*图\s*\d+\s*[　\s]*", "", f.caption)
            out[fid] = f"图 {n}　{cap}"
        return out

    def chapter_by_file(self, fname) -> Chapter | None:
        for ch in self.chapters:
            if ch.file == fname or ch.stem == os.path.splitext(os.path.basename(fname))[0]:
                return ch
        return None

    def part_of(self, ch: Chapter) -> Part | None:
        for p in self.parts:
            if p.key == ch.part:
                return p
        return None

    def part_chapters(self, part: Part) -> list[Chapter]:
        return [c for c in self.chapters if c.part == part.key]


# ---------------------------------------------------------------------------
#  读取与合并
# ---------------------------------------------------------------------------
def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_toml(path: str) -> dict:
    if _toml is None:
        raise RuntimeError("需要 Python 3.11+ 的 tomllib（或用 pip install tomli）")
    with open(path, "rb") as f:
        return _toml.load(f)


DEFAULTS = {
    "book": {
        "subtitle": "",
        "version": "V1.0",
        "out_html": "book.html",
        "out_xml": "book.xml",
        "figs_dir": "figs",
        "png_dir": "figs-png",
    }
}


def load(root: str = ".", name: str = "book.toml") -> Book:
    """读 book.toml（+ 可选 book.local.toml 覆盖），做 schema 校验。"""
    root = os.path.abspath(root)
    main = os.path.join(root, name)
    if not os.path.exists(main):
        raise FileNotFoundError(f"找不到配置文件：{main}")
    raw = _deep_merge(DEFAULTS, _read_toml(main))
    local = os.path.join(root, "book.local.toml")
    if os.path.exists(local):
        raw = _deep_merge(raw, _read_toml(local))

    b = raw.get("book") or {}
    for k in ("title", "author"):
        if not b.get(k):
            raise ValueError(f"book.toml 缺少 book.{k}")

    figs: dict[str, Figure] = {}
    for item in raw.get("figure") or []:
        fid = item.get("id", "").strip()
        if not fid:
            raise ValueError("[[figure]] 缺少 id")
        if fid in figs:
            raise ValueError(f"[[figure]] id 重复：{fid}")
        figs[fid] = Figure(
            id=fid,
            caption=item.get("caption", ""),
            width_html=int(item.get("width_html", 760)),
            width_feishu=int(item.get("width_feishu", 760)),
            kind=item.get("kind", "route"),
            number=int(item["number"]) if item.get("number") is not None else None,
        )

    parts = [Part(key=p["key"], title=p["title"]) for p in (raw.get("part") or [])]
    part_keys = {p.key for p in parts}

    chapters: list[Chapter] = []
    for item in raw.get("chapter") or []:
        f = item.get("file", "").strip()
        if not f:
            raise ValueError("[[chapter]] 缺少 file")
        fs = item.get("figures") or []
        for fid in fs:
            if fid not in figs:
                raise ValueError(f"{f} 引用了未定义的图：{fid}")
        pk = item.get("part", "")
        if pk and pk not in part_keys:
            raise ValueError(f"{f} 的 part={pk!r} 没有对应的 [[part]]")
        chapters.append(Chapter(
            file=f,
            figures=list(fs),
            part=pk,
            demote=bool(item.get("demote", True)),
            toc=bool(item.get("toc", True)),
            title=item.get("title", ""),
        ))

    if not chapters:
        raise ValueError("book.toml 里没有任何 [[chapter]]")

    used = {f for c in chapters for f in c.figures}
    # data-fig 写法不进 chapter.figures，扫一遍正文补上，否则会误报「图没用到」
    for c in chapters:
        p = os.path.join(root, c.file)
        if os.path.exists(p):
            txt = open(p, encoding="utf-8", errors="ignore").read()
            used |= set(re.findall(r'data-fig\s*=\s*"([^"]+)"', txt))
    unused = set(figs) - used
    if unused:
        print(f"[config] 警告：有 {len(unused)} 张图定义了但没被任何章节引用："
              f"{', '.join(sorted(unused))}", file=sys.stderr)

    return Book(
        root=root,
        title=b["title"], subtitle=b.get("subtitle", ""), author=b["author"],
        version=b.get("version", "V1.0"),
        out_html=b["out_html"], out_xml=b["out_xml"],
        figs_dir=b["figs_dir"], png_dir=b["png_dir"],
        parts=parts, chapters=chapters, figures=figs, raw=raw,
    )


# ---------------------------------------------------------------------------
#  占位框解析（build_book 与 convert_feishu 共用）
# ---------------------------------------------------------------------------
IMGPH_RE = re.compile(r'<div\b[^>]*class="[^"]*\bimgph\b[^"]*"[^>]*>', re.I)


def scan_placeholders(html: str) -> list[dict]:
    """返回每个 imgph 占位框：{start, end, data_fig, text}。

    用深度匹配找闭合 div，避免 `.*?</div>` 被内层 div 截断（历史坑 #1）。
    """
    out = []
    for m in IMGPH_RE.finditer(html):
        i = m.start()
        depth, j = 0, i
        for t in re.finditer(r"<div\b|</div>", html[i:]):
            if t.group(0) == "</div>":
                depth -= 1
                if depth == 0:
                    j = i + t.end()
                    break
            else:
                depth += 1
        else:
            j = len(html)
        tag = m.group(0)
        dm = re.search(r'data-fig\s*=\s*"([^"]+)"', tag)
        out.append({
            "start": i, "end": j,
            "data_fig": dm.group(1) if dm else None,
            "text": html[i:j],
        })
    return out


def resolve_figures(html: str, chapter: Chapter, book: Book) -> list[tuple[dict, str]]:
    """把占位框与实际图 id 配对。返回 [(placeholder, fig_id)]。

    优先 data-fig；没有就按出现顺序取 chapter.figures。
    数量对不上直接报错，不静默吞掉（历史坑 #2：13 张图只出 12 个图注）。
    """
    phs = scan_placeholders(html)
    if not phs:
        return []
    has_data = any(p["data_fig"] for p in phs)
    if not chapter.figures and not has_data:
        # 还没配图：保留占位框，当作写作中的半成品，不报错
        return []
    pairs, auto = [], 0
    for idx, ph in enumerate(phs):
        if ph["data_fig"]:
            fid = ph["data_fig"]
            if fid not in book.figures:
                raise ValueError(f"{chapter.file} 的 data-fig={fid!r} 未在 book.toml 定义")
        else:
            # 没写 data-fig 的占位框，按「第几个无标注占位框」去配 figures
            if auto >= len(chapter.figures):
                raise ValueError(
                    f"{chapter.file} 有 {len(phs)} 个占位框，但 book.toml 只给了 "
                    f"{len(chapter.figures)} 张图。第 {idx+1} 个占位框没有图可配"
                    f"（要么给它写 data-fig，要么在 figures 里补一个）。")
            fid = chapter.figures[auto]
            auto += 1
        pairs.append((ph, fid))
    if len(chapter.figures) > auto:
        raise ValueError(
            f"{chapter.file} 在 book.toml 里配了 {len(chapter.figures)} 张图，"
            f"但正文只有 {auto} 个没有 data-fig 的占位框。多出来的："
            f"{chapter.figures[auto:]}")
    return pairs


# ---------------------------------------------------------------------------
#  命令行
# ---------------------------------------------------------------------------
def _cmd_show(root):
    b = load(root)
    print(f"书名：{b.title}　{b.subtitle}")
    print(f"作者：{b.author}　版本：{b.version}")
    print(f"章节：{len(b.chapters)}　图：{len(b.figures)}　图号序列：{len(b.figure_order())}")
    print("-" * 66)
    cur = None
    for ch in b.chapters:
        if ch.part and ch.part != cur:
            cur = ch.part
            p = b.part_of(ch)
            print(f"[{p.title}]")
        phs = 0
        p = b.path(ch.file)
        if os.path.exists(p):
            phs = len(scan_placeholders(open(p, encoding="utf-8").read()))
        flag = "OK " if phs == len(ch.figures) else "!! "
        print(f"  {flag}{ch.file:34s} 占位 {phs} / 配图 {len(ch.figures)}")
    print("-" * 66)
    for fid, cap in b.numbered_captions().items():
        print(f"  {fid:24s} {cap}")


def _cmd_doctor(root):
    b = load(root)
    bad = 0
    for ch in b.chapters:
        if not os.path.exists(b.path(ch.file)):
            print(f"[缺章] {ch.file}"); bad += 1
    for fid, f in b.figures.items():
        if not os.path.exists(os.path.join(b.fig_dir, f.svg)):
            print(f"[缺 SVG] {f.svg}"); bad += 1
    print("doctor:", "全部就位" if not bad else f"{bad} 个问题")
    return 1 if bad else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    root = sys.argv[2] if len(sys.argv) > 2 else "."
    if cmd == "show":
        _cmd_show(root)
    elif cmd == "doctor":
        sys.exit(_cmd_doctor(root))
    else:
        print(__doc__)
