# -*- coding: utf-8 -*-
"""MolCanvas — 纯 PyQt5 3D 分子渲染器。

渲染逻辑移植自 LOG-render（D:\\LOG-render\\molcanvas.py），适配 xTBridge 的
dict 原子数据结构，保留 VMD 风格与 gau_default 球体渐变。
特性：球体渐变、深度排序键、环线十字准星、选中高亮、旋转/平移/缩放、多种视觉风格。
"""

import math

from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QPoint, QPointF
from PyQt5.QtGui import (
    QFont, QPainter, QPen, QBrush, QColor,
    QRadialGradient, QLinearGradient, QPainterPath,
)

from .atom_data import ATOM_RADII, ATOM_COLORS


# ═════════════════════════════════════════════════════
#  风格预设（移植自 LOG-render，保留 VMD 与 Chem311）
# ═════════════════════════════════════════════════════

STYLE_PRESETS = {
    "Houk": {
        "name": "Houk 经典",
        "bg_gradient": True,
        "bg_colors": ("#E8EDF5", "#F5F7FB", "#FFFFFF"),
        "bond_color": "#000000",
        "atom_scale": 0.32,
        "bond_width": 3.0,
        "shadows": True,
        "crosshair": True,
        "rim": True,
        "gradient": "full",
        "label_mode": 2,
    },
    "Academic": {
        "name": "学术论文",
        "bg_gradient": False,
        "bg_colors": ("#FFFFFF", "#FFFFFF", "#FFFFFF"),
        "bond_color": "#B0B8C4",
        "atom_scale": 0.32,
        "bond_width": 3.0,
        "shadows": True,
        "crosshair": False,
        "rim": False,
        "gradient": "soft_matte",
        "label_mode": 2,
    },
    "Publication": {
        "name": "期刊插图",
        "bg_gradient": False,
        "bg_colors": ("#FAFBFD", "#FAFBFD", "#FAFBFD"),
        "bond_color": "#7A8694",
        "atom_scale": 0.32,
        "bond_width": 3.0,
        "shadows": True,
        "crosshair": False,
        "rim": False,
        "gradient": "subtle",
        "label_mode": 2,
    },
    "CYLView": {
        "name": "CYLView",
        "bg_gradient": False,
        "bg_colors": ("#FFFFFF", "#FFFFFF", "#FFFFFF"),
        "bond_color": "#505050",
        "atom_scale": 0.32,
        "bond_width": 3.0,
        "shadows": False,
        "crosshair": True,
        "rim": True,
        "gradient": "flat",
        "label_mode": 2,
    },
    "AppleGlass": {
        "name": "Apple Glass",
        "bg_gradient": True,
        "bg_colors": ("#F3F7FB", "#FFFFFF", "#F8FAFC"),
        "bond_color": "#C0C7D1",
        "atom_scale": 0.32,
        "bond_width": 3.0,
        "shadows": True,
        "crosshair": False,
        "rim": False,
        "gradient": "soft_matte",
        "label_mode": 2,
    },
    "DarkPro": {
        "name": "深色专业",
        "bg_gradient": False,
        "bg_colors": ("#121417", "#121417", "#121417"),
        "bond_color": "#707780",
        "atom_scale": 0.32,
        "bond_width": 3.0,
        "shadows": False,
        "crosshair": False,
        "rim": False,
        "gradient": "soft_matte",
        "label_mode": 2,
    },
    # SobArt = sob-art 经典白键风格，显示名 Chem311（贴合 AIM 默认）
    "SobArt": {
        "name": "Chem311",
        "bg_gradient": False,
        "bg_colors": ("#FFFFFF", "#FFFFFF", "#FFFFFF"),
        "bond_color": "#FFFFFF",
        "atom_scale": 0.30,
        "bond_width": 3.5,
        "shadows": False,
        "crosshair": False,
        "rim": True,
        "gradient": "sob_art",
        "label_mode": 2,
    },
    "AppleLiquid": {
        "name": "Apple Liquid Glass",
        "bg_gradient": True,
        "bg_colors": ("#EEF4FF", "#F8FBFF", "#FFFFFF"),
        "bond_color": "#C7D2E0",
        "atom_scale": 0.19,
        "bond_width": 3.2,
        "shadows": True,
        "crosshair": False,
        "rim": False,
        "gradient": "apple_liquid",
        "label_mode": 2,
    },
    "ModernPaper": {
        "name": "Modern Paper",
        "bg_gradient": True,
        "bg_colors": ("#F8FAFC", "#FFFFFF", "#F1F5F9"),
        "bond_color": "#D6DEE8",
        "atom_scale": 0.30,
        "bond_width": 2.6,
        "shadows": True,
        "crosshair": False,
        "rim": True,
        "gradient": "paper_matte",
        "label_mode": 2,
    },
    "HoukPremium": {
        "name": "Houk Premium",
        "bg_gradient": True,
        "bg_colors": ("#EAF0F8", "#F8FBFF", "#FFFFFF"),
        "bond_color": "#28323D",
        "atom_scale": 0.31,
        "bond_width": 2.8,
        "shadows": True,
        "crosshair": True,
        "rim": True,
        "gradient": "premium_full",
        "label_mode": 2,
    },
    "SoftClay": {
        "name": "Soft Clay",
        "bg_gradient": True,
        "bg_colors": ("#F6F7F4", "#FFFFFF", "#EEF1ED"),
        "bond_color": "#BBC5C0",
        "atom_scale": 0.33,
        "bond_width": 3.1,
        "shadows": True,
        "crosshair": False,
        "rim": True,
        "gradient": "clay_matte",
        "label_mode": 2,
    },
    "GlassPlus": {
        "name": "Glass Plus",
        "bg_gradient": True,
        "bg_colors": ("#EEF6FF", "#FFFFFF", "#F6FAFF"),
        "bond_color": "#D3DEEA",
        "atom_scale": 0.24,
        "bond_width": 3.0,
        "shadows": True,
        "crosshair": False,
        "rim": True,
        "gradient": "glass_plus",
        "label_mode": 2,
    },
    "DarkNeon": {
        "name": "Dark Neon",
        "bg_gradient": True,
        "bg_colors": ("#10151D", "#161D27", "#0B0F14"),
        "bond_color": "#65758A",
        "atom_scale": 0.30,
        "bond_width": 3.0,
        "shadows": False,
        "crosshair": False,
        "rim": True,
        "gradient": "neon_glow",
        "label_mode": 2,
    },
    "InkMinimal": {
        "name": "Ink Minimal",
        "bg_gradient": False,
        "bg_colors": ("#FFFFFF", "#FFFFFF", "#FFFFFF"),
        "bond_color": "#222222",
        "atom_scale": 0.25,
        "bond_width": 1.8,
        "shadows": False,
        "crosshair": False,
        "rim": True,
        "gradient": "ink_flat",
        "label_mode": 2,
    },
    # xTBridge 独有：VMD 深色背景 + 标准 CPK
    "VMD": {
        "name": "VMD 默认",
        "bg_gradient": False,
        "bg_colors": ("#202020", "#202020", "#202020"),
        "bond_color": "#FFFFFF",
        "atom_scale": 0.30,
        "bond_width": 3.2,
        "shadows": False,
        "crosshair": False,
        "rim": True,
        "gradient": "flat",
        "label_mode": 2,
    },
    # HoukMol：移植自 gau_xtb_viewer.py 的默认样式
    #   黑色 RoundCap 实线键 + gau_default 球体渐变 + 0.8px 黑描边 + 标准 CPK
    "HoukMol": {
        "name": "HoukMol",
        "bg_gradient": True,
        "bg_colors": ("#E8EDF5", "#F5F7FB", "#FFFFFF"),
        "bond_color": "#000000",
        "atom_scale": 0.30,
        "bond_width": 10,          # 按 scale=80 折算，绘制时 × zoom × scale/80
        "shadows": True,
        "crosshair": False,
        "rim": False,              # 用 0.8px 黑描边代替 rim
        "gradient": "gau_default",
        "label_mode": 2,
    },
}


