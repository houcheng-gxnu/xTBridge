#!/usr/bin/env python3
"""xTBridge 入口 — Gaussian + xTB External 联用，带 3D 分子可视化。

用法:
    python -m xtbridge.main
    或
    python xtbridge/main.py
"""

import sys
import os
import time
import faulthandler
from pathlib import Path

# 确保项目根目录在 path 中（直接运行时需要）
if getattr(sys, "frozen", False):
    _proj_root = Path(sys._MEIPASS)
else:
    _proj_root = Path(__file__).resolve().parent.parent
if str(_proj_root) not in sys.path:
    sys.path.insert(0, str(_proj_root))

# === 崩溃日志：faulthandler 能抓到原生崩溃（try/except 抓不到的那种）===
if getattr(sys, "frozen", False):
    _crash_path = Path(sys.executable).parent / "xTBridge_crash.log"
else:
    _crash_path = _proj_root / "xTBridge_crash.log"
try:
    _fault_file = open(_crash_path, "a", encoding="utf-8")
    _fault_file.write(f"\n=== Launch at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    _fault_file.flush()
    faulthandler.enable(file=_fault_file, all_threads=True)
except Exception:
    _fault_file = None


def _pkg_dir() -> Path:
    """xtbridge 包自身目录（含 gau_xtb.py / OfakeG 等内嵌依赖）。
    CLI 路径专用副本：不依赖 main_window.py 的导入。
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", str(Path(sys.executable).parent)))
    return Path(__file__).resolve().parent


if __name__ == "__main__":
    # ==================================================================
    # CLI 路径：被高斯 External 调用（sys.argv 包含 layer/InputFile 等）
    # 关键原则：绝对不导入 PyQt5 或任何 GUI 模块！
    # ==================================================================
    if len(sys.argv) > 1:
        # 优先用标准 import（frozen 模式下模块已在 PYZ 中，依赖完整）
        try:
            from xtbridge.gau_xtb import main as _gau_xtb_main
            sys.exit(_gau_xtb_main())
        except SystemExit as e:
            sys.exit(e.code if isinstance(e.code, int) else 0)
        except ImportError:
            pass

        # 回退：importlib 动态加载（开发模式 fallback）
        try:
            import importlib.util
            _script = _pkg_dir() / "gau_xtb.py"
            _spec = importlib.util.spec_from_file_location("gau_xtb", str(_script))
            _gau_xtb = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_gau_xtb)
            sys.exit(_gau_xtb.main())
        except SystemExit as e:
            sys.exit(e.code if isinstance(e.code, int) else 0)
        except Exception:
            import runpy
            _script = _pkg_dir() / "gau_xtb.py"
            if _script.exists():
                sys.argv = [str(_script)] + sys.argv[1:]
                try:
                    runpy.run_path(str(_script), run_name="__main__")
                except SystemExit as e:
                    sys.exit(e.code if isinstance(e.code, int) else 0)
            sys.exit(1)

    # ==================================================================
    # GUI 路径：正常启动 — 从这里才开始导入 PyQt5
    # ==================================================================
    os.environ.setdefault("QT_OPENGL", "software")

    from PyQt5.QtWidgets import QApplication, QMessageBox
    from xtbridge.styles import LIGHT_QSS
    from xtbridge.main_window import GauXtbViewer, _app_dir

    def main():
        """GUI 入口（当未被高斯 External 调用时）。"""
        try:
            app = QApplication(sys.argv)
            app.setStyle("Fusion")
            app.setStyleSheet(LIGHT_QSS)
            win = GauXtbViewer()
            win.show()
            sys.exit(app.exec_())
        except Exception as exc:
            import traceback
            crash_log = _app_dir() / "xTBridge_crash.log"
            crash_log.write_text(
                f"Crash at {time.strftime('%Y-%m-%d %H:%M:%S')}\n{traceback.format_exc()}",
                encoding="utf-8",
            )
            try:
                QMessageBox.critical(None, "启动错误 / Launch Error", f"程序崩溃 / Program crashed:\n{exc}")
            except Exception:
                pass
            sys.exit(1)

    main()
