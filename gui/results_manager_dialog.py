"""结果管理对话框：查看、删除当前用户的处理结果记录，可打开输出文件所在目录。"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtCore import QUrl
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


class ResultsManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("结果管理")
        self.resize(880, 500)
        self._user = auth.require_login()

        layout = QVBoxLayout(self)

        header = QLabel(f"结果管理（用户：{self._user.username}）")
        header.setStyleSheet("font-weight:bold;font-size:14px;")
        layout.addWidget(header)

        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            ["ID", "图片文件", "输出路径", "状态", "文字替换", "头像替换", "错误", "处理时间"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table)

        self._count_lbl = QLabel("")
        layout.addWidget(self._count_lbl)

        btn_row = QHBoxLayout()
        b_refresh = QPushButton("刷新")
        b_open = QPushButton("打开输出目录")
        b_del = QPushButton("删除选中")
        b_clear = QPushButton("清空全部")
        b_close = QPushButton("关闭")
        b_refresh.clicked.connect(self._refresh)
        b_open.clicked.connect(self._on_open_output)
        b_del.clicked.connect(self._on_delete)
        b_clear.clicked.connect(self._on_clear)
        b_close.clicked.connect(self.accept)
        btn_row.addWidget(b_refresh)
        btn_row.addWidget(b_open)
        btn_row.addWidget(b_del)
        btn_row.addStretch()
        btn_row.addWidget(b_clear)
        btn_row.addWidget(b_close)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self):
        rows = db.list_results(self._user.id)
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            success = bool(r["success"])
            self._table.setItem(i, 0, QTableWidgetItem(str(r["id"])))
            self._table.setItem(i, 1, QTableWidgetItem(r["image_filename"]))
            self._table.setItem(i, 2, QTableWidgetItem(r["output_path"] or ""))
            status_item = QTableWidgetItem("成功" if success else "失败")
            status_item.setForeground(QColor("#27ae60" if success else "#c0392b"))
            self._table.setItem(i, 3, status_item)
            self._table.setItem(i, 4, QTableWidgetItem(str(r["replaced_count"])))
            self._table.setItem(i, 5, QTableWidgetItem(str(r["avatar_count"])))
            self._table.setItem(i, 6, QTableWidgetItem(r["error"] or ""))
            self._table.setItem(i, 7, QTableWidgetItem(r["created_at"]))
        total = len(rows)
        ok = sum(1 for r in rows if r["success"])
        self._count_lbl.setText(f"共 {total} 条结果（成功 {ok}，失败 {total - ok}）")

    def _selected_ids(self) -> list[int]:
        ids = []
        for idx in self._table.selectionModel().selectedRows():
            ids.append(int(self._table.item(idx.row(), 0).text()))
        return ids

    def _on_open_output(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "请先选择一条结果")
            return
        out_path = self._table.item(rows[0].row(), 2).text()
        if not out_path or not os.path.exists(out_path):
            # 尝试打开所在目录
            folder = os.path.dirname(out_path) if out_path else ""
            if folder and os.path.isdir(folder):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            else:
                QMessageBox.warning(self, "提示", "输出文件不存在或已被移动")
            return
        folder = os.path.dirname(out_path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _on_delete(self):
        ids = self._selected_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先选择要删除的记录")
            return
        if QMessageBox.question(
            self, "确认", f"删除选中的 {len(ids)} 条结果记录？",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        for i in ids:
            db.delete_result(i)
        self._refresh()

    def _on_clear(self):
        rows = db.list_results(self._user.id)
        if not rows:
            QMessageBox.information(self, "提示", "暂无记录")
            return
        if QMessageBox.question(
            self, "确认", f"清空全部 {len(rows)} 条结果记录？",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        for r in rows:
            db.delete_result(r["id"])
        self._refresh()