# ═════════════════════════════════════════════════════
#  风格专用 CPK 配色
# ═════════════════════════════════════════════════════

SOB_ART_CPK = {
    'H': '#F0F0F0', 'C': '#B38F5C', 'N': '#3050F8', 'O': '#FF2010',
    'S': '#FFC832', 'P': '#FF8020', 'F': '#7AE060',
    'Cl': '#30C040', 'Br': '#802020', 'I': '#620062',
}

_NON_METALS = {
    'H', 'He', 'B', 'C', 'N', 'O', 'F', 'Ne',
    'Si', 'P', 'S', 'Cl', 'Ar',
    'Ge', 'As', 'Se', 'Br', 'Kr',
    'Sb', 'Te', 'I', 'Xe', 'Rn', 'At',
}

APPLE_CPK = {
    'H': '#F7F8FA', 'C': '#A8B4C3', 'N': '#6F9EFF', 'O': '#FF7B8A',
    'S': '#FFD166', 'P': '#FFB366', 'F': '#81D8D0', 'Cl': '#78D67A',
}

PAPER_CPK = {
    'H': '#F8FAFC', 'C': '#A5B0BC', 'N': '#5B7FE8', 'O': '#EF5B5B',
    'S': '#E6B94A', 'P': '#E58A4A', 'F': '#78D7C6',
    'Cl': '#74C476', 'Br': '#A06A5E', 'I': '#8C6DB3',
}

CLAY_CPK = {
    'H': '#F2F0EA', 'C': '#9C9285', 'N': '#6278B8', 'O': '#C96E64',
    'S': '#D6B85C', 'P': '#C98655', 'F': '#80BFA8',
    'Cl': '#86B878', 'Br': '#8E5D55', 'I': '#75608E',
}


# ═════════════════════════════════════════════════════
#  MolCanvas
# ═════════════════════════════════════════════════════

