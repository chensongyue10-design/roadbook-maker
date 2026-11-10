# -*- coding: utf-8 -*-
"""
charts —— 路书用信息图（通用，数据全部由调用方传入）

和 lib_svg 的分工：
  lib_svg  画地图：投影、海岸线、路线、点位
  charts   画数据：预算对照、行程时间轴、气候曲线、参数表

约定
----
* 每张图都从 (W, H, title, subtitle) 开始，内部用 chart_frame() 统一留白与标题排布。
* 数据用 list[dict] 或 list[tuple] 传入，函数内部不出现任何业务数字。
* 所有颜色走 Theme，不写死色值。
"""
import lib_svg as S
from lib_svg import txt, svg_open, DEFAULT

__all__ = [
    "chart_frame", "insight_box", "bar_compare", "timeline_bars",
    "line_chart", "table_fig", "legend_row",
]

C_TEXT, C_TEXTSUB, C_ROUTE, C_ROUTE2, C_POI = (
    S.C_TEXT, S.C_TEXTSUB, S.C_ROUTE, S.C_ROUTE2, S.C_POI)
GRID = "#e2e8ec"


# ---------------------------------------------------------------------
#  骨架
# ---------------------------------------------------------------------
def chart_frame(W, H, title, subtitle="", label=None, color=None):
    """白底 + 主标题 + 副标题。返回 (零件列表, 内容区起点 y)。"""
    s = svg_open(W, H, label or title)
    s.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>')
    s.append(txt(W / 2, 34, title, 17, "bold", color or C_TEXT, "middle"))
    if subtitle:
        s.append(txt(W / 2, 58, subtitle, 11.5, "normal", C_TEXTSUB, "middle"))
    return s, (84 if subtitle else 66)


def insight_box(x, y, w, lines, title=None, h=None, accent="#666666", bg="#fafafa"):
    """底部结论框：左侧一条粗竖线 + 浅灰底。lines 里第一条可作小标题。"""
    n = len(lines) + (1 if title else 0)
    h = h or (24 + n * 20 + 14)
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{bg}" stroke="#bbbbbb"/>',
           f'<rect x="{x}" y="{y}" width="6" height="{h}" fill="{accent}"/>']
    yy = y + 24
    if title:
        out.append(txt(x + 20, yy, title, 12.5, "bold", C_TEXT))
        yy += 22
    for i, ln in enumerate(lines):
        out.append(txt(x + 20, yy + i * 20, ln, 11.5, "normal", C_TEXT))
    return out


def legend_row(x, y, items, size=11.5, gap=18):
    """横排小图例。items: [(color, label)]"""
    out, cx = [], x
    for col, label in items:
        out.append(f'<rect x="{cx}" y="{y-9}" width="22" height="10" fill="{col}" fill-opacity="0.75" stroke="{col}"/>')
        out.append(txt(cx + 28, y, label, size, "normal", C_TEXTSUB))
        cx += 28 + S.text_em(label) * size + gap
    return out


# ---------------------------------------------------------------------
#  双列条形对照（预算、票价比价、两地对比）
# ---------------------------------------------------------------------
def bar_compare(W, H, title, subtitle, items, columns,
                max_value=None, unit="元", note=None, note_title=None,
                left_pad=96, right_pad=30, color=None):
    """两组数字并排比长短。

    items   : [(名称, 值1, 值2, ...)] 值按 columns 顺序对应
    columns : [(列名, 颜色, 总人数)]  总人数用于算人均，None 表示不算
    """
    colors = [c[1] for c in columns]
    totals = [sum(it[i + 1] for it in items) for i in range(len(columns))]
    maxv = max_value or (max(max(totals), max(max(it[1:]) for it in items)) * 1.12)

    s, top = chart_frame(W, H, title, subtitle)
    bw = (W - left_pad - right_pad - 26 * (len(columns) - 1)) / len(columns)
    row_h, bar_h = 27, 20
    hdr_h = 30
    # 列头框在副标题之下（副标题基线 y=58，占位到 ~66），数据区从 top+hdr_h 开始
    rows_top = top + hdr_h

    for ci, (cname, col, npeople) in enumerate(columns):
        x0 = left_pad + ci * (bw + 26)
        s.append(f'<rect x="{x0}" y="{top-6}" width="{bw}" height="{hdr_h}" fill="#f2f2f2" stroke="{S.C_BOXEDGE}"/>')
        s.append(txt(x0 + bw / 2, top + 15, cname, 13.5, "bold", C_TEXT, "middle"))
        s.append(f'<line x1="{x0}" y1="{rows_top}" x2="{x0}" y2="{rows_top+len(items)*row_h}" stroke="{C_POI}" stroke-width="1.6"/>')
        px_per_unit = (bw - 74) / maxv
        for i, it in enumerate(items):
            nm, val = it[0], it[ci + 1]
            y = rows_top + i * row_h + row_h / 2
            s.append(txt(x0 - 12, y + 5, nm, 12.5, "bold", C_TEXT, "end"))
            s.append(f'<rect x="{x0}" y="{y-bar_h/2}" width="{round(bw-74,1)}" height="{bar_h}" fill="#f7f8fa" stroke="none"/>')
            if val:
                s.append(f'<rect x="{x0}" y="{y-bar_h/2}" width="{round(val*px_per_unit,1)}" '
                         f'height="{bar_h}" fill="{col}" fill-opacity="0.72" stroke="{col}" stroke-width="1"/>')
            s.append(txt(x0 + 8 + max(val * px_per_unit, 0), y + 5, f"{val:,}", 12,
                         "bold", col if val else "#888888"))
        base = rows_top + len(items) * row_h + 8
        s.append(f'<line x1="{x0}" y1="{base}" x2="{x0+bw-14}" y2="{base}" stroke="{C_POI}" stroke-width="1.6"/>')
        s.append(txt(x0, base + 26, "合计", 13.5, "bold", C_TEXT))
        s.append(txt(x0 + bw - 14, base + 26, f"{totals[ci]:,} {unit}", 16, "bold", col, "end"))
        if npeople:
            s.append(txt(x0, base + 50, f"人均 {totals[ci]/npeople:,.0f} {unit}（按 {npeople} 人计）",
                         11.5, "normal", C_TEXTSUB))

    if note:
        yy = rows_top + len(items) * row_h + 96
        s += insight_box(left_pad - 42, yy, W - left_pad - right_pad + 42, note, title=note_title)
    s.append("</svg>")
    return "\n".join(s)


