"""xTBridge — Gaussian + xTB + ORCA 联用，带 3D 分子可视化。

基于 PyQt5 的跨平台桌面 GUI 应用。

用法:
    python -m xtbridge.main
    或
    python xtbridge/main.py

模块结构:
    xtbridge/
    ├── atom_data.py      # 原子数据
    ├── file_parser.py    # 文件解析
    ├── mol_canvas.py     # 3D 分子渲染
    ├── widgets.py        # GUI 组件
    ├── workers.py        # 计算线程
    ├── orca_utils.py     # ORCA 工具
    ├── translator.py     # 中英文字典
    ├── styles.py         # QSS 样式
    ├── main_window.py    # 主窗口
    └── main.py           # 入口
"""

from .mol_canvas import MolCanvas
from .widgets import StatusButton, ScanChart
from .workers import GaussianWorker, XtbWorker, OrcaWorker
from .main_window import GauXtbViewer
