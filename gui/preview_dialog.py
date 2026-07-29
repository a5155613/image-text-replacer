"""前后对比预览对话框：左原图、右结果，同步缩放。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
)


class PreviewDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("前后对比预览")
        self.resize(1280, 760)
        self._orig_img: QImage | None = None
        self._result_img: QImage | None = None

        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal, self)

        self._left_scroll = self._make_panel("原图")
        self._right_scroll = self._make_panel("替换结果")
        self._left_label: QLabel = self._left_scroll.widget()
        self._right_label: QLabel = self._right_scroll.widget()

        splitter.addWidget(self._left_scroll)
        splitter.addWidget(self._right_scroll)
        splitter.setSizes([640, 640])
        layout.addWidget(splitter)

    def _make_panel(self, title: str) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWindowTitle(title)
        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumSize(400, 400)
        label.setStyleSheet("background:#282828;color:#bbb;font-size:14px;")
        scroll.setWidget(label)
        return scroll

    def set_images(self, original: QImage, result: QImage):
        self._orig_img = original
        self._result_img = result
        self._render()

    def _render(self):
        if self._orig_img is not None:
            self._left_label.setPixmap(
                QPixmap.fromImage(self._orig_img).scaled(
                    self._left_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        if self._result_img is not None:
            self._right_label.setPixmap(
                QPixmap.fromImage(self._result_img).scaled(
                    self._right_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()
