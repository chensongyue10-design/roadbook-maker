# -*- coding: utf-8 -*-
"""
lib_svg —— 路书地图通用绘图库（零业务知识）

设计原则
--------
1. 这里只放"怎么画"，不放"画什么"。经纬度、海岸线、地名一律由调用方传入。
2. 颜色不是散落的常量，而是一个 Theme；模块级 C_* 常量是它的兼容别名。
3. 投影对象 Projection 会回传真实 scale，比例尺必须从它取，禁止自己算 px/km。
4. 提供两套签名：老的坐标签名（pts_ll, bbox, W, H, PAD）与新的投影签名（proj, ...）。
   两者靠参数类型自动分派，老脚本可以原样跑。

典型用法
--------
    from lib_svg import *

    proj = make_projection((18.60, 19.76, 110.18, 111.10), 760, 880, 54)
    s  = svg_open(760, 880, "第 3 天路线总览")
    s += poly(proj, COAST, fill=C_LAND)
    s += draw_route(proj, ROUTE, C_ROUTE, 5)
    s += poi(proj, 19.666, 111.023, "文昌铜鼓岭", "起点", side="right")
    s += scalebar(proj, 64, 824, 70)
    svg = svg_doc(760, 880, s, "第 3 天路线总览")
"""
import math
import os
import re

__all__ = [
    # 主题与常量
    "Theme", "DEFAULT", "FONT",
    "C_SEA", "C_SEA_DEEP", "C_LAND", "C_GREEN", "C_COAST", "C_HIGHWAY",
    "C_NATROAD", "C_TOURROAD", "C_ROUTE", "C_ROUTE2", "C_POI",
    "C_TEXT", "C_TEXTSUB", "C_BOX", "C_BOXEDGE",
    # 投影
    "Projection", "make_projection", "project", "fit_bbox",
    # 路径
    "path_d", "smooth_d", "poly", "line", "draw_route",
    # 文字
    "text_em", "txt", "labelbox", "leader", "water",
    # 图元
    "svg_open", "svg_doc", "north", "scalebar", "legend_box", "numbox",
    "poi", "poi_xy", "poi_num", "side_list",
    # 输出
    "write_svg", "check_text_bounds",
]


# =====================================================================
#  主题
# =====================================================================
class Theme:
    """一本路书一套配色。改这里就换了全书的视觉。"""

    def __init__(self, **kw):
        self.sea = "#cfe4f2"        # 浅蓝海面
        self.sea_deep = "#b3d4e8"   # 深水区
        self.land = "#f9f5e9"       # 陆地米白
        self.green = "#dbebd2"      # 林地 / 保护区
        self.coast = "#7d9aae"      # 海岸线
        self.highway = "#f2bd63"    # 高速公路（橘黄）
        self.natroad = "#e0805c"    # 国道省道
        self.tourroad = "#4a86b8"   # 旅游公路（蓝，虚线）
        self.route = "#c0392b"      # 当日主行车路线（正红）
        self.route2 = "#1f6f9e"     # 次路线 / 支线（蓝）
        self.poi = "#1f3a4d"        # 点位描边
        self.text = "#0f2b39"       # 主文字
        self.textsub = "#57707f"    # 次文字
        self.box = "#ffffff"        # 标注框底
        self.boxedge = "#c9d6de"    # 标注框边
        # 字体：末尾务必带 CJK 回退，否则没装宋体的机器会 fallback 成无衬线，
        # 行宽整体变化，之前算好的所有标签偏移全部失效。
        self.font_stack = "Songti SC, SimSun, Noto Serif CJK SC, serif"
        for k, v in kw.items():
            if not hasattr(self, k):
                raise AttributeError(f"Theme 没有字段 {k!r}")
            setattr(self, k, v)


DEFAULT = Theme()

# 兼容别名：老脚本 `from mapgen import C_SEA` 仍可用
C_SEA, C_SEA_DEEP, C_LAND, C_GREEN = DEFAULT.sea, DEFAULT.sea_deep, DEFAULT.land, DEFAULT.green
C_COAST, C_HIGHWAY, C_NATROAD = DEFAULT.coast, DEFAULT.highway, DEFAULT.natroad
C_TOURROAD, C_ROUTE, C_ROUTE2 = DEFAULT.tourroad, DEFAULT.route, DEFAULT.route2
C_POI, C_TEXT, C_TEXTSUB, C_BOX, C_BOXEDGE = (
    DEFAULT.poi, DEFAULT.text, DEFAULT.textsub, DEFAULT.box, DEFAULT.boxedge)

