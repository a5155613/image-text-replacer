"""头像替换设置对话框：选新头像、形状、应用范围，含缩略图预览。

确认后通过 get_result() 返回 (avatar_path, shape, apply_all)。
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class AvatarDialog(QDialog):
    """框选/点选头像后弹出，确认替换参数。

    初始 rect/shape 提示在标题中显示，apply_all 决定全局/单图。
    """

    def __init__(self, rect: tuple[int, int, int, int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("替换头像")
        self.resize(440, 360)
        self._avatar_path = ""

        root = QVBoxLayout(self)

        info = QLabel(f"框选区域：x={rect[0]}, y={rect[1]}, 宽={rect[2]}, 高={rect[3]}")
        info.setStyleSheet("color:#2c7;font-weight:bold;")
        root.addWidget(info)

        # 头像路径选择
        form = QFormLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("点击右侧按钮选择新头像图片")
        self._path_edit.setReadOnly(True)
        b_browse = QPushButton("浏览...")
        b_browse.clicked.connect(self._on_browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(b_browse)
        path_wrap = QWidget()
        path_wrap.setLayout(path_row)
        form.addRow("新头像:", path_wrap)

        # 形状
        self._r_circle = QRadioButton("圆形（默认）")
        self._r_rounded = QRadioButton("圆角")
        self._r_square = QRadioButton("方形")
        self._r_circle.setChecked(True)
        shape_group = QButtonGroup(self)
        shape_group.addButton(self._r_circle)
        shape_group.addButton(self._r_rounded)
        shape_group.addButton(self._r_square)
        shape_row = QHBoxLayout()
        shape_row.addWidget(self._r_circle)
        shape_row.addWidget(self._r_rounded)
        shape_row.addWidget(self._r_square)
        shape_row.addStretch()
        shape_wrap = QWidget()
        shape_wrap.setLayout(shape_row)
        form.addRow("形状:", shape_wrap)

        # 应用范围
        self._r_current = QRadioButton("仅当前图")
        self._r_all = QRadioButton("所有图同位置")
        self._r_current.setChecked(True)
        scope_group = QButtonGroup(self)
        scope_group.addButton(self._r_current)
        scope_group.addButton(self._r_all)
        scope_row = QHBoxLayout()
        scope_row.addWidget(self._r_current)
        scope_row.addWidget(self._r_all)
        scope_row.addStretch()
        scope_wrap = QWidget()
        scope_wrap.setLayout(scope_row)
        form.addRow("应用范围:", scope_wrap)
        root.addLayout(form)

        # 缩略图预览
        self._preview = QLabel("（预览）")
        self._preview.setFixedHeight(120)
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setStyleSheet("background:#222;color:#888;border:1px dashed #555;")
        root.addWidget(self._preview)

        # 按钮
        btns = QHBoxLayout()
        btns.addStretch()
        b_ok = QPushButton("确定")
        b_cancel = QPushButton("取消")
        b_ok.clicked.connect(self._on_ok)
        b_cancel.clicked.connect(self.reject)
        btns.addWidget(b_ok)
        btns.addWidget(b_cancel)
        root.addLayout(btns)

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择新头像", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)"
        )
        if not path:
            return
        self._avatar_path = path
        self._path_edit.setText(path)
        pix = QPixmap(path)
        if not pix.isNull():
            self._preview.setPixmap(
                pix.scaled(
                    self._preview.width(),
                    self._preview.height(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

    def _on_ok(self):
        if not self._avatar_path or not os.path.exists(self._avatar_path):
            self._path_edit.setFocus()
            self._path_edit.setStyleSheet("border:1px solid #e74c3c;")
            return
        self.accept()

    def get_result(self) -> tuple[str, str, bool]:
        """返回 (avatar_path, shape, apply_all)。"""
        shape = "circle"
        if self._r_rounded.isChecked():
            shape = "rounded"
        elif self._r_square.isChecked():
            shape = "square"
        return self._avatar_path, shape, self._r_all.isChecked()