# ---------------------------------------------------------------------
#  行程时间轴（每天一条，长度 = 里程）
# ---------------------------------------------------------------------
def timeline_bars(W, H, title, subtitle, rows,
                  max_km=None, unit="公里", footer=None,
                  left_pad=104, right_pad=168, row_h=52, color=None):
    """rows: [{"day":"第 1 天","theme":"海口市区","km":25.0,"note":"骑楼老街 · 省博物馆"}]"""
    col = color or C_ROUTE
    maxv = max_km or max(r["km"] for r in rows) * 1.08
    s, top = chart_frame(W, H, title, subtitle)
    bw = W - left_pad - right_pad

    for i, r in enumerate(rows):
        y = top + i * row_h
        s.append(txt(left_pad - 14, y + 18, r["day"], 13.5, "bold", C_TEXT, "end"))
        cur = round(bw * (r["km"] / maxv), 1)
        s.append(f'<rect x="{left_pad}" y="{y}" width="{cur}" height="26" '
                 f'fill="{col}" fill-opacity="0.72" stroke="{col}"/>')
        lab = f"{r['km']:g} {unit}"
        if cur >= S.text_em(lab) * 12 + 22:
            # 柱子够宽：数值放柱内白字
            s.append(txt(left_pad + 10, y + 18, lab, 12, "bold", "#ffffff", halo=False))
        else:
            # 柱子太窄：数值挪到柱右下方、深色，避免白字溢出看不见
            s.append(txt(left_pad + cur + 10, y + 31, lab, 11.5, "bold", col, halo=False))
        s.append(txt(left_pad + bw * (r["km"] / maxv) + 10, y + 13, r["theme"], 12.5, "bold", C_TEXT))
        if r.get("note"):
            s.append(txt(left_pad + bw * (r["km"] / maxv) + 10, y + 31, r["note"], 11,
                         "normal", C_TEXTSUB))

    total = sum(r["km"] for r in rows)
    yy = top + len(rows) * row_h + 22
    s.append(f'<line x1="{left_pad}" y1="{yy}" x2="{W-right_pad}" y2="{yy}" stroke="{C_POI}" stroke-width="1.6"/>')
    s.append(txt(left_pad, yy + 28, "合计", 13.5, "bold", C_TEXT))
    s.append(txt(left_pad + 60, yy + 30, f"{total:g} {unit}", 17, "bold", col))
    for i, ln in enumerate(footer or []):
        s.append(txt(left_pad + 200, yy + 28 + i * 20, ln, 12 if i == 0 else 11,
                     "normal", C_TEXT if i == 0 else C_TEXTSUB))
    s.append("</svg>")
    return "\n".join(s)