# 注意：这里刻意不带引号，与历史版本的 SVG 输出保持逐字节一致
FONT = "Songti SC, SimSun, serif"


# =====================================================================
#  投影
# =====================================================================
class Projection:
    """等距圆柱 + 纬度余弦修正。把经纬度换成画布坐标，并把 scale 留给比例尺用。

    bbox = (lat_min, lat_max, lng_min, lng_max)
    """

    __slots__ = ("bbox", "W", "H", "pad", "kx", "ky", "scale", "off_x", "off_y")

    def __init__(self, bbox, W, H, pad):
        lat_min, lat_max, lng_min, lng_max = bbox
        if lat_min >= lat_max or lng_min >= lng_max:
            raise ValueError(f"bbox 顺序应为 (lat_min, lat_max, lng_min, lng_max)，收到 {bbox}")
        if W - 2 * pad <= 0 or H - 2 * pad <= 0:
            raise ValueError(f"pad={pad} 太大，画布 {W}x{H} 放不下")
        self.bbox = tuple(bbox)
        self.W, self.H, self.pad = W, H, pad
        lat_mid = (lat_min + lat_max) / 2.0
        self.kx = 111.32 * math.cos(math.radians(lat_mid))   # 经度方向 km/度
        self.ky = 110.57                                     # 纬度方向 km/度
        span_x = (lng_max - lng_min) * self.kx
        span_y = (lat_max - lat_min) * self.ky
        avail_w, avail_h = W - 2 * pad, H - 2 * pad
        self.scale = min(avail_w / span_x, avail_h / span_y)  # px/km
        self.off_x = (avail_w - span_x * self.scale) / 2.0
        self.off_y = (avail_h - span_y * self.scale) / 2.0

    def __call__(self, lat, lng):
        lat_min, lat_max, lng_min, lng_max = self.bbox
        x = self.pad + self.off_x + (lng - lng_min) * self.kx * self.scale
        y = self.pad + self.off_y + (lat_max - lat) * self.ky * self.scale
        return (round(x, 1), round(y, 1))

    def many(self, pts):
        return [self(lat, lng) for lat, lng in pts]

    @property
    def km_per_px(self):
        """比例尺唯一来源。历史代码自己在外部算，高窄图会偏长约 12%。"""
        return 1.0 / self.scale

    def km_px(self, km):
        """给定公里数，返回应该画多长（px）。"""
        return km * self.scale

    def contains(self, lat, lng, margin=0.0):
        lat_min, lat_max, lng_min, lng_max = self.bbox
        return (lat_min - margin <= lat <= lat_max + margin and
                lng_min - margin <= lng <= lng_max + margin)

    def __repr__(self):
        return (f"Projection(bbox={self.bbox}, {self.W}x{self.H}, "
                f"scale={self.scale:.2f}px/km, pad={self.pad})")


def make_projection(bbox, W, H, pad):
    return Projection(bbox, W, H, pad)


def project(pts, bbox, W, H, pad):
    """老签名：直接返回坐标列表。新代码建议用 make_projection().many()。"""
    proj = Projection(bbox, W, H, pad)
    return proj.many(pts)


def fit_bbox(points_ll, aspect=1.0, pad_ratio=0.08):
    """按点位自动取景。aspect = 画布宽/高，用于把没点位的方向也撑开。"""
    lats = [p[0] for p in points_ll]
    lngs = [p[1] for p in points_ll]
    lat_min, lat_max = min(lats), max(lats)
    lng_min, lng_max = min(lngs), max(lngs)
    lat_mid = (lat_min + lat_max) / 2.0
    kx = 111.32 * math.cos(math.radians(lat_mid))
    ky = 110.57
    span_x = max((lng_max - lng_min) * kx, 1e-6)
    span_y = max((lat_max - lat_min) * ky, 1e-6)
    if span_x / span_y < aspect:                 # 太窄，横向撑开
        want = span_y * aspect
        d = (want - span_x) / 2.0 / kx
        lng_min, lng_max = lng_min - d, lng_max + d
    else:                                        # 太扁，纵向撑开
        want = span_x / aspect
        d = (want - span_y) / 2.0 / ky
        lat_min, lat_max = lat_min - d, lat_max + d
    dx = (lng_max - lng_min) * pad_ratio
    dy = (lat_max - lat_min) * pad_ratio
    return (round(lat_min - dy, 5), round(lat_max + dy, 5),
            round(lng_min - dx, 5), round(lng_max + dx, 5))


