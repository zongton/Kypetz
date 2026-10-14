# -*- coding: utf-8 -*-
"""
Kypetz 现代 Apple 风格基础 UI 控件集
包含纯内联 SVG 矢量图标库、胶囊拖拽手柄、浮动磨砂控制栏与分段按钮 (SegmentedButton)。
"""

import re
from PySide6.QtCore import Qt, QPoint, Signal, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPainterPath, QColor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QFrame
from PySide6.QtSvg import QSvgRenderer

# ---------------- 内联矢量 SVG 图标库与渲染助手 ----------------
SVGS = {
    "cat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#68D391" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 5c-3.8 0-6.5 2.8-6.5 6.5v5.5a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-5.5c0-3.7-2.7-6.5-6.5-6.5z"/>
      <path d="M5.5 8.5L3 3l5.5 2.5"/>
      <path d="M18.5 8.5L21 3l-5.5 2.5"/>
      <circle cx="9" cy="12.5" r="1.2" fill="#68D391"/>
      <circle cx="15" cy="12.5" r="1.2" fill="#68D391"/>
      <path d="M10.5 15.5c.8.5 2.2.5 3 0"/>
    </svg>""",
    "settings": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>""",
    "chat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>""",
    "power": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FF453A" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M18.36 6.64a9 9 0 1 1-12.73 0"/>
      <line x1="12" y1="2" x2="12" y2="12"/>
    </svg>""",
    "search": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="11" cy="11" r="8"/>
      <line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>""",
    "rocket": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/>
      <path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/>
      <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/>
      <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>
    </svg>""",
    "user": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#64D2FF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
      <circle cx="12" cy="7" r="4"/>
    </svg>""",
    "cpu": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#BF5AF2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2"/>
      <rect x="9" y="9" width="6" height="6"/>
      <path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>
    </svg>""",
    "sound": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FFD60A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
    </svg>""",
    "skin": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FF375F" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M20.38 3.46L16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"/>
    </svg>""",
    "folder": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
    </svg>""",
    "refresh": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3L21.5 8M22 12.5a10 10 0 0 1-18.8 4.2L2.5 16"/>
    </svg>""",
}

def make_svg_icon(svg_str, size=18, stroke_color=None):
    if stroke_color:
        svg_str = re.sub(r'stroke="[^"]*"', f'stroke="{stroke_color}"', svg_str)
    renderer = QSvgRenderer(QByteArray(svg_str.encode('utf-8')))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = max(1, int(size * 0.08))
    target_rect = pm.rect().adjusted(margin, margin, -margin, -margin)
    renderer.render(painter, target_rect)
    painter.end()
    return QIcon(pm)

def make_svg_label(svg_str, size=24, stroke_color=None):
    if stroke_color:
        svg_str = re.sub(r'stroke="[^"]*"', f'stroke="{stroke_color}"', svg_str)
    renderer = QSvgRenderer(QByteArray(svg_str.encode('utf-8')))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = max(1, int(size * 0.08))
    target_rect = pm.rect().adjusted(margin, margin, -margin, -margin)
    renderer.render(painter, target_rect)
    painter.end()
    lbl = QLabel()
    lbl.setPixmap(pm)
    lbl.setFixedSize(size, size)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl



# ---------------- Apple 风格交互控件 ----------------
class AppleDragHandle(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self._start_pos = None
        self._start_mouse = None
        self._dragging = False
        self.setFixedHeight(18)
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = 36, 4
        x = (self.width() - w) // 2
        y = (self.height() - h) // 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 60))
        p.drawRoundedRect(x, y, w, h, 2, 2)
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._start_pos = self.window().pos()
            self._start_mouse = e.globalPosition().toPoint()
            self._dragging = False
    def mouseMoveEvent(self, e):
        if self._start_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            delta = e.globalPosition().toPoint() - self._start_mouse
            if not self._dragging and (delta.x()**2 + delta.y()**2) > 36:
                self._dragging = True
            if self._dragging:
                self.window().move(self._start_pos + delta)
    def mouseReleaseEvent(self, e):
        self._start_pos = None
        self._start_mouse = None
        self._dragging = False

# ---------------- Apple 风格磨砂控制栏 ----------------
class AppleControlBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedHeight(44)
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(10, 2, -10, -4)
        p.setPen(QColor(255, 255, 255, 30))
        p.setBrush(QColor(28, 28, 34, 185))
        p.drawRoundedRect(rect, 19, 19)

# ---------------- 现代极简流体分段胶囊按钮 ----------------
class SegmentedButton(QWidget):
    changed = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(3, 3, 3, 3)
        self.layout.setSpacing(4)
        self.buttons = []
        self.current_index = 0

        self.setStyleSheet("""
            QWidget {
                background: rgba(0, 0, 0, 0.45);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 13px;
            }
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                color: rgba(255, 255, 255, 0.55);
                font-size: 12px;
                font-weight: 500;
                padding: 6px 14px;
            }
            QPushButton:hover {
                color: #ffffff;
            }
            QPushButton[selected="true"] {
                background: rgba(255, 255, 255, 0.14);
                color: #ffffff;
                font-weight: 600;
            }
        """)

        for i, text in enumerate(labels):
            btn = QPushButton(text, self)
            btn.setProperty("selected", i == 0)
            btn.clicked.connect(lambda _, idx=i: self.set_index(idx))
            self.buttons.append(btn)
            self.layout.addWidget(btn)

    def set_index(self, idx):
        if idx == self.current_index:
            return
        self.current_index = idx
        for i, b in enumerate(self.buttons):
            b.setProperty("selected", i == idx)
            b.style().unpolish(b)
            b.style().polish(b)
        self.changed.emit(idx)


