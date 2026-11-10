# -*- coding: utf-8 -*-
"""roadbook.py — 自驾路书制作的一站式命令行。

用法（在书稿项目目录下执行）：
    python roadbook.py init  <目录名> [--title 书名] [--author 署名]   新建一本书
    python roadbook.py doctor [目录]                                   环境与配置体检（先跑这个）
    python roadbook.py build [目录]                                    章节合并成 HTML
    python roadbook.py png   [目录] [--only 图id]                      SVG 渲染 PNG
    python roadbook.py xml   [目录]                                    生成飞书 XML
    python roadbook.py pdf   [目录] [--out 文件名.pdf]                  成书 HTML → A4 PDF（矢量图）
    python roadbook.py feishu [目录]                                   xml + 上传飞书（需 lark-cli 登录）

init 之后的目录结构：
    <目录名>/
      book.toml          书籍配置（章节顺序、图号、图注、宽度），唯一事实源
      封面-目录.html     各章正文，占位框处插图
      figs/              出图脚本产出的 SVG
      figs-png/          render_png 产出的 PNG（自动生成）

环境变量：
    ROADBOOK_PYTHON   指定跑 png 的解释器（默认用当前解释器）
    ROADBOOK_BROWSER  指定浏览器可执行文件（默认自动探测 chrome/edge）
    ROADBOOK_SCALE    PNG 倍率，默认 2

完整流程见 SKILL.md；写书前先读 references/pitfalls.md。
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _py() -> str:
    return sys.executable


def cmd_init(args):
    dest = os.path.abspath(args[0])
    title, author = "我的自驾路书", "作者名"
    if "--title" in args:
        title = args[args.index("--title") + 1]
    if "--author" in args:
        author = args[args.index("--author") + 1]
    if os.path.exists(dest):
        print(f"目录已存在：{dest}", file=sys.stderr)
        return 1
    os.makedirs(os.path.join(dest, "figs"))

    tpl = open(os.path.join(HERE, "..", "assets", "book.toml.template"),
               encoding="utf-8").read()
    open(os.path.join(dest, "book.toml"), "w", encoding="utf-8").write(
        tpl.replace("{{TITLE}}", title).replace("{{AUTHOR}}", author))

    for src_name, dst_name in (("章节-模板.html", "01-第一章.html"),
                               ("figmap.py", "figmap.py")):
        src = os.path.join(HERE, "..", "assets", src_name)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(dest, dst_name))
    print(f"已创建 {dest}\n"
          f"  book.toml        ← 加章节、加图、改书名\n"
          f"  01-第一章.html    ← 照这个写每一章\n"
          f"  figmap.py        ← 照这个画每张图\n"
          f"下一步：写章节 → $PY $RB build .")
    return 0


def _run(script, root, extra=None):
    cmd = [_py(), os.path.join(HERE, script), root] + (extra or [])
    r = subprocess.run(cmd)
    return r.returncode


def cmd_build(root):
    return _run("build_book.py", root)


def cmd_png(root, extra=None):
    """render_png 需要 playwright，优先用装好 playwright 的解释器跑。"""
    try:
        import playwright  # noqa: F401
        exe = _py()
    except ImportError:
        exe = os.environ.get("ROADBOOK_PYTHON", _py())
    cmd = [exe, os.path.join(HERE, "render_png.py"), root] + (extra or [])
    return subprocess.run(cmd).returncode


def cmd_xml(root):
    return _run("convert_feishu.py", root)


def cmd_pdf(root, extra=None):
    """成书 HTML → A4 PDF（矢量图不糊）。需要 playwright 环境，见 ROADBOOK_PYTHON。"""
    exe = os.environ.get("ROADBOOK_PYTHON", _py())
    cmd = [exe, os.path.join(HERE, "render_pdf.py"), root] + (extra or [])
    return subprocess.run(cmd).returncode


def cmd_feishu(root):
    """xml + 上传。需要 lark-cli 已登录。"""
    if cmd_xml(root) != 0:
        return 1
    book_dir = os.path.abspath(root)
    book = __import__("config").load(book_dir)
    xml = book.path(book.out_xml)
    print("\n上传飞书……")
    args = ["docs", "+create", "--doc-format", "xml",
            "--content", f"@./{book.out_xml}", "--as", "user"]
    lc = shutil.which("lark-cli")
    if lc and lc.lower().endswith((".cmd", ".bat")):
        # Windows 的 npm 垫片是批处理文件，CreateProcess 不能直接执行
        r = subprocess.run(["cmd", "/c", lc] + args, cwd=book_dir)
    else:
        r = subprocess.run([lc or "lark-cli"] + args, cwd=book_dir)
    if r.returncode == 0:
        print(f"\n完成后建议回读校验字数：lark-cli docs +fetch --doc <doc_id> --as user")
    return r.returncode


def cmd_doctor(root):
    return subprocess.run([_py(), os.path.join(HERE, "config.py"), "doctor",
                           os.path.abspath(root)]).returncode


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd == "init":
        return cmd_init(rest)
    root = rest[0] if rest and not rest[0].startswith("-") else "."
    extra = [a for a in rest if a != root]
    if cmd == "build":
        return cmd_build(root)
    if cmd == "png":
        return cmd_png(root, extra)
    if cmd == "xml":
        return cmd_xml(root)
    if cmd == "pdf":
        return cmd_pdf(root, extra)
    if cmd == "feishu":
        return cmd_feishu(root)
    if cmd == "doctor":
        return cmd_doctor(root)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
