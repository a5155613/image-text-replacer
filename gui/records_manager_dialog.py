"""替换记录管理对话框：查看、删除当前用户的替换规则历史。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

import auth
import db

_MODE_LABELS = {"exact": "精确", "contains": "包含", "regex": "正则"}


class RecordsManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("替换记录管理")
        self.resize(860, 480)
        self._user = auth.require_login()

        layout = QVBoxLayout(self)

        header = QLabel(f"替换记录管理（用户：{self._user.username}）")
        header.setStyleSheet("font-weight:bold;font-size:14px;")
        layout.addWidget(header)

        self._table = QTableWidget()
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels(
            ["ID", "图片", "匹配", "原文字", "新文字", "字体", "字号", "颜色", "创建时间"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table)

        self._count_lbl = QLabel("")
        layout.addWidget(self._count_lbl)

        btn_row = QHBoxLayout()
        b_refresh = QPushButton("刷新")
        b_del = QPushButton("删除选中")
        b_clear = QPushButton("清空全部")
        b_close = QPushButton("关闭")
        b_refresh.clicked.connect(self._refresh)
        b_del.clicked.connect(self._on_delete)
        b_clear.clicked.connect(self._on_clear)
        b_close.clicked.connect(self.accept)
        btn_row.addWidget(b_refresh)
        btn_row.addWidget(b_del)
        btn_row.addStretch()
        btn_row.addWidget(b_clear)
        btn_row.addWidget(b_close)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self):
        rows = db.list_records(self._user.id)
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(str(r["id"])))
            self._table.setItem(i, 1, QTableWidgetItem(r["image_pattern"] or "*"))
            self._table.setItem(i, 2, QTableWidgetItem(_MODE_LABELS.get(r["match_mode"], r["match_mode"])))
            self._table.setItem(i, 3, QTableWidgetItem(r["old_text"]))
            self._table.setItem(i, 4, QTableWidgetItem(r["new_text"]))
            self._table.setItem(i, 5, QTableWidgetItem(r["font"] or ""))
            self._table.setItem(i, 6, QTableWidgetItem(str(r["font_size"]) if r["font_size"] else ""))
            self._table.setItem(i, 7, QTableWidgetItem(r["color"] or ""))
            self._table.setItem(i, 8, QTableWidgetItem(r["created_at"]))
        self._count_lbl.setText(f"共 {len(rows)} 条替换记录")

    def _selected_ids(self) -> list[int]:
        ids = []
        for idx in self._table.selectionModel().selectedRows():
            ids.append(int(self._table.item(idx.row(), 0).text()))
        return ids

    def _on_delete(self):
        ids = self._selected_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先选择要删除的记录")
            return
        if QMessageBox.question(
            self, "确认", f"删除选中的 {len(ids)} 条替换记录？",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        for i in ids:
            db.delete_record(i)
        self._refresh()

    def _on_clear(self):
        rows = db.list_records(self._user.id)
        if not rows:
            QMessageBox.information(self, "提示", "暂无记录")
            return
        if QMessageBox.question(
            self, "确认", f"清空全部 {len(rows)} 条替换记录？",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        for r in rows:
            db.delete_record(r["id"])
        self._refresh()
