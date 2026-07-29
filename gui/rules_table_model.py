"""替换规则表数据模型：QAbstractTableModel，8 列可编辑。"""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from models import ReplaceRule, TextStyle
from utils import hex_to_rgb, rgb_to_hex
import config_loader


class RulesTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules: list[ReplaceRule] = []
        self._headers = config_loader.HEADERS

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rules)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._headers[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self._rules[index.row()]
        col = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            if col == 0:
                return r.image_pattern
            if col == 1:
                return r.match_mode
            if col == 2:
                return r.old_text
            if col == 3:
                return r.new_text
            if col == 4:
                return r.style.font_path or ""
            if col == 5:
                return str(r.style.font_size) if r.style.font_size is not None else ""
            if col == 6:
                return rgb_to_hex(r.style.font_color) if r.style.font_color else ""
            if col == 7:
                return "是" if r.style.bold else ""
        return None

    def setData(self, index, value, role=Qt.EditRole) -> bool:
        if not index.isValid() or role != Qt.EditRole:
            return False
        r = self._rules[index.row()]
        col = index.column()
        v = value.strip() if isinstance(value, str) else value
        try:
            if col == 0:
                r.image_pattern = v
            elif col == 1:
                r.match_mode = v if v in ("exact", "contains", "regex") else "contains"
            elif col == 2:
                r.old_text = v
            elif col == 3:
                r.new_text = v
            elif col == 4:
                r.style.font_path = v or None
            elif col == 5:
                r.style.font_size = int(v) if v else None
            elif col == 6:
                r.style.font_color = hex_to_rgb(v) if v else None
            elif col == 7:
                if isinstance(v, str):
                    r.style.bold = v.lower() in ("是", "true", "1", "yes", "y")
                else:
                    r.style.bold = bool(v)
        except (ValueError, IndexError):
            return False
        self.dataChanged.emit(index, index)
        return True

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def set_rules(self, rules: list[ReplaceRule]):
        self.beginResetModel()
        self._rules = list(rules)
        self.endResetModel()

    def get_rules(self) -> list[ReplaceRule]:
        # 过滤掉原文字为空的无效规则
        return [r for r in self._rules if r.old_text.strip()]

    def add_rule(self, rule: ReplaceRule | None = None):
        rule = rule or ReplaceRule(
            image_pattern="*",
            match_mode="contains",
            old_text="",
            new_text="",
            style=TextStyle(),
        )
        self.beginInsertRows(QModelIndex(), len(self._rules), len(self._rules))
        self._rules.append(rule)
        self.endInsertRows()

    def remove_rule(self, row: int):
        if 0 <= row < len(self._rules):
            self.beginRemoveRows(QModelIndex(), row, row)
            self._rules.pop(row)
            self.endRemoveRows()