# ---------------------------------------------------------------------
#  折线图（气温、客流、降雨）
# ---------------------------------------------------------------------
def line_chart(W, H, title, subtitle, x_labels, series, y_range=None,
               bands=None, notes=None, y_unit="", label_every=2,
               left_pad=76, right_pad=24, top_pad=84, bottom_pad=16):
    """series: [{"name":"海口","values":[...],"color":"#1f6f9e"}]

    底部布局是预算制的：x 轴标签 24 + 背景带 + 结论框，全部先算好高度，
    再用剩余空间做绘图区。H 给小了只会压扁曲线，不会裁掉结论框。
    """
    # ---- 底部需求预算 ----
    bands = bands or []
    max_row = max((b.get("row", 0) for b in bands), default=-1)
    bands_h = 0 if not bands else 40 + max_row * 28 + 22
    n_notes = 0 if not notes else (1 if isinstance(notes, str) else len(notes))
    notes_h = 0 if not notes else 24 + n_notes * 20 + 14  # 与 insight_box 的 h 公式一致
    bottom_need = 24 + (6 + bands_h if bands else 0) + (14 + notes_h if notes else 0) + bottom_pad
    plot_w = W - left_pad - right_pad
    plot_h = H - top_pad - bottom_need
    allv = [v for s in series for v in s["values"]]
    ymin, ymax = y_range or (min(allv) * 0.92, max(allv) * 1.04)

    def X(i):
        return left_pad + plot_w * i / max(len(x_labels) - 1, 1)

    def Y(v):
        return top_pad + plot_h - plot_h * (v - ymin) / (ymax - ymin)

    s, _ = chart_frame(W, H, title, subtitle)

    # 网格与轴标签
    step = max(round((ymax - ymin) / 4), 1)
    v = int(ymin // step * step)
    while v <= ymax:
        if v >= ymin:
            y = Y(v)
            s.append(f'<line x1="{left_pad}" y1="{round(y,1)}" x2="{W-right_pad}" y2="{round(y,1)}" stroke="{GRID}" stroke-width="1"/>')
            s.append(txt(left_pad - 12, round(y, 1) + 4, f"{v}{y_unit}", 10.5, "normal", C_TEXTSUB, "end"))
        v += step
    for i, lb in enumerate(x_labels):
        s.append(txt(X(i), top_pad + plot_h + 24, lb, 10.5, "normal", C_TEXTSUB, "middle"))

    # 背景带（台风季、雨季）
    for b in bands:
        i0, i1 = b["from"], b["to"]
        y0 = b.get("row", 0)
        s.append(f'<rect x="{X(i0)}" y="{top_pad+plot_h+40+y0*28}" width="{X(i1)-X(i0)}" '
                 f'height="22" fill="{b.get("fill","#dbe8f2")}" stroke="{b.get("stroke","#a9c4d8")}"/>')
        s.append(txt((X(i0) + X(i1)) / 2, top_pad + plot_h + 56 + y0 * 28, b["label"], 12,
                     "bold", b.get("text", "#2a5d80"), "middle"))

    s.append(f'<rect x="0" y="{top_pad}" width="{W}" height="{plot_h}" fill="none" stroke="#cbd6dd"/>')

    # 曲线
    for si, ser in enumerate(series):
        col = ser.get("color") or (C_ROUTE if si else C_ROUTE2)
        pts = [(X(i), Y(val)) for i, val in enumerate(ser["values"])]
        d = "M " + " L ".join(f"{round(x,1)} {round(y,1)}" for x, y in pts)
        s.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="3" stroke-linejoin="round"/>')
        for x, y in pts:
            s.append(f'<circle cx="{round(x,1)}" cy="{round(y,1)}" r="3.4" fill="#ffffff" '
                     f'stroke="{col}" stroke-width="2"/>')
        if label_every:
            for i, (x, y) in enumerate(pts):
                if i % label_every == 0:
                    dy = ser.get("dy", -10 if si else 20)
                    s.append(txt(x, y + dy, f"{ser['values'][i]:.0f}", 10, "normal", col, "middle"))
        # 系列名放在曲线起点附近（图内），避免右缘截断
        ax = ser.get("label_at", 0)
        s.append(txt(X(ax) + ser.get("label_dx", 14), Y(ser["values"][ax]) + ser.get("label_dy", -30),
                     ser["name"], 12.5, "bold", col))

    if notes:
        s += insight_box(left_pad, H - notes_h - bottom_pad, W - left_pad - right_pad,
                         [notes] if isinstance(notes, str) else notes)
    s.append("</svg>")
    return "\n".join(s)


# ---------------------------------------------------------------------
#  参数表（车程、门票、船班）
# ---------------------------------------------------------------------
def table_fig(W, H, title, subtitle, header, rows, widths=None,
              note=None, row_h=30, left_pad=32, right_pad=32, top_pad=100):
    """rows: [[c1, c2, ...]]，纯文本，单元格内不换行。"""
    s, _ = chart_frame(W, H, title, subtitle)
    n = len(header)
    widths = widths or [1.0 / n] * n
    avail = W - left_pad - right_pad
    xs, acc = [], left_pad
    for w in widths:
        xs.append(acc)
        acc += avail * w

    s.append(f'<rect x="{left_pad}" y="{top_pad-30}" width="{avail}" height="30" fill="#f2f2f2" stroke="#808080"/>')
    for i, h in enumerate(header):
        s.append(txt(xs[i] + 10, top_pad - 10, h, 12, "bold", C_TEXT))
    for r, row in enumerate(rows):
        y = top_pad + r * row_h
        fill = "#ffffff" if r % 2 == 0 else "#fbfbfb"
        s.append(f'<rect x="{left_pad}" y="{y}" width="{avail}" height="{row_h}" fill="{fill}" stroke="#c9d6de"/>')
        for i, cell in enumerate(row):
            s.append(txt(xs[i] + 10, y + row_h / 2 + 4.5, str(cell), 11.5, "normal", C_TEXT))
    if note:
        s += insight_box(left_pad, top_pad + len(rows) * row_h + 20,
                         avail, [note] if isinstance(note, str) else note)
    s.append("</svg>")
    return "\n".join(s)
