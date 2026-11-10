# -*- coding: utf-8 -*-
"""出图脚本模板：一个目的地一份，照抄改数据。

跑法：把本文件放在书稿项目根目录，改名成 figmap.py，然后
    python figmap.py            # 生成 figs/ 下所有 SVG
    python roadbook.py png .    # 再转 PNG

三条规矩（都是踩出来的）：
1. 密集点位不要硬塞文字，用编号框 poi_num + 右侧清单 side_list，否则必糊。
2. 标签位置宁可手写坐标（dx/dy 参数），别指望自动避让。
3. 先跑一遍看 PNG，再调 bbox。图好不好看，八成取决于 bbox 留白。
"""
import os
import sys

# 指向 skill 的 scripts 目录。按顺序探测：
# 1. 环境变量 ROADBOOK_SKILL_SCRIPTS
# 2. 本文件在书稿目录里时，上一级的 scripts/（git clone 仓库后的典型布局）
# 3. WorkBuddy 用户级 skill 安装位置
CANDIDATES = [
    os.environ.get("ROADBOOK_SKILL_SCRIPTS") or "",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"),
    os.path.expanduser("~/.workbuddy/skills/roadbook-maker/scripts"),
]
SKILL_SCRIPTS = next((c for c in CANDIDATES if c and os.path.isdir(c)), CANDIDATES[1])
if SKILL_SCRIPTS not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS)
import lib_svg as S          # noqa: E402   投影、路线、点位、图例、比例尺
import charts as C           # noqa: E402   柱状对照、时间轴、曲线、参数表

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs")
os.makedirs(OUT, exist_ok=True)


def save(name, svg):
    path = os.path.join(OUT, name + ".svg")
    open(path, "w", encoding="utf-8").write(svg)
    print("  ", path, len(svg), "bytes")


# ---------------------------------------------------------------------------
#  地图：第 1 天路线
#  投影 = 等距圆柱 + 纬度余弦校正，bbox 用 (南, 北, 西, 东)
# ---------------------------------------------------------------------------
def map_day1():
    W, H, PAD = 760, 640, 56
    proj = S.make_projection((30.20, 30.32, 120.10, 120.28), W, H, PAD)

    # 陆地/水域底：先用矩形示意，真实项目换成你抓的海岸线折线
    land = [(30.20, 120.10), (30.20, 120.28), (30.32, 120.28), (30.32, 120.10)]

    p = []
    p += S.poly(proj, land, fill=S.C_LAND, stroke=S.C_COAST, sw=1.6)
    # 主路线（红色，带白色描边，压在任何底色上都看得清）
    p += S.draw_route(proj, [(30.24, 120.14), (30.27, 120.19), (30.30, 120.25)],
                      S.C_ROUTE, 5)
    # 起终点：文字在点的一侧，side 决定方向
    p += S.poi(proj, 30.24, 120.14, "起点", "08:00 出发", side="right")
    p += S.poi(proj, 30.30, 120.25, "终点", "17:30", side="left")
    # 密集点位：编号框 + 右上角清单
    p += S.poi_num(proj, 30.26, 120.20, 1, rec=True)   # rec=True 表示推荐
    p += S.poi_num(proj, 30.27, 120.22, 2)
    p += S.side_list(470, 120, 250, [(1, "1 号停车场 · 免费", True),
                                     (2, "2 号停车场 · 10 元/次")], title="停车")
    p += S.legend_box(470, 300, 250, [("line", S.C_ROUTE, "当日路线"),
                                      ("dash", S.C_TOURROAD, "旅游公路")], title="图例")
    p += S.north(70, 90)
    p += S.scalebar(proj, 60, H - 56, 10)   # 10 公里，长度自动算
    save("fig-01-day1-route", S.svg_doc(W, H, p, "第 1 天路线"))


# ---------------------------------------------------------------------------
#  信息图：预算对照（两组数字比长短）
# ---------------------------------------------------------------------------
def fig_budget():
    save("fig-02-budget", C.bar_compare(
        760, 520, "预算构成：两人 与 三口", "平季价格 · 单位：元",
        [("住宿", 2750, 3250), ("租车", 1800, 2100), ("门票", 1238, 1612)],
        [("两人", S.C_ROUTE, 2), ("三口", S.C_ROUTE2, 3)],
        note=["人均反而三口更低：固定支出被三个人摊薄", "真正决定总额的是住宿"],
        note_title="两个反直觉的结论"))


# ---------------------------------------------------------------------------
#  信息图：行程时间轴（每天一条，长度 = 里程）
# ---------------------------------------------------------------------------
def fig_timeline():
    save("fig-03-timeline", C.timeline_bars(
        760, 520, "六天行程主题与里程", "合计 494.7 公里",
        [{"day": "第 1 天", "theme": "市区慢启动", "km": 25, "note": "老街 · 博物馆"},
         {"day": "第 2 天", "theme": "北上文昌", "km": 110, "note": "铜鼓岭 · 石头公园"}],
        footer=["全程不设收费站，费用折入油价", "油费按 0.62 元/公里估算"]))


if __name__ == "__main__":
    print("出图：")
    map_day1()
    fig_budget()
    fig_timeline()
    print("完成。接着跑  python roadbook.py png .")
