"""计算工作线程：GaussianWorker, XtbWorker, OrcaWorker。"""

import os
import subprocess
import time
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal


class GaussianWorker(QThread):
    output_line = pyqtSignal(str)
    finished = pyqtSignal(int)
    progress = pyqtSignal(int)

    def __init__(self, command, cwd, env, outfile=None):
        super().__init__()
        self.command = command
        self.cwd = cwd
        self.env = env
        self.outfile = outfile
        self.proc = None
        self._abort_flag = False

    def run(self):
        try:
            self.proc = subprocess.Popen(
                self.command, cwd=self.cwd, env=self.env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except FileNotFoundError:
            self.output_line.emit("[ERROR] 高斯程序未找到")
            self.finished.emit(1)
            return

        outfile = self.outfile
        waited = 0
        while outfile and not Path(outfile).is_file() and self.proc.poll() is None and waited < 150:
            time.sleep(0.2)
            waited += 1

        if outfile and Path(outfile).is_file():
            self._tail_file(outfile)
        elif self.proc.poll() is not None:
            self.output_line.emit("[WARN] 进程已退出，.out 文件未生成")
        elif outfile:
            self.output_line.emit("[WARN] .out 文件生成超时，改用管道输出")
            tick_count = 0
            for line in iter(self.proc.stdout.readline, ""):
                if self._abort_flag:
                    self.proc.terminate()
                    break
                self.output_line.emit(line.rstrip("\n"))
                tick_count += 1
                if tick_count % 10 == 0:
                    self.progress.emit(min(tick_count // 10, 98))
        else:
            tick_count = 0
            for line in iter(self.proc.stdout.readline, ""):
                if self._abort_flag:
                    self.proc.terminate()
                    break
                self.output_line.emit(line.rstrip("\n"))
                tick_count += 1
                if tick_count % 10 == 0:
                    self.progress.emit(min(tick_count // 10, 98))

        try:
            remaining = self.proc.stdout.read()
            lines = [l for l in remaining.splitlines() if l.strip()]
            _BATCH = 20
            for i in range(0, len(lines), _BATCH):
                self.output_line.emit("\n".join(lines[i:i + _BATCH]))
        except Exception:
            pass
        self.proc.wait()
        self.progress.emit(100)
        self.finished.emit(self.proc.returncode)

    def _tail_file(self, path):
        tick_count = 0
        last_size = 0
        _BATCH = 20

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                existing = f.read()
            lines = [l for l in existing.splitlines() if l.strip()]
            last_size = Path(path).stat().st_size
            for i in range(0, len(lines), _BATCH):
                batch = "\n".join(lines[i:i + _BATCH])
                self.output_line.emit(batch)
                tick_count += len(lines[i:i + _BATCH])
                if tick_count % 10 == 0:
                    self.progress.emit(min(tick_count // 10, 98))
        except Exception:
            pass

        while self.proc.poll() is None and not self._abort_flag:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(last_size)
                    new_content = f.read()
                    cur_pos = f.tell()
                    if cur_pos > last_size:
                        last_size = cur_pos
                        lines = [l for l in new_content.splitlines() if l.strip()]
                        for i in range(0, len(lines), _BATCH):
                            batch = "\n".join(lines[i:i + _BATCH])
                            self.output_line.emit(batch)
                            tick_count += len(lines[i:i + _BATCH])
                            if tick_count % 10 == 0:
                                self.progress.emit(min(tick_count // 10, 98))
            except Exception:
                pass
            time.sleep(0.3)

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(last_size)
                remaining = f.read()
            lines = [l for l in remaining.splitlines() if l.strip()]
            for i in range(0, len(lines), _BATCH):
                self.output_line.emit("\n".join(lines[i:i + _BATCH]))
        except Exception as e:
            self.output_line.emit(f"[WARN] 读取输出文件失败: {e}")

    def abort(self):
        self._abort_flag = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.output_line.emit("[ABORT] 用户终止")


class XtbWorker(QThread):
    """后台跑 xTB 独立计算的线程。"""
    output_line = pyqtSignal(str)
    finished = pyqtSignal(int)

    def __init__(self, command, cwd):
        super().__init__()
        self.command = command
        self.cwd = cwd
        self.proc = None

    def run(self):
        try:
            env = os.environ.copy()
            self.proc = subprocess.Popen(
                self.command, cwd=self.cwd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except FileNotFoundError:
            self.output_line.emit("[ERROR] xtb.exe 未找到")
            self.finished.emit(1)
            return
        _BATCH = 20
        _buf = []
        for line in self.proc.stdout:
            _buf.append(line.rstrip("\n"))
            if len(_buf) >= _BATCH:
                self.output_line.emit("\n".join(_buf))
                _buf.clear()
        if _buf:
            self.output_line.emit("\n".join(_buf))
        self.proc.wait()
        self.finished.emit(self.proc.returncode)

    def abort(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.output_line.emit("[ABORT] 用户终止")


class OrcaWorker(QThread):
    """后台运行 ORCA 的线程。"""
    output_line = pyqtSignal(str)
    finished = pyqtSignal(int)

    def __init__(self, orca_exe, inp_path, cwd):
        super().__init__()
        self.orca_exe = orca_exe
        self.inp_path = inp_path
        self.cwd = cwd
        self.proc = None
        self._abort_flag = False

    def run(self):
        out_path = str(self.inp_path).replace('.inp', '.out')
        command = [self.orca_exe, self.inp_path.name]
        try:
            self.proc = subprocess.Popen(
                command, cwd=str(self.cwd),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except FileNotFoundError:
            self.output_line.emit("[ERROR] ORCA not found: " + self.orca_exe)
            self.finished.emit(1)
            return
        try:
            out_f = open(out_path, "w", encoding="utf-8", errors="replace")
        except OSError:
            self.output_line.emit(f"[ERROR] Cannot write to: {out_path}")
            self.proc.terminate()
            self.finished.emit(1)
            return
        _BATCH = 20
        _buf = []
        try:
            for line in iter(self.proc.stdout.readline, ""):
                if self._abort_flag:
                    self.proc.terminate()
                    out_f.write("[ABORTED by user]\n")
                    break
                out_f.write(line)
                out_f.flush()
                stripped = line.rstrip("\n")
                if stripped:
                    _buf.append(stripped)
                    if len(_buf) >= _BATCH:
                        self.output_line.emit("\n".join(_buf))
                        _buf.clear()
        except Exception as e:
            self.output_line.emit(f"[ERROR] Read error: {e}")
        finally:
            out_f.close()
            if _buf:
                self.output_line.emit("\n".join(_buf))
        try:
            remaining = self.proc.stdout.read()
            if remaining:
                with open(out_path, "a", encoding="utf-8", errors="replace") as f:
                    f.write(remaining)
                for line in remaining.splitlines():
                    if line.strip():
                        self.output_line.emit(line)
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            pass
        self.finished.emit(self.proc.returncode)

    def abort(self):
        self._abort_flag = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.output_line.emit("[ABORT] Job terminated by user")
