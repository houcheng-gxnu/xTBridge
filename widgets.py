"""GUI 组件：StatusButton 胶囊状态按钮、ScanChart 扫描能量折线图。"""

import math

from PyQt5.QtWidgets import QPushButton, QWidget
from PyQt5.QtCore import Qt, QTimer, QPointF, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
)


class StatusButton(QPushButton):
    """胶囊状态按钮，静态时显示状态文字，运行时带蓝色呼吸脉冲。"""

    def __init__(self, text="就绪", parent=None):
        super().__init__(text, parent)
        self._state_text = text
        self._state_color = QColor("#1565C0")
        self._offset = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._running = False
        self._breath_color = QColor("#1565C0")
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style(self._state_color.name())

    def _apply_style(self, bg):
        self.setStyleSheet(
            f"QPushButton {{"
            f"  background: {bg}; color: white; font-weight: bold; font-size: 11pt;"
            f"  padding: 8px 34px; border-radius: 20px; border: none;"
            f"}}"
        )

    def _tick(self):
        self._offset = (self._offset + 0.02) % 2.0
        self.update()

    def set_status(self, text, bg):
        self._state_text = text
        self._state_color = QColor(bg)
        self.stop()
        self.setText(text)
        self._apply_style(bg)

    def start(self, text="计算中"):
        if not self._running:
            self._running = True
            self._state_text = text
            self.setText(text)
            self._timer.start(16)

    def stop(self):
        if self._running:
            self._running = False
            self._timer.stop()
            self._apply_style(self._state_color.name())

    def paintEvent(self, event):
        if self._running:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            alpha = int(100 + 100 * (0.5 + 0.5 * math.sin(self._offset * math.pi)))
            c = QColor(self._breath_color)
            c.setAlpha(alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(0, 0, w, h, 20, 20)
            p.setPen(QColor("white"))
            f = p.font(); f.setBold(True); f.setPointSizeF(11)
            p.setFont(f)
            p.drawText(0, 0, w, h, Qt.AlignCenter, self._state_text)
            p.end()
        else:
            super().paintEvent(event)


class ScanChart(QWidget):
    """扫描能量 vs 步数折线图，点击数据点可选中。"""
    point_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self._selected = -1
        self._hovered = -1
        self.setMouseTracking(True)
        self.setMinimumHeight(180)

    def set_data(self, data: list):
        self._data = data
        self._selected = 0 if data else -1
        self._hovered = -1
        self.update()

    @property
    def selected_step(self) -> int:
        return self._selected

    def paintEvent(self, event):
        if not self._data:
            painter = QPainter(self)
            painter.drawText(self.rect(), Qt.AlignCenter, "(No scan data)")
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        m = 48

        energies = [d['energy_relative'] for d in self._data]
        steps = [d['step'] for d in self._data]
        y_min, y_max = min(energies) - 0.5, max(energies) + 0.5
        if y_max - y_min < 1.0:
            y_min -= 0.5; y_max += 0.5
        x_min, x_max = 0.5, len(self._data) + 0.5

        def tx(x): return m + (x - x_min) / (x_max - x_min) * (w - 2 * m)
        def ty(y): return h - m - (y - y_min) / (y_max - y_min) * (h - 2 * m)

        painter.fillRect(self.rect(), QColor("#ffffff"))
        pen = QPen(QColor("#e8e8e8"), 1, Qt.DotLine)
        painter.setPen(pen)
        for i in range(int(y_min), int(y_max) + 1):
            painter.drawLine(int(tx(x_min)), int(ty(i)), int(tx(x_max)), int(ty(i)))
        for i in range(1, len(self._data) + 1):
            painter.drawLine(int(tx(i)), int(ty(y_min)), int(tx(i)), int(ty(y_max)))

        ax_pen = QPen(QColor("#333333"), 1.5)
        painter.setPen(ax_pen)
        painter.drawLine(int(tx(x_min)), int(ty(y_min)), int(tx(x_max)), int(ty(y_min)))
        painter.drawLine(int(tx(x_min)), int(ty(y_min)), int(tx(x_min)), int(ty(y_max)))

        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        painter.setPen(QColor("#555555"))
        fm = QFontMetrics(font)
        for i in range(int(y_min), int(y_max) + 1):
            txt = f"{i:.0f}"
            painter.drawText(int(tx(x_min)) - fm.horizontalAdvance(txt) - 4,
                             int(ty(i)) + fm.height() // 4, txt)

        data_pen = QPen(QColor("#1E88E5"), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(data_pen)
        path = None
        from PyQt5.QtGui import QPainterPath
        for j, d in enumerate(self._data):
            px, py = tx(d['step']), ty(d['energy_relative'])
            if path is None:
                path = QPainterPath()
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        if path:
            painter.drawPath(path)

        for j, d in enumerate(self._data):
            px, py = tx(d['step']), ty(d['energy_relative'])
            if j == self._selected:
                painter.setBrush(QColor("#1565C0"))
                painter.setPen(QPen(QColor("#0D47A1"), 2))
                painter.drawEllipse(QPointF(px, py), 6, 6)
            elif j == self._hovered:
                painter.setBrush(QColor("#64B5F6"))
                painter.setPen(QPen(QColor("#1E88E5"), 1.5))
                painter.drawEllipse(QPointF(px, py), 5, 5)
            else:
                painter.setBrush(QColor("#90CAF9"))
                painter.setPen(QPen(QColor("#1E88E5"), 1))
                painter.drawEllipse(QPointF(px, py), 4, 4)

    def mouseMoveEvent(self, event):
        if not self._data:
            return
        w = self.width()
        m = 48
        x_min, x_max = 0.5, len(self._data) + 0.5
        x = event.x()
        best = -1
        best_dist = 1e9
        for j, d in enumerate(self._data):
            px = m + (d['step'] - x_min) / (x_max - x_min) * (w - 2 * m)
            dist = abs(x - px)
            if dist < 15 and dist < best_dist:
                best = j
                best_dist = dist
        if best != self._hovered:
            self._hovered = best
            self.update()

    def mousePressEvent(self, event):
        if self._hovered >= 0:
            self._selected = self._hovered
            self.point_clicked.emit(self._selected)
            self.update()
