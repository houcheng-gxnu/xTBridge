"""xTBridge 主窗口 — 3 Tab GUI: Gaussian+xTB External / xTB Standalone / ORCA Submit。"""

import json
import math
import os
import re
import shutil
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFileDialog, QDialog, QTabWidget,
    QGroupBox, QGridLayout, QSpinBox, QMessageBox, QComboBox, QCheckBox,
    QDoubleSpinBox, QSplitter, QFrame, QScrollArea, QShortcut,
    QSlider,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QTextCursor, QKeySequence

from .atom_data import ATOMIC_NUMBERS, _MULT_TEXT, ALPB_SOLVENTS, COSMO_SOLVENTS
from .file_parser import (
    _auto_bonds, parse_gjf_coords_all, parse_xyz_coords,
    parse_xtb_scan_log, parse_orca_allxyz,
    load_molecule, parse_last_standard_orientation,
)
from .mol_canvas import MolCanvas, STYLE_PRESETS
from .widgets import StatusButton, ScanChart
from .workers import GaussianWorker, XtbWorker, OrcaWorker
from .orca_utils import ORCA_EXE, build_orca_input
from .translator import TR


def _app_dir() -> Path:
    """配置文件目录（exe 所在目录或项目根目录，始终可写）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _pkg_dir() -> Path:
    """xtbridge 包自身目录（含 gau_xtb.py / OfakeG 等内嵌依赖）。
    开发模式: 指向 xtbridge/ 目录
    打包模式: 指向 PyInstaller _MEIPASS（gau_xtb.py / OfakeG 被 datas 解压到这里）
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", str(Path(sys.executable).parent)))
    return Path(__file__).resolve().parent

CONFIG_FILE = _app_dir() / "xTBridge_config.json"

class GauXtbViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self._worker: GaussianWorker | XtbWorker | OrcaWorker | None = None
        self._lang = "zh"
        self._config = {
            "gaussian_path": "", "xtb_path": "",
            "gfn_level": 2, "threads": min(os.cpu_count() or 4, 8),
            "extra_args": "",
            # ORCA
            "orca_path": ORCA_EXE, "orca_method": "XTB2",
            "orca_basis": "", "orca_job_type": "SP",
            "orca_nprocs": 4, "orca_memory": 4096,
            "orca_solvent_idx": 0, "orca_solvent_name": "water",
            "orca_extra": "", "orca_ofakeg_path": "",
        }
        self._orca_atoms = []
        self._orca_bonds = []
        self._orca_qst2_product_atoms = []
        self._orca_out_path = None
        self._load_config()
        self._init_ui()
        self._apply_config()
        self._apply_lang_ui()
        # 日志行计数器（每 50 行做一次行数裁剪，避免卡顿）
        self._log_line_count = 0
        self._xtb_log_line_count = 0
        self._orca_log_line_count = 0

    def _tr(self, key, **fmt):
        """获取翻译文字（支持 {key} 格式化）。"""
        s = TR.get(key, {}).get(self._lang, key)
        if fmt:
            s = s.format(**fmt)
        return s

    def _switch_lang(self):
        """切换中英文。"""
        self._lang = "en" if self._lang == "zh" else "zh"
        self._apply_lang_ui()

    def _apply_lang_ui(self):
        """刷新所有 UI 文字以匹配当前语言。"""
        self.setWindowTitle(self._tr("win_title"))
        self._lang_btn.setText(self._tr("lang_btn"))
        self._lang_btn2.setText(self._tr("lang_btn"))

        # Tab titles
        self.main_tabs.setTabText(0, self._tr("tab_gaussian"))
        self.main_tabs.setTabText(1, self._tr("tab_xtb"))

        # ===== Tab 1: Gaussian =====
        self._gaussian_input_gb.setTitle(self._tr("input_file"))
        self._gaussian_path_gb.setTitle(self._tr("prog_path"))
        self._gaussian_calc_gb.setTitle(self._tr("calc_setup"))
        self._gaussian_output_gb.setTitle(self._tr("calc_output"))
        self.file_edit.setPlaceholderText(self._tr("placeholder_gjf"))
        self.g16_edit.setPlaceholderText(self._tr("placeholder_g16"))
        self.xtb_edit.setPlaceholderText(self._tr("placeholder_xtb"))
        self.route_edit.setPlaceholderText(self._tr("placeholder_route"))
        self.route_edit.setToolTip(self._tr("tooltip_route"))
        self.extra_edit.setPlaceholderText(self._tr("placeholder_extra"))
        self.chrg_spin.setToolTip(self._tr("tooltip_chrg"))
        self.mult_spin.setToolTip(self._tr("tooltip_mult"))
        self.solv_combo.setItemText(0, self._tr("gas_phase"))
        self.run_btn.setText(self._tr("run"))
        self.abort_btn.setText(self._tr("abort"))
        self._gaussian_output_gb.setTitle(self._tr("calc_output"))
        self.viz_single_gb.setTitle(self._tr("mol_structure"))
        self.viz_qst_tabs.setTabText(0, self._tr("reactant"))
        self.viz_qst_tabs.setTabText(1, self._tr("product"))
        self.viz_rotate_hint.setText(self._tr("rotate_hint"))
        self.viz_reset_btn.setText(self._tr("reset_view"))
        self._browse_btn1.setText(self._tr("browse"))
        self._clear_btn.setText(self._tr("clear_log"))
        self._browse_g16_btn.setText(self._tr("setup"))
        self._browse_xtb_btn.setText(self._tr("setup"))
        self._label_g16.setText(self._tr("g16_path"))
        self._label_xtb.setText(self._tr("xtb_path"))
        self._label_route.setText(self._tr("route"))
        self._label_gfn.setText(self._tr("gfn_level"))
        self._label_threads.setText(self._tr("threads"))
        self._label_charge.setText(self._tr("charge"))
        self._label_mult.setText(self._tr("mult"))
        self._label_scf_acc.setText(self._tr("scf_acc"))
        self._label_etemp.setText(self._tr("etemp"))
        self._label_solv.setText(self._tr("solvation"))
        self._label_solvent.setText(self._tr("solvent"))
        self._label_extra_args.setText(self._tr("extra_args"))
        # ===== Tab 2: xTB =====
        self._xtb_input_gb.setTitle(self._tr("input_file"))
        self._xtb_calc_gb.setTitle(self._tr("calc_setup"))
        self._xtb_output_gb.setTitle(self._tr("xtb_output"))
        self.xtb_file_edit.setPlaceholderText(self._tr("placeholder_xyz"))
        self.xtb2_edit.setPlaceholderText(self._tr("placeholder_xtb2"))
        self.xtb_workdir_edit.setPlaceholderText(self._tr("placeholder_workdir"))
        self.xtb_run_btn.setText(self._tr("run"))
        self.xtb_abort_btn.setText(self._tr("abort"))
        self._xtb_preview_btn.setText(self._tr("preview"))
        self._xtb_clear_btn.setText(self._tr("clear_log"))
        self.xtb_solv_combo.setItemText(0, self._tr("gas_phase"))
        self._xtb_browse_btn.setText(self._tr("browse"))
        self._xtb_browse_xtb_btn.setText(self._tr("setup"))
        self._xtb_browse_workdir_btn.setText(self._tr("setup"))
        self._label_xtb_method.setText(self._tr("method"))
        self._label_xtb2_path.setText(self._tr("xtb2_path"))
        self._label_xtb_calc_type.setText(self._tr("calc_type"))
        self._label_xtb_workdir.setText(self._tr("workdir"))
        self._label_xtb_charge.setText(self._tr("charge"))
        self._label_xtb_unpaired.setText(self._tr("unpaired"))
        self._label_xtb_scf_acc.setText(self._tr("scf_acc"))
        self._label_xtb_etemp.setText(self._tr("etemp_short"))
        self._label_xtb_solv.setText(self._tr("solvation_short"))
        self._label_xtb_solvent.setText(self._tr("solvent_short"))
        self._label_xtb_parallel.setText(self._tr("parallel"))
        self._label_xtb_output_opts.setText(self._tr("output_opts"))
        # Update status buttons if idle
        if hasattr(self, '_status_btn') and not self._status_btn._running:
            self._status_btn.set_status(self._tr("ready"), "#1565C0")
        if hasattr(self, '_xtb_status_btn') and not self._xtb_status_btn._running:
            self._xtb_status_btn.set_status(self._tr("ready"), "#1565C0")
        # Update viz info labels if they exist
        if hasattr(self, 'viz_info_label') and self.viz_info_label.text():
            pass  # kept via _on_file_changed

        # ===== Tab 3: ORCA =====
        self.main_tabs.setTabText(2, self._tr("tab_orca"))
        if hasattr(self, '_orca_file_gb'):
            self._orca_file_gb.setTitle(self._tr("orca_file"))
            self.orca_file_edit.setPlaceholderText(self._tr("orca_ph_file"))
            self._orca_status_btn.set_status(self._tr("ready"), "#1565C0")

    # ── 打包/路径辅助 ──

    @staticmethod
    def _extract_script() -> Path | None:
        dest = _pkg_dir() / "gau_xtb.py"
        if dest.exists():
            return dest
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            src = Path(meipass) / "gau_xtb.py"
            if src.exists():
                dest.write_text(src.read_text(encoding="utf-8"))
                return dest
        return None

    @staticmethod
    def _write_client_bat(python_exe: str, gau_xtb_path: str) -> Path:
        bat_path = _app_dir() / "gau_xtb_client.bat"
        try:
            bat_path.write_text(
                f'@echo off\n"{python_exe}" "{gau_xtb_path}" %*\n',
                encoding="ascii",
            )
        except (PermissionError, OSError):
            import tempfile
            bat_path = Path(tempfile.gettempdir()) / "gau_xtb_client.bat"
            bat_path.write_text(
                f'@echo off\n"{python_exe}" "{gau_xtb_path}" %*\n',
                encoding="ascii",
            )
        return bat_path

    @staticmethod
    def _extract_route_from_gjf(content: str) -> str:
        """从 .gjf 中提取路由段关键字（去掉 external=... 部分）。"""
        lines = content.splitlines()
        start = None
        for i, line in enumerate(lines):
            if line.strip().startswith("#"):
                start = i
                break
        if start is None:
            return ""
        route_parts = []
        for i in range(start, len(lines)):
            s = lines[i].strip()
            if not s:
                break
            route_parts.append(s)
        joined = " ".join(route_parts)
        # 去掉 external= 部分
        joined = re.sub(r"\s*external\s*=\s*('[^']*'|\"[^\"]*\"|\S+)", "", joined, flags=re.IGNORECASE)
        # 去掉开头的 #P / #p / #
        joined = re.sub(r"^#[Pp]?\s*", "", joined).strip()
        return joined

    @staticmethod
    def _inject_external(content: str, external_cmd: str, route_override: str | None = None) -> str | None:
        lines = content.splitlines()
        # 找路由段
        start = None
        for i, line in enumerate(lines):
            if line.strip().startswith("#"):
                start = i
                break
        if start is None:
            return None
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].strip() == "":
                end = i
                break
        new_lines = list(lines)

        if route_override is not None:
            # 替换整个路由段：用用户指定的关键字 + external
            new_route = f"#P {route_override.strip()} external='{external_cmd}'"
            new_lines[start] = new_route
            for i in range(end - 1, start, -1):
                del new_lines[i]
        else:
            # 保持原路由段，只注入 External
            route_lines = lines[start:end]
            joined = " ".join(line.strip() for line in route_lines)
            has_ext = bool(re.search(r"\bexternal\s*=\s*(['\"`]|\S+)", joined, re.IGNORECASE))

            if has_ext:
                joined = re.sub(
                    r"\s*external\s*=\s*(['\"`]).*?\1",
                    f" external='{external_cmd}'",
                    joined, count=1, flags=re.IGNORECASE,
                )
                joined = re.sub(
                    r"\s*external\s*=\s*\S+",
                    f" external='{external_cmd}'",
                    joined, count=1, flags=re.IGNORECASE,
                )
                new_lines[start] = joined
                for i in range(end - 1, start, -1):
                    del new_lines[i]
            else:
                new_lines[end - 1] = new_lines[end - 1].rstrip() + f" external='{external_cmd}'"
        return "\n".join(new_lines)

    @staticmethod
    def _patch_charge_mult(content: str, chrg: int, mult: int) -> str:
        """替换 gjf 内容中的电荷/多重度行（支持 qst2 多组）。"""
        lines = content.splitlines()
        found_blank = 0
        patched = False
        for i, line in enumerate(lines):
            s = line.strip()
            if not s:
                found_blank += 1
                continue
            if found_blank >= 2:
                parts = s.split()
                if len(parts) == 2:
                    try:
                        int(float(parts[0]))
                        int(float(parts[1]))
                        lines[i] = f" {chrg}  {mult}"
                        patched = True
                    except (ValueError, IndexError):
                        pass
                if patched:
                    break
        return "\n".join(lines)

    # ── UI ──

    def _init_ui(self):
        self.setWindowTitle(self._tr("win_title"))
        self.setMinimumSize(1300, 750)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ── 水平分割: 左=设置面板 / 右=共享分子画布 ──
        self._hsplitter = QSplitter(Qt.Horizontal)
        self._hsplitter.setChildrenCollapsible(False)

        # 左侧：选项卡（仅设置面板，无画布）
        self.main_tabs = QTabWidget()
        self.main_tabs.tabBar().setElideMode(Qt.ElideNone)
        self.main_tabs.tabBar().setExpanding(False)
        self._hsplitter.addWidget(self.main_tabs)

        # 右侧：共享分子可视化画布
        self._build_shared_canvas()
        self._hsplitter.addWidget(self.viz_container)
        self._hsplitter.setSizes([680, 550])

        root.addWidget(self._hsplitter, stretch=1)

        # ═══ Tab 1: Gaussian + xTB External ═══
        self._build_gaussian_tab()

        # ═══ Tab 2: xTB 独立计算 ═══
        self._build_xtb_tab()

        # ═══ Tab 3: ORCA Submit ═══
        self._build_orca_tab()

    def _build_shared_canvas(self):
        """构建共享分子可视化画布（所有 Tab 共用）。"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.viz_single_gb = QGroupBox(self._tr("mol_structure"))
        svl = QVBoxLayout()
        self.viz_canvas = MolCanvas()
        svl.addWidget(self.viz_canvas, stretch=1)
        # 提示行 + 风格控制
        hint_row = QHBoxLayout()
        hint_row.setSpacing(6)
        self.viz_rotate_hint = QLabel(self._tr("rotate_hint"))
        self.viz_rotate_hint.setStyleSheet("color: #4A5568; font-size: 8pt; padding: 1px 3px;")
        hint_row.addWidget(self.viz_rotate_hint)
        self.viz_info_label = QLabel(self._tr("no_mol"))
        self.viz_info_label.setStyleSheet("color: #4A5568; font-size: 9pt; padding: 2px 4px;")
        hint_row.addWidget(self.viz_info_label)
        hint_row.addStretch()

        # 风格
        lbl_style = QLabel("风格:")
        lbl_style.setStyleSheet("color: #4A5568; font-size: 8pt; padding: 1px 2px;")
        hint_row.addWidget(lbl_style)
        self.cb_style = QComboBox()
        style_names = [STYLE_PRESETS[k]["name"] for k in STYLE_PRESETS]
        self.cb_style.addItems(style_names)
        default_style_name = STYLE_PRESETS.get("HoukMol", {}).get("name", "HoukMol")
        self.cb_style.setCurrentText(default_style_name)
        self.cb_style.setMaximumWidth(100)
        self.cb_style.setStyleSheet("font-size: 8pt;")
        self.cb_style.currentIndexChanged.connect(self._on_style_changed)
        hint_row.addWidget(self.cb_style)

        # 标签
        lbl_mode = QLabel("标签:")
        lbl_mode.setStyleSheet("color: #4A5568; font-size: 8pt; padding: 1px 2px;")
        hint_row.addWidget(lbl_mode)
        self.cb_label = QComboBox()
        self.cb_label.addItems(["元素", "编号", "无"])
        self.cb_label.setCurrentIndex(1)
        self.cb_label.setMaximumWidth(50)
        self.cb_label.setStyleSheet("font-size: 8pt;")
        self.cb_label.currentIndexChanged.connect(
            lambda idx: (setattr(self.viz_canvas, 'label_mode', idx),
                         setattr(self.viz_canvas_r, 'label_mode', idx),
                         setattr(self.viz_canvas_p, 'label_mode', idx),
                         self.viz_canvas.update(), self.viz_canvas_r.update(), self.viz_canvas_p.update())
        )
        hint_row.addWidget(self.cb_label)

        # 阴影
        self.chk_shadow = QCheckBox("阴影")
        self.chk_shadow.setChecked(True)
        self.chk_shadow.setStyleSheet("font-size: 8pt; padding: 0px 2px;")
        self.chk_shadow.toggled.connect(
            lambda v: (setattr(self.viz_canvas, 'show_shadows', v),
                       setattr(self.viz_canvas_r, 'show_shadows', v),
                       setattr(self.viz_canvas_p, 'show_shadows', v),
                       self.viz_canvas.update(), self.viz_canvas_r.update(), self.viz_canvas_p.update())
        )
        hint_row.addWidget(self.chk_shadow)

        # 十字
        self.chk_crosshair = QCheckBox("十字")
        self.chk_crosshair.setChecked(False)
        self.chk_crosshair.setStyleSheet("font-size: 8pt; padding: 0px 2px;")
        self.chk_crosshair.toggled.connect(
            lambda v: (setattr(self.viz_canvas, 'show_crosshair', v),
                       setattr(self.viz_canvas_r, 'show_crosshair', v),
                       setattr(self.viz_canvas_p, 'show_crosshair', v),
                       self.viz_canvas.update(), self.viz_canvas_r.update(), self.viz_canvas_p.update())
        )
        hint_row.addWidget(self.chk_crosshair)

        # 样式设置
        self.viz_style_btn = QPushButton(" 样式设置 ")
        self.viz_style_btn.setMaximumHeight(22)
        self.viz_style_btn.setStyleSheet("font-size: 7.5pt; padding: 1px 6px;")
        self.viz_style_btn.clicked.connect(self._open_style_settings)
        hint_row.addWidget(self.viz_style_btn)

        # 重置视角
        self.viz_reset_btn = QPushButton(self._tr("reset_view"))
        self.viz_reset_btn.setMaximumHeight(22)
        self.viz_reset_btn.setStyleSheet("font-size: 7.5pt; padding: 1px 6px;")
        self.viz_reset_btn.clicked.connect(lambda: self._reset_shared_views())
        hint_row.addWidget(self.viz_reset_btn)

        svl.addLayout(hint_row)
        self.viz_single_gb.setLayout(svl)
        layout.addWidget(self.viz_single_gb, stretch=1)

        self.viz_qst_tabs = QTabWidget()
        self.viz_canvas_r = MolCanvas()
        self.viz_canvas_p = MolCanvas()
        self.viz_qst_tabs.addTab(self.viz_canvas_r, self._tr("reactant"))
        self.viz_qst_tabs.addTab(self.viz_canvas_p, self._tr("product"))
        self.viz_qst_tabs.hide()
        layout.addWidget(self.viz_qst_tabs, stretch=1)

        self.viz_container = w

    def _build_gaussian_tab(self):
        """构建 Tab 1: Gaussian + xTB External 联用。"""
        tab = QWidget()
        tab_layout = QHBoxLayout(tab)
        tab_layout.setContentsMargins(4, 4, 4, 4)
        tab_layout.setSpacing(8)

        # ── 左面板 ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # 文件选择
        self._gaussian_input_gb = QGroupBox(self._tr("input_file"))
        fl = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText(self._tr("placeholder_gjf"))
        self.file_edit.editingFinished.connect(lambda: self._on_file_changed(self.file_edit.text()))
        fl.addWidget(self.file_edit)
        self._browse_btn1 = QPushButton(self._tr("browse"))
        self._browse_btn1.clicked.connect(self._browse_gjf)
        fl.addWidget(self._browse_btn1)
        self._lang_btn = QPushButton(self._tr("lang_btn"))
        self._lang_btn.setCursor(Qt.PointingHandCursor)
        self._lang_btn.setStyleSheet(
            "QPushButton {"
            "  background: #00897B; color: #FFFFFF; font-weight: bold;"
            "  font-size: 9pt; border: 1px solid #00695C; border-radius: 5px;"
            "}"
            "QPushButton:hover { background: #26A69A; border: 1px solid #00897B; color: #FFFFFF; }"
            "QPushButton:pressed { background: #00695C; }"
        )
        self._lang_btn.clicked.connect(self._switch_lang)
        fl.addWidget(self._lang_btn)
        self._gaussian_input_gb.setLayout(fl)
        left_layout.addWidget(self._gaussian_input_gb)

        # 设置区（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        set_w = QWidget()
        set_layout = QVBoxLayout(set_w)
        set_layout.setContentsMargins(0, 0, 0, 0)
        set_layout.setSpacing(6)

        # 高斯 / xTB 路径
        self._gaussian_path_gb = QGroupBox(self._tr("prog_path"))
        gl = QGridLayout()
        gl.setVerticalSpacing(2)
        gl.setHorizontalSpacing(2)
        self._label_g16 = QLabel(self._tr("g16_path"))
        gl.addWidget(self._label_g16, 0, 0)
        self.g16_edit = QLineEdit()
        self.g16_edit.setPlaceholderText(self._tr("placeholder_g16"))
        gl.addWidget(self.g16_edit, 0, 1)
        self._browse_g16_btn = QPushButton(self._tr("setup"))
        self._browse_g16_btn.setMaximumWidth(120)
        self._browse_g16_btn.clicked.connect(lambda: self._browse_exe(self.g16_edit, "g16.exe"))
        gl.addWidget(self._browse_g16_btn, 0, 2)
        self._label_xtb = QLabel(self._tr("xtb_path"))
        gl.addWidget(self._label_xtb, 1, 0)
        self.xtb_edit = QLineEdit()
        self.xtb_edit.setPlaceholderText(self._tr("placeholder_xtb"))
        gl.addWidget(self.xtb_edit, 1, 1)
        self._browse_xtb_btn = QPushButton(self._tr("setup"))
        self._browse_xtb_btn.setMaximumWidth(120)
        self._browse_xtb_btn.clicked.connect(lambda: self._browse_exe(self.xtb_edit, "xtb.exe"))
        gl.addWidget(self._browse_xtb_btn, 1, 2)
        self._gaussian_path_gb.setLayout(gl)
        self._label_g16.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._label_xtb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        gl.setColumnStretch(1, 1)
        set_layout.addWidget(self._gaussian_path_gb)

        # 计算方法
        self._gaussian_calc_gb = QGroupBox(self._tr("calc_setup"))
        cgl = QGridLayout()
        cgl.setVerticalSpacing(2)
        cgl.setHorizontalSpacing(2)
        self._label_route = QLabel(self._tr("route"))
        cgl.addWidget(self._label_route, 0, 0)
        self.route_edit = QLineEdit()
        self.route_edit.setPlaceholderText(self._tr("placeholder_route"))
        self.route_edit.setToolTip(self._tr("tooltip_route"))
        cgl.addWidget(self.route_edit, 0, 1, 1, 3)
        self._label_gfn = QLabel(self._tr("gfn_level"))
        cgl.addWidget(self._label_gfn, 1, 0)
        self.gfn_combo = QComboBox()
        self.gfn_combo.addItems(["GFN2-xTB", "GFN1-xTB", "GFN0-xTB", "GFN-FF"])
        cgl.addWidget(self.gfn_combo, 1, 1)
        self._label_threads = QLabel(self._tr("threads"))
        cgl.addWidget(self._label_threads, 1, 2)
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 256)
        self.thread_spin.setValue(min(os.cpu_count() or 4, 8))
        cgl.addWidget(self.thread_spin, 1, 3)
        self._label_charge = QLabel(self._tr("charge"))
        cgl.addWidget(self._label_charge, 2, 0)
        self.chrg_spin = QSpinBox()
        self.chrg_spin.setRange(-10, 10); self.chrg_spin.setValue(0)
        self.chrg_spin.setToolTip(self._tr("tooltip_chrg"))
        cgl.addWidget(self.chrg_spin, 2, 1)
        self._label_mult = QLabel(self._tr("mult"))
        cgl.addWidget(self._label_mult, 2, 2)
        self.mult_spin = QSpinBox()
        self.mult_spin.setRange(1, 10); self.mult_spin.setValue(1)
        self.mult_spin.setToolTip(self._tr("tooltip_mult"))
        cgl.addWidget(self.mult_spin, 2, 3)
        self._label_scf_acc = QLabel(self._tr("scf_acc"))
        cgl.addWidget(self._label_scf_acc, 3, 0)
        self.acc_spin = QDoubleSpinBox()
        self.acc_spin.setRange(0.01, 10.0); self.acc_spin.setValue(1.0)
        self.acc_spin.setSingleStep(0.1)
        cgl.addWidget(self.acc_spin, 3, 1)
        self._label_etemp = QLabel(self._tr("etemp"))
        cgl.addWidget(self._label_etemp, 3, 2)
        self.etemp_spin = QSpinBox()
        self.etemp_spin.setRange(1, 10000); self.etemp_spin.setValue(300)
        self.etemp_spin.setSingleStep(100)
        cgl.addWidget(self.etemp_spin, 3, 3)
        self._label_solv = QLabel(self._tr("solvation"))
        cgl.addWidget(self._label_solv, 4, 0)
        self.solv_combo = QComboBox()
        self.solv_combo.addItems([self._tr("gas_phase"), "ALPB", "COSMO"])
        self.solv_combo.currentIndexChanged.connect(self._on_gau_xtb_solv_changed)
        cgl.addWidget(self.solv_combo, 4, 1)
        self._label_solvent = QLabel(self._tr("solvent"))
        cgl.addWidget(self._label_solvent, 4, 2)
        self.solvent_combo = QComboBox()
        self.solvent_combo.addItems(ALPB_SOLVENTS)
        self.solvent_combo.setCurrentText("water")
        self.solvent_combo.setEnabled(False)
        cgl.addWidget(self.solvent_combo, 4, 3)
        self._label_extra_args = QLabel(self._tr("extra_args"))
        cgl.addWidget(self._label_extra_args, 5, 0)
        self.extra_edit = QLineEdit()
        self.extra_edit.setPlaceholderText(self._tr("placeholder_extra"))
        cgl.addWidget(self.extra_edit, 5, 1, 1, 3)
        self._gaussian_calc_gb.setLayout(cgl)
        # 标签右对齐，靠紧输入框
        for i in range(cgl.count()):
            w = cgl.itemAt(i).widget()
            if isinstance(w, QLabel):
                w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cgl.setColumnStretch(1, 1)
        cgl.setColumnStretch(3, 1)
        set_layout.addWidget(self._gaussian_calc_gb)
        set_layout.addStretch()
        scroll.setWidget(set_w)
        left_layout.addWidget(scroll, stretch=1)

        # 控制栏
        ctrl = QHBoxLayout()
        self._preview_btn = QPushButton(self._tr("preview"))
        self._preview_btn.setCursor(Qt.PointingHandCursor)
        self._preview_btn.setStyleSheet(
            "QPushButton {"
            "  background: #1565C0; color: white; font-weight: bold; font-size: 11pt;"
            "  padding: 8px 34px; border-radius: 20px; border: none;"
            "}"
            "QPushButton:hover { background: #1E88E5; }"
            "QPushButton:disabled { background: #bdbdbd; color: #e0e0e0; }"
        )
        self._preview_btn.clicked.connect(self._preview_gaussian_command)
        ctrl.addWidget(self._preview_btn)
        self.run_btn = QPushButton(self._tr("run"))
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.setStyleSheet(
            "QPushButton {"
            "  background: #43a047; color: white; font-weight: bold; font-size: 11pt;"
            "  padding: 8px 34px; border-radius: 20px; border: none;"
            "}"
            "QPushButton:hover { background: #388e3c; }"
            "QPushButton:pressed { background: #2e7d32; }"
            "QPushButton:disabled { background: #bdbdbd; color: #e0e0e0; }"
        )
        self.run_btn.clicked.connect(self._run)
        ctrl.addWidget(self.run_btn)
        self.abort_btn = QPushButton(self._tr("abort"))
        self.abort_btn.setCursor(Qt.PointingHandCursor)
        self.abort_btn.setStyleSheet(
            "QPushButton {"
            "  background: #e53935; color: white; font-weight: bold; font-size: 11pt;"
            "  padding: 8px 34px; border-radius: 20px; border: none;"
            "}"
            "QPushButton:hover { background: #d32f2f; }"
            "QPushButton:pressed { background: #c62828; }"
            "QPushButton:disabled { background: #bdbdbd; color: #e0e0e0; }"
        )
        self.abort_btn.setEnabled(False)
        self.abort_btn.clicked.connect(self._abort)
        ctrl.addWidget(self.abort_btn)
        self._status_btn = StatusButton(self._tr("ready"))
        ctrl.addWidget(self._status_btn)
        self._clear_btn = QPushButton(self._tr("clear_log"))
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.setStyleSheet(
            "QPushButton {"
            "  background: #546E7A; color: white; font-weight: bold; font-size: 11pt;"
            "  padding: 8px 34px; border-radius: 20px; border: none;"
            "}"
            "QPushButton:hover { background: #607D8B; }"
            "QPushButton:disabled { background: #bdbdbd; color: #e0e0e0; }"
        )
        self._clear_btn.clicked.connect(self._clear_log)
        ctrl.addWidget(self._clear_btn)
        ctrl.addStretch()
        left_layout.addLayout(ctrl)

        # 输出日志
        self._gaussian_output_gb = QGroupBox(self._tr("calc_output"))
        ol = QVBoxLayout()
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(
            "QTextEdit { background: #F1F5F9; color: #1E293B; border-radius: 4px;"
            " font-family: 'Cascadia Mono', 'Consolas', 'Courier New', monospace; font-size: 9pt; }"
        )
        ol.addWidget(self.log)
        self._gaussian_output_gb.setLayout(ol)
        left_layout.addWidget(self._gaussian_output_gb, stretch=1)


        # ── 添加到选项卡 ──
        tab_layout.addWidget(left)
        self.main_tabs.addTab(tab, self._tr("tab_gaussian"))

    def _build_xtb_tab(self):
        """构建 Tab 2: xTB 独立计算。"""
        tab = QWidget()
        tab_layout = QHBoxLayout(tab)
        tab_layout.setContentsMargins(4, 4, 4, 4)
        tab_layout.setSpacing(8)

        # ── 左面板: xTB 设置 ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # 输入文件
        self._xtb_input_gb = QGroupBox(self._tr("input_file"))
        fl = QHBoxLayout()
        self.xtb_file_edit = QLineEdit()
        self.xtb_file_edit.setPlaceholderText(self._tr("placeholder_xyz"))
        fl.addWidget(self.xtb_file_edit)
        self._xtb_browse_btn = QPushButton(self._tr("browse"))
        self._xtb_browse_btn.clicked.connect(self._browse_xtb_file)
        fl.addWidget(self._xtb_browse_btn)
        self._lang_btn2 = QPushButton(self._tr("lang_btn"))
        self._lang_btn2.setCursor(Qt.PointingHandCursor)
        self._lang_btn2.setStyleSheet(
            "QPushButton {"
            "  background: #00897B; color: #FFFFFF; font-weight: bold;"
            "  font-size: 9pt; border: 1px solid #00695C; border-radius: 5px;"
            "}"
            "QPushButton:hover { background: #26A69A; border: 1px solid #00897B; color: #FFFFFF; }"
            "QPushButton:pressed { background: #00695C; }"
        )
        self._lang_btn2.clicked.connect(self._switch_lang)
        fl.addWidget(self._lang_btn2)
        self._xtb_input_gb.setLayout(fl)
        left_layout.addWidget(self._xtb_input_gb)

        # 设置区（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        set_w = QWidget()
        set_layout = QVBoxLayout(set_w)
        set_layout.setContentsMargins(0, 0, 0, 0)
        set_layout.setSpacing(6)

        self._xtb_calc_gb = QGroupBox(self._tr("calc_setup"))
        gl = QGridLayout()
        gl.setVerticalSpacing(2)
        gl.setHorizontalSpacing(2)
        self._label_xtb_method = QLabel(self._tr("method"))
        gl.addWidget(self._label_xtb_method, 0, 0)
        self.xtb_method_combo = QComboBox()
        self.xtb_method_combo.addItems(["g-xTB", "GFN2-xTB", "GFN1-xTB", "GFN0-xTB", "GFN-FF"])
        gl.addWidget(self.xtb_method_combo, 0, 1)

        self._label_xtb2_path = QLabel(self._tr("xtb2_path"))
        gl.addWidget(self._label_xtb2_path, 0, 2)
        self.xtb2_edit = QLineEdit()
        self.xtb2_edit.setPlaceholderText(self._tr("placeholder_xtb2"))
        self.xtb2_edit.setMinimumWidth(300)
        gl.addWidget(self.xtb2_edit, 0, 3)
        self._xtb_browse_xtb_btn = QPushButton(self._tr("setup"))
        self._xtb_browse_xtb_btn.setMaximumWidth(120)
        self._xtb_browse_xtb_btn.clicked.connect(lambda: self._browse_exe(self.xtb2_edit, "xtb.exe"))
        gl.addWidget(self._xtb_browse_xtb_btn, 0, 4)

        self._label_xtb_calc_type = QLabel(self._tr("calc_type"))
        gl.addWidget(self._label_xtb_calc_type, 1, 0)
        self.xtb_calc_combo = QComboBox()
        self.xtb_calc_combo.addItems([
            "Single Point", "Geometry Optimization", "Opt + Hessian",
            "TS Optimization", "Frequency", "Numerical Hessian",
            "Mode Following", "Reaction Path", "Molecular Dynamics",
            "Metadynamics", "Relaxed Scan",
        ])
        self.xtb_calc_combo.currentIndexChanged.connect(self._on_xtb_calc_changed)
        gl.addWidget(self.xtb_calc_combo, 1, 1)

        self._label_xtb_workdir = QLabel(self._tr("workdir"))
        gl.addWidget(self._label_xtb_workdir, 1, 2)
        self.xtb_workdir_edit = QLineEdit()
        self.xtb_workdir_edit.setPlaceholderText(self._tr("placeholder_workdir"))
        gl.addWidget(self.xtb_workdir_edit, 1, 3)
        self._xtb_browse_workdir_btn = QPushButton(self._tr("setup"))
        self._xtb_browse_workdir_btn.clicked.connect(self._browse_xtb_workdir)
        gl.addWidget(self._xtb_browse_workdir_btn, 1, 4)

        self._label_xtb_charge = QLabel(self._tr("charge"))
        gl.addWidget(self._label_xtb_charge, 2, 0)
        self.xtb_chrg_spin = QSpinBox()
        self.xtb_chrg_spin.setRange(-10, 10); self.xtb_chrg_spin.setValue(0)
        gl.addWidget(self.xtb_chrg_spin, 2, 1)

        self._label_xtb_unpaired = QLabel(self._tr("unpaired"))
        gl.addWidget(self._label_xtb_unpaired, 2, 2)
        self.xtb_uhf_spin = QSpinBox()
        self.xtb_uhf_spin.setRange(0, 10); self.xtb_uhf_spin.setValue(0)
        gl.addWidget(self.xtb_uhf_spin, 2, 3)

        self._label_xtb_scf_acc = QLabel(self._tr("scf_acc"))
        gl.addWidget(self._label_xtb_scf_acc, 2, 4)
        self.xtb_acc_spin = QDoubleSpinBox()
        self.xtb_acc_spin.setRange(0.01, 10.0); self.xtb_acc_spin.setValue(1.0)
        self.xtb_acc_spin.setSingleStep(0.1)
        gl.addWidget(self.xtb_acc_spin, 2, 5)

        self._label_xtb_etemp = QLabel(self._tr("etemp_short"))
        gl.addWidget(self._label_xtb_etemp, 3, 0)
        self.xtb_etemp_spin = QSpinBox()
        self.xtb_etemp_spin.setRange(1, 10000); self.xtb_etemp_spin.setValue(300)
        self.xtb_etemp_spin.setSingleStep(100)
        gl.addWidget(self.xtb_etemp_spin, 3, 1)

        self._label_xtb_solv = QLabel(self._tr("solvation_short"))
        gl.addWidget(self._label_xtb_solv, 3, 2)
        self.xtb_solv_combo = QComboBox()
        self.xtb_solv_combo.addItems([self._tr("gas_phase"), "ALPB", "COSMO"])
        self.xtb_solv_combo.currentIndexChanged.connect(self._on_xtb_solv_changed)
        gl.addWidget(self.xtb_solv_combo, 3, 3)

        self._label_xtb_solvent = QLabel(self._tr("solvent_short"))
        gl.addWidget(self._label_xtb_solvent, 3, 4)
        self.xtb_solvent_combo = QComboBox()
        self.xtb_solvent_combo.addItems(ALPB_SOLVENTS)
        self.xtb_solvent_combo.setCurrentText("water")
        self.xtb_solvent_combo.setEnabled(False)
        gl.addWidget(self.xtb_solvent_combo, 3, 5)

        self._label_xtb_parallel = QLabel(self._tr("parallel"))
        gl.addWidget(self._label_xtb_parallel, 4, 0)
        self.xtb_parallel_spin = QSpinBox()
        self.xtb_parallel_spin.setRange(1, 64)
        self.xtb_parallel_spin.setValue(min(os.cpu_count() or 4, 8))
        gl.addWidget(self.xtb_parallel_spin, 4, 1)

        opts = QHBoxLayout()
        self.xtb_molden_cb = QCheckBox("Molden")
        opts.addWidget(self.xtb_molden_cb)
        self.xtb_json_cb = QCheckBox("JSON")
        opts.addWidget(self.xtb_json_cb)
        self.xtb_verbose_cb = QCheckBox("Verbose")
        opts.addWidget(self.xtb_verbose_cb)
        self._label_xtb_output_opts = QLabel(self._tr("output_opts"))
        gl.addWidget(self._label_xtb_output_opts, 4, 2)
        gl.addLayout(opts, 4, 3, 1, 3)

        self._xtb_calc_gb.setLayout(gl)
        # 标签右对齐，靠紧输入框
        for i in range(gl.count()):
            w = gl.itemAt(i).widget()
            if isinstance(w, QLabel):
                w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        gl.setColumnStretch(1, 1)
        gl.setColumnStretch(3, 1)
        gl.setColumnStretch(4, 1)
        set_layout.addWidget(self._xtb_calc_gb)

        # TS/Path 动态参数
        self.xtb_ts_widget = QWidget()
        ts_layout = QGridLayout(self.xtb_ts_widget)
        ts_layout.setContentsMargins(0, 0, 0, 0)
        ts_layout.addWidget(QLabel(self._tr("ts_product")), 0, 0)
        self.xtb_product_edit = QLineEdit()
        ts_layout.addWidget(self.xtb_product_edit, 0, 1)
        b = QPushButton(self._tr("browse"))
        b.clicked.connect(self._browse_xtb_product)
        ts_layout.addWidget(b, 0, 2)
        ts_layout.addWidget(QLabel(self._tr("ts_modef")), 1, 0)
        self.xtb_modef_spin = QSpinBox()
        self.xtb_modef_spin.setRange(1, 200); self.xtb_modef_spin.setValue(7)
        ts_layout.addWidget(self.xtb_modef_spin, 1, 1)
        set_layout.addWidget(self.xtb_ts_widget)
        self.xtb_ts_widget.setVisible(False)

        # Scan 动态参数 (xcontrol 编辑器)
        self.xtb_scan_widget = QWidget()
        scan_layout = QVBoxLayout(self.xtb_scan_widget)
        scan_layout.setContentsMargins(0, 4, 0, 0)
        scan_layout.setSpacing(2)
        scan_hint = QLabel(self._tr("scan_hint"))
        scan_hint.setStyleSheet("color: #4A5568; font-size: 8.5pt;")
        scan_layout.addWidget(scan_hint)
        # 约束力常数
        fk_row = QHBoxLayout()
        fk_row.setContentsMargins(0, 0, 0, 0)
        fk_lbl = QLabel(self._tr("scan_force_k"))
        fk_lbl.setStyleSheet("color: #4A5568; font-size: 8.5pt;")
        fk_row.addWidget(fk_lbl)
        self.xtb_force_k_spin = QDoubleSpinBox()
        self.xtb_force_k_spin.setRange(0.001, 10.0)
        self.xtb_force_k_spin.setValue(0.5)
        self.xtb_force_k_spin.setSingleStep(0.05)
        self.xtb_force_k_spin.setDecimals(3)
        self.xtb_force_k_spin.setToolTip(self._tr("scan_force_k"))
        fk_row.addWidget(self.xtb_force_k_spin)
        fk_row.addStretch()
        scan_layout.addLayout(fk_row)
        self.xtb_scan_edit = QTextEdit()
        self.xtb_scan_edit.setPlaceholderText(
            "$constrain\n force constant=0.50\n dihedral: 8,5,1,4,60.0\n"
            "$scan\n 1: 60.0, 420.0, 72\n$end")
        self.xtb_scan_edit.setMaximumHeight(120)
        self.xtb_scan_edit.setStyleSheet(
            "QTextEdit { background: #F1F5F9; color: #1E293B; border-radius: 4px;"
            " font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 9pt; }")
        scan_layout.addWidget(self.xtb_scan_edit)
        set_layout.addWidget(self.xtb_scan_widget)
        self.xtb_scan_widget.setVisible(False)

        set_layout.addStretch()
        scroll.setWidget(set_w)
        left_layout.addWidget(scroll, stretch=1)

        # 控制栏
        ctrl = QHBoxLayout()
        self.xtb_run_btn = QPushButton(self._tr("run"))
        self.xtb_run_btn.setCursor(Qt.PointingHandCursor)
        self.xtb_run_btn.setStyleSheet(
            "QPushButton {"
            "  background: #43a047; color: white; font-weight: bold; font-size: 11pt;"
            "  padding: 8px 34px; border-radius: 20px; border: none;"
            "}"
            "QPushButton:hover { background: #388e3c; }"
            "QPushButton:pressed { background: #2e7d32; }"
            "QPushButton:disabled { background: #bdbdbd; color: #e0e0e0; }"
        )
        self.xtb_run_btn.clicked.connect(self._run_xtb)
        ctrl.addWidget(self.xtb_run_btn)

        self.xtb_abort_btn = QPushButton(self._tr("abort"))
        self.xtb_abort_btn.setCursor(Qt.PointingHandCursor)
        self.xtb_abort_btn.setStyleSheet(
            "QPushButton {"
            "  background: #e53935; color: white; font-weight: bold; font-size: 11pt;"
            "  padding: 8px 34px; border-radius: 20px; border: none;"
            "}"
            "QPushButton:hover { background: #d32f2f; }"
            "QPushButton:pressed { background: #c62828; }"
            "QPushButton:disabled { background: #bdbdbd; color: #e0e0e0; }"
        )
        self.xtb_abort_btn.setEnabled(False)
        self.xtb_abort_btn.clicked.connect(self._abort)
        ctrl.addWidget(self.xtb_abort_btn)

        self._xtb_preview_btn = QPushButton(self._tr("preview"))
        self._xtb_preview_btn.setCursor(Qt.PointingHandCursor)
        self._xtb_preview_btn.setStyleSheet(
            "QPushButton {"
            "  background: #1565C0; color: white; font-weight: bold; font-size: 11pt;"
            "  padding: 8px 34px; border-radius: 20px; border: none;"
            "}"
            "QPushButton:hover { background: #1E88E5; }"
            "QPushButton:disabled { background: #bdbdbd; color: #e0e0e0; }"
        )
        self._xtb_preview_btn.clicked.connect(self._preview_xtb_command)
        ctrl.addWidget(self._xtb_preview_btn)
        self._xtb_status_btn = StatusButton(self._tr("ready"))
        ctrl.addWidget(self._xtb_status_btn)
        self._xtb_clear_btn = QPushButton(self._tr("clear_log"))
        self._xtb_clear_btn.setCursor(Qt.PointingHandCursor)
        self._xtb_clear_btn.setStyleSheet(
            "QPushButton {"
            "  background: #546E7A; color: white; font-weight: bold; font-size: 11pt;"
            "  padding: 8px 34px; border-radius: 20px; border: none;"
            "}"
            "QPushButton:hover { background: #607D8B; }"
            "QPushButton:disabled { background: #bdbdbd; color: #e0e0e0; }"
        )
        self._xtb_clear_btn.clicked.connect(self._clear_xtb_log)
        ctrl.addWidget(self._xtb_clear_btn)

        ctrl.addStretch()
        left_layout.addLayout(ctrl)

        # 输出日志
        self._xtb_output_gb = QGroupBox(self._tr("xtb_output"))
        ol = QVBoxLayout()
        self.xtb_log = QTextEdit()
        self.xtb_log.setReadOnly(True)
        self.xtb_log.setStyleSheet(
            "QTextEdit { background: #F1F5F9; color: #1E293B; border-radius: 4px;"
            " font-family: 'Cascadia Mono', 'Consolas', 'Courier New', monospace; font-size: 9pt; }"
        )
        ol.addWidget(self.xtb_log)
        self._xtb_output_gb.setLayout(ol)
        left_layout.addWidget(self._xtb_output_gb, stretch=1)

        tab_layout.addWidget(left)

        self.main_tabs.addTab(tab, self._tr("tab_xtb"))

        # Ctrl+O 快捷键打开文件（根据当前选项卡）
        self._shortcut_open = QShortcut(QKeySequence("Ctrl+O"), self)
        self._shortcut_open.activated.connect(self._shortcut_open_file)

    # ── ORCA Tab ──

    def _build_orca_tab(self):
        """构建 Tab 3: ORCA 作业提交。"""
        tab = QWidget()
        tab_layout = QHBoxLayout(tab)
        tab_layout.setContentsMargins(4, 4, 4, 4)
        tab_layout.setSpacing(8)

        # ── 左面板
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # 文件选择
        self._orca_file_gb = QGroupBox(self._tr("orca_file"))
        fl = QHBoxLayout()
        self.orca_file_edit = QLineEdit()
        self.orca_file_edit.setPlaceholderText(self._tr("orca_ph_file"))
        self.orca_file_edit.editingFinished.connect(
            lambda: self._on_orca_file_changed(self.orca_file_edit.text()))
        fl.addWidget(self.orca_file_edit)
        btn = QPushButton(self._tr("browse"))
        btn.clicked.connect(self._browse_orca_file)
        fl.addWidget(btn)
        self._orca_file_gb.setLayout(fl)
        left_layout.addWidget(self._orca_file_gb)

        # 设置区（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        set_w = QWidget()
        set_layout = QVBoxLayout(set_w)
        set_layout.setContentsMargins(0, 0, 0, 0)
        set_layout.setSpacing(6)

        # ORCA 路径
        path_gb = QGroupBox(self._tr("orca_path"))
        pl = QHBoxLayout()
        self.orca_path_edit = QLineEdit()
        self.orca_path_edit.setPlaceholderText("E:\\ORCA\\orca.exe")
        pl.addWidget(self.orca_path_edit)
        btn = QPushButton("...")
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self._browse_exe(self.orca_path_edit, "orca.exe"))
        pl.addWidget(btn)
        path_gb.setLayout(pl)
        set_layout.addWidget(path_gb)

        # OfakeG 路径
        ofakeg_gb = QGroupBox(self._tr("orca_ofakeg_path"))
        ol = QHBoxLayout()
        self.orca_ofakeg_edit = QLineEdit()
        self.orca_ofakeg_edit.setPlaceholderText("OfakeG.exe (留空 = 自动搜索)")
        ol.addWidget(self.orca_ofakeg_edit)
        btn_o = QPushButton("...")
        btn_o.setFixedWidth(30)
        btn_o.clicked.connect(lambda: self._browse_exe(self.orca_ofakeg_edit, "OfakeG.exe"))
        ol.addWidget(btn_o)
        ofakeg_gb.setLayout(ol)
        set_layout.addWidget(ofakeg_gb)

        # 计算设置
        calc_gb = QGroupBox(self._tr("orca_job"))
        cgl = QGridLayout()

        lbl = QLabel(self._tr("orca_method"))
        cgl.addWidget(lbl, 0, 0)
        self.orca_method_combo = QComboBox()
        self.orca_method_combo.addItems([
            "XTB2", "GFN1-xTB", "GFN0-xTB", "GFN-FF",
            "B3LYP", "PBE0", "wB97X-D3", "M06-2X",
            "B97-3c", "r2SCAN-3c", "HF-3c",
        ])
        self.orca_method_combo.currentTextChanged.connect(self._on_orca_method_changed)
        cgl.addWidget(self.orca_method_combo, 0, 1)

        lbl = QLabel(self._tr("orca_basis"))
        cgl.addWidget(lbl, 0, 2)
        self.orca_basis_combo = QComboBox()
        self.orca_basis_combo.addItems([
            "", "def2-SVP", "def2-TZVP", "def2-TZVPP", "def2-QZVP",
            "6-31G(d)", "6-311+G(d,p)", "cc-pVDZ", "cc-pVTZ",
            "ma-def2-SVP", "ma-def2-TZVP",
        ])
        cgl.addWidget(self.orca_basis_combo, 0, 3)

        lbl = QLabel(self._tr("orca_job_type"))
        cgl.addWidget(lbl, 0, 4)
        self.orca_job_combo = QComboBox()
        self.orca_job_combo.addItems([
            "SP", "OPT", "FREQ", "OPT FREQ",
            "NEB-TS", "IRC", "TIGHTSCF OPT", "Scan",
        ])
        self.orca_job_combo.currentTextChanged.connect(self._on_orca_job_changed)
        cgl.addWidget(self.orca_job_combo, 0, 5)

        lbl = QLabel(self._tr("threads"))
        cgl.addWidget(lbl, 1, 0)
        self.orca_nprocs_spin = QSpinBox()
        self.orca_nprocs_spin.setRange(1, 256)
        self.orca_nprocs_spin.setValue(4)
        cgl.addWidget(self.orca_nprocs_spin, 1, 1)

        lbl = QLabel(self._tr("orca_mem"))
        cgl.addWidget(lbl, 1, 2)
        self.orca_mem_spin = QSpinBox()
        self.orca_mem_spin.setRange(512, 65536)
        self.orca_mem_spin.setSingleStep(1024)
        self.orca_mem_spin.setValue(4096)
        cgl.addWidget(self.orca_mem_spin, 1, 3)

        lbl = QLabel(self._tr("charge"))
        cgl.addWidget(lbl, 1, 4)
        self.orca_chrg_spin = QSpinBox()
        self.orca_chrg_spin.setRange(-10, 10)
        self.orca_chrg_spin.setValue(0)
        cgl.addWidget(self.orca_chrg_spin, 1, 5)

        lbl = QLabel(self._tr("mult"))
        cgl.addWidget(lbl, 2, 0)
        self.orca_mult_spin = QSpinBox()
        self.orca_mult_spin.setRange(1, 10)
        self.orca_mult_spin.setValue(1)
        cgl.addWidget(self.orca_mult_spin, 2, 1)

        lbl = QLabel(self._tr("solvation"))
        cgl.addWidget(lbl, 2, 2)
        self.orca_solv_combo = QComboBox()
        self.orca_solv_combo.addItems([self._tr("gas_phase"), "SMD (CPCM)"])
        self.orca_solv_combo.currentIndexChanged.connect(self._on_orca_solv_changed)
        cgl.addWidget(self.orca_solv_combo, 2, 3)

        lbl = QLabel(self._tr("solvent"))
        cgl.addWidget(lbl, 2, 4)
        self.orca_solvent_combo = QComboBox()
        self.orca_solvent_combo.addItems([
            "water", "ethanol", "methanol", "acetonitrile", "acetone",
            "dmso", "dmf", "thf", "dichloromethane", "chloroform",
            "toluene", "benzene", "hexane", "diethylether", "ethylacetate",
            "1,4-dioxane", "carbontetrachloride", "nitromethane",
        ])
        self.orca_solvent_combo.setCurrentText("water")
        self.orca_solvent_combo.setEnabled(False)
        cgl.addWidget(self.orca_solvent_combo, 2, 5)

        # NEB extra
        self.orca_neb_widget = QWidget()
        neb_root = QVBoxLayout(self.orca_neb_widget)
        neb_root.setContentsMargins(0, 0, 0, 0)
        neb_root.setSpacing(2)
        neb_r1 = QHBoxLayout()
        neb_r1.setContentsMargins(0, 0, 0, 0)
        self.orca_neb_product_lbl = QLabel(self._tr("orca_product"))
        neb_r1.addWidget(self.orca_neb_product_lbl)
        self.orca_neb_product_edit = QLineEdit()
        self.orca_neb_product_edit.setPlaceholderText("product.gjf / product.xyz")
        neb_r1.addWidget(self.orca_neb_product_edit)
        btn_n = QPushButton("...")
        btn_n.setFixedWidth(30)
        btn_n.clicked.connect(self._browse_orca_neb_product)
        neb_r1.addWidget(btn_n)
        neb_root.addLayout(neb_r1)
        neb_r2 = QHBoxLayout()
        neb_r2.setContentsMargins(0, 0, 0, 0)
        self.orca_neb_nimages_lbl = QLabel(self._tr("orca_nimages"))
        neb_r2.addWidget(self.orca_neb_nimages_lbl)
        self.orca_neb_nimages_spin = QSpinBox()
        self.orca_neb_nimages_spin.setRange(2, 100)
        self.orca_neb_nimages_spin.setValue(16)
        neb_r2.addWidget(self.orca_neb_nimages_spin)
        neb_r2.addSpacing(12)
        self.orca_neb_free_end_cb = QCheckBox(self._tr("orca_free_end"))
        neb_r2.addWidget(self.orca_neb_free_end_cb)
        neb_r2.addStretch()
        neb_root.addLayout(neb_r2)
        cgl.addWidget(self.orca_neb_widget, 3, 0, 1, 6)
        self.orca_neb_widget.setVisible(False)

        # Scan widget
        self.orca_scan_widget = QWidget()
        scan_layout = QVBoxLayout(self.orca_scan_widget)
        scan_layout.setContentsMargins(0, 4, 0, 0)
        scan_layout.setSpacing(2)
        scan_hint = QLabel(self._tr("orca_scan_hint"))
        scan_hint.setStyleSheet("color: #4A5568; font-size: 8.5pt;")
        scan_layout.addWidget(scan_hint)
        self.orca_scan_edit = QTextEdit()
        self.orca_scan_edit.setPlaceholderText(
            "%geom\n  Scan\n    B 0 1 = 1.0, 3.0, 21\n    A 1 2 3 = 90.0, 180.0, 19\n  end\nend")
        self.orca_scan_edit.setMaximumHeight(120)
        scan_layout.addWidget(self.orca_scan_edit)
        cgl.addWidget(self.orca_scan_widget, 4, 0, 1, 6)
        self.orca_scan_widget.setVisible(False)

        lbl = QLabel(self._tr("orca_extra"))
        cgl.addWidget(lbl, 5, 0)
        self.orca_extra_edit = QLineEdit()
        self.orca_extra_edit.setPlaceholderText(self._tr("orca_ph_extra"))
        cgl.addWidget(self.orca_extra_edit, 5, 1, 1, 5)

        calc_gb.setLayout(cgl)
        set_layout.addWidget(calc_gb)

        set_layout.addStretch()
        scroll.setWidget(set_w)
        left_layout.addWidget(scroll, stretch=1)

        # 控制栏
        ctrl = QHBoxLayout()
        self._orca_preview_btn = QPushButton(self._tr("preview"))
        self._orca_preview_btn.setCursor(Qt.PointingHandCursor)
        self._orca_preview_btn.setStyleSheet(
            "QPushButton {"
            "  background: #1565C0; color: white; font-weight: bold; font-size: 11pt;"
            "  padding: 8px 34px; border-radius: 20px; border: none;"
            "}"
            "QPushButton:hover { background: #1E88E5; }"
            "QPushButton:disabled { background: #bdbdbd; color: #e0e0e0; }"
        )
        self._orca_preview_btn.clicked.connect(self._preview_orca_input)
        ctrl.addWidget(self._orca_preview_btn)
        self.orca_run_btn = QPushButton(self._tr("run"))
        self.orca_run_btn.setCursor(Qt.PointingHandCursor)
        self.orca_run_btn.setStyleSheet(
            "QPushButton {"
            "  background: #43a047; color: white; font-weight: bold; font-size: 11pt;"
            "  padding: 8px 34px; border-radius: 20px; border: none;"
            "}"
            "QPushButton:hover { background: #388e3c; }"
            "QPushButton:pressed { background: #2e7d32; }"
            "QPushButton:disabled { background: #bdbdbd; color: #e0e0e0; }"
        )
        self.orca_run_btn.clicked.connect(self._run_orca)
        ctrl.addWidget(self.orca_run_btn)
        self.orca_abort_btn = QPushButton(self._tr("abort"))
        self.orca_abort_btn.setCursor(Qt.PointingHandCursor)
        self.orca_abort_btn.setEnabled(False)
        self.orca_abort_btn.setStyleSheet(
            "QPushButton {"
            "  background: #e53935; color: white; font-weight: bold; font-size: 11pt;"
            "  padding: 8px 34px; border-radius: 20px; border: none;"
            "}"
            "QPushButton:hover { background: #d32f2f; }"
            "QPushButton:pressed { background: #c62828; }"
            "QPushButton:disabled { background: #bdbdbd; color: #e0e0e0; }"
        )
        self.orca_abort_btn.clicked.connect(self._abort_orca)
        ctrl.addWidget(self.orca_abort_btn)
        self._orca_status_btn = StatusButton(self._tr("ready"))
        ctrl.addWidget(self._orca_status_btn)
        self._orca_clear_btn = QPushButton(self._tr("clear_log"))
        self._orca_clear_btn.setCursor(Qt.PointingHandCursor)
        self._orca_clear_btn.setStyleSheet(
            "QPushButton {"
            "  background: #546E7A; color: white; font-weight: bold; font-size: 11pt;"
            "  padding: 8px 34px; border-radius: 20px; border: none;"
            "}"
            "QPushButton:hover { background: #607D8B; }"
            "QPushButton:disabled { background: #bdbdbd; color: #e0e0e0; }"
        )
        self._orca_clear_btn.clicked.connect(self._clear_orca_log)
        ctrl.addWidget(self._orca_clear_btn)
        ctrl.addStretch()
        left_layout.addLayout(ctrl)

        # 输出日志
        out_gb = QGroupBox(self._tr("orca_output"))
        ol = QVBoxLayout()
        self.orca_log = QTextEdit()
        self.orca_log.setReadOnly(True)
        self.orca_log.setStyleSheet(
            "QTextEdit { background: #F1F5F9; color: #1E293B; border-radius: 4px;"
            " font-family: 'Cascadia Mono', 'Consolas', 'Courier New', monospace; font-size: 9pt; }"
        )
        ol.addWidget(self.orca_log)
        out_gb.setLayout(ol)
        left_layout.addWidget(out_gb, stretch=1)

        tab_layout.addWidget(left)

        self.main_tabs.addTab(tab, self._tr("tab_orca"))

    # ── ORCA Event Handlers ──

    def _browse_orca_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self._tr("orca_fd_input"), "",
            self._tr("orca_filter_all"))
        if path:
            self.orca_file_edit.setText(path)
            self._on_orca_file_changed(path)

    def _browse_orca_neb_product(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self._tr("orca_fd_product"), "",
            self._tr("orca_filter_xyz"))
        if path:
            self.orca_neb_product_edit.setText(path)

    def _on_orca_method_changed(self, text):
        is_xtb = any(x in text for x in ("XTB", "GFN", "HF-3c", "B97-3c", "r2SCAN-3c"))
        self.orca_basis_combo.setEnabled(not is_xtb)
        if is_xtb:
            self.orca_basis_combo.setCurrentText("")

    def _on_orca_job_changed(self, text):
        self.orca_neb_widget.setVisible("NEB" in text)
        self.orca_scan_widget.setVisible("Scan" in text)
        if "Scan" in text:
            try:
                self._auto_fill_orca_scan()
            except Exception:
                pass

    def _on_orca_solv_changed(self, idx):
        self.orca_solvent_combo.setEnabled(idx > 0)

    def _on_orca_file_changed(self, text):
        """ORCA Tab 文件改变 → 三 Tab 同步。"""
        if getattr(self, '_loading_file', False):
            return
        self._loading_file = True
        try:
            p = text.strip()
            if not p or not Path(p).is_file():
                self._orca_qst2_product_atoms = []
                return

            # 同步路径到 Tab 1 (Gaussian) 和 Tab 2 (xTB)
            if self.file_edit.text().strip() != p:
                self.file_edit.blockSignals(True)
                self.file_edit.setText(p)
                self.file_edit.blockSignals(False)
            if self.xtb_file_edit.text().strip() != p:
                self.xtb_file_edit.blockSignals(True)
                self.xtb_file_edit.setText(p)
                self.xtb_file_edit.blockSignals(False)

            # 委托给统一加载方法
            try:
                self._load_molecule_both(p, caller="orca")
            except Exception:
                import traceback
                traceback.print_exc()

            # ORCA 特有：Scan 自动转换
            ext = Path(p).suffix.lower()
            if ext in ('.gjf', '.com') and "Scan" in self.orca_job_combo.currentText():
                try:
                    self._auto_fill_orca_scan()
                except Exception:
                    pass
        finally:
            self._loading_file = False

    def _auto_fill_orca_scan(self):
        """若 ORCA Tab 载入的 .gjf 含 modredundant/addred，自动转为 ORCA %geom Scan 填入编辑器。"""
        filepath = self.orca_file_edit.text().strip()
        if not filepath or not filepath.lower().endswith('.gjf'):
            return
        try:
            content = Path(filepath).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return
        route_lower = " ".join(
            line.strip() for line in content.splitlines()
            if line.strip().startswith("#")
        ).lower()
        if any(kw in route_lower for kw in ("modredundant", "addred")):
            scan_block = self._gaussian_to_orca_scan(content)
            if scan_block:
                self.orca_scan_edit.setPlainText(scan_block)

    @staticmethod
    def _gaussian_to_orca_scan(content: str) -> str | None:
        """将 Gaussian 扫描约束转换为 ORCA %geom Scan 块。返回 None 表示无扫描约束。"""
        atoms = GauXtbViewer._parse_gjf_atoms(content)
        if not atoms:
            return None
        constraints = GauXtbViewer._parse_gaussian_scan_constraints(content, len(atoms))
        if not constraints:
            return None
        lines = ["%geom", "  Scan"]
        for c in constraints:
            typ = c["type"]
            idx_list = c["indices"]
            if len(idx_list) < (2 if typ == "B" else 3 if typ == "A" else 4):
                continue
            a0 = atoms[idx_list[0] - 1]
            a1 = atoms[idx_list[1] - 1]
            if typ == "B":
                init_val = GauXtbViewer._calc_distance(a0, a1)
            elif typ == "A":
                a2 = atoms[idx_list[2] - 1]
                init_val = GauXtbViewer._calc_angle(a0, a1, a2)
            elif typ == "D":
                a2 = atoms[idx_list[2] - 1]
                a3 = atoms[idx_list[3] - 1]
                init_val = GauXtbViewer._calc_dihedral(a0, a1, a2, a3)
            else:
                continue
            idx_str = " ".join(str(i) for i in idx_list)  # ORCA %geom 用 1-based 空格分隔（同高斯）
            if c.get("scan"):
                nsteps = c["scan"]["nsteps"]
                stepsize = c["scan"]["stepsize"]
                end_val = init_val + nsteps * stepsize
                lines.append(f"    {typ} {idx_str} = {init_val:.4f}, {end_val:.4f}, {nsteps + 1}")
            else:
                # constraint without scan step — just freeze
                lines.append(f"    {typ} {idx_str} = {init_val:.4f}")
        if len(lines) == 2:
            return None  # no valid constraints
        lines.append("  end")
        lines.append("end")
        return "\n".join(lines)

    def _reset_shared_views(self):
        """重置共享画布视图。"""
        for c in [self.viz_canvas, self.viz_canvas_r, self.viz_canvas_p]:
            if c.atoms:
                c.auto_fit()

    def _on_style_changed(self, idx):
        """风格预设切换，同步到所有共享画布。"""
        keys = list(STYLE_PRESETS.keys())
        if 0 <= idx < len(keys):
            key = keys[idx]
            preset = STYLE_PRESETS[key]
            for c in [self.viz_canvas, self.viz_canvas_r, self.viz_canvas_p]:
                c.set_style(key)
            # 同步复选框状态
            self.chk_shadow.blockSignals(True)
            self.chk_shadow.setChecked(preset["shadows"])
            self.chk_shadow.blockSignals(False)
            self.chk_crosshair.blockSignals(True)
            self.chk_crosshair.setChecked(preset["crosshair"])
            self.chk_crosshair.blockSignals(False)
            self.cb_label.blockSignals(True)
            self.cb_label.setCurrentIndex(preset["label_mode"])
            self.cb_label.blockSignals(False)

    def _open_style_settings(self):
        """弹出样式调整对话框（原子大小 / 键粗细 / 环角度）。"""
        dlg = QDialog(self)
        dlg.setWindowTitle("样式设置")
        dlg.setMinimumWidth(440)
        layout = QGridLayout(dlg)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(10)

        canvas = self.viz_canvas
        sl = {}

        def _make_slider(label, key, vmin, vmax, init_v, fmt_str, row, col):
            lbl = QLabel(label)
            layout.addWidget(lbl, row, col * 3)
            sld = QSlider(Qt.Horizontal)
            sld.setRange(vmin, vmax)
            sld.setValue(int(init_v))
            sld.setTracking(True)
            sl[key] = sld
            layout.addWidget(sld, row, col * 3 + 1)
            val = QLabel(fmt_str.format(init_v))
            val.setFixedWidth(42)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            sl[key + "_val"] = val
            layout.addWidget(val, row, col * 3 + 2)

        _make_slider("原子大小", "atom_scale", 10, 60,
                     canvas.atom_scale * 100, "{:.2f}", 0, 0)
        _make_slider("键粗细", "bond_width", 10, 100,
                     canvas.bond_width * 10, "{:.1f}", 0, 1)
        _make_slider("环A方位", "ring_a_angle", 0, 360,
                     canvas.ring_a_angle, "{}°", 1, 0)
        _make_slider("环A倾斜", "ring_a_tilt", 0, 180,
                     canvas.ring_a_tilt, "{}°", 1, 1)
        _make_slider("环B方位", "ring_b_angle", 0, 360,
                     canvas.ring_b_angle, "{}°", 2, 0)
        _make_slider("环B倾斜", "ring_b_tilt", 0, 180,
                     canvas.ring_b_tilt, "{}°", 2, 1)

        def _on_slider():
            for c in [self.viz_canvas, self.viz_canvas_r, self.viz_canvas_p]:
                c.atom_scale = sl["atom_scale"].value() / 100.0
                c.bond_width = sl["bond_width"].value() / 10.0
                c.ring_a_angle = sl["ring_a_angle"].value()
                c.ring_a_tilt = sl["ring_a_tilt"].value()
                c.ring_b_angle = sl["ring_b_angle"].value()
                c.ring_b_tilt = sl["ring_b_tilt"].value()
                c.update()
            sl["atom_scale_val"].setText("{:.2f}".format(canvas.atom_scale))
            sl["bond_width_val"].setText("{:.1f}".format(canvas.bond_width))
            sl["ring_a_angle_val"].setText("{}°".format(canvas.ring_a_angle))
            sl["ring_a_tilt_val"].setText("{}°".format(canvas.ring_a_tilt))
            sl["ring_b_angle_val"].setText("{}°".format(canvas.ring_b_angle))
            sl["ring_b_tilt_val"].setText("{}°".format(canvas.ring_b_tilt))

        for k in ["atom_scale", "bond_width",
                  "ring_a_angle", "ring_a_tilt", "ring_b_angle", "ring_b_tilt"]:
            sl[k].valueChanged.connect(_on_slider)

        btn_row = 3
        layout.addWidget(QWidget(), btn_row, 0, 1, 5)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close, btn_row, 5, 1, 1)

        dlg.exec_()

    def _orca_log(self, text):
        self.orca_log.append(text)
        self.orca_log.moveCursor(QTextCursor.End)
        self._orca_log_line_count += 1
        if self._orca_log_line_count % 50 == 0:
            self._trim_log(self.orca_log)
            self._orca_log_line_count = 0

    def _clear_orca_log(self):
        self._orca_log_line_count = 0
        self.orca_log.clear()

    def _build_orca_input(self, product_xyz_name=None):
        method = self.orca_method_combo.currentText()
        basis = self.orca_basis_combo.currentText()
        if any(x in method for x in ("XTB", "GFN", "HF-3c", "B97-3c", "r2SCAN-3c")):
            basis = ""
        job_type = self.orca_job_combo.currentText()
        charge = self.orca_chrg_spin.value()
        mult = self.orca_mult_spin.value()
        nprocs = self.orca_nprocs_spin.value()
        memory = self.orca_mem_spin.value()
        solvent = self.orca_solvent_combo.currentText() if self.orca_solv_combo.currentIndex() > 0 else ""
        extra = self.orca_extra_edit.text().strip()
        if product_xyz_name:
            product_file = product_xyz_name
        else:
            product_file = self.orca_neb_product_edit.text().strip() if "NEB" in job_type else None
        nimages = self.orca_neb_nimages_spin.value()
        neb_free_end = self.orca_neb_free_end_cb.isChecked() if "NEB" in job_type else False
        scan_block = self.orca_scan_edit.toPlainText().strip() if "Scan" in job_type else ""
        return build_orca_input(
            self._orca_atoms, charge, mult, method, basis, job_type,
            solvent, solvent, nprocs, memory,
            extra, product_file, nimages,
            neb_free_end=neb_free_end, scan_block=scan_block)

    def _preview_orca_input(self):
        if not self._orca_atoms:
            QMessageBox.warning(self, self._tr("orca_msg_warn"), self._tr("orca_msg_no_mol"))
            return
        inp, _ = self._build_orca_input()
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(self._tr("orca_dlg_preview"))
        dlg.resize(700, 600)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(8, 8, 8, 8)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setStyleSheet(
            "QTextEdit { font-family: 'Consolas', monospace; font-size: 10pt; "
            "background: #FAFBFC; color: #2C3E50; }")
        te.setPlainText(inp)
        layout.addWidget(te, stretch=1)
        btn = QPushButton(self._tr("close"))
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.exec_()

    def _run_orca(self):
        if not self._orca_atoms:
            QMessageBox.warning(self, self._tr("orca_msg_err"), self._tr("orca_msg_no_mol"))
            return
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, self._tr("hint"), self._tr("already_running"))
            return

        orca_exe = self.orca_path_edit.text().strip()
        if not Path(orca_exe).exists():
            QMessageBox.warning(self, self._tr("orca_msg_err"), self._tr("orca_msg_no_orca") + orca_exe)
            return

        gjf_path = self.orca_file_edit.text().strip()
        if gjf_path and Path(gjf_path).exists():
            work_dir = Path(gjf_path).parent
            base = Path(gjf_path).stem
        else:
            work_dir = _app_dir()
            base = "orca_job"

        # NEB-TS: get product coordinates
        product_xyz_name = None
        job_type = self.orca_job_combo.currentText()
        if "NEB" in job_type:
            prod_atoms = None
            product_path = self.orca_neb_product_edit.text().strip()
            if product_path and Path(product_path).is_file():
                try:
                    p_sets, _ = load_molecule(product_path)
                    prod_atoms = p_sets[0] if p_sets else None
                except Exception:
                    prod_atoms = None
            if not prod_atoms and getattr(self, '_orca_qst2_product_atoms', None):
                prod_atoms = self._orca_qst2_product_atoms
                self._orca_log("[NEB] Using product coords from QST2 input")
            if prod_atoms:
                pxyz_path = work_dir / "_product_orca.xyz"
                pxyz_lines = [f"{len(prod_atoms)}", "Product structure"]
                for a in prod_atoms:
                    pxyz_lines.append(f"{a['sym']:<2s}  {a['x']:15.8f}  {a['y']:15.8f}  {a['z']:15.8f}")
                pxyz_path.write_text("\n".join(pxyz_lines) + "\n", encoding="utf-8")
                product_xyz_name = pxyz_path.name
            else:
                QMessageBox.warning(self, self._tr("orca_msg_err"), self._tr("orca_msg_neb"))
                return

        inp_content, xyz_content = self._build_orca_input(product_xyz_name=product_xyz_name)
        xyz_path = work_dir / f"_{base}_orca.xyz"
        xyz_path.write_text(xyz_content + "\n", encoding="utf-8")
        inp_content = f"{inp_content}\n* xyzfile {self.orca_chrg_spin.value()} {self.orca_mult_spin.value()} {xyz_path.name}\n"
        inp_path = work_dir / f"_{base}_orca.inp"
        inp_path.write_text(inp_content, encoding="utf-8")

        self._clear_orca_log()
        self._orca_log("=" * 60)
        self._orca_log(self._tr("orca_log_job"))
        self._orca_log(f"{self._tr('orca_log_time')} {datetime.now():%Y-%m-%d %H:%M:%S}")
        self._orca_log(f"{self._tr('orca_log_orca')}  {orca_exe}")
        self._orca_log(f"{self._tr('orca_log_input')} {inp_path}")
        self._orca_log(f"{self._tr('orca_log_work')}  {work_dir}")
        self._orca_log("=" * 60)
        self._orca_log("")
        self._orca_log(self._tr("orca_log_preview"))
        for line in inp_content.strip().splitlines():
            self._orca_log(f"  {line}")
        self._orca_log(self._tr("orca_log_end_preview"))
        self._orca_log("")

        self._orca_out_path = str(inp_path).replace('.inp', '.out')
        self._worker = OrcaWorker(orca_exe, inp_path, work_dir)
        self._worker.output_line.connect(self._orca_log)
        self._worker.finished.connect(self._on_orca_finished)
        self._worker.start()

        self.orca_run_btn.setEnabled(False)
        self.orca_abort_btn.setEnabled(True)
        self._orca_status_btn.start(self._tr("running"))

    def _abort_orca(self):
        if self._worker:
            self._worker.abort()
            self._orca_status_btn.set_status(self._tr("aborted"), "#e53935")
            self.orca_run_btn.setEnabled(True)
            self.orca_abort_btn.setEnabled(False)

    def _on_orca_finished(self, code):
        self.orca_run_btn.setEnabled(True)
        self.orca_abort_btn.setEnabled(False)
        self._orca_log("")
        if code == 0:
            self._orca_status_btn.set_status(self._tr("done"), "#43a047")
            self._orca_log("=" * 60)
            self._orca_log(self._tr("orca_log_ok"))
            if self._orca_out_path and Path(self._orca_out_path).exists():
                self._run_orca_ofakeg(self._orca_out_path)
            QTimer.singleShot(100, self._show_orca_neb_result)
            QTimer.singleShot(100, self._show_orca_final_structure)
            QTimer.singleShot(100, self._show_orca_scan_viewer)
        else:
            self._orca_status_btn.set_status(self._tr("exit_code", code=code), "#e53935")
            self._orca_log(f"{self._tr('orca_log_err')} {code}")
        self._save_config()

    def _get_ofakeg_path(self) -> Path | None:
        """获取 OfakeG.exe 路径：优先用户配置，否则自动搜索包目录。"""
        user = self.orca_ofakeg_edit.text().strip()
        if user:
            return Path(user)
        auto = _pkg_dir() / "OfakeG_1.3.3" / "OfakeG.exe"
        if auto.exists():
            return auto
        return None

    def _run_orca_ofakeg(self, out_path):
        ofakeg_exe = self._get_ofakeg_path()
        if ofakeg_exe is None:
            return
        job_type = self.orca_job_combo.currentText()
        if job_type in ("SP", "Scan") or "NEB" in job_type or "IRC" in job_type:
            return
        try:
            proc = subprocess.run(
                [str(ofakeg_exe), str(out_path)],
                capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if proc.returncode == 0:
                fake = str(out_path).replace('.out', '_fake.out')
                if Path(fake).exists():
                    self._orca_log("")
                    self._orca_log(f"{self._tr('orca_log_ofakeg_out')} {fake}")
                    self._orca_status_btn.set_status(self._tr("done"), "#43a047")
        except Exception:
            pass

    def _convert_orca_ofakeg_manual(self):
        ofakeg_exe = self._get_ofakeg_path()
        if ofakeg_exe is None:
            QMessageBox.warning(self, self._tr("orca_msg_ofakeg"),
                f"请先设置 OfakeG.exe 路径，或将 OfakeG_1.3.3 放入程序目录。\nDownload from http://sobereva.com/soft/OfakeG")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self._tr("orca_fd_out"), "", self._tr("orca_filter_out"))
        if not path:
            return
        try:
            proc = subprocess.run(
                [str(ofakeg_exe), str(path)],
                capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._orca_log(f"[OfakeG] {proc.stdout.strip()}")
            if proc.returncode == 0:
                fake = str(path).replace('.out', '_fake.out')
                if Path(fake).exists():
                    self._orca_log(f"[OK] Generated: {fake}")
                    os.startfile(str(Path(fake).parent))
            else:
                self._orca_log(f"[ERR] OfakeG failed: {proc.stderr}")
        except Exception as e:
            self._orca_log(f"[ERR] OfakeG: {e}")

    def _show_orca_neb_result(self):
        if not self._orca_out_path:
            return
        job_type = self.orca_job_combo.currentText()
        if "NEB" not in job_type:
            return
        out_path = Path(self._orca_out_path)
        work_dir = out_path.parent
        for suffix in ["_NEB-TS_converged.xyz", "_NEB-CI_converged.xyz"]:
            candidate = work_dir / (out_path.stem + suffix)
            if candidate.is_file():
                ts_atoms = parse_xyz_coords(str(candidate))
                if ts_atoms:
                    bonds = _auto_bonds(ts_atoms)
                    self._show_orca_structure_dialog(ts_atoms, bonds, candidate)
                    return
        for f in work_dir.glob("*NEB-TS_converged.xyz"):
            ts_atoms = parse_xyz_coords(str(f))
            if ts_atoms:
                bonds = _auto_bonds(ts_atoms)
                self._show_orca_structure_dialog(ts_atoms, bonds, f)
                return

    def _show_orca_structure_dialog(self, atoms, bonds, source_path):
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(self._tr("orca_neb_title"))
        dlg.resize(600, 550)
        dlg.setMinimumSize(400, 350)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(8, 8, 8, 8)
        canvas = MolCanvas()
        canvas.set_data(atoms, bonds)
        layout.addWidget(QLabel(self._tr("orca_neb_from_file",
            name=source_path.name, n=len(atoms), b=len(bonds))))
        layout.addWidget(canvas, stretch=1)
        hint = QHBoxLayout()
        hint.addWidget(QLabel(self._tr("orca_rotate_hint")))
        hint.addStretch()
        btn_gjf = QPushButton(self._tr("save_gjf"))
        btn_gjf.clicked.connect(lambda: self._export_gjf(atoms, dlg,
            chrg=self.orca_chrg_spin.value(), mult=self.orca_mult_spin.value()))
        hint.addWidget(btn_gjf)
        btn_folder = QPushButton(self._tr("open_folder"))
        btn_folder.clicked.connect(lambda: os.startfile(str(source_path.parent)))
        hint.addWidget(btn_folder)
        btn_close = QPushButton(self._tr("close"))
        btn_close.clicked.connect(dlg.accept)
        hint.addWidget(btn_close)
        layout.addLayout(hint)
        dlg.exec_()

    def _show_orca_final_structure(self):
        """ORCA 优化/FREQ 完成后，从 .xyz 文件解析最终结构弹窗可视化。"""
        job_type = self.orca_job_combo.currentText()
        if "NEB" in job_type or "Scan" in job_type:
            return  # NEB 走 _show_orca_neb_result；Scan 输出到轨迹文件
        if not self._orca_out_path:
            return
        out_path = Path(self._orca_out_path)
        # ORCA 生成的 .xyz 与 .inp 同 stem
        xyz_path = out_path.with_suffix(".xyz")
        if not xyz_path.is_file():
            return
        atoms = parse_xyz_coords(str(xyz_path))
        if not atoms:
            return
        bonds = _auto_bonds(atoms)
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(self._tr("opt_structure"))
        dlg.resize(600, 550)
        dlg.setMinimumSize(400, 350)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(8, 8, 8, 8)
        canvas = MolCanvas()
        canvas.set_data(atoms, bonds)
        layout.addWidget(QLabel(self._tr("from_file",
            name=xyz_path.name, n=len(atoms), b=len(bonds))))
        layout.addWidget(canvas, stretch=1)
        hint = QHBoxLayout()
        hint.addWidget(QLabel(self._tr("rotate_hint")))
        hint.addStretch()
        btn_gjf = QPushButton(self._tr("save_gjf"))
        btn_gjf.clicked.connect(lambda: self._export_gjf(atoms, dlg,
            chrg=self.orca_chrg_spin.value(), mult=self.orca_mult_spin.value()))
        hint.addWidget(btn_gjf)
        btn_folder = QPushButton(self._tr("open_folder"))
        btn_folder.clicked.connect(lambda: os.startfile(str(xyz_path.parent)))
        hint.addWidget(btn_folder)
        btn_close = QPushButton(self._tr("close"))
        btn_close.clicked.connect(dlg.accept)
        hint.addWidget(btn_close)
        layout.addLayout(hint)
        dlg.exec_()

    def _show_orca_scan_viewer(self):
        """解析 ORCA 扫描 .allxyz，弹出能量折线图 + 结构对话框。"""
        if not self._orca_out_path:
            return
        out_path = Path(self._orca_out_path)
        allxyz = out_path.with_suffix(".allxyz")
        if not allxyz.is_file():
            self._orca_log("[WARN] .allxyz not found")
            return
        scan_data = parse_orca_allxyz(str(allxyz))
        if not scan_data:
            self._orca_log("[WARN] .allxyz parse failed")
            return

        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(self._tr("scan_viewer_title", steps=len(scan_data)))
        dlg.resize(720, 680)
        dlg.setMinimumSize(600, 500)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(8, 8, 8, 8)

        # 折线图
        chart = ScanChart()
        chart.set_data(scan_data)
        layout.addWidget(chart, stretch=2)

        # 分子画布
        canvas = MolCanvas()
        atoms_0 = scan_data[0]['atoms']
        bonds_0 = _auto_bonds(atoms_0)
        canvas.set_data(atoms_0, bonds_0)
        info_label = QLabel(self._tr("scan_step_info", step=1, e=scan_data[0]['energy'],
                                     e_rel=scan_data[0]['energy_relative']))
        layout.addWidget(info_label)
        layout.addWidget(canvas, stretch=3)

        def on_step_clicked(idx: int):
            if 0 <= idx < len(scan_data):
                d = scan_data[idx]
                bonds = _auto_bonds(d['atoms'])
                canvas.set_data(d['atoms'], bonds)
                info_label.setText(self._tr("scan_step_info", step=d['step'],
                                            e=d['energy'], e_rel=d['energy_relative']))
        chart.point_clicked.connect(on_step_clicked)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_gjf = QPushButton(self._tr("save_gjf"))
        btn_gjf.clicked.connect(lambda: self._export_gjf(
            scan_data[chart.selected_step]['atoms'], dlg,
            chrg=self.orca_chrg_spin.value(),
            mult=self.orca_mult_spin.value()))
        btn_row.addWidget(btn_gjf)
        btn_folder = QPushButton(self._tr("open_folder"))
        btn_folder.clicked.connect(lambda: os.startfile(str(out_path.parent)))
        btn_row.addWidget(btn_folder)
        btn_close = QPushButton(self._tr("close"))
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        dlg.exec_()

    # ── 配置 ──

    def _load_config(self):
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if k in self._config:
                        self._config[k] = v
            except Exception:
                pass

    def _save_config(self):
        gfn_idx = self.gfn_combo.currentIndex()
        gfn_map = {0: 2, 1: 1, 2: 0, 3: -1}
        cfg = {
            "gaussian_path": self.g16_edit.text(),
            "xtb_path": self.xtb_edit.text(),
            "gfn_level": gfn_map.get(gfn_idx, 2),
            "threads": self.thread_spin.value(),
            "extra_args": self.extra_edit.text(),
            "chrg": self.chrg_spin.value(),
            "uhf": self.mult_spin.value() - 1,
            "acc": self.acc_spin.value(),
            "etemp": self.etemp_spin.value(),
            "solv": self.solv_combo.currentIndex(),
            "solvent": self.solvent_combo.currentText(),
            # ORCA
            "orca_path": self.orca_path_edit.text(),
            "orca_method": self.orca_method_combo.currentText(),
            "orca_basis": self.orca_basis_combo.currentText(),
            "orca_job_type": self.orca_job_combo.currentText(),
            "orca_nprocs": self.orca_nprocs_spin.value(),
            "orca_memory": self.orca_mem_spin.value(),
            "orca_solvent_idx": self.orca_solv_combo.currentIndex(),
            "orca_solvent_name": self.orca_solvent_combo.currentText(),
            "orca_extra": self.orca_extra_edit.text(),
            "orca_ofakeg_path": self.orca_ofakeg_edit.text(),
        }
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    def closeEvent(self, event):
        self._save_config()
        super().closeEvent(event)

    def _apply_config(self):
        xtb_path = self._config.get("xtb_path", "")
        self.g16_edit.setText(self._config.get("gaussian_path", ""))
        self.xtb_edit.setText(xtb_path)
        self.xtb2_edit.setText(xtb_path)
        gfn_val = self._config.get("gfn_level", 2)
        idx = {2: 0, 1: 1, 0: 2, -1: 3}.get(gfn_val, 0)
        self.gfn_combo.setCurrentIndex(idx)
        self.thread_spin.setValue(self._config.get("threads", min(os.cpu_count() or 4, 8)))
        self.extra_edit.setText(self._config.get("extra_args", ""))
        self.chrg_spin.setValue(self._config.get("chrg", 0))
        self.mult_spin.setValue(self._config.get("uhf", 0) + 1)
        self.acc_spin.setValue(self._config.get("acc", 1.0))
        self.etemp_spin.setValue(self._config.get("etemp", 300))
        self.solv_combo.setCurrentIndex(self._config.get("solv", 0))
        self.solvent_combo.setCurrentText(self._config.get("solvent", "water"))

        # ── ORCA settings ──
        self.orca_path_edit.setText(self._config.get("orca_path", ORCA_EXE))
        idx = self.orca_method_combo.findText(self._config.get("orca_method", "XTB2"))
        if idx >= 0:
            self.orca_method_combo.setCurrentIndex(idx)
        idx = self.orca_basis_combo.findText(self._config.get("orca_basis", ""))
        if idx >= 0:
            self.orca_basis_combo.setCurrentIndex(idx)
        idx = self.orca_job_combo.findText(self._config.get("orca_job_type", "SP"))
        if idx >= 0:
            self.orca_job_combo.setCurrentIndex(idx)
        self.orca_nprocs_spin.setValue(self._config.get("orca_nprocs", 4))
        self.orca_mem_spin.setValue(self._config.get("orca_memory", 4096))
        self.orca_solv_combo.setCurrentIndex(self._config.get("orca_solvent_idx", 0))
        self.orca_solvent_combo.setCurrentText(self._config.get("orca_solvent_name", "water"))
        self.orca_extra_edit.setText(self._config.get("orca_extra", ""))
        self.orca_ofakeg_edit.setText(self._config.get("orca_ofakeg_path", ""))

    # ── 文件浏览 ──

    def _shortcut_open_file(self):
        """Ctrl+O: 根据当前选项卡打开对应文件对话框。"""
        idx = self.main_tabs.currentIndex()
        if idx == 0:
            self._browse_gjf()
        elif idx == 1:
            self._browse_xtb_file()
        else:
            self._browse_orca_file()

    def _browse_gjf(self):
        path, _ = QFileDialog.getOpenFileName(self, self._tr("open_gjf"), "", self._tr("gaussian_filter"))
        if path:
            self.file_edit.setText(path)
            self._on_file_changed(path)  # editingFinished 不一定触发，手动调用

    def _browse_exe(self, edit, name):
        path, _ = QFileDialog.getOpenFileName(self, self._tr("open_file", name=name), "", self._tr("exe_filter"))
        if path:
            edit.setText(path)

    def _browse_xtb_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, self._tr("open_coord"), "",
            self._tr("coord_filter"),
        )
        if filepath:
            self.xtb_file_edit.setText(filepath)
            self.xtb_workdir_edit.setText(os.path.dirname(filepath))
            # 同步路径到高斯 Tab
            if self.file_edit.text().strip() != filepath:
                self.file_edit.blockSignals(True)
                self.file_edit.setText(filepath)
                self.file_edit.blockSignals(False)
            # 同步路径到 ORCA Tab
            if self.orca_file_edit.text().strip() != filepath:
                self.orca_file_edit.blockSignals(True)
                self.orca_file_edit.setText(filepath)
                self.orca_file_edit.blockSignals(False)
            try:
                self._load_molecule_both(filepath, caller="xtb")
            except Exception:
                import traceback
                traceback.print_exc()
            # 如果已是 Scan 模式，自动转换约束
            if self.xtb_calc_combo.currentIndex() == 10:
                try:
                    self._auto_fill_scan_xcontrol()
                except Exception:
                    pass

    def _load_xtb_molecule(self, filepath):
        """xTB Tab 加载分子（向后兼容，委托给统一方法）。"""
        try:
            self._load_molecule_both(filepath, caller="xtb")
        except Exception:
            import traceback
            traceback.print_exc()

    def _browse_xtb_workdir(self):
        d = QFileDialog.getExistingDirectory(self, self._tr("open_workdir"))
        if d:
            self.xtb_workdir_edit.setText(d)

    def _browse_xtb_product(self):
        p, _ = QFileDialog.getOpenFileName(self, self._tr("open_product"))
        if p:
            self.xtb_product_edit.setText(p)

    def _on_file_changed(self, text):
        """Tab 1 文件改变 → 三 Tab 同步加载分子结构。"""
        if getattr(self, '_loading_file', False):
            return
        self._loading_file = True
        try:
            p = text.strip()
            # 同步路径到 xtb Tab
            if self.xtb_file_edit.text().strip() != p:
                self.xtb_file_edit.blockSignals(True)
                self.xtb_file_edit.setText(p)
                self.xtb_file_edit.blockSignals(False)
            # 同步路径到 ORCA Tab
            if self.orca_file_edit.text().strip() != p:
                self.orca_file_edit.blockSignals(True)
                self.orca_file_edit.setText(p)
                self.orca_file_edit.blockSignals(False)
            try:
                self._load_molecule_both(p, caller="gaussian")
            except Exception:
                import traceback
                traceback.print_exc()
            # 如果 xTB Tab 已是 Scan 模式，自动转换约束
            if self.xtb_calc_combo.currentIndex() == 10:
                try:
                    self._auto_fill_scan_xcontrol()
                except Exception:
                    pass
            # 提取高斯路由关键字
            try:
                raw = Path(p).read_text(encoding="utf-8", errors="replace")
                route = self._extract_route_from_gjf(raw)
                if route:
                    self.route_edit.setText(route)
                else:
                    self.route_edit.setText("opt")
            except Exception:
                pass
        finally:
            self._loading_file = False

    def _load_molecule_both(self, filepath, caller="gaussian"):
        """统一加载分子到共享画布。caller: 'gaussian' | 'xtb' | 'orca'"""
        p = filepath.strip()
        if not p or not Path(p).is_file():
            self._orca_atoms = []; self._orca_bonds = []; self._orca_qst2_product_atoms = []
            self.viz_single_gb.show(); self.viz_qst_tabs.hide()
            self.viz_info_label.setText(self._tr("no_mol"))
            return

        try:
            atom_sets, bond_sets = load_molecule(p)
        except Exception:
            atom_sets, bond_sets = [], []

        if not atom_sets or not atom_sets[0]:
            self._orca_atoms = []; self._orca_bonds = []; self._orca_qst2_product_atoms = []
            self.viz_single_gb.show(); self.viz_qst_tabs.hide()
            self.viz_info_label.setText(self._tr("no_parse"))
            return

        n_structures = len(atom_sets)
        mf = self._mol_formula(atom_sets)

        # 共享画布：单结构 / QST2 双结构
        if n_structures >= 2:
            self.viz_single_gb.hide(); self.viz_qst_tabs.show()
            self.viz_qst_tabs.setCurrentIndex(0)
            try:
                self.viz_canvas_r.set_data(atom_sets[0], bond_sets[0] if len(bond_sets) > 0 else [])
                self.viz_canvas_p.set_data(atom_sets[1], bond_sets[1] if len(bond_sets) > 1 else [])
            except Exception:
                pass
            self.viz_info_label.setText(
                self._tr("mol_info_qst2", formula=mf, nr=len(atom_sets[0]), np=len(atom_sets[1])))
        else:
            self.viz_single_gb.show(); self.viz_qst_tabs.hide()
            try:
                self.viz_canvas.set_data(atom_sets[0], bond_sets[0] if bond_sets else [])
            except Exception:
                pass

            # 分子信息标签
            if caller == "orca":
                chrg = self.orca_chrg_spin.value()
                mult = self.orca_mult_spin.value()
            else:
                chrg = self.chrg_spin.value()
                mult = self.mult_spin.value()
            self.viz_info_label.setText(self._mol_info_str(atom_sets[0], chrg, mult))

        # 从 gjf 自动读取电荷和多重度
        gjf_chrg, gjf_mult = self._read_gjf_charge_mult(p)
        if gjf_chrg is not None:
            self.chrg_spin.setValue(gjf_chrg)
            self.xtb_chrg_spin.setValue(gjf_chrg)
            self.orca_chrg_spin.setValue(gjf_chrg)
        if gjf_mult is not None:
            self.mult_spin.setValue(gjf_mult)
            self.xtb_uhf_spin.setValue(gjf_mult - 1)
            self.orca_mult_spin.setValue(gjf_mult)

        # ORCA Tab 内部引用（NEB 等仍需要这些字段）
        self._orca_atoms = atom_sets[0]
        self._orca_bonds = bond_sets[0] if bond_sets else []
        self._orca_qst2_product_atoms = atom_sets[1] if n_structures >= 2 else []

        # 同步电荷和多重度到 xTB Tab
        if caller == "gaussian":
            self.xtb_chrg_spin.setValue(self.chrg_spin.value())
            self.xtb_uhf_spin.setValue(self.mult_spin.value() - 1)

    @staticmethod
    def _mol_formula(atom_sets):
        all_atoms = [a for s in atom_sets for a in s]
        syms = {}
        for a in all_atoms:
            syms[a['sym']] = syms.get(a['sym'], 0) + 1
        return "".join(f"{k}{v if v>1 else ''}" for k, v in sorted(syms.items()))

    @staticmethod
    def _mol_info_str(atoms, charge, mult):
        """构建分子信息字符串: 原子数, 电子数, 电荷状态, 多重度。"""
        natoms = len(atoms)
        total_z = sum(ATOMIC_NUMBERS.get(a['sym'], 0) for a in atoms)
        electrons = total_z - charge
        if charge == 0:
            chg_text = "neutral"
        elif charge < 0:
            chg_text = "anion"
        else:
            chg_text = "cation"
        mult_text = _MULT_TEXT.get(mult, f"mult={mult}")
        return f"{natoms} atoms, {electrons} electrons, {chg_text}, {mult_text}"

    # ── 日志 ──

    MAX_LOG_LINES = 5000

    def _log(self, text):
        """逐行写入日志，每 50 行裁剪一次防止 OOM。"""
        self.log.append(text)
        self._log_line_count += 1
        if self._log_line_count % 50 == 0:
            self._trim_log(self.log)
            self._log_line_count = 0

    def _trim_log(self, widget):
        """裁剪日志面板行数。"""
        doc = widget.document()
        if doc.blockCount() > self.MAX_LOG_LINES + 500:
            cursor = QTextCursor(doc.begin())
            cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, 500)
            cursor.movePosition(QTextCursor.Start, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        widget.moveCursor(QTextCursor.End)

    def _clear_log(self):
        self._log_line_count = 0
        self.log.clear()

    def _clear_xtb_log(self):
        self._xtb_log_line_count = 0
        self.xtb_log.clear()

    # ── Gaussian 扫描 → xTB xcontrol 转换 ──

    @staticmethod
    def _parse_gjf_atoms(content: str) -> list[dict]:
        """从 .gjf 解析原子坐标。返回 [{idx, sym, x, y, z}, ...]，索引从 1 开始。"""
        lines = content.splitlines()
        atoms = []
        rout_end = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("#"):
                rout_end = i
        if rout_end < 0:
            return atoms
        # 跳过路由行 → 空行 → 标题行 → 空行 → chrg/mult 行 → 坐标
        title_found = False
        chrg_mult_found = False
        for i in range(rout_end + 1, len(lines)):
            s = lines[i].strip()
            if not s:
                continue
            if not title_found:
                title_found = True
                continue
            if not chrg_mult_found:
                chrg_mult_found = True
                continue
            parts = s.split()
            if len(parts) >= 4:
                sym = parts[0].capitalize()
                if sym not in ATOMIC_NUMBERS:
                    break  # 不再是坐标行（可能是约束行 B/A/D 等）
                try:
                    atoms.append({
                        'idx': len(atoms) + 1,
                        'sym': sym,
                        'x': float(parts[1]), 'y': float(parts[2]), 'z': float(parts[3]),
                    })
                except (ValueError, IndexError):
                    pass
            else:
                break
        return atoms

    @staticmethod
    def _parse_gaussian_scan_constraints(content: str, natoms: int) -> list[dict]:
        """解析 .gjf 末尾的 modredundant 约束。"""
        lines = content.splitlines()
        constraints = []
        in_constraints = False
        for line in lines:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split()
            if not parts or parts[0] not in ("B", "A", "D"):
                # 如果已经进入约束区，且当前行不是约束，退出
                if in_constraints:
                    # 可能是其他关键字如 S, F 等
                    if parts and parts[0] in ("F", "S", "X"):
                        pass
                    else:
                        continue
                continue
            try:
                typ = parts[0]
                indices = []
                for p in parts[1:]:
                    try:
                        indices.append(int(p))
                    except ValueError:
                        break
                # B: 2 atoms, A: 3 atoms, D: 4 atoms
                if typ == "B" and len(indices) >= 2:
                    rest = parts[2 + 1:]  # after indices
                elif typ == "A" and len(indices) >= 3:
                    rest = parts[3 + 1:]
                elif typ == "D" and len(indices) >= 4:
                    rest = parts[4 + 1:]
                else:
                    continue
                # 找 S (scan) 参数
                scan_info = None
                for k, token in enumerate(rest):
                    if token.upper() == "S":
                        if k + 2 < len(rest):
                            try:
                                nsteps = int(rest[k + 1])
                                stepsize = float(rest[k + 2])
                                scan_info = {"nsteps": nsteps, "stepsize": stepsize}
                            except (ValueError, IndexError):
                                pass
                        break
                constraints.append({
                    "type": typ, "indices": indices[:2 if typ == "B" else 3 if typ == "A" else 4],
                    "scan": scan_info,
                })
                in_constraints = True
            except Exception:
                continue
        return constraints

    @staticmethod
    def _calc_distance(a, b):
        import math
        return math.sqrt((a['x'] - b['x']) ** 2 + (a['y'] - b['y']) ** 2 + (a['z'] - b['z']) ** 2)

    @staticmethod
    def _calc_angle(a, b, c):
        import math
        v1 = (a['x'] - b['x'], a['y'] - b['y'], a['z'] - b['z'])
        v2 = (c['x'] - b['x'], c['y'] - b['y'], c['z'] - b['z'])
        dot = v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]
        m1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2 + v1[2] ** 2)
        m2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2 + v2[2] ** 2)
        cos_a = max(-1.0, min(1.0, dot / (m1 * m2)))
        return math.degrees(math.acos(cos_a))

    @staticmethod
    def _calc_dihedral(a, b, c, d):
        import math
        v1 = (b['x'] - a['x'], b['y'] - a['y'], b['z'] - a['z'])
        v2 = (c['x'] - b['x'], c['y'] - b['y'], c['z'] - b['z'])
        v3 = (d['x'] - c['x'], d['y'] - c['y'], d['z'] - c['z'])
        # normal to b-c and a-b
        n1 = (
            v1[1] * v2[2] - v1[2] * v2[1],
            v1[2] * v2[0] - v1[0] * v2[2],
            v1[0] * v2[1] - v1[1] * v2[0],
        )
        n2 = (
            v2[1] * v3[2] - v2[2] * v3[1],
            v2[2] * v3[0] - v2[0] * v3[2],
            v2[0] * v3[1] - v2[1] * v3[0],
        )
        m1 = math.sqrt(n1[0] ** 2 + n1[1] ** 2 + n1[2] ** 2)
        m2 = math.sqrt(n2[0] ** 2 + n2[1] ** 2 + n2[2] ** 2)
        if m1 < 1e-12 or m2 < 1e-12:
            return 0.0
        dot = n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2]
        cos_d = max(-1.0, min(1.0, dot / (m1 * m2)))
        return math.degrees(math.acos(cos_d))

    @classmethod
    def _gaussian_to_xtb_scan(cls, content: str, force_k: float = 0.5) -> str | None:
        """将 Gaussian 扫描约束转换为 xTB xcontrol 输入。返回 xcontrol 文本或 None。"""
        atoms = cls._parse_gjf_atoms(content)
        if not atoms:
            return None
        constraints = cls._parse_gaussian_scan_constraints(content, len(atoms))
        if not constraints:
            return None
        lines = ["$constrain", f" force constant={force_k:.3f}"]
        scan_lines = ["$scan"]
        has_scan = False
        scan_idx = 0
        for c in constraints:
            typ_map = {"B": "distance", "A": "angle", "D": "dihedral"}
            name = typ_map.get(c["type"])
            if name is None:
                continue
            idx_list = c["indices"]
            if len(idx_list) < (2 if c["type"] == "B" else 3 if c["type"] == "A" else 4):
                continue
            # 计算初始值
            a0 = atoms[idx_list[0] - 1]
            a1 = atoms[idx_list[1] - 1]
            if c["type"] == "B":
                init_val = cls._calc_distance(a0, a1)
            elif c["type"] == "A":
                a2 = atoms[idx_list[2] - 1]
                init_val = cls._calc_angle(a0, a1, a2)
            elif c["type"] == "D":
                a2 = atoms[idx_list[2] - 1]
                a3 = atoms[idx_list[3] - 1]
                init_val = cls._calc_dihedral(a0, a1, a2, a3)
            else:
                init_val = 0.0
            idx_str = ", ".join(str(i) for i in idx_list)
            lines.append(f" {name}: {idx_str}, {init_val:.3f}")
            if c.get("scan"):
                scan_idx += 1
                nsteps = c["scan"]["nsteps"]
                stepsize = c["scan"]["stepsize"]
                end_val = init_val + nsteps * stepsize
                scan_lines.append(f" {scan_idx}: {init_val:.3f}, {end_val:.3f}, {nsteps + 1}")
                has_scan = True
        if not has_scan:
            scan_lines.append(" 1: 0.0, 1.0, 2")
        scan_lines.append("$end")
        return "\n".join(lines + scan_lines)

    # ── 运行 / 终止 ──

    def _preview_gaussian_command(self):
        """预览高斯 + xTB External 联用的命令行。"""
        gjf_str = self.file_edit.text().strip()
        g16 = self.g16_edit.text().strip()
        xtb = self.xtb_edit.text().strip()
        user_route = self.route_edit.text().strip() or "opt"
        threads = self.thread_spin.value()
        gfn_idx = self.gfn_combo.currentIndex()
        gfn_map = {0: "2", 1: "1", 2: "0", 3: "-1"}
        gfn_level_key = gfn_map.get(gfn_idx, "2")
        extra = self._build_gau_xtb_extra()

        self._clear_log()
        self._log("=" * 60)
        self._log("[INFO] 输入文件:  " + (gjf_str or "(未选择)"))
        self._log("[INFO] 高斯:      " + (g16 or "(未设置)"))
        self._log("[INFO] xTB:       " + (xtb or "(未设置)"))
        self._log("[INFO] GFN 级别:  " + self.gfn_combo.currentText())
        self._log("[INFO] 线程数:    " + str(threads))
        self._log("[INFO] 计算关键字:  " + user_route)
        self._log("[INFO] 额外参数:  " + (extra or "(无)"))
        if gjf_str and Path(gjf_str).exists():
            new_gjf = Path(gjf_str).parent / f"_{Path(gjf_str).stem}_xtb.gjf"
            raw_cmd = f'"{g16}" "{new_gjf.name}"'
            self._log(f"[CMD] 高斯命令:  {raw_cmd}")
        gfn_flag_map = {"2": "--gfn 2", "1": "--gfn 1", "0": "--gfn 0", "-1": "--gfnff"}
        xtb_cmd = f'"{xtb}" xxx.xyz --acc {self.acc_spin.value():.1f} {gfn_flag_map[gfn_level_key]} --parallel {threads}'
        if extra:
            xtb_cmd += f" {extra}"
        self._log(f"[CMD] xTB 命令:  {xtb_cmd}")
        self._log("=" * 60)

    def _run(self):
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, self._tr("hint"), self._tr("already_running"))
            return
        gjf_str = self.file_edit.text().strip()
        if not gjf_str or not Path(gjf_str).exists():
            QMessageBox.warning(self, self._tr("error"), f"{self._tr('err_gjf_notfound')}\n{gjf_str}")
            return
        original_gjf = Path(gjf_str)

        g16 = Path(self.g16_edit.text().strip())
        if not g16.exists():
            QMessageBox.warning(self, self._tr("error"), f"{self._tr('err_g16_notfound')}\n{g16}")
            return

        xtb = self.xtb_edit.text().strip()
        if not Path(xtb).exists():
            QMessageBox.warning(self, self._tr("error"), f"{self._tr('err_xtb_notfound')}\n{xtb}")
            return

        frozen = getattr(sys, "frozen", False)
        if not frozen:
            # 开发模式: 需要 gau_xtb.py 在同目录，bat 调用 python + gau_xtb.py
            script = self._extract_script()
            if script is None:
                QMessageBox.warning(self, self._tr("error"), self._tr("err_missing_script"))
                return

        py_exe = sys.executable

        # 生成 bat 包装器 — 冻结打包时用 exe 自身代替 python + gau_xtb.py
        if frozen:
            bat_path = _app_dir() / "gau_xtb_client.bat"
            try:
                bat_path.write_text(f'@echo off\n"{py_exe}" %*\n', encoding="ascii")
            except (PermissionError, OSError):
                import tempfile as _tempfile
                bat_path = Path(_tempfile.gettempdir()) / "gau_xtb_client.bat"
                bat_path.write_text(f'@echo off\n"{py_exe}" %*\n', encoding="ascii")
        else:
            bat_path = self._write_client_bat(py_exe, str(script))
        external_cmd = str(bat_path)

        # 读取 & 注入 External
        try:
            content = original_gjf.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            QMessageBox.warning(self, self._tr("error"), f"{self._tr('err_read_gjf')}\n{e}")
            return

        # 用户编辑的路由关键字
        user_route = self.route_edit.text().strip()
        if not user_route:
            user_route = "opt"  # 默认优化

        # modredundant/addred 联用 External 自动注入 nomicro（写入 opt(...) 内）
        if any(kw in user_route.lower() for kw in ("modredundant", "addred")):
            # 检查 opt(...) 内是否已有 nomicro
            m = re.search(r'(?i)\bopt\s*\(([^)]*)\)', user_route)
            if m:
                inside = m.group(1)
                if "nomicro" not in inside.lower():
                    user_route = user_route[:m.start(1)] + inside.strip() + ",nomicro" + user_route[m.end(1):]
            else:
                # opt=addred → opt=(addred,nomicro)
                user_route = re.sub(
                    r'(?i)\bopt\s*=\s*(\w+)', r'opt=(\1,nomicro)', user_route, count=1,
                )

        patched = self._inject_external(content, external_cmd, user_route)
        if patched is None:
            QMessageBox.warning(self, self._tr("error"), self._tr("err_no_route"))
            return

        # 用 UI 中的电荷/多重度覆盖 gjf 中的值
        patched = self._patch_charge_mult(patched, self.chrg_spin.value(), self.mult_spin.value())

        # 写入 _xxx_xtb.gjf
        new_gjf = original_gjf.parent / f"_{original_gjf.stem}_xtb.gjf"
        try:
            new_gjf.write_text(patched.rstrip("\n") + "\n\n", encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, self._tr("error"), f"{self._tr('err_write_tmp')}\n{new_gjf}\n{e}")
            return

        # 环境变量
        cwd = str(original_gjf.parent)
        gauss_exedir = str(g16.parent).replace("\\", "/") + "/"
        threads = self.thread_spin.value()
        gfn_idx = self.gfn_combo.currentIndex()
        gfn_map = {0: "2", 1: "1", 2: "0", 3: "-1"}
        extra = self._build_gau_xtb_extra()

        env = os.environ.copy()
        env["GAUSS_EXEDIR"] = gauss_exedir
        env["GAU_XTB_COMMAND"] = xtb
        env["GAU_XTB_THREADS"] = str(threads)
        env["GAU_XTB_GFN"] = gfn_map.get(gfn_idx, "2")
        if extra:
            env["GAU_XTB_ARGS"] = extra

        # 日志
        self._clear_log()
        self._log("=" * 60)
        self._log(f"[INFO] 原始输入:  {original_gjf}")
        self._log(f"[INFO] 实际运行:  {new_gjf}")
        self._log(f"[INFO] 高斯:      {g16}")
        self._log(f"[INFO] xTB:       {xtb}")
        self._log(f"[INFO] GFN 级别:  {self.gfn_combo.currentText()}")
        self._log(f"[INFO] 线程数:    {threads}")
        self._log(f"[INFO] 额外参数:  {extra or '(无)'}")
        self._log(f"[INFO] 计算关键字:  {user_route}")
        self._log(f"[INFO] 已注入 External → 使用 xTB 计算")
        # 构造 xtb 命令行供参考
        gfn_level_key = int(gfn_map.get(gfn_idx, "2"))
        gfn_flag_map = {2: "--gfn 2", 1: "--gfn 1", 0: "--gfn 0", -1: "--gfnff"}
        gfn_flag = gfn_flag_map[gfn_level_key]
        xtb_cmd = f'"{xtb}" xxx.xyz --acc 1.0 {gfn_flag} --parallel {threads}'
        if extra:
            xtb_cmd += f" {extra}"
        self._log(f"[INFO] xtb 命令:   {xtb_cmd}")
        self._log("=" * 60)

        # 启动（传入 out 文件路径用于实时 tail）
        command = [str(g16), new_gjf.name]
        self._out_path = new_gjf.parent / f"_{original_gjf.stem}_xtb.out"
        # 删除旧 .out 避免 tail 先读旧内容
        try:
            self._out_path.unlink(missing_ok=True)
        except Exception:
            pass
        self._worker = GaussianWorker(command, cwd, env, str(self._out_path))
        self._worker.output_line.connect(self._log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

        self.run_btn.setEnabled(False)
        self.abort_btn.setEnabled(True)
        self._status_btn.start(self._tr("running"))

    def _abort(self):
        if self._worker:
            self._worker.abort()
            self._status_btn.set_status(self._tr("aborted"), "#e53935")
            self._xtb_status_btn.set_status(self._tr("aborted"), "#e53935")
            self.run_btn.setEnabled(True)
            self.abort_btn.setEnabled(False)
            self.xtb_run_btn.setEnabled(True)
            self.xtb_abort_btn.setEnabled(False)
            self.orca_run_btn.setEnabled(True)
            self.orca_abort_btn.setEnabled(False)
            self._orca_status_btn.set_status(self._tr("aborted"), "#e53935")

    def _on_finished(self, code):
        self.run_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)
        if code == 0:
            self._status_btn.set_status(self._tr("done"), "#43a047")
            self._log("=" * 60)
            self._log("[OK] Normal termination")
        else:
            self._status_btn.set_status(self._tr("exit_code", code=code), "#e53935")
            self._log(f"[ERR] Exit code: {code}")
        # 刷新完事件队列后弹出最终结构
        QTimer.singleShot(0, self._show_final_structure)

    def _on_xtb_calc_changed(self, idx):
        """xTB 计算类型切换，显隐 TS/Path/Scan 参数。"""
        need_extra = idx in (3, 6, 7)  # TS, ModeF, Path
        self.xtb_ts_widget.setVisible(need_extra)
        self.xtb_product_edit.setVisible(idx in (3, 7))
        # Scan (index 10) — 如果载入的是 .gjf 且含 scan 关键字，自动转换
        self.xtb_scan_widget.setVisible(idx == 10)
        if idx == 10:
            try:
                self._auto_fill_scan_xcontrol()
            except Exception:
                pass
            if not self.xtb_scan_edit.toPlainText().strip():
                self.xtb_scan_edit.setPlainText(
                    "$constrain\n"
                    "   force constant=0.5\n"
                    "   distance: 1, 2, auto\n"
                    "$scan\n"
                    "   1: 1.2, 3.0, 20\n"
                    "$end"
                )

    def _auto_fill_scan_xcontrol(self):
        """若 xTB Tab 载入的 .gjf 含 modredundant/addred，自动转为 xcontrol 填入编辑器。"""
        filepath = self.xtb_file_edit.text().strip()
        if not filepath or not filepath.lower().endswith('.gjf'):
            return
        try:
            content = Path(filepath).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return
        route_lower = " ".join(
            line.strip() for line in content.splitlines()
            if line.strip().startswith("#")
        ).lower()
        if any(kw in route_lower for kw in ("modredundant", "addred")):
            force_k = self.xtb_force_k_spin.value()
            xcontrol = self._gaussian_to_xtb_scan(content, force_k=force_k)
            if xcontrol:
                self.xtb_scan_edit.setPlainText(xcontrol)

    def _on_xtb_solv_changed(self, idx):
        """xTB 溶剂化模型切换。"""
        if idx == 0:
            self.xtb_solvent_combo.setEnabled(False)
        else:
            self.xtb_solvent_combo.setEnabled(True)
            self.xtb_solvent_combo.clear()
            if idx == 1:
                self.xtb_solvent_combo.addItems(ALPB_SOLVENTS)
            elif idx == 2:
                self.xtb_solvent_combo.addItems(COSMO_SOLVENTS)
            self.xtb_solvent_combo.setCurrentText("water")

    def _on_gau_xtb_solv_changed(self, idx):
        """Tab1 溶剂化模型切换。"""
        if idx == 0:
            self.solvent_combo.setEnabled(False)
        else:
            self.solvent_combo.setEnabled(True)
            self.solvent_combo.clear()
            if idx == 1:
                self.solvent_combo.addItems(ALPB_SOLVENTS)
            elif idx == 2:
                self.solvent_combo.addItems(COSMO_SOLVENTS)
            self.solvent_combo.setCurrentText("water")

    def _build_gau_xtb_extra(self) -> str:
        """从 UI 控件组装 xTB 额外参数字符串。"""
        parts = []

        # SCF 精度
        acc = self.acc_spin.value()
        if abs(acc - 1.0) > 0.001:
            parts.append(f"--acc {acc}")

        # 电子温度
        etemp = self.etemp_spin.value()
        if etemp != 300:
            parts.append(f"--etemp {etemp}")

        # 溶剂化
        solv = self.solv_combo.currentIndex()
        if solv == 1:
            parts.append(f"--alpb {self.solvent_combo.currentText()}")
        elif solv == 2:
            parts.append(f"--cosmo {self.solvent_combo.currentText()}")

        # 用户手动输入的额外参数
        user_extra = self.extra_edit.text().strip()
        if user_extra:
            parts.append(user_extra)

        return " ".join(parts)

    @staticmethod
    def _read_gjf_charge_mult(filepath: str):
        """从 gjf 读取 charge multiplicity。"""
        try:
            content = Path(filepath).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None, None
        lines = content.splitlines()
        found_blank = 0
        for s in lines:
            s = s.strip()
            if not s:
                found_blank += 1
                if found_blank >= 2:
                    continue
            elif found_blank >= 2:
                parts = s.split()
                if len(parts) == 2:
                    try:
                        return int(float(parts[0])), int(float(parts[1]))
                    except (ValueError, IndexError):
                        return None, None
                break
        return None, None

    def _build_xtb_command(self):
        """构建 xTB 独立计算命令行。"""
        filepath = self.xtb_file_edit.text().strip()
        if not filepath or not os.path.isfile(filepath):
            raise ValueError("请选择输入文件")

        xtb_path = self.xtb2_edit.text().strip()
        if not xtb_path or not os.path.isfile(xtb_path):
            raise ValueError(f"xtb.exe 不存在: {xtb_path}")

        workdir = self.xtb_workdir_edit.text().strip()
        if not workdir or not os.path.isdir(workdir):
            raise ValueError(f"工作目录无效: {workdir}")

        cmd = [xtb_path]

        # 方法
        method = self.xtb_method_combo.currentIndex()
        method_map = {0: "--gfn 2", 1: "--gfn 2", 2: "--gfn 1", 3: "--gfn 0", 4: "--gfnff"}
        val = method_map[method]
        cmd.extend(val.split())

        # 计算类型
        calc = self.xtb_calc_combo.currentIndex()
        calc_flags = {
            0: [], 1: ["--opt"], 2: ["--ohess"], 3: ["--opt"],
            4: ["--freq"], 5: ["--hess"],
            6: ["--modef", str(self.xtb_modef_spin.value())],
            7: [], 8: ["--omd"], 9: ["--metadyn"],
            10: ["--opt", "--input", "xTBridge_scan.inp"],
        }
        cmd.extend(calc_flags.get(calc, []))

        # 电荷/自旋
        chrg = self.xtb_chrg_spin.value()
        uhf = self.xtb_uhf_spin.value()
        if chrg != 0:
            cmd.extend(["--chrg", str(chrg)])
        if uhf != 0:
            cmd.extend(["--uhf", str(uhf)])

        # 精度/温度
        acc = self.xtb_acc_spin.value()
        if abs(acc - 1.0) > 0.001:
            cmd.extend(["--acc", str(acc)])
        etemp = self.xtb_etemp_spin.value()
        if etemp != 300:
            cmd.extend(["--etemp", str(etemp)])

        # 溶剂化
        solv = self.xtb_solv_combo.currentIndex()
        if solv == 1:
            cmd.extend(["--alpb", self.xtb_solvent_combo.currentText()])
        elif solv == 2:
            cmd.extend(["--cosmo", self.xtb_solvent_combo.currentText()])

        # 选项
        if self.xtb_molden_cb.isChecked():
            cmd.append("--molden")
        if self.xtb_json_cb.isChecked():
            cmd.append("--json")
        if self.xtb_verbose_cb.isChecked():
            cmd.append("--verbose")

        parallel = self.xtb_parallel_spin.value()
        if parallel > 1:
            cmd.extend(["--parallel", str(parallel)])

        # 输入文件: gjf/com → xyz (复用已有的 parse_gjf_coords_all)
        ext = os.path.splitext(filepath)[1].lower()
        if ext in (".gjf", ".com"):
            atom_sets = parse_gjf_coords_all(filepath)
            if not atom_sets or not atom_sets[0]:
                raise ValueError("无法从 gjf 解析坐标")
            atoms = [(a['sym'], a['x'], a['y'], a['z']) for a in atom_sets[0]]
            # 只有用户没改电荷/自旋时才从 gjf 自动读取
            gjf_chrg, gjf_mult = self._read_gjf_charge_mult(filepath)
            gui_chrg = self.xtb_chrg_spin.value()
            gui_uhf = self.xtb_uhf_spin.value()
            if gui_chrg == 0 and gui_uhf == 0 and gjf_chrg is not None:
                chrg = gjf_chrg
                if gjf_mult is not None:
                    uhf = gjf_mult - 1
            for flag in ("--chrg", "--uhf"):
                if flag in cmd:
                    i = cmd.index(flag)
                    cmd.pop(i); cmd.pop(i)
            if chrg != 0:
                cmd.extend(["--chrg", str(chrg)])
            if uhf != 0:
                cmd.extend(["--uhf", str(uhf)])
            base = os.path.splitext(os.path.basename(filepath))[0]
            xyz_name = f"{base}_from_gjf.xyz"
            xyz_path = os.path.join(workdir, xyz_name)
            with open(xyz_path, "w", encoding="utf-8") as f:
                f.write(f"{len(atoms)}\nconverted from {os.path.basename(filepath)}\n")
                for sym, x, y, z in atoms:
                    f.write(f"{sym}  {x:15.8f}  {y:15.8f}  {z:15.8f}\n")
            cmd.append(xyz_name)
        else:
            cmd.append(os.path.basename(filepath))

        # TS: xcontrol_ts.inp
        if calc == 3:
            xctrl = os.path.join(workdir, "xcontrol_ts.inp")
            with open(xctrl, "w") as f:
                f.write("$opt\n   ts=1\n$end\n")
            cmd.extend(["--input", "xcontrol_ts.inp"])

        # Path: 产物文件
        if calc == 7:
            prod = self.xtb_product_edit.text().strip()
            if not prod or not os.path.isfile(prod):
                raise ValueError("Reaction Path 需要指定产物结构文件")
            prod_basename = os.path.basename(prod)
            dest = os.path.join(workdir, prod_basename)
            if os.path.normpath(prod) != os.path.normpath(dest):
                shutil.copy2(prod, dest)
            cmd.extend(["--path", prod_basename])

        return cmd, workdir

    def _xtb_log(self, text):
        """逐行写入 xTB 日志，每 50 行裁剪一次。"""
        self.xtb_log.append(text)
        self._xtb_log_line_count += 1
        if self._xtb_log_line_count % 50 == 0:
            self._trim_log(self.xtb_log)
            self._xtb_log_line_count = 0

    def _clear_xtb_log(self):
        self._xtb_log_line_count = 0
        self.xtb_log.clear()

    def _preview_xtb_command(self):
        try:
            cmd, workdir = self._build_xtb_command()
        except ValueError as e:
            QMessageBox.warning(self, self._tr("err_param"), str(e))
            return
        cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        self._clear_xtb_log()
        self._xtb_log(self._tr("preview_title") + "\n")
        self._xtb_log(self._tr("preview_workdir") + f" {workdir}\n")
        self._xtb_log(self._tr("preview_cmd") + f" {cmd_str}\n")

    def _run_xtb(self):
        try:
            cmd, workdir = self._build_xtb_command()
        except ValueError as e:
            QMessageBox.warning(self, self._tr("err_param"), str(e))
            return
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, self._tr("hint"), self._tr("already_running"))
            return

        cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        self._clear_xtb_log()
        self._xtb_log("=" * 60)
        self._xtb_log("xTB 独立计算")
        self._xtb_log(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._xtb_log(f"工作目录: {workdir}")
        self._xtb_log(f"命令: {cmd_str}")
        # 如果需要扫描，写出 xcontrol 文件
        if self.xtb_calc_combo.currentIndex() == 10:
            scan_text = self.xtb_scan_edit.toPlainText().strip()
            if scan_text:
                scan_path = Path(workdir) / "xTBridge_scan.inp"
                scan_path.write_text(scan_text, encoding="utf-8")
                self._xtb_log(f"[INFO] xcontrol 文件已写入: {scan_path}")
            else:
                QMessageBox.warning(self, self._tr("error"), self._tr("err_scan_empty"))
                return
        self._xtb_log("=" * 60)
        self._xtb_log("")

        self._xtb_workdir = workdir
        self._worker = XtbWorker(cmd, workdir)
        self._worker.output_line.connect(self._xtb_log)
        self._worker.finished.connect(self._on_xtb_finished)
        self._worker.start()

        self.xtb_run_btn.setEnabled(False)
        self.xtb_abort_btn.setEnabled(True)
        self._xtb_status_btn.start(self._tr("running"))

    def _on_xtb_finished(self, code):
        self.xtb_run_btn.setEnabled(True)
        self.xtb_abort_btn.setEnabled(False)
        if code == 0:
            self._xtb_status_btn.set_status(self._tr("done"), "#43a047")
            self._xtb_log("")
            self._xtb_log("=" * 60)
            self._xtb_log("[OK] xTB Normal termination")
            self._auto_export_xtbopt_gjf()
            if self.xtb_calc_combo.currentIndex() == 10:
                QTimer.singleShot(0, self._show_scan_viewer)
            else:
                QTimer.singleShot(0, self._show_xtb_structure)
        else:
            self._xtb_status_btn.set_status(self._tr("exit_code", code=code), "#e53935")
            self._xtb_log(f"\n[ERR] Exit code: {code}")

    def _show_scan_viewer(self):
        """解析 xtbscan.log，弹出扫描能量图 + 结构对话框。"""
        if not hasattr(self, '_xtb_workdir'):
            return
        scan_path = Path(self._xtb_workdir) / "xtbscan.log"
        if not scan_path.is_file():
            self._xtb_log("[WARN] xtbscan.log not found, showing xtbopt.xyz instead")
            self._show_xtb_structure()
            return
        scan_data = parse_xtb_scan_log(str(scan_path))
        if not scan_data:
            self._xtb_log("[WARN] xtbscan.log parse failed, showing xtbopt.xyz instead")
            self._show_xtb_structure()
            return

        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(self._tr("scan_viewer_title", steps=len(scan_data)))
        dlg.resize(720, 680)
        dlg.setMinimumSize(600, 500)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(8, 8, 8, 8)

        # 折线图
        chart = ScanChart()
        chart.set_data(scan_data)
        layout.addWidget(chart, stretch=2)

        # 分子画布
        canvas = MolCanvas()
        atoms_0 = scan_data[0]['atoms']
        bonds_0 = _auto_bonds(atoms_0)
        canvas.set_data(atoms_0, bonds_0)
        info_label = QLabel(self._tr("scan_step_info", step=1, e=scan_data[0]['energy'],
                                     e_rel=scan_data[0]['energy_relative']))
        layout.addWidget(info_label)
        layout.addWidget(canvas, stretch=3)

        # 点击图表 → 更新画布
        def on_step_clicked(idx: int):
            if 0 <= idx < len(scan_data):
                d = scan_data[idx]
                bonds = _auto_bonds(d['atoms'])
                canvas.set_data(d['atoms'], bonds)
                info_label.setText(self._tr("scan_step_info", step=d['step'],
                                            e=d['energy'], e_rel=d['energy_relative']))
        chart.point_clicked.connect(on_step_clicked)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_gjf = QPushButton(self._tr("save_gjf"))
        btn_gjf.clicked.connect(lambda: self._export_gjf(
            scan_data[chart.selected_step]['atoms'], dlg,
            chrg=self.xtb_chrg_spin.value(),
            mult=self.xtb_uhf_spin.value() + 1))
        btn_row.addWidget(btn_gjf)
        btn_folder = QPushButton(self._tr("open_folder"))
        btn_folder.clicked.connect(lambda: os.startfile(str(scan_path.parent)))
        btn_row.addWidget(btn_folder)
        btn_close = QPushButton(self._tr("close"))
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        dlg.exec_()

    def _show_xtb_structure(self):
        """从 xtbopt.xyz 解析 xTB 优化结构，弹窗可视化。"""
        if not hasattr(self, '_xtb_workdir'):
            return
        xyz_path = Path(self._xtb_workdir) / "xtbopt.xyz"
        if not xyz_path.is_file():
            return
        atoms = parse_xyz_coords(str(xyz_path))
        if not atoms:
            return
        bonds = _auto_bonds(atoms)
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(self._tr("xtb_opt_title"))
        dlg.resize(600, 550)
        dlg.setMinimumSize(400, 350)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(8, 8, 8, 8)
        canvas = MolCanvas()
        canvas.set_data(atoms, bonds)
        layout.addWidget(QLabel(self._tr("from_file", name=xyz_path.name, n=len(atoms), b=len(bonds))))
        layout.addWidget(canvas, stretch=1)
        hint = QHBoxLayout()
        hint.addWidget(QLabel(self._tr("rotate_hint")))
        hint.addStretch()
        btn_gjf = QPushButton(self._tr("save_gjf"))
        btn_gjf.clicked.connect(lambda: self._export_gjf(atoms, dlg,
            chrg=self.xtb_chrg_spin.value(),
            mult=self.xtb_uhf_spin.value() + 1))
        hint.addWidget(btn_gjf)
        btn_folder = QPushButton(self._tr("open_folder"))
        btn_folder.clicked.connect(lambda: os.startfile(str(xyz_path.parent)))
        hint.addWidget(btn_folder)
        btn_close = QPushButton(self._tr("close"))
        btn_close.clicked.connect(dlg.accept)
        hint.addWidget(btn_close)
        layout.addLayout(hint)
        dlg.exec_()

    def _show_final_structure(self):
        """从 out 文件的最后一个 Standard orientation 解析结构，弹窗可视化。"""
        atoms = None
        if hasattr(self, '_out_path') and self._out_path is not None and self._out_path.is_file():
            atoms = parse_last_standard_orientation(str(self._out_path))
        if not atoms:
            return
        bonds = _auto_bonds(atoms)
        # 弹出对话框
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(self._tr("opt_structure"))
        dlg.resize(600, 550)
        dlg.setMinimumSize(400, 350)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(8, 8, 8, 8)
        canvas = MolCanvas()
        canvas.set_data(atoms, bonds)
        layout.addWidget(QLabel(self._tr("from_file", name=self._out_path.name, n=len(atoms), b=len(bonds))))
        layout.addWidget(canvas, stretch=1)
        hint = QHBoxLayout()
        hint.addWidget(QLabel(self._tr("rotate_hint")))
        hint.addStretch()
        # 导出 GJF
        btn_gjf = QPushButton(self._tr("save_gjf"))
        btn_gjf.clicked.connect(lambda: self._export_gjf(atoms, dlg))
        hint.addWidget(btn_gjf)
        if hasattr(self, '_out_path') and self._out_path.parent.is_dir():
            btn_folder = QPushButton(self._tr("open_folder"))
            btn_folder.clicked.connect(lambda: os.startfile(str(self._out_path.parent)))
            hint.addWidget(btn_folder)
        btn_close = QPushButton(self._tr("close"))
        btn_close.clicked.connect(dlg.accept)
        hint.addWidget(btn_close)
        layout.addLayout(hint)
        dlg.exec_()

    def _auto_export_xtbopt_gjf(self):
        """xTB 完成后，自动将 xtbopt.xyz 转成 {源文件名}_xtbopt.gjf。"""
        if not hasattr(self, '_xtb_workdir'):
            return
        xyz_path = Path(self._xtb_workdir) / "xtbopt.xyz"
        if not xyz_path.is_file():
            return
        atoms = parse_xyz_coords(str(xyz_path))
        if not atoms:
            return
        # 从入口文件推断输出名
        src = self.xtb_file_edit.text().strip()
        if src and Path(src).exists():
            out_name = Path(src).stem + "_xtbopt.gjf"
        else:
            out_name = "xtbopt.gjf"
        out_path = xyz_path.parent / out_name
        chrg = self.xtb_chrg_spin.value()
        mult = self.xtb_uhf_spin.value() + 1
        lines = ["#p", "", f"Exported from xTBridge – xtbopt", "", f"{chrg} {mult}"]
        for a in atoms:
            lines.append(f" {a['sym']:<3s} {a['x']:12.6f} {a['y']:12.6f} {a['z']:12.6f}")
        lines.append("")
        try:
            out_path.write_text("\n".join(lines), encoding="utf-8")
            self._xtb_log(f"[OK] 已自动导出: {out_path}")
        except Exception as e:
            self._xtb_log(f"[WARN] 自动导出失败: {e}")

    def _export_gjf(self, atoms, parent_dlg, chrg=None, mult=None):
        """将原子坐标导出为 Gaussian 输入文件 .gjf。"""
        path, _ = QFileDialog.getSaveFileName(parent_dlg, self._tr("save_gjf"),
                                               "", "Gaussian Input (*.gjf);;All Files (*)")
        if not path:
            return
        if chrg is None:
            chrg = self.chrg_spin.value()
        if mult is None:
            mult = self.mult_spin.value()
        lines = ["#p", "", f"Exported from xTBridge", "", f"{chrg} {mult}"]
        for a in atoms:
            lines.append(f" {a['sym']:<3s} {a['x']:12.6f} {a['y']:12.6f} {a['z']:12.6f}")
        lines.append("")
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(parent_dlg, self._tr("error"), str(e))


# ═══════════════════════════════════════════════════════════════════
#  QSS 样式
# ═══════════════════════════════════════════════════════════════════