# =====================================================================
#  路径
# =====================================================================
def path_d(coords, close=False):
    d = "M " + " L ".join(f"{x} {y}" for x, y in coords)
    if close:
        d += " Z"
    return d


def smooth_d(coords, close=False):
    """Catmull-Rom 转贝塞尔，让海岸线和路线更自然。"""
    if len(coords) < 3:
        return path_d(coords, close)
    p = list(coords)
    if close:
        p = [p[-1]] + p + [p[0], p[1]]
    else:
        p = [p[0]] + p + [p[-1]]
    d = f"M {p[1][0]} {p[1][1]}"
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        d += (f" C {round(c1[0],1)} {round(c1[1],1)}, "
              f"{round(c2[0],1)} {round(c2[1],1)}, {p2[0]} {p2[1]}")
    if close:
        d += " Z"
    return d


def poly(proj, pts_ll, fill, stroke="none", sw=1.0, close=True, smooth=True,
         opacity=None):
    """填充面：海、陆地、林地、保护区。"""
    d = smooth_d(proj.many(pts_ll), close) if smooth else path_d(proj.many(pts_ll), close)
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return (f'<path d="{d}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linejoin="round"{op}/>')


def line(proj, pts_ll, color, width=4, dash=None, halo=True, halo_extra=4,
         cap="round", smooth=True):
    """画线：公路、路线、支线。halo=True 会给一层白底，压在底色上也看得清。"""
    d = smooth_d(proj.many(pts_ll)) if smooth else path_d(proj.many(pts_ll))
    da = f' stroke-dasharray="{dash}"' if dash else ""
    out = []
    if halo:
        out.append(f'<path d="{d}" fill="none" stroke="#ffffff" '
                   f'stroke-width="{width + halo_extra}" stroke-linecap="{cap}"/>')
    out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
               f'stroke-linecap="{cap}"{da}/>')
    return out


def draw_route(*args, **kw):
    """双签名，按第一个参数类型自动分派。

    新：draw_route(proj, pts_ll, color, width=5, dash=None, halo=True)
    旧：draw_route(pts_ll, bbox, W, H, PAD, color, width=5, dash=None, halo=True)
    """
    if args and isinstance(args[0], Projection):
        proj, pts = args[0], args[1]
        rest = list(args[2:])
        color = rest[0] if rest else kw.pop("color", C_ROUTE)
        width = rest[1] if len(rest) > 1 else kw.pop("width", 5)
        dash = rest[2] if len(rest) > 2 else kw.pop("dash", None)
        halo = rest[3] if len(rest) > 3 else kw.pop("halo", True)
        return line(proj, pts, color, width=width, dash=dash, halo=halo)
    # 旧签名
    pts_ll, bbox, W, H, PAD = args[:5]
    color = kw.pop("color", C_ROUTE)
    width = kw.pop("width", 5)
    dash = kw.pop("dash", None)
    halo = kw.pop("halo", True)
    p = project(pts_ll, bbox, W, H, PAD)
    da = f' stroke-dasharray="{dash}"' if dash else ""
    out = []
    if halo:
        out.append(f'<path d="{smooth_d(p)}" fill="none" stroke="#ffffff" '
                   f'stroke-width="{width + 4}" stroke-linecap="round"/>')
    out.append(f'<path d="{smooth_d(p)}" fill="none" stroke="{color}" '
               f'stroke-width="{width}" stroke-linecap="round"{da}/>')
    return out


# =====================================================================
#  文字
# =====================================================================
def text_em(s):
    """估算文字宽度（单位 em）。这就是"标签压线"问题的唯一根因所在。

    不能用 len(s)：它把"100.4 公里"和"博鳌"当成同一单价，
    结果白底框要么太宽要么太窄。中文 1em、数字 0.56em、西文 0.55em、空格 0.3em。
    """
    w = 0.0
    for ch in s:
        o = ord(ch)
        if o >= 0x2E80:          # CJK 统一表意文字、全角标点、假名
            w += 1.0
        elif ch.isdigit():
            w += 0.56
        elif ch == " ":
            w += 0.30
        elif o >= 0x2000:        # 通用标点（·—→ 等）
            w += 0.55
        else:
            w += 0.55
    return w


def txt(x, y, s, size=12, weight="normal", fill=None, anchor="start",
        italic=False, halo=True, font=None, opacity=None):
    fill = fill or C_TEXT
    halo_attr = (' paint-order="stroke" stroke="#ffffff" stroke-width="3" '
                 'stroke-linejoin="round"') if halo else ""
    it = ' font-style="italic"' if italic else ""
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" font-family="{font or FONT}"'
            f'{halo_attr}{it}{op}>{s}</text>')


