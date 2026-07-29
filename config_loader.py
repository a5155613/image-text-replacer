"""Excel/CSV 配置读写与模板生成。

列：图片路径 | 匹配模式 | 原文字 | 新文字 | 字体 | 字号 | 颜色 | 加粗
后 4 列可选，留空 = 自动匹配。CSV 用 UTF-8-BOM 避免 Excel 中文乱码。
"""
from __future__ import annotations

import csv
import os

from models import ReplaceRule, TextStyle
from utils import hex_to_rgb, rgb_to_hex

HEADERS = ["图片路径", "匹配模式", "原文字", "新文字", "字体", "字号", "颜色", "加粗"]
SAMPLE_ROWS = [
    ["*", "contains", "你好", "Hello", "", "", "", ""],
    ["*", "contains", "世界", "World", "", "", "", ""],
    ["*", "regex", r"\d{4}-\d{2}-\d{2}", "2026-07-30", "", "", "", ""],
    ["banner.png", "exact", "限时特惠", "限时特惠", "msyhbd.ttc", "36", "#E60012", "是"],
    ["price.png", "exact", "￥99", "￥199", "", "28", "#FF0000", ""],
]

VALID_MODES = {"exact", "contains", "regex"}


def _parse_style(row) -> TextStyle:
    def cell(i: int) -> str:
        return str(row[i]).strip() if len(row) > i and row[i] is not None else ""

    font_raw = cell(4)
    size_raw = cell(5)
    color_raw = cell(6)
    bold_raw = cell(7)

    font_size: int | None = None
    if size_raw:
        try:
            font_size = int(float(size_raw))
        except ValueError:
            font_size = None

    font_color: tuple[int, int, int] | None = None
    if color_raw:
        try:
            font_color = hex_to_rgb(color_raw)
        except (ValueError, IndexError):
            font_color = None

    bold = bold_raw.lower() in ("是", "true", "1", "yes", "y")
    return TextStyle(
        font_color=font_color,
        font_size=font_size,
        font_path=font_raw or None,  # 保留原始名，运行时 resolve
        bold=bold,
    )


def load_rules(path: str) -> list[ReplaceRule]:
    ext = os.path.splitext(path)[1].lower()
    rows = _read_csv(path) if ext == ".csv" else _read_xlsx(path)
    rules: list[ReplaceRule] = []
    for row in rows:
        if not row or all((str(c).strip() == "") for c in row if c is not None):
            continue
        first = str(row[0]).strip() if row[0] is not None else ""
        if first == HEADERS[0]:
            continue  # 跳过表头
        if len(row) < 4:
            continue
        match_mode = str(row[1]).strip().lower() if row[1] else ""
        if match_mode not in VALID_MODES:
            match_mode = "contains"
        old_text = str(row[2]) if row[2] is not None else ""
        new_text = str(row[3]) if row[3] is not None else ""
        if not old_text.strip():
            continue
        rules.append(
            ReplaceRule(
                image_pattern=first,
                match_mode=match_mode,
                old_text=old_text,
                new_text=new_text,
                style=_parse_style(row),
            )
        )
    return rules


def save_rules(rules: list[ReplaceRule], path: str) -> None:
    ext = os.path.splitext(path)[1].lower()
    rows = [HEADERS] + [_rule_to_row(r) for r in rules]
    if ext == ".csv":
        _write_csv(path, rows)
    else:
        _write_xlsx(path, rows)


def generate_template(path: str = "config_template.xlsx") -> None:
    ext = os.path.splitext(path)[1].lower()
    rows = [HEADERS] + SAMPLE_ROWS
    if ext == ".csv":
        _write_csv(path, rows)
    else:
        _write_xlsx(path, rows)


def _rule_to_row(rule: ReplaceRule) -> list:
    return [
        rule.image_pattern,
        rule.match_mode,
        rule.old_text,
        rule.new_text,
        rule.style.font_path or "",
        rule.style.font_size if rule.style.font_size is not None else "",
        rgb_to_hex(rule.style.font_color) if rule.style.font_color else "",
        "是" if rule.style.bold else "",
    ]


def _read_xlsx(path: str) -> list[list]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = [list(row) for row in ws.iter_rows(values_only=True)]
    wb.close()
    return rows


def _read_csv(path: str) -> list[list]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.reader(f)]


def _write_xlsx(path: str, rows: list[list]) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "替换规则"
    for row in rows:
        ws.append(row)
    widths = [16, 12, 22, 22, 14, 8, 10, 8]
    for i, wd in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = wd
    wb.save(path)


def _write_csv(path: str, rows: list[list]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow(row)