class MolCanvas(QWidget):
    """3D 分子可视化画布 — 支持旋转/缩放/平移、多种视觉风格、环线十字准星、选中高亮。

    原子数据为 dict: {'idx','sym','x','y','z'}（xTBridge 接口）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.atoms = []           # [{'idx','sym','x','y','z'}, ...]
        self.bonds = []           # [(idx1, idx2), ...]
        self._projected = []      # [(sx, sy, sz, r), ...]
        self.rot_x = 30.0
        self.rot_y = -45.0
        self.rot_z = 0.0
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.scale = 80.0
        self._drag_start = None
        self._drag_rot = None
        self._drag_pan = None
        self._click_pos = None

        # 选中原子（高亮）与点击回调
        self.selected_atom = None
        self.selected_atom2 = None
        self.on_atom_click = None

        # 风格属性（默认 HoukMol — 移植自 gau_xtb_viewer.py）
        self._current_style = "HoukMol"
        self.bg_gradient = True
        self.bg_colors = ("#E8EDF5", "#F5F7FB", "#FFFFFF")
        self.bond_color_hex = "#000000"
        self.atom_scale = 0.30
        self.bond_width = 10
        self.show_shadows = True
        self.show_crosshair = False
        self.rim_visible = False
        self.gradient_type = "gau_default"
        self.label_mode = 2     # 0=元素, 1=编号, 2=无

        # 环线十字准星角度（Houk 风格用）
        self.ring_a_angle = 90
        self.ring_a_tilt = 71
        self.ring_b_angle = 205
        self.ring_b_tilt = 0

        self.setMouseTracking(True)
        self.setMinimumSize(350, 280)

    # ── 数据 ──

    def set_data(self, atoms, bonds):
        self.atoms = atoms
        self.bonds = bonds
        self.selected_atom = None
        self.selected_atom2 = None
        self.auto_fit()

    def set_style(self, style_key):
        if style_key not in STYLE_PRESETS:
            return
        p = STYLE_PRESETS[style_key]
        self._current_style = style_key
        self.bg_gradient = p["bg_gradient"]
        self.bg_colors = p["bg_colors"]
        self.bond_color_hex = p["bond_color"]
        self.atom_scale = p["atom_scale"]
        self.bond_width = p["bond_width"]
        self.show_shadows = p["shadows"]
        self.show_crosshair = p["crosshair"]
        self.rim_visible = p["rim"]
        self.gradient_type = p["gradient"]
        self.label_mode = p["label_mode"]
        self.update()

    def auto_fit(self):
        if not self.atoms:
            return
        cw, ch = self.width(), self.height()
        if cw < 2 or ch < 2:
            return
        max_ext = 0.0
        for a in self.atoms:
            max_ext = max(max_ext, abs(a['x']), abs(a['y']), abs(a['z']))
        self.rot_x, self.rot_y, self.rot_z = 30.0, -45.0, 0.0
        self.zoom = 1.0
        self.pan_x, self.pan_y = 0.0, 0.0
        self.scale = min(cw, ch) / (max_ext * 2.8 + 1)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.atoms:
            self.auto_fit()

    # ── 3D 变换 ──

    def _rotate(self, x, y, z):
        rx = math.radians(self.rot_x)
        y1 = y * math.cos(rx) - z * math.sin(rx)
        z1 = y * math.sin(rx) + z * math.cos(rx)
        ry = math.radians(self.rot_y)
        x1 = x * math.cos(ry) + z1 * math.sin(ry)
        z2 = -x * math.sin(ry) + z1 * math.cos(ry)
        rz = math.radians(self.rot_z)
        x2 = x1 * math.cos(rz) - y1 * math.sin(rz)
        y2 = x1 * math.sin(rz) + y1 * math.cos(rz)
        return x2, y2, z2

    def _project(self, x, y, z):
        cw, ch = max(self.width(), 1), max(self.height(), 1)
        px, py, pz = self._rotate(x, y, z)
        s = self.scale * self.zoom
        return cw / 2 + px * s + self.pan_x, ch / 2 - py * s + self.pan_y, pz

    def _atom_screen_radius(self, sym):
        r = ATOM_RADII.get(sym, 0.7) * self.scale * self.zoom * self.atom_scale
        # LOG-render 逻辑：H 放大 1.5，非金属放大 1.15，金属缩小 0.85
        if sym == 'H':
            r *= 1.50
        elif sym in _NON_METALS:
            r *= 1.15
        else:
            r *= 0.85
        return max(r, 3)

    def _depth_factor(self, z_val):
        return max(0.3, min(1.0, 0.5 + 0.5 * ((z_val + 10) / 20)))

    # ── 颜色工具 ──

    @staticmethod
    def _hex_to_rgb(h):
        return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)

    @classmethod
    def _brighten(cls, hex_color, factor=0.25):
        r, g, b = cls._hex_to_rgb(hex_color)
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f"#{r:02X}{g:02X}{b:02X}"

    @staticmethod
    def _brighten_color(c, f=0.25):
        """Brighten a QColor by factor f。"""
        return QColor(
            min(255, int(c.red() + (255 - c.red()) * f)),
            min(255, int(c.green() + (255 - c.green()) * f)),
            min(255, int(c.blue() + (255 - c.blue()) * f)),
        )

    @classmethod
    def _mix_hex(cls, hex_color, target="#FFFFFF", amount=0.5):
        r, g, b = cls._hex_to_rgb(hex_color)
        rt, gt, bt = cls._hex_to_rgb(target)
        r = int(r * (1 - amount) + rt * amount)
        g = int(g * (1 - amount) + gt * amount)
        b = int(b * (1 - amount) + bt * amount)
        return f"#{r:02X}{g:02X}{b:02X}"

    def _get_atom_color(self, sym):
        """根据当前风格返回原子颜色。"""
        style = self._current_style
        if style == "VMD":
            return ATOM_COLORS.get(sym, '#AAAAAA')
        if style == "SobArt":
            return SOB_ART_CPK.get(sym, '#AAAAAA')
        if style == "HoukMol":
            # gau_xtb_viewer 默认风格：直接用标准 CPK，不做 brighten
            return ATOM_COLORS.get(sym, '#B8B8B8')
        if style in ("AppleLiquid", "GlassPlus"):
            return APPLE_CPK.get(sym, '#AEB8C4')
        if style in ("ModernPaper", "HoukPremium"):
            return PAPER_CPK.get(sym, self._brighten(ATOM_COLORS.get(sym, '#AAAAAA'), 0.18))
        if style == "SoftClay":
            return CLAY_CPK.get(sym, self._mix_hex(ATOM_COLORS.get(sym, '#AAAAAA'), "#D8D0C2", 0.32))
        if style == "InkMinimal":
            return self._mix_hex(PAPER_CPK.get(sym, ATOM_COLORS.get(sym, '#AAAAAA')), "#FFFFFF", 0.34)
        return self._brighten(ATOM_COLORS.get(sym, '#AAAAAA'))

    # ── 球体渐变 ──

    @staticmethod
    def _clamp_color(rv, gv, bv, df):
        rr = int(rv * df)
        gg = int(gv * df)
        bb = int(bv * df)
        if rr < 0: rr = 0
        if rr > 255: rr = 255
        if gg < 0: gg = 0
        if gg > 255: gg = 255
        if bb < 0: bb = 0
        if bb > 255: bb = 255
        return QColor(rr, gg, bb)

    def _make_sphere_gradient(self, hex_color, r, sx, sy, depth_factor):
        r0, g0, b0 = self._hex_to_rgb(hex_color)
        df = depth_factor
        ho = r * 0.3
        grad = QRadialGradient(QPointF(sx - ho, sy - ho), r)
        gt = self.gradient_type

        def c(rv, gv, bv):
            return self._clamp_color(rv, gv, bv, df)

        def hi():
            return c(min(255, r0 + 35), min(255, g0 + 35), min(255, b0 + 35))

        if gt == "flat":
            grad.setColorAt(0.0, c(r0, g0, b0))
            grad.setColorAt(1.0, c(r0, g0, b0))
            return grad

        if gt == "ink_flat":
            grad.setColorAt(0.0, QColor(hex_color))
            grad.setColorAt(1.0, QColor(hex_color))
            return grad

        # xTBridge 保留：gau_default 渐层球体（brighten + darker）
        if gt == "gau_default":
            base = QColor(hex_color)
            ho2 = r * 0.25
            grad2 = QRadialGradient(QPointF(sx - ho2, sy - ho2), r)
            grad2.setColorAt(0.0, self._brighten_color(base, 0.5))
            grad2.setColorAt(0.15, self._brighten_color(base, 0.2))
            grad2.setColorAt(0.5, base)
            grad2.setColorAt(0.85, base.darker(140))
            grad2.setColorAt(1.0, base.darker(180))
            return grad2

        if gt == "sob_art":
            grad.setColorAt(0.00, c(min(255, r0 + 95), min(255, g0 + 95), min(255, b0 + 95)))
            grad.setColorAt(0.06, c(r0 + (255 - r0) * 0.90, g0 + (255 - g0) * 0.90, b0 + (255 - b0) * 0.90))
            grad.setColorAt(0.14, c(r0, g0, b0))
            grad.setColorAt(0.40, c(r0, g0, b0))
            grad.setColorAt(0.68, c(int(r0 * 0.80), int(g0 * 0.80), int(b0 * 0.80)))
            grad.setColorAt(1.00, c(int(r0 * 0.55), int(g0 * 0.55), int(b0 * 0.55)))
            return grad

        if gt == "apple_liquid":
            grad.setColorAt(0.00, c(min(255, r0 + 85), min(255, g0 + 85), min(255, b0 + 85)))
            grad.setColorAt(0.08, c(min(255, r0 + 55), min(255, g0 + 55), min(255, b0 + 55)))
            grad.setColorAt(0.30, c(r0, g0, b0))
            grad.setColorAt(0.70, c(int(r0 * 0.95), int(g0 * 0.95), int(b0 * 0.95)))
            grad.setColorAt(1.00, c(int(r0 * 0.75), int(g0 * 0.75), int(b0 * 0.75)))
            return grad

        if gt == "paper_matte":
            grad.setColorAt(0.00, c(r0 + (255 - r0) * 0.62, g0 + (255 - g0) * 0.62, b0 + (255 - b0) * 0.62))
            grad.setColorAt(0.18, c(r0 + (255 - r0) * 0.26, g0 + (255 - g0) * 0.26, b0 + (255 - b0) * 0.26))
            grad.setColorAt(0.56, c(r0, g0, b0))
            grad.setColorAt(0.86, c(int(r0 * 0.90), int(g0 * 0.90), int(b0 * 0.90)))
            grad.setColorAt(1.00, c(int(r0 * 0.78), int(g0 * 0.78), int(b0 * 0.78)))
            return grad

        if gt == "premium_full":
            grad.setColorAt(0.00, c(min(255, r0 + 58), min(255, g0 + 58), min(255, b0 + 58)))
            grad.setColorAt(0.05, c(r0 + (255 - r0) * 0.78, g0 + (255 - g0) * 0.78, b0 + (255 - b0) * 0.78))
            grad.setColorAt(0.20, c(r0 + (255 - r0) * 0.34, g0 + (255 - g0) * 0.34, b0 + (255 - b0) * 0.34))
            grad.setColorAt(0.52, c(r0, g0, b0))
            grad.setColorAt(0.82, c(int(r0 * 0.84), int(g0 * 0.84), int(b0 * 0.84)))
            grad.setColorAt(1.00, c(int(r0 * 0.68), int(g0 * 0.68), int(b0 * 0.68)))
            return grad

        if gt == "clay_matte":
            grad.setColorAt(0.00, c(r0 + (255 - r0) * 0.42, g0 + (255 - g0) * 0.42, b0 + (255 - b0) * 0.42))
            grad.setColorAt(0.20, c(r0 + (255 - r0) * 0.12, g0 + (255 - g0) * 0.12, b0 + (255 - b0) * 0.12))
            grad.setColorAt(0.62, c(r0, g0, b0))
            grad.setColorAt(0.84, c(int(r0 * 0.88), int(g0 * 0.88), int(b0 * 0.88)))
            grad.setColorAt(1.00, c(int(r0 * 0.70), int(g0 * 0.70), int(b0 * 0.70)))
            return grad

        if gt == "glass_plus":
            grad.setColorAt(0.00, c(min(255, r0 + 110), min(255, g0 + 110), min(255, b0 + 110)))
            grad.setColorAt(0.07, c(r0 + (255 - r0) * 0.92, g0 + (255 - g0) * 0.92, b0 + (255 - b0) * 0.92))
            grad.setColorAt(0.24, c(r0 + (255 - r0) * 0.32, g0 + (255 - g0) * 0.32, b0 + (255 - b0) * 0.32))
            grad.setColorAt(0.58, c(r0, g0, b0))
            grad.setColorAt(0.82, c(int(r0 * 1.08), int(g0 * 1.08), int(b0 * 1.08)))
            grad.setColorAt(1.00, c(int(r0 * 0.66), int(g0 * 0.66), int(b0 * 0.66)))
            return grad

        if gt == "neon_glow":
            grad.setColorAt(0.00, c(min(255, r0 + 120), min(255, g0 + 120), min(255, b0 + 120)))
            grad.setColorAt(0.10, c(min(255, r0 + 72), min(255, g0 + 72), min(255, b0 + 72)))
            grad.setColorAt(0.34, c(r0, g0, b0))
            grad.setColorAt(0.70, c(int(r0 * 0.72), int(g0 * 0.72), int(b0 * 0.72)))
            grad.setColorAt(1.00, c(int(r0 * 0.42), int(g0 * 0.42), int(b0 * 0.42)))
            return grad

        if gt == "subtle":
            grad.setColorAt(0.00, hi())
            grad.setColorAt(0.12, c(r0 + (255 - r0) * 0.40, g0 + (255 - g0) * 0.40, b0 + (255 - b0) * 0.40))
            grad.setColorAt(0.40, c(r0, g0, b0))
            grad.setColorAt(0.80, c(int(r0 * 0.85), int(g0 * 0.85), int(b0 * 0.85)))
            grad.setColorAt(1.00, c(int(r0 * 0.72), int(g0 * 0.72), int(b0 * 0.72)))
            return grad

        if gt == "soft_matte":
            grad.setColorAt(0.00, c(min(255, r0 + 55), min(255, g0 + 55), min(255, b0 + 55)))
            grad.setColorAt(0.08, c(r0 + (255 - r0) * 0.15, g0 + (255 - g0) * 0.15, b0 + (255 - b0) * 0.15))
            grad.setColorAt(0.25, c(r0, g0, b0))
            grad.setColorAt(0.60, c(r0, g0, b0))
            grad.setColorAt(0.82, c(int(r0 * 0.82), int(g0 * 0.82), int(b0 * 0.82)))
            grad.setColorAt(1.00, c(int(r0 * 0.62), int(g0 * 0.62), int(b0 * 0.62)))
            return grad

        # fallback "full"
        grad.setColorAt(0.00, hi())
        grad.setColorAt(0.06, c(r0 + (255 - r0) * 0.75, g0 + (255 - g0) * 0.75, b0 + (255 - b0) * 0.75))
        grad.setColorAt(0.18, c(r0 + (255 - r0) * 0.30, g0 + (255 - g0) * 0.30, b0 + (255 - b0) * 0.30))
        grad.setColorAt(0.40, c(r0 + (255 - r0) * 0.05, g0 + (255 - g0) * 0.05, b0 + (255 - b0) * 0.05))
        grad.setColorAt(0.65, c(r0, g0, b0))
        grad.setColorAt(0.85, c(int(r0 * 0.86), int(g0 * 0.86), int(b0 * 0.86)))
        grad.setColorAt(1.00, c(int(r0 * 0.75), int(g0 * 0.75), int(b0 * 0.75)))
        return grad

    # ── 命中测试 ──

    def _find_nearest_atom(self, mx, my):
        best, best_dist = None, float('inf')
        for i, (sx, sy, sz, r) in enumerate(self._projected):
            d = math.sqrt((mx - sx) ** 2 + (my - sy) ** 2)
            if d < max(r, 10) and d < best_dist:
                best, best_dist = i + 1, d
        return best

    # ── 鼠标事件 ──

    def mousePressEvent(self, event):
        self._drag_start = (event.x(), event.y())
        self._drag_rot = (self.rot_x, self.rot_y)
        self._drag_pan = (self.pan_x, self.pan_y)
        self._click_pos = (event.x(), event.y())

    def mouseMoveEvent(self, event):
        if self._drag_start is None or not self.atoms:
            return
        dx = event.x() - self._drag_start[0]
        dy = event.y() - self._drag_start[1]
        if event.buttons() & Qt.LeftButton:
            self.rot_y = self._drag_rot[1] + dx * 0.5
            self.rot_x = self._drag_rot[0] - dy * 0.5
        elif event.buttons() & Qt.RightButton:
            self.pan_x = self._drag_pan[0] + dx
            self.pan_y = self._drag_pan[1] + dy
        self.update()

    def mouseReleaseEvent(self, event):
        if self._click_pos:
            dx = event.x() - self._click_pos[0]
            dy = event.y() - self._click_pos[1]
            # 视为点击（未拖动）则选中原子
            if abs(dx) < 5 and abs(dy) < 5:
                atom_idx = self._find_nearest_atom(event.x(), event.y())
                if atom_idx is not None:
                    self.selected_atom = atom_idx
                    self.update()
                    if self.on_atom_click:
                        self.on_atom_click(atom_idx)
                else:
                    self.selected_atom = None
                    self.update()
        self._drag_start = None
        self._click_pos = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y() / 120.0
        self.zoom = max(0.1, self.zoom * (1.0 + delta * 0.15))
        self.update()

    # ── 渲染 ──

    def paintEvent(self, event):
        bg0, bg1, bg2 = self.bg_colors
        is_dark = self._current_style in ("DarkPro", "DarkNeon", "VMD")

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景
        if self.bg_gradient:
            bg = QLinearGradient(0, 0, 0, self.height())
            bg.setColorAt(0.0, QColor(bg0))
            bg.setColorAt(0.5, QColor(bg1))
            bg.setColorAt(1.0, QColor(bg2))
            painter.fillRect(self.rect(), QBrush(bg))
        else:
            painter.fillRect(self.rect(), Qt.black if is_dark else Qt.white)

        # 无数据提示
        if not self.atoms:
            painter.setPen(QColor('#94A3B8') if not is_dark else QColor('#586E8A'))
            painter.drawText(self.rect(), Qt.AlignCenter, "选择 .gjf 文件以查看 3D 结构")
            painter.end()
            return

        # 投影所有原子
        self._projected = []
        for a in self.atoms:
            try:
                sx, sy, sz = self._project(a['x'], a['y'], a['z'])
            except Exception:
                continue
            r = self._atom_screen_radius(a['sym'])
            self._projected.append((sx, sy, sz, r))
        if not self._projected:
            painter.end()
            return

        # ── 键（按深度排序，先画）──
        bond_items = []
        for a1_idx, a2_idx in self.bonds:
            i1, i2 = a1_idx - 1, a2_idx - 1
            if 0 <= i1 < len(self._projected) and 0 <= i2 < len(self._projected):
                p1, p2 = self._projected[i1], self._projected[i2]
                bond_items.append(((p1[2] + p2[2]) / 2, p1, p2, i1, i2))
        bond_items.sort(key=lambda x: x[0])

        is_sob_art = self._current_style == "SobArt"
        is_vmd = self._current_style == "VMD"
        is_neon = self._current_style == "DarkNeon"
        is_ink = self._current_style == "InkMinimal"
        is_gau = self._current_style == "HoukMol"

        for avg_z, p1, p2, ai, aj in bond_items:
            sx1, sy1, sr1 = p1[0], p1[1], p1[3]
            sx2, sy2, sr2 = p2[0], p2[1], p2[3]
            dx, dy = sx2 - sx1, sy2 - sy1
            length = math.sqrt(dx * dx + dy * dy)
            if length < 1:
                continue
            df = self._depth_factor(avg_z)
            w = max(1.5, self.bond_width * self.zoom * df)
            cut1, cut2 = sr1 * 0.85, sr2 * 0.85
            r1 = cut1 / length
            r2 = cut2 / length
            x1 = sx1 + dx * r1
            y1 = sy1 + dy * r1
            x2 = sx2 - dx * r2
            y2 = sy2 - dy * r2
            nx = -dy / length
            ny = dx / length
            hw = w * 0.5

            cx1, cy1 = x1 + nx * hw, y1 + ny * hw
            cx2, cy2 = x1 - nx * hw, y1 - ny * hw
            cx3, cy3 = x2 - nx * hw, y2 - ny * hw
            cx4, cy4 = x2 + nx * hw, y2 + ny * hw
            mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2

            if is_ink:
                painter.save()
                painter.setPen(QPen(QColor(self.bond_color_hex), max(1, int(w)), cap=Qt.RoundCap))
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
                painter.restore()
                continue

            # HoukMol：gau_xtb_viewer 默认风格 — 黑色 RoundCap 实线键
            # 宽度按 bond_width × zoom × scale/80 折算（与 gau_xtb_viewer 一致）
            if is_gau:
                bw = self.bond_width * self.zoom * (self.scale / 80)
                painter.save()
                painter.setPen(QPen(QColor(self.bond_color_hex), bw, Qt.SolidLine, Qt.RoundCap))
                painter.setBrush(Qt.NoBrush)
                painter.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))
                painter.restore()
                continue

            # SobArt / VMD：半色键（两端各取原子色）
            if is_sob_art or is_vmd:
                sym1 = self.atoms[ai]['sym']
                sym2 = self.atoms[aj]['sym']
                if is_vmd:
                    col1 = ATOM_COLORS.get(sym1, '#AAAAAA')
                    col2 = ATOM_COLORS.get(sym2, '#AAAAAA')
                else:
                    col1 = SOB_ART_CPK.get(sym1, '#AAAAAA')
                    col2 = SOB_ART_CPK.get(sym2, '#AAAAAA')
                mcx1, mcy1 = (cx1 + cx4) / 2, (cy1 + cy4) / 2
                mcx2, mcy2 = (cx2 + cx3) / 2, (cy2 + cy3) / 2
                for half, col_hex in [(0, col1), (1, col2)]:
                    if half == 0:
                        ax1, ay1, ax2, ay2, ax3, ay3, ax4, ay4 = (
                            cx1, cy1, cx2, cy2, mcx2, mcy2, mcx1, mcy1)
                    else:
                        ax1, ay1, ax2, ay2, ax3, ay3, ax4, ay4 = (
                            mcx1, mcy1, mcx2, mcy2, cx3, cy3, cx4, cy4)
                    r_b, g_b, b_b = self._hex_to_rgb(col_hex)
                    gmid_x = (ax1 + ax4) / 2
                    gmid_y = (ay1 + ay4) / 2
                    knx = ax2 - ax1
                    kny = ay2 - ay1
                    klen = max(1, math.sqrt(knx * knx + kny * kny))
                    knx, kny = knx / klen, kny / klen
                    hw2 = hw * 1.0
                    ks = QLinearGradient(
                        gmid_x - knx * hw2, gmid_y - kny * hw2,
                        gmid_x + knx * hw2, gmid_y + kny * hw2,
                    )
                    ks.setColorAt(0.00, QColor(max(0, min(255, int(r_b * df * 0.62))),
                                               max(0, min(255, int(g_b * df * 0.62))),
                                               max(0, min(255, int(b_b * df * 0.62)))))
                    ks.setColorAt(0.15, QColor(max(0, min(255, int(r_b * df * 0.80))),
                                               max(0, min(255, int(g_b * df * 0.80))),
                                               max(0, min(255, int(b_b * df * 0.80)))))
                    ks.setColorAt(0.30, QColor(max(0, min(255, int(r_b * df * 0.96))),
                                               max(0, min(255, int(g_b * df * 0.96))),
                                               max(0, min(255, int(b_b * df * 0.96)))))
                    ks.setColorAt(0.44, QColor(max(0, min(255, int(r_b * df * 1.15))),
                                               max(0, min(255, int(g_b * df * 1.15))),
                                               max(0, min(255, int(b_b * df * 1.15)))))
                    ks.setColorAt(0.56, QColor(max(0, min(255, int(r_b * df * 1.10))),
                                               max(0, min(255, int(g_b * df * 1.10))),
                                               max(0, min(255, int(b_b * df * 1.10)))))
                    ks.setColorAt(0.70, QColor(max(0, min(255, int(r_b * df * 0.92))),
                                               max(0, min(255, int(g_b * df * 0.92))),
                                               max(0, min(255, int(b_b * df * 0.92)))))
                    ks.setColorAt(0.85, QColor(max(0, min(255, int(r_b * df * 0.70))),
                                               max(0, min(255, int(g_b * df * 0.70))),
                                               max(0, min(255, int(b_b * df * 0.70)))))
                    ks.setColorAt(1.00, QColor(max(0, min(255, int(r_b * df * 0.55))),
                                               max(0, min(255, int(g_b * df * 0.55))),
                                               max(0, min(255, int(b_b * df * 0.55)))))
                    path = QPainterPath()
                    path.moveTo(ax1, ay1)
                    path.lineTo(ax4, ay4)
                    path.lineTo(ax3, ay3)
                    path.lineTo(ax2, ay2)
                    path.closeSubpath()
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(ks))
                    painter.drawPath(path)
            else:
                # 通用键：bond_color 渐层
                bond_rgb = self._hex_to_rgb(self.bond_color_hex)
                r_b, g_b, b_b = bond_rgb
                ks = QLinearGradient(
                    mid_x - nx * hw, mid_y - ny * hw,
                    mid_x + nx * hw, mid_y + ny * hw,
                )

                def bc(factor):
                    return QColor(
                        max(0, min(255, int(r_b * df * factor))),
                        max(0, min(255, int(g_b * df * factor))),
                        max(0, min(255, int(b_b * df * factor))),
                    )

                ks.setColorAt(0.00, bc(0.42))
                ks.setColorAt(0.15, bc(0.60))
                ks.setColorAt(0.30, bc(0.88))
                ks.setColorAt(0.44, bc(1.07))
                ks.setColorAt(0.56, bc(1.03))
                ks.setColorAt(0.70, bc(0.80))
                ks.setColorAt(0.85, bc(0.52))
                ks.setColorAt(1.00, bc(0.38))
                path = QPainterPath()
                path.moveTo(cx1, cy1)
                path.lineTo(cx4, cy4)
                path.lineTo(cx3, cy3)
                path.lineTo(cx2, cy2)
                path.closeSubpath()
                if is_neon:
                    painter.save()
                    painter.setOpacity(0.14)
                    painter.setPen(QPen(QColor("#8FB8FF"), max(2, int(w * 2.8)), cap=Qt.RoundCap))
                    painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
                    painter.restore()
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(ks))
                painter.drawPath(path)

        # ── 原子绘制顺序（按深度）──
        draw_order = sorted(enumerate(self._projected), key=lambda x: x[1][2])

        # 阴影（键之后、原子之前）
        if self.show_shadows:
            for i, (sx, sy, sz, r) in draw_order:
                if r < 5:
                    continue
                df = self._depth_factor(sz)
                if self._current_style == "AppleLiquid":
                    opacity = 0.02 + 0.04 * df
                    shx, shy = int(sx + r * 0.15), int(sy + r * 0.35)
                    shrx, shry = int(r * 1.05), max(1, int(r * 0.22))
                elif self._current_style in ("AppleGlass", "GlassPlus", "ModernPaper"):
                    opacity = 0.03 + 0.06 * df
                    shx, shy = int(sx + r * 0.3), int(sy + r * 0.55)
                    shrx, shry = int(r * 1.25), max(1, int(r * 0.32))
                elif self._current_style == "SoftClay":
                    opacity = 0.05 + 0.10 * df
                    shx, shy = int(sx + r * 0.3), int(sy + r * 0.55)
                    shrx, shry = int(r * 1.25), max(1, int(r * 0.32))
                else:
                    opacity = 0.06 + 0.12 * df
                    shx, shy = int(sx + r * 0.3), int(sy + r * 0.55)
                    shrx, shry = int(r * 1.25), max(1, int(r * 0.32))
                painter.save()
                painter.setOpacity(opacity)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(0, 0, 0)))
                painter.drawEllipse(QPoint(shx, shy), shrx, shry)
                painter.restore()

        is_glass = self._current_style in ("AppleLiquid", "GlassPlus")

        # ── 原子 ──
        for i, (sx, sy, sz, r) in draw_order:
            a = self.atoms[i]
            sym = a['sym']
            idx = a['idx']
            ax, ay, az = a['x'], a['y'], a['z']
            color = self._get_atom_color(sym)
            df = self._depth_factor(sz)
            cx, cy = int(sx), int(sy)
            ir = int(r)

            # DarkNeon 辉光
            if is_neon and ir > 4:
                glow = QColor(color)
                painter.save()
                painter.setPen(Qt.NoPen)
                for k, alpha in enumerate((34, 22, 12)):
                    glow.setAlpha(alpha)
                    painter.setBrush(QBrush(glow))
                    painter.drawEllipse(QPoint(cx, cy), ir + 4 + k * 5, ir + 4 + k * 5)
                painter.restore()

            # 球体
            sphere_grad = self._make_sphere_gradient(color, r, sx, sy, df)
            # HoukMol：0.8px 黑色描边（gau_xtb_viewer 默认风格）
            if is_gau:
                painter.setPen(QPen(QColor("#000000"), 0.8))
            else:
                painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(sphere_grad))
            painter.drawEllipse(QPoint(cx, cy), ir, ir)

            # Glass 高光
            if is_glass and ir > 4:
                painter.save()
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 255, 255, 105 if self._current_style == "GlassPlus" else 90))
                painter.drawEllipse(int(cx - ir * 0.42), int(cy - ir * 0.42),
                                    int(ir * 0.60), int(ir * 0.45))
                painter.restore()

            if is_glass and ir > 4:
                painter.save()
                for k in range(4):
                    painter.setOpacity(0.055 - k * 0.010 if self._current_style == "GlassPlus" else 0.04 - k * 0.008)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(255, 255, 255))
                    painter.drawEllipse(QPoint(cx, cy), ir + k * 2, ir + k * 2)
                painter.restore()

            if is_glass and ir > 6:
                painter.save()
                painter.setOpacity(0.22 if self._current_style == "GlassPlus" else 0.15)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 255, 255))
                path = QPainterPath()
                path.moveTo(cx - ir * 0.6, cy - ir * 0.15)
                path.quadTo(cx, cy - ir * 0.55, cx + ir * 0.55, cy - ir * 0.05)
                path.quadTo(cx + ir * 0.38, cy - ir * 0.22, cx - ir * 0.5, cy - ir * 0.22)
                path.closeSubpath()
                painter.drawPath(path)
                painter.restore()

            # 轮廓线
            if ir > 6 and self.rim_visible:
                gt = self.gradient_type
                if gt == "sob_art":
                    rim = QColor(0, 0, 0, 200)
                    rim_w = max(1, int(ir * 0.10))
                elif gt == "flat":
                    rim = QColor(20, 20, 20)
                    rim_w = max(1, int(ir * 0.12))
                elif gt == "ink_flat":
                    rim = QColor(25, 25, 25, 210)
                    rim_w = max(1, int(ir * 0.10))
                elif gt == "glass_plus":
                    rim = QColor(255, 255, 255, 140)
                    rim_w = max(1, int(ir * 0.06))
                elif gt == "paper_matte":
                    rim = QColor(92, 111, 132, 90)
                    rim_w = max(1, int(ir * 0.045))
                elif gt == "clay_matte":
                    rim = QColor(92, 80, 70, 90)
                    rim_w = max(1, int(ir * 0.055))
                elif gt == "premium_full":
                    rim = QColor(24, 34, 46, 145)
                    rim_w = max(1, int(ir * 0.055))
                elif gt == "neon_glow":
                    rim = QColor(color)
                    rim.setAlpha(210)
                    rim_w = max(1, int(ir * 0.07))
                elif gt == "soft_matte":
                    base_r = int(color[1:3], 16)
                    base_g = int(color[3:5], 16)
                    base_b = int(color[5:7], 16)
                    rim = QColor(int(base_r * 0.55 + 100 * 0.45),
                                 int(base_g * 0.55 + 115 * 0.45),
                                 int(base_b * 0.55 + 130 * 0.45), 110)
                    rim_w = max(1, int(ir * 0.05))
                elif is_dark:
                    rim = QColor(min(255, int(int(color[1:3], 16) * df * 0.50)),
                                 min(255, int(int(color[3:5], 16) * df * 0.50)),
                                 min(255, int(int(color[5:7], 16) * df * 0.50)))
                    rim_w = max(1, int(ir * 0.06))
                else:
                    rim = QColor(int(int(color[1:3], 16) * df * 0.25),
                                 int(int(color[3:5], 16) * df * 0.25),
                                 int(int(color[5:7], 16) * df * 0.25))
                    rim_w = max(1, int(ir * 0.08))
                painter.setPen(QPen(rim, rim_w))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPoint(cx, cy), ir, ir)

            # 选中高亮（金色 / 青色双选）
            if self.selected_atom == idx:
                hw_sel = max(2, int(ir * 0.2))
                painter.setPen(QPen(QColor('#FFD700'), hw_sel))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPoint(cx, cy), ir, ir)

            if self.selected_atom2 == idx:
                hw_sel = max(2, int(ir * 0.2))
                painter.setPen(QPen(QColor('#00BCD4'), hw_sel))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPoint(cx, cy), ir, ir)

            # 环线十字准星（Houk 风格：两个倾斜环，只画前半）
            if self.show_crosshair and ir > 4:
                n_pts = 60
                pen_w = max(1, int(ir * 0.06))
                painter.save()
                xhair_color = QColor(200, 210, 230, 180) if is_dark else QColor(0, 0, 0, 130)
                painter.setPen(QPen(xhair_color, pen_w, cap=Qt.RoundCap))
                _, _, cz = self._project(ax, ay, az)
                rr = ir / self.scale / self.zoom * 0.92

                def _draw_front_arc(ring_points):
                    path = QPainterPath()
                    started = False
                    for px, py, pz in ring_points:
                        if pz >= cz:
                            if not started:
                                path.moveTo(px, py)
                                started = True
                            else:
                                path.lineTo(px, py)
                        else:
                            started = False
                    painter.drawPath(path)

                def _ring(azimuth, tilt):
                    az_r = math.radians(azimuth)
                    ti_r = math.radians(tilt)
                    ux = -math.sin(az_r)
                    uy = math.cos(az_r)
                    uz = 0.0
                    vx = -math.cos(az_r) * math.sin(ti_r)
                    vy = -math.sin(az_r) * math.sin(ti_r)
                    vz = math.cos(ti_r)
                    pts = []
                    for k in range(n_pts + 1):
                        t = 2 * math.pi * k / n_pts
                        ct = math.cos(t)
                        st = math.sin(t)
                        wx = ax + rr * (ux * ct + vx * st)
                        wy = ay + rr * (uy * ct + vy * st)
                        wz = az + rr * (uz * ct + vz * st)
                        px, py, pz = self._project(wx, wy, wz)
                        pts.append((px, py, pz))
                    _draw_front_arc(pts)

                _ring(self.ring_a_angle, self.ring_a_tilt)
                _ring(self.ring_b_angle, self.ring_b_tilt)
                painter.restore()

            # 标签
            if ir >= 6 and self.label_mode != 2:
                label_color = QColor(220, 220, 230) if is_dark else Qt.black
                painter.setPen(QPen(label_color))
                fm = painter.fontMetrics()
                if self.label_mode == 0:
                    label = sym
                else:
                    label = str(idx)
                tw = fm.horizontalAdvance(label)
                th = fm.height()
                fs = max(7, int(ir * 0.7))
                font = painter.font()
                font.setPointSize(fs)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(int(sx - tw / 2), int(sy + th / 3), label)

        painter.end()