def labelbox(x, y, s, size=12, anchor="middle", pad=16, em=False):
    """白底标注框。em=True 用 text_em 精确估宽（新代码建议开）。"""
    w = (text_em(s) if em else len(s) * 0.95) * size + pad
    h = size + 14
    if anchor == "middle":
        rx = x - w / 2
    elif anchor == "start":
        rx = x
    else:
        rx = x - w
    return (f'<rect x="{round(rx,1)}" y="{round(y-h/2,1)}" '
            f'width="{round(w,1)}" height="{h}" '
            f'fill="{C_BOX}" stroke="{C_BOXEDGE}" stroke-width="1"/>'
            + f'<text x="{round(rx+w/2,1)}" y="{round(y+size*0.36,1)}" '
              f'font-size="{size}" fill="{C_TEXT}" text-anchor="middle" '
              f'font-family="{FONT}">{s}</text>')


def leader(proj, a_ll, b_ll, text="", color=None, dash="5,4", size=13):
    """引线 + 说明。点位太密、标签放不下时，把名字拉到空白处。"""
    color = color or C_ROUTE
    ax, ay = proj(*a_ll) if isinstance(a_ll, (tuple, list)) else a_ll
    bx, by = proj(*b_ll) if isinstance(b_ll, (tuple, list)) else b_ll
    out = [f'<line x1="{ax}" y1="{ay}" x2="{bx}" y2="{by}" stroke="{color}" '
           f'stroke-width="1.4" stroke-dasharray="{dash}"/>',
           f'<circle cx="{bx}" cy="{by}" r="2.6" fill="{color}"/>']
    if text:
        out.append(txt(bx + 6, by + 4, text, size, "normal", C_TEXT))
    return out


def water(proj, lat, lng, text, size=13, color="#6d90a8", spacing=None):
    """海域名 / 江河名，斜体浅蓝，不带白描边。"""
    x, y = proj(lat, lng)
    sp = f' letter-spacing="{spacing}"' if spacing else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
            f'font-family="{FONT}" font-style="italic" text-anchor="middle"'
            f'{sp}>{text}</text>')


# =====================================================================
#  画布与图元
# =====================================================================
def svg_open(w, h, label=""):
    a = f' role="img" aria-label="{label}"' if label else ""
    return [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg"{a}>']


def svg_doc(w, h, parts, label=""):
    """把零件列表拼成完整 SVG 字符串。"""
    if isinstance(parts, str):
        parts = [parts]
    return "".join(svg_open(w, h, label)) + "".join(parts) + "</svg>"


def north(x, y, size=1.0):
    sc = f" scale({size})" if size != 1.0 else ""
    return (f'<g transform="translate({x},{y}){sc}">'
            f'<polygon points="0,-18 6,7 0,0 -6,7" fill="{C_POI}"/>'
            f'{txt(0,-26,"北",13,"bold",C_TEXT,"middle")}</g>')


def _scalebar_body(x, y, km, px_per_km):
    w = km * px_per_km
    mid = ("%g" % (km / 2))  # 2.5 不能截成 2
    return (f'<g transform="translate({x},{y})">'
            f'<line x1="0" y1="0" x2="{round(w,1)}" y2="0" stroke="{C_POI}" stroke-width="1.8"/>'
            f'<line x1="0" y1="-5" x2="0" y2="5" stroke="{C_POI}" stroke-width="1.8"/>'
            f'<line x1="{round(w,1)}" y1="-5" x2="{round(w,1)}" y2="5" stroke="{C_POI}" stroke-width="1.8"/>'
            f'<line x1="{round(w/2,1)}" y1="-4" x2="{round(w/2,1)}" y2="4" stroke="{C_POI}" stroke-width="1.2"/>'
            f'{txt(0,-10,"0",10.5,"normal",C_TEXTSUB,"middle")}'
            f'{txt(round(w/2,1),-10,mid,10.5,"normal",C_TEXTSUB,"middle")}'
            f'{txt(round(w,1),-10,str(km)+" 公里",10.5,"normal",C_TEXTSUB,"middle")}</g>')


def scalebar(*args, **kw):
    """双签名：

    新：scalebar(proj, x, y, km)      —— 长度自动从 proj.scale 算
    旧：scalebar(x, y, km, px_per_km) —— 长度由调用方自己给

    历史坑：旧签名里外部手算的 px/km 没考虑 letterbox 留白，高窄图会偏长 10% 以上。
    新代码一律用投影签名。
    """
    if args and isinstance(args[0], Projection):
        proj, x, y, km = args[:4]
        return _scalebar_body(x, y, km, proj.scale)
    x, y, km, px_per_km = args[:4]
    return _scalebar_body(x, y, km, px_per_km)


def legend_box(x, y, w, rows, title=None):
    """通用图例框。rows: [(kind, color, label)]，kind ∈ line/dash/dot/square/box"""
    out = []
    th = 30 if title else 14
    h = th + len(rows) * 26 + 12
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#ffffff" '
               f'stroke="{C_BOXEDGE}" stroke-width="1.2"/>')
    if title:
        out.append(txt(x + 14, y + 26, title, 13.5, "bold", C_TEXT))
    for i, (kind, col, label) in enumerate(rows):
        y0 = y + th + 14 + i * 26
        if kind == "line":
            out.append(f'<line x1="{x+14}" y1="{y0}" x2="{x+46}" y2="{y0}" '
                       f'stroke="{col}" stroke-width="4.5" stroke-linecap="round"/>')
        elif kind == "dash":
            out.append(f'<line x1="{x+14}" y1="{y0}" x2="{x+46}" y2="{y0}" '
                       f'stroke="{col}" stroke-width="3.4" stroke-dasharray="8,5"/>')
        elif kind == "dot":
            out.append(f'<circle cx="{x+30}" cy="{y0}" r="7" fill="#fff" '
                       f'stroke="{col}" stroke-width="2.8"/>')
        elif kind == "square":
            out.append(f'<rect x="{x+20}" y="{y0-9}" width="18" height="18" '
                       f'fill="#fff" stroke="{col}" stroke-width="2.4"/>')
        else:
            out.append(f'<rect x="{x+16}" y="{y0-8}" width="26" height="16" '
                       f'fill="{col}" stroke="{col}"/>')
        out.append(txt(x + 58, y0 + 4, label, 11.5, "normal", C_TEXT))
    return out


