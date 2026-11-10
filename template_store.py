"""头像模板持久化：保存/加载/管理可复用的头像位置模板。

模板存储位置与 db.py 一致（家目录 ~/.image-text-replacer/，不可写时回退到项目 .data/）。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from db import _DB_DIR  # 复用 db 的数据目录解析逻辑
from models import AvatarTemplate

_DEFAULT_DIR = _DB_DIR
_DEFAULT_FILE = _DEFAULT_DIR / "avatar_templates.json"


def _resolve_path(path: str | None = None) -> Path:
    if path:
        return Path(path).resolve()
    _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    return _DEFAULT_FILE


def list_templates(path: str | None = None) -> list[AvatarTemplate]:
    """读取全部头像模板，按创建时间倒序排列。"""
    fp = _resolve_path(path)
    if not fp.exists():
        return []
    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("templates", []) if isinstance(data, dict) else data
        templates = [AvatarTemplate.from_dict(d) for d in items if isinstance(d, dict)]
        templates.sort(key=lambda t: t.created_at or "", reverse=True)
        return templates
    except (json.JSONDecodeError, KeyError, ValueError):
        return []


def save_template(template: AvatarTemplate, path: str | None = None) -> None:
    """新增或更新模板（以 name 为主键覆盖）。"""
    fp = _resolve_path(path)
    templates = list_templates(path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not template.created_at:
        template.created_at = now
    # 同名覆盖
    existing_names = {t.name: i for i, t in enumerate(templates)}
    if template.name in existing_names:
        templates[existing_names[template.name]] = template
    else:
        templates.append(template)
    _write(fp, templates)


def delete_template(name: str, path: str | None = None) -> bool:
    """按名字删除模板，返回是否删除成功。"""
    fp = _resolve_path(path)
    templates = list_templates(path)
    new_list = [t for t in templates if t.name != name]
    if len(new_list) == len(templates):
        return False
    _write(fp, new_list)
    return True


def rename_template(old_name: str, new_name: str, path: str | None = None) -> bool:
    """重命名模板。"""
    fp = _resolve_path(path)
    templates = list_templates(path)
    for t in templates:
        if t.name == old_name:
            t.name = new_name
            _write(fp, templates)
            return True
    return False


def _write(fp: Path, templates: list[AvatarTemplate]) -> None:
    data = {
        "version": 1,
        "templates": [t.to_dict() for t in templates],
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def export_templates(templates: list[AvatarTemplate], path: str) -> None:
    """导出到指定文件（用于在不同电脑间迁移）。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "version": 1,
                "templates": [t.to_dict() for t in templates],
                "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def import_templates(path: str) -> list[AvatarTemplate]:
    """从指定文件导入模板，与现有模板合并（同名覆盖）。返回导入后的完整列表。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("templates", []) if isinstance(data, dict) else data
    imported = [AvatarTemplate.from_dict(d) for d in items if isinstance(d, dict)]
    # 合并
    existing = {t.name: t for t in list_templates()}
    for t in imported:
        if not t.created_at:
            t.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing[t.name] = t
    _write(_resolve_path(), list(existing.values()))
    return list_templates()


def templates_dir() -> Path:
    """返回模板存储目录（供 UI 显示）。"""
    return _DEFAULT_DIR
