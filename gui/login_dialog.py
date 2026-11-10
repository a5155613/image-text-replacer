"""登录 / 注册对话框。

支持在登录与注册模式间切换。登录成功后返回 SessionUser；注册成功自动切回登录。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import auth


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登录 / 注册")
        self.setFixedSize(380, 320)
        self._mode = "login"  # login / register

        layout = QVBoxLayout(self)

        title = QLabel("批量图片文字替换工具")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:18px;font-weight:bold;color:#2c3e50;")
        layout.addWidget(title)

        sub = QLabel("请登录或注册账号")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color:#7f8c8d;")
        layout.addWidget(sub)
        layout.addSpacing(10)

        form = QFormLayout()
        self._username = QLineEdit()
        self._username.setPlaceholderText("用户名")
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setPlaceholderText("密码")
        self._password2 = QLineEdit()
        self._password2.setEchoMode(QLineEdit.Password)
        self._password2.setPlaceholderText("再次输入密码")
        form.addRow("用户名:", self._username)
        form.addRow("密码:", self._password)
        form.addRow("确认密码:", self._password2)
        layout.addLayout(form)

        # 切换登录/注册
        switch_row = QHBoxLayout()
        switch_row.addStretch()
        self._switch_btn = QPushButton("没有账号？点击注册")
        self._switch_btn.setFlat(True)
        self._switch_btn.setStyleSheet("color:#2980b9;")
        self._switch_btn.clicked.connect(self._toggle_mode)
        switch_row.addWidget(self._switch_btn)
        layout.addLayout(switch_row)

        # 操作按钮
        btn_row = QHBoxLayout()
        self._ok_btn = QPushButton("登录")
        self._cancel_btn = QPushButton("退出")
        self._ok_btn.clicked.connect(self._on_ok)
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._ok_btn)
        btn_row.addWidget(self._cancel_btn)
        layout.addLayout(btn_row)

        tip = QLabel("默认管理员：admin / admin123（登录后请修改密码）")
        tip.setStyleSheet("color:#95a5a6;font-size:11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self._apply_mode()

    def _toggle_mode(self):
        self._mode = "register" if self._mode == "login" else "login"
        self._apply_mode()

    def _apply_mode(self):
        if self._mode == "login":
            self.setWindowTitle("登录")
            self._ok_btn.setText("登录")
            self._switch_btn.setText("没有账号？点击注册")
            self._password2.setVisible(False)
        else:
            self.setWindowTitle("注册")
            self._ok_btn.setText("注册")
            self._switch_btn.setText("已有账号？点击登录")
            self._password2.setVisible(True)
        self._adjust_size()

    def _adjust_size(self):
        if self._mode == "login":
            self.setFixedSize(380, 300)
        else:
            self.setFixedSize(380, 340)

    def _on_ok(self):
        username = self._username.text().strip()
        password = self._password.text()
        if self._mode == "login":
            ok, msg = auth.login(username, password)
            if ok:
                QMessageBox.information(self, "成功", msg)
                self.accept()
            else:
                QMessageBox.warning(self, "登录失败", msg)
        else:
            password2 = self._password2.text()
            if password != password2:
                QMessageBox.warning(self, "注册失败", "两次输入的密码不一致")
                return
            ok, msg = auth.register(username, password)
            if ok:
                QMessageBox.information(self, "成功", msg)
                # 注册成功切回登录
                self._mode = "login"
                self._apply_mode()
                self._password.clear()
                self._password2.clear()
            else:
                QMessageBox.warning(self, "注册失败", msg)

    def get_user(self) -> auth.SessionUser | None:
        return auth.get_current_user()
