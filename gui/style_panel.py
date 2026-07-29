"""样式调整面板：显示选中 bbox 信息 + 快捷添加替换规则。

当 canvas 选中某个 OCR 文字框时，此处显示其 OCR 文本、置信度、自动检测的
颜色/字号；用户可填新文字并设置样式覆盖，点击"添加替换规则"即写入规则表。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models import ReplaceRule, TextBox, TextStyle
from utils import resolve_font

# 字体下拉候选：(显示名, font_path 输入值)
_FONT_CHOICES = [
    ("自动", ""),
    ("微软雅黑 (msyh.ttc)", "msyh.ttc"),
    ("微软雅黑粗 (msyhbd.ttc)", "msyhbd.ttc"),
    ("宋体 (simsun.ttc)", "simsun.ttc"),
    ("黑体 (simhei.ttf)", "simhei.ttf"),
    ("Arial (arial.ttf)", "arial.ttf"),
    ("Arial 粗 (arialbd.ttf)", "arialbd.ttf"),
]


class StylePanel(QWidget):
    apply_rule = Signal(ReplaceRule)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # 信息展示
        info_box = QGroupBox("选中文字框信息")
        info_layout = QFormLayout(info_box)
        self._lbl_text = QLabel("（未选中）")
        self._lbl_text.setWordWrap(True)
        self._lbl_text.setStyleSheet("color:#222;font-weight:bold;")
        self._lbl_score = QLabel("-")
        self._lbl_pos = QLabel("-")
        self._lbl_color = QLabel("自动")
        self._lbl_color.setMinimumSize(60, 20)
        self._lbl_size = QLabel("-")
        info_layout.addRow("OCR 文本:", self._lbl_text)
        info_layout.addRow("置信度:", self._lbl_score)
        info_layout.addRow("位置:", self._lbl_pos)
        info_layout.addRow("检测颜色:", self._lbl_color)
        info_layout.addRow("估算字号:", self._lbl_size)
        layout.addWidget(info_box)

        # 替换设置
        edit_box = QGroupBox("快捷添加替换规则")
        edit_layout = QFormLayout(edit_box)
        self._edit_new = QLineEdit()
        self._edit_new.setPlaceholderText("输入替换后的新文字")
        edit_layout.addRow("新文字:", self._edit_new)

        self._combo_font = QComboBox()
        for name, _ in _FONT_CHOICES:
            self._combo_font.addItem(name)
        edit_layout.addRow("字体:", self._combo_font)

        self._spin_size = QSpinBox()
        self._spin_size.setRange(0, 300)
        self._spin_size.setValue(0)
        self._spin_size.setSpecialValueText("自动")
        edit_layout.addRow("字号:", self._spin_size)

        color_row = QHBoxLayout()
        self._chk_auto_color = QCheckBox("自动")
        self._chk_auto_color.setChecked(True)
        self._btn_color = QPushButton("选择颜色")
        self._btn_color.setEnabled(False)
        self._cur_color: tuple[int, int, int] = (0, 0, 0)
        color_row.addWidget(self._chk_auto_color)
        color_row.addWidget(self._btn_color)
        color_row.addStretch()
        edit_layout.addRow("颜色:", color_row)

        self._chk_bold = QCheckBox("加粗")
        edit_layout.addRow("加粗:", self._chk_bold)

        self._btn_add = QPushButton("添加替换规则")
        self._btn_add.setStyleSheet("padding:6px;font-weight:bold;")
        edit_layout.addRow(self._btn_add)
        layout.addWidget(edit_box)

        layout.addStretch()

        # 信号
        self._chk_auto_color.toggled.connect(self._on_auto_color_toggled)
        self._btn_color.clicked.connect(self._on_pick_color)
        self._btn_add.clicked.connect(self._on_apply)

        self._current_tb: TextBox | None = None
        self._current_pattern = "*"

    def set_pattern(self, pattern: str):
        """设置当前图片对应的 image_pattern（单图规则用文件名）。"""
        self._current_pattern = pattern

    def show_textbox(self, tb: TextBox, detected: TextStyle):
        self._current_tb = tb
        x, y, w, h = tb.bbox_rect
        self._lbl_text.setText(tb.text)
        self._lbl_score.setText(f"{tb.score:.1%}")
        self._lbl_pos.setText(f"({x},{y}) {w}×{h}")
        if detected.font_color:
            r, g, b = detected.font_color
            self._lbl_color.setText(f"#{r:02X}{g:02X}{b:02X}")
            self._lbl_color.setStyleSheet(
                f"background:{self._color_qss(detected.font_color)};color:#fff;padding:2px;"
            )
        else:
            self._lbl_color.setText("自动")
        self._lbl_size.setText(str(detected.font_size or "-"))

    def clear_info(self):
        self._current_tb = None
        self._lbl_text.setText("（未选中）")
        self._lbl_score.setText("-")
        self._lbl_pos.setText("-")
        self._lbl_color.setText("自动")
        self._lbl_color.setStyleSheet("")
        self._lbl_size.setText("-")

    def _on_auto_color_toggled(self, checked: bool):
        self._btn_color.setEnabled(not checked)

    def _on_pick_color(self):
        color = QColorDialog.getColor(QColor(*self._cur_color), self, "选择文字颜色")
        if color.isValid():
            self._cur_color = (color.red(), color.green(), color.blue())
            self._btn_color.setStyleSheet(
                f"background:{self._color_qss(self._cur_color)};"
            )

    def _on_apply(self):
        if self._current_tb is None or not self._current_tb.text.strip():
            return
        new_text = self._edit_new.text()
        if not new_text:
            return
        # 构造 style
        font_val = _FONT_CHOICES[self._combo_font.currentIndex()][1]
        size = self._spin_size.value() or None
        if self._chk_auto_color.isChecked():
            color = None
        else:
            color = self._cur_color
        bold = self._chk_bold.isChecked()
        style = TextStyle(
            font_color=color,
            font_size=size,
            font_path=font_val or None,
            bold=bold,
        )
        rule = ReplaceRule(
            image_pattern=self._current_pattern,
            match_mode="contains",
            old_text=self._current_tb.text,
            new_text=new_text,
            style=style,
        )
        self.apply_rule.emit(rule)
        self._edit_new.clear()

    @staticmethod
    def _color_qss(rgb: tuple) -> str:
        return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