def numbox(x, y, num, rec=False, size=24, color=None):
    """编号方框。rec=True 表示"推荐"，用主路线红加粗。"""
    col = color or (C_ROUTE if rec else C_POI)
    sw = 3.4 if rec else 2.4
    return [
        f'<rect x="{round(x-size/2,1)}" y="{round(y-size/2,1)}" width="{size}" '
        f'height="{size}" fill="#ffffff" stroke="{col}" stroke-width="{sw}"/>',
        txt(x, y + size * 0.24, str(num), 13.5, "bold", col, "middle"),
    ]


def _poi_body(x, y, name, sub, side, name_size, sub_size):
    out = [
        f'<circle cx="{x}" cy="{y}" r="9.5" fill="#ffffff" stroke="{C_ROUTE}" stroke-width="3"/>',
        f'<circle cx="{x}" cy="{y}" r="3.2" fill="{C_ROUTE}"/>',
    ]
    if side == "right":
        ox, anc = x + 16, "start"
    elif side == "left":
        ox, anc = x - 16, "end"
    elif side == "top":
        ox, anc = x, "middle"
    else:
        ox, anc = x, "middle"
    if side in ("right", "left"):
        out.append(txt(ox, y - 4, name, name_size, "bold", C_TEXT, anc))
        out.append(txt(ox, y + 16, sub, sub_size, "normal", C_TEXTSUB, anc))
    else:
        out.append(txt(ox, y - 18, name, name_size, "bold", C_TEXT, anc))
        out.append(txt(ox, y + 30, sub, sub_size, "normal", C_TEXTSUB, anc))
    return out


def poi_xy(x, y, name, sub, side, name_size=14.5, sub_size=11.5):
    """老签名：直接给画布坐标。"""
    return _poi_body(x, y, name, sub, side, name_size, sub_size)


