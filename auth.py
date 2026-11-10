"""用户认证：注册、登录、登出，密码加盐 SHA-256 哈希，当前会话缓存。"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

import db


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


@dataclass
class SessionUser:
    id: int
    username: str
    role: str  # admin / user

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


_current_user: SessionUser | None = None


def get_current_user() -> SessionUser | None:
    return _current_user


def require_login() -> SessionUser:
    """未登录时抛出异常，用于需要鉴权的操作。"""
    if _current_user is None:
        raise RuntimeError("请先登录")
    return _current_user


def register(username: str, password: str, role: str = "user") -> tuple[bool, str]:
    """注册新用户。返回 (成功, 消息)。"""
    username = username.strip()
    if not username:
        return False, "用户名不能为空"
    if len(username) < 2:
        return False, "用户名至少 2 个字符"
    if not password or len(password) < 4:
        return False, "密码至少 4 个字符"
    if db.get_user_by_username(username) is not None:
        return False, f"用户名 {username} 已存在"

    salt = secrets.token_hex(8)
    pw_hash = _hash_password(password, salt)
    try:
        db.add_user(username, pw_hash, salt, role)
        return True, "注册成功"
    except Exception as e:
        return False, f"注册失败：{e}"


def login(username: str, password: str) -> tuple[bool, str]:
    """登录。成功后设置当前会话用户。返回 (成功, 消息)。"""
    global _current_user
    username = username.strip()
    if not username or not password:
        return False, "请输入用户名和密码"
    row = db.get_user_by_username(username)
    if row is None:
        return False, "用户名或密码错误"
    if row["status"] != "active":
        return False, "该账号已被禁用，请联系管理员"
    pw_hash = _hash_password(password, row["salt"])
    if pw_hash != row["password_hash"]:
        return False, "用户名或密码错误"

    _current_user = SessionUser(id=row["id"], username=row["username"], role=row["role"])
    db.update_last_login(row["id"])
    return True, f"欢迎，{row['username']}（{'管理员' if row['role'] == 'admin' else '普通用户'}）"


def logout() -> None:
    global _current_user
    _current_user = None
