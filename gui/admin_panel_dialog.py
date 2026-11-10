"""管理员面板：系统统计 + 用户管理（启用/禁用、设为管理员、重置密码、删除）。

仅管理员可访问。包含修改自身密码功能。
"""
from __future__ import annotations

import hashlib
import secrets

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

import auth
import db


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


class AdminPanelDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("管理员面板")
        self.resize(860, 560)
        self._user = auth.require_login()
        if not self._user.is_admin:
            raise RuntimeError("仅管理员可访问")

        layout = QVBoxLayout(self)

        # 统计
        stats_box = QGroupBox("系统统计")
        stats_form = QHBoxLayout(stats_box)
        self._lbl_users = QLabel()
        self._lbl_images = QLabel()
        self._lbl_records = QLabel()
        self._lbl_results = QLabel()
        for lbl in (self._lbl_users, self._lbl_images, self._lbl_records, self._lbl_results):
            lbl.setStyleSheet("font-size:13px;padding:4px 12px;")
            stats_form.addWidget(lbl)
        layout.addWidget(stats_box)

        # 用户表
        layout.addWidget(QLabel("用户管理："))
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["ID", "用户名", "角色", "状态", "创建时间", "最后登录"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table)

        # 操作按钮
        btn_row = QHBoxLayout()
        b_toggle = QPushButton("启用/禁用")
        b_role = QPushButton("切换角色")
        b_reset = QPushButton("重置密码")
        b_del = QPushButton("删除用户")
        b_refresh = QPushButton("刷新")
        b_pwd = QPushButton("修改自己的密码")
        b_close = QPushButton("关闭")
        b_toggle.clicked.connect(self._on_toggle_status)
        b_role.clicked.connect(self._on_toggle_role)
        b_reset.clicked.connect(self._on_reset_password)
        b_del.clicked.connect(self._on_delete_user)
        b_refresh.clicked.connect(self._refresh)
        b_pwd.clicked.connect(self._on_change_own_password)
        b_close.clicked.connect(self.accept)
        btn_row.addWidget(b_toggle)
        btn_row.addWidget(b_role)
        btn_row.addWidget(b_reset)
        btn_row.addWidget(b_del)
        btn_row.addWidget(b_refresh)
        btn_row.addStretch()
        btn_row.addWidget(b_pwd)
        btn_row.addWidget(b_close)
        layout.addLayout(btn_row)

        self._refresh()

    # ---------- 统计 / 刷新 ----------

    def _refresh(self):
        # 统计
        total_users = db.count_users()
        total_images = db.count_images()
        total_records = db.count_records()
        total_results = db.count_results()
        success = db.count_success_results()
        rate = (success / total_results * 100) if total_results else 0
        self._lbl_users.setText(f"👥 用户：{total_users}")
        self._lbl_images.setText(f"🖼️ 图片：{total_images}")
        self._lbl_records.setText(f"📝 替换记录：{total_records}")
        self._lbl_results.setText(f"✅ 结果：{total_results}（成功率 {rate:.1f}%）")

        # 用户表
        rows = db.list_users()
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(str(r["id"])))
            self._table.setItem(i, 1, QTableWidgetItem(r["username"]))
            role_item = QTableWidgetItem("管理员" if r["role"] == "admin" else "普通用户")
            if r["role"] == "admin":
                role_item.setForeground(QColor("#8e44ad"))
            self._table.setItem(i, 2, role_item)
            status = r["status"]
            status_item = QTableWidgetItem("启用" if status == "active" else "禁用")
            status_item.setForeground(QColor("#27ae60" if status == "active" else "#c0392b"))
            self._table.setItem(i, 3, status_item)
            self._table.setItem(i, 4, QTableWidgetItem(r["created_at"]))
            self._table.setItem(i, 5, QTableWidgetItem(r["last_login"] or ""))

    def _selected_user_id(self) -> int | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "请先选择一个用户")
            return None
        return int(self._table.item(rows[0].row(), 0).text())

    # ---------- 用户操作 ----------

    def _on_toggle_status(self):
        uid = self._selected_user_id()
        if uid is None:
            return
        if uid == self._user.id:
            QMessageBox.warning(self, "提示", "不能禁用自己")
            return
        row = db.get_user_by_id(uid)
        new_status = "disabled" if row["status"] == "active" else "active"
        db.set_user_status(uid, new_status)
        self._refresh()

    def _on_toggle_role(self):
        uid = self._selected_user_id()
        if uid is None:
            return
        row = db.get_user_by_id(uid)
        new_role = "user" if row["role"] == "admin" else "admin"
        db.set_user_role(uid, new_role)
        self._refresh()

    def _on_reset_password(self):
        uid = self._selected_user_id()
        if uid is None:
            return
        new_pwd, ok = QInputDialog.getText(
            self, "重置密码", "请输入新密码（至少 4 位）：", QLineEdit.Password
        )
        if not ok or not new_pwd:
            return
        if len(new_pwd) < 4:
            QMessageBox.warning(self, "提示", "密码至少 4 位")
            return
        salt = secrets.token_hex(8)
        pw_hash = _hash_password(new_pwd, salt)
        db.reset_user_password(uid, pw_hash, salt)
        QMessageBox.information(self, "成功", "密码已重置")

    def _on_delete_user(self):
        uid = self._selected_user_id()
        if uid is None:
            return
        if uid == self._user.id:
            QMessageBox.warning(self, "提示", "不能删除自己")
            return
        row = db.get_user_by_id(uid)
        if QMessageBox.question(
            self, "确认", f"删除用户 {row['username']}？其所有数据将被一并删除",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        db.delete_user(uid)
        self._refresh()

    def _on_change_own_password(self):
        old_pwd, ok = QInputDialog.getText(
            self, "修改密码", "当前密码：", QLineEdit.Password
        )
        if not ok:
            return
        row = db.get_user_by_id(self._user.id)
        if _hash_password(old_pwd, row["salt"]) != row["password_hash"]:
            QMessageBox.warning(self, "错误", "当前密码不正确")
            return
        new_pwd, ok = QInputDialog.getText(
            self, "修改密码", "新密码（至少 4 位）：", QLineEdit.Password
        )
        if not ok or len(new_pwd) < 4:
            QMessageBox.warning(self, "提示", "密码至少 4 位")
            return
        salt = secrets.token_hex(8)
        pw_hash = _hash_password(new_pwd, salt)
        db.reset_user_password(self._user.id, pw_hash, salt)
        QMessageBox.information(self, "成功", "密码修改成功，请重新登录")
