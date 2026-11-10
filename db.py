"""SQLite 数据库层：持久化用户、图片、替换记录、处理结果。

数据存储位置（按优先级）：
1. 环境变量 IMAGE_REPLACER_DATA_DIR 指定的目录
2. 用户主目录 ~/.image-text-replacer/
3. 回退到项目目录下的 .data/（当家目录不可写时，如沙箱环境）
全部使用参数化查询，避免 SQL 注入。
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path


def _resolve_data_dir() -> Path:
    """解析数据存储目录，优先家目录，不可写则回退到项目本地 .data/。"""
    env_dir = os.environ.get("IMAGE_REPLACER_DATA_DIR")
    if env_dir:
        p = Path(env_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    home_dir = Path.home() / ".image-text-replacer"
    try:
        home_dir.mkdir(parents=True, exist_ok=True)
        # 测试可写性
        test_file = home_dir / ".write_test"
        test_file.write_text("")
        test_file.unlink()
        return home_dir
    except (OSError, PermissionError):
        # 家目录不可写（如沙箱），回退到项目目录
        local_dir = Path(__file__).resolve().parent / ".data"
        local_dir.mkdir(parents=True, exist_ok=True)
        return local_dir


_DB_DIR = _resolve_data_dir()
_DB_PATH = _DB_DIR / "app.db"

_conn: sqlite3.Connection | None = None


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_conn() -> sqlite3.Connection:
    """获取单例连接（行工厂设为 Row，方便按列名访问）。

    每次调用前用 SELECT 1 探活；若连接已失效（Qt 事件循环后偶发），自动重建。
    """
    global _conn
    if _conn is None:
        _conn = _open_conn()
        return _conn
    # 探活：若失效则重建
    try:
        _conn.execute("SELECT 1").close()
    except sqlite3.Error:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = _open_conn()
    return _conn


def _open_conn() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    import time
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            # timeout=10 允许等待锁释放（Windows 索引/杀毒可能短暂锁文件）
            conn = sqlite3.connect(
                str(_DB_PATH), timeout=10.0, check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            _create_tables(conn)
            _ensure_admin(conn)
            return conn
        except sqlite3.OperationalError as e:
            last_err = e
            # "unable to open database file" 通常是目录/文件被短暂占用，重试
            time.sleep(0.5)
    raise last_err  # type: ignore[misc]


def _create_tables(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',   -- admin / user
            status TEXT NOT NULL DEFAULT 'active',  -- active / disabled
            created_at TEXT NOT NULL,
            last_login TEXT
        );

        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_path TEXT NOT NULL,
            size INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS replacement_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            image_pattern TEXT NOT NULL,
            match_mode TEXT NOT NULL,
            old_text TEXT NOT NULL,
            new_text TEXT NOT NULL,
            font TEXT,
            font_size INTEGER,
            color TEXT,
            bold INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            image_id INTEGER,
            image_filename TEXT NOT NULL,
            output_path TEXT,
            success INTEGER NOT NULL DEFAULT 0,
            replaced_count INTEGER DEFAULT 0,
            avatar_count INTEGER DEFAULT 0,
            error TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_images_user ON images(user_id);
        CREATE INDEX IF NOT EXISTS idx_records_user ON replacement_records(user_id);
        CREATE INDEX IF NOT EXISTS idx_results_user ON results(user_id);
        """
    )
    conn.commit()


def _ensure_admin(conn: sqlite3.Connection) -> None:
    """首次启动创建默认管理员 admin/admin123（登录后建议修改）。"""
    cur = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role='admin'")
    if cur.fetchone()["c"] == 0:
        import hashlib
        salt = "admin_salt_default"
        pw_hash = hashlib.sha256(("admin123" + salt).encode()).hexdigest()
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, role, status, created_at) "
            "VALUES (?, ?, ?, 'admin', 'active', ?)",
            ("admin", pw_hash, salt, _now()),
        )
        conn.commit()


# ---------------- 用户 ----------------

def add_user(username: str, password_hash: str, salt: str, role: str = "user") -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, salt, role, status, created_at) "
        "VALUES (?, ?, ?, ?, 'active', ?)",
        (username, password_hash, salt, role, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_user_by_username(username: str) -> sqlite3.Row | None:
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM users WHERE username=?", (username,)
    ).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    conn = get_conn()
    return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def update_last_login(user_id: int) -> None:
    conn = get_conn()
    conn.execute("UPDATE users SET last_login=? WHERE id=?", (_now(), user_id))
    conn.commit()