def poi(proj, lat, lng, name, sub="", side="right", offset=(16, -4),
        name_size=14.5, sub_size=11.5, marker="dot"):
    """新签名：给经纬度，自动投影。

    offset 是标签相对点位的像素微调，是唯一允许硬编码在图脚本里的视觉参数。
    密集点位（间距 < 40px）不要用 poi，改用 poi_num + side_list：
    文字重叠可以接受，编号重叠不能接受。
    """
    x, y = proj(lat, lng)
    if marker == "dot":
        out = [
            f'<circle cx="{x}" cy="{y}" r="9.5" fill="#ffffff" stroke="{C_ROUTE}" stroke-width="3"/>',
            f'<circle cx="{x}" cy="{y}" r="3.2" fill="{C_ROUTE}"/>',
        ]
    else:
        out = numbox(x, y, marker, rec=True)
    dx, dy = offset
    if side == "right":
        ox, anc = x + dx, "start"
    elif side == "left":
        ox, anc = x + dx, "end"
    elif side == "top":
        ox, anc = x + dx, "middle"
    else:
        ox, anc = x + dx, "middle"
    if side in ("right", "left"):
        out.append(txt(ox, y + dy, name, name_size, "bold", C_TEXT, anc))
        if sub:
            out.append(txt(ox, y + dy + 20, sub, sub_size, "normal", C_TEXTSUB, anc))
    else:
        out.append(txt(ox, y + dy - 14, name, name_size, "bold", C_TEXT, anc))
        if sub:
            out.append(txt(ox, y + dy + 34, sub, sub_size, "normal", C_TEXTSUB, anc))
    return out


def poi_num(proj, lat, lng, num, rec=False, size=22, offset=(0, 0), color=None):
    """密集区专用：只画编号，名字交给 side_list。"""
    x, y = proj(lat, lng)
    return numbox(x + offset[0], y + offset[1], num, rec=rec, size=size, color=color)


def side_list(x, y, w, rows, title=None, rec_first=False, row_h=24, size=11.5):
    """编号清单，配合 poi_num 使用。rows: [(num, text)] 或 [(num, text, rec)]"""
    th = 28 if title else 10
    h = th + len(rows) * row_h + 10
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#ffffff" '
           f'stroke="{C_BOXEDGE}" stroke-width="1.2"/>']
    if title:
        out.append(txt(x + 12, y + 20, title, 12.5, "bold", C_TEXT))
    for i, row in enumerate(rows):
        num, label = row[0], row[1]
        rec = row[2] if len(row) > 2 else (rec_first and i == 0)
        y0 = y + th + 12 + i * row_h
        out += numbox(x + 20, y0, num, rec=rec, size=15)
        out.append(txt(x + 36, y0 + 4.5, label, size, "normal", C_TEXT))
    return out


# =====================================================================
#  输出与校验
# =====================================================================
def write_svg(path, svg):
    """原子写，返回 sha256。用于回归比对。"""
    import hashlib
    data = svg.encode("utf-8") if isinstance(svg, str) else svg
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return hashlib.sha256(data).hexdigest()


def check_text_bounds(svg_path, browser=None, tol=0.5):
    """用浏览器读每个 <text> 的真实 bbox，找出越界或互相重叠的标签。

    这是唯一能真正发现"字出框"的手段：光看 SVG 源码看不出来，
    因为文字宽度取决于渲染字体。返回问题清单，空列表表示干净。
    """
    from playwright.sync_api import sync_playwright  # 延迟导入，不用时不报错

    problems = []
    with sync_playwright() as p:
        kw = {"executable_path": browser} if browser else {}
        b = p.chromium.launch(**kw)
        page = b.new_page()
        page.goto("file:///" + os.path.abspath(svg_path).replace("\\", "/"))
        data = page.evaluate("""() => {
            const svg = document.querySelector('svg');
            const vb = svg.viewBox.baseVal;
            const box = {w: vb.width, h: vb.height};
            const out = [];
            for (const t of svg.querySelectorAll('text')) {
                const r = t.getBBox();
                out.push({t: t.textContent, x: r.x, y: r.y, w: r.width, h: r.height});
            }
            return {box, items: out};
        }""")
        b.close()

    W, H = data["box"]["w"], data["box"]["h"]
    items = data["items"]
    for it in items:
        if it["x"] < -tol or it["y"] < -tol:
            problems.append(f"越界(左上)：{it['t']!r} @({it['x']:.1f},{it['y']:.1f})")
        if it["x"] + it["w"] > W + tol or it["y"] + it["h"] > H + tol:
            problems.append(f"越界(右下)：{it['t']!r} 右={it['x']+it['w']:.1f}/{W} 下={it['y']+it['h']:.1f}/{H}")
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, c = items[i], items[j]
            ox = min(a["x"] + a["w"], c["x"] + c["w"]) - max(a["x"], c["x"])
            oy = min(a["y"] + a["h"], c["y"] + c["h"]) - max(a["y"], c["y"])
            if ox > 2 and oy > 2:
                problems.append(f"文字重叠：{a['t']!r} ↔ {c['t']!r}")
    return problems
