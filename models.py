"""跨模块数据契约。先于其他模块定型。"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class TextBox:
    """OCR 识别到的一个文字块。"""

    box: np.ndarray  # shape (4, 2)，四点多边形坐标
    text: str
    score: float

    @property
    def bbox_rect(self) -> tuple[int, int, int, int]:
        """外接矩形 (x, y, w, h)。"""
        xs = self.box[:, 0]
        ys = self.box[:, 1]
        x, y = int(xs.min()), int(ys.min())
        return x, y, int(xs.max() - xs.min()), int(ys.max() - ys.min())

    @property
    def polygon(self) -> list[tuple[int, int]]:
        return [(int(p[0]), int(p[1])) for p in self.box]


@dataclass
class TextStyle:
    """文字样式。任一字段为 None 表示自动检测/匹配。颜色统一用 RGB。"""

    font_color: tuple[int, int, int] | None = None
    font_size: int | None = None
    font_path: str | None = None
    bold: bool = False

    def is_full_auto(self) -> bool:
        return (
            self.font_color is None
            and self.font_size is None
            and self.font_path is None
            and not self.bold
        )


@dataclass
class ReplaceRule:
    """一条替换规则。"""

    image_pattern: str  # "*" 或空 = 全局；文件名 = 单图（basename 比较）
    match_mode: str  # "exact" | "contains" | "regex"
    old_text: str
    new_text: str
    style: TextStyle = field(default_factory=TextStyle)

    def is_global(self) -> bool:
        return not self.image_pattern or self.image_pattern.strip() == "*"


@dataclass
class AvatarReplace:
    """一条头像替换操作。与 ReplaceRule 同样按 image_pattern 区分全局/单图。"""

    image_pattern: str  # "*" 或空 = 全局；文件名 = 单图（basename 比较）
    rect: tuple[int, int, int, int]  # x, y, w, h（原图像素坐标）
    avatar_path: str
    shape: str = "circle"  # circle / rounded / square

    def is_global(self) -> bool:
        return not self.image_pattern or self.image_pattern.strip() == "*"

    @staticmethod
    def applies(pattern: str, fname_lower: str) -> bool:
        """判断该 pattern 是否对某文件生效（与 ImageEditor._rule_applies 一致语义）。"""
        if not pattern or pattern.strip() == "*":
            return True
        import os as _os

        return _os.path.basename(pattern).lower() == fname_lower


@dataclass
class TaskResult:
    """单张图片的处理结果。"""

    image_path: str
    output_path: str | None
    success: bool
    replaced_count: int
    avatar_count: int = 0  # 本次头像替换次数
    error: str | None = None