def list_users() -> list[sqlite3.Row]:
    conn = get_conn()
    return conn.execute(
        "SELECT id, username, role, status, created_at, last_login FROM users ORDER BY id"
    ).fetchall()


def set_user_status(user_id: int, status: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE users SET status=? WHERE id=?", (status, user_id))
    conn.commit()


def set_user_role(user_id: int, role: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    conn.commit()


def reset_user_password(user_id: int, password_hash: str, salt: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE users SET password_hash=?, salt=? WHERE id=?",
        (password_hash, salt, user_id),
    )
    conn.commit()


def delete_user(user_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()


def count_users() -> int:
    conn = get_conn()
    return conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]


# ---------------- 图片 ----------------

def add_image(user_id: int, filename: str, original_path: str, size: int = 0) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO images (user_id, filename, original_path, size, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, filename, original_path, size, _now()),
    )
    conn.commit()
    return cur.lastrowid


def list_images(user_id: int) -> list[sqlite3.Row]:
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM images WHERE user_id=? ORDER BY id DESC", (user_id,)
    ).fetchall()


def delete_image(image_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM images WHERE id=?", (image_id,))
    conn.commit()


def count_images(user_id: int | None = None) -> int:
    conn = get_conn()
    if user_id is None:
        return conn.execute("SELECT COUNT(*) AS c FROM images").fetchone()["c"]
    return conn.execute(
        "SELECT COUNT(*) AS c FROM images WHERE user_id=?", (user_id,)
    ).fetchone()["c"]


# ---------------- 替换记录 ----------------

def add_record(
    user_id: int,
    image_pattern: str,
    match_mode: str,
    old_text: str,
    new_text: str,
    font: str | None = None,
    font_size: int | None = None,
    color: str | None = None,
    bold: bool = False,
) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO replacement_records "
        "(user_id, image_pattern, match_mode, old_text, new_text, font, font_size, color, bold, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id, image_pattern, match_mode, old_text, new_text,
            font, font_size, color, 1 if bold else 0, _now(),
        ),
    )
    conn.commit()
    return cur.lastrowid


def list_records(user_id: int) -> list[sqlite3.Row]:
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM replacement_records WHERE user_id=? ORDER BY id DESC",
        (user_id,),
    ).fetchall()


def delete_record(record_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM replacement_records WHERE id=?", (record_id,))
    conn.commit()


def count_records(user_id: int | None = None) -> int:
    conn = get_conn()
    if user_id is None:
        return conn.execute("SELECT COUNT(*) AS c FROM replacement_records").fetchone()["c"]
    return conn.execute(
        "SELECT COUNT(*) AS c FROM replacement_records WHERE user_id=?", (user_id,)
    ).fetchone()["c"]


# ---------------- 结果 ----------------

def add_result(
    user_id: int,
    image_id: int | None,
    image_filename: str,
    output_path: str | None,
    success: bool,
    replaced_count: int = 0,
    avatar_count: int = 0,
    error: str | None = None,
) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO results "
        "(user_id, image_id, image_filename, output_path, success, replaced_count, avatar_count, error, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id, image_id, image_filename, output_path,
            1 if success else 0, replaced_count, avatar_count, error, _now(),
        ),
    )
    conn.commit()
    return cur.lastrowid


def list_results(user_id: int) -> list[sqlite3.Row]:
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM results WHERE user_id=? ORDER BY id DESC", (user_id,)
    ).fetchall()


def delete_result(result_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM results WHERE id=?", (result_id,))
    conn.commit()


def count_results(user_id: int | None = None) -> int:
    conn = get_conn()
    if user_id is None:
        return conn.execute("SELECT COUNT(*) AS c FROM results").fetchone()["c"]
    return conn.execute(
        "SELECT COUNT(*) AS c FROM results WHERE user_id=?", (user_id,)
    ).fetchone()["c"]


def count_success_results(user_id: int | None = None) -> int:
    conn = get_conn()
    if user_id is None:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM results WHERE success=1"
        ).fetchone()["c"]
    return conn.execute(
        "SELECT COUNT(*) AS c FROM results WHERE user_id=? AND success=1",
        (user_id,),
    ).fetchone()["c"]


def close() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
