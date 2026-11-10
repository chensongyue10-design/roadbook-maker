# -*- coding: utf-8 -*-
"""
tests/p0_check.py —— P0 回归：抽库后必须逐字节一致

做两件事：
1. 用 lib_svg 重建 13 张 SVG，与基线 sha256 逐一比对；
2. 把 hainan 版 convert_feishu 里的解析函数替换成 htmltree 的实现，
   重建飞书 XML，与基线字符串比对。

用法（在 hainan 目录下）：
    python <skill>/tests/p0_check.py --hainan .
"""
import argparse
import hashlib
import importlib.util
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import htmltree  # noqa: E402


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def check_svg(hainan):
    """lib_svg 重建 SVG，与基线逐个比 sha256。"""
    print("[1/2] 重建 13 张 SVG 并比对 sha256")
    figs = os.path.join(hainan, "figs")
    scripts = os.path.join(hainan, "scripts")
    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), "p0check")
    os.makedirs(os.path.join(tmp, "scripts"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "figs"), exist_ok=True)

    src = open(os.path.join(scripts, "mapgen.py"), encoding="utf-8").read()
    mark = "# =====================================================================\n#  地图 1"
    tail = src[src.index(mark):]
    head = ('# -*- coding: utf-8 -*-\nimport math\nfrom lib_svg import *\n\n')
    open(os.path.join(tmp, "scripts", "mapgen.py"), "w", encoding="utf-8").write(head + tail)

    for f in ("maps_day12.py", "maps_all.py"):
        open(os.path.join(tmp, "scripts", f), "w", encoding="utf-8").write(
            open(os.path.join(scripts, f), encoding="utf-8").read())
    open(os.path.join(tmp, "scripts", "lib_svg.py"), "w", encoding="utf-8").write(
        open(os.path.join(SKILL, "scripts", "lib_svg.py"), encoding="utf-8").read())

    r = subprocess.run([sys.executable, "scripts/maps_all.py"], cwd=tmp,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("  !! maps_all.py 执行失败")
        print(r.stdout[-1500:], r.stderr[-1500:])
        return False

    ok = bad = 0
    for name in sorted(os.listdir(os.path.join(figs))):
        if not name.endswith(".svg"):
            continue
        a = sha(os.path.join(tmp, "figs", name))
        b = sha(os.path.join(figs, name))
        if a == b:
            ok += 1
        else:
            bad += 1
            print(f"  DIFF {name}")
    print(f"  SVG 一致 {ok} / 不一致 {bad}  {'✓' if bad == 0 else '✗'}")
    return bad == 0


def check_xml(hainan):
    """htmltree 替换解析层后，飞书 XML 必须与基线完全一致。"""
    print("[2/2] 用 htmltree 重建飞书 XML 并比对")
    base_path = os.path.join(hainan, "feishu-book.xml")
    if not os.path.exists(base_path):
        print("  跳过：没有基线 feishu-book.xml")
        return True
    baseline = open(base_path, encoding="utf-8").read()

    cf = load_module(os.path.join(hainan, "scripts", "convert_feishu.py"), "cf_hainan")
    for fn in ("esc", "parse_attrs", "balanced_divs", "parse", "inline"):
        setattr(cf, fn, getattr(htmltree, fn))

    parts = ["<title>海南东线自驾路书 · 东线精华版 V1.0</title>"]
    for fname, mapping in cf.CHAPTERS:
        parts.append(cf.convert_chapter(fname, mapping))
    new = "\n".join(parts)

    if new == baseline:
        print(f"  XML 完全一致（{len(new.encode('utf-8'))} bytes）✓")
        return True
    # 给最小差异
    import difflib
    a = baseline.splitlines()
    b = new.splitlines()
    print(f"  XML 有差异：基线 {len(a)} 行 / 新 {len(b)} 行")
    n = 0
    for line in difflib.unified_diff(a, b, "baseline", "htmltree", lineterm="", n=0):
        print("   ", line[:220])
        n += 1
        if n > 24:
            print("    ...(截断)")
            break
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hainan", default=".", help="海南书项目目录")
    a = ap.parse_args()
    hainan = os.path.abspath(a.hainan)
    print(f"项目：{hainan}\n")
    r1 = check_svg(hainan)
    print()
    r2 = check_xml(hainan)
    print()
    print("P0 结果：" + ("全部通过 ✓" if r1 and r2 else "存在差异 ✗"))
    return 0 if (r1 and r2) else 1


if __name__ == "__main__":
    sys.exit(main())
