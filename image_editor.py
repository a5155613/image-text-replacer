"""核心编辑：擦除原文字(cv2.inpaint) + 按样式重绘新文字(PIL)。

流程：匹配规则 → 在【原图】上检测样式 → 擦除文字 → 在擦除后图上重绘新文字。
颜色检测必须在擦除之前，否则文字已被抹掉无法取色。
"""
from __future__ import annotations

import os
import re

import cv2
import numpy as np

from models import ReplaceRule, TextBox, TextStyle
from style_detector import StyleDetector
from utils import basename_lower


class ImageEditor:
    def __init__(self, detector: StyleDetector | None = None):
        self.detector = detector or StyleDetector()

    def replace(
        self,
        image_bgr: np.ndarray,
        boxes: list[TextBox],
        rules: list[ReplaceRule],
        image_filename: str = "",
        inpaint_algo: str = "TELEA",
        dilate_iter: int = 2,
        erase_only: bool = False,
    ) -> tuple[np.ndarray, int]:
        """对单张图执行替换。返回 (处理后图像, 替换处数)。"""
        matched = self._match(boxes, rules, image_filename)
        if not matched:
            return image_bgr, 0

        # 1. 在原图上检测样式（文字还在，可取色）
        #    关键：传入 new_text 以便字体选择基于实际要绘制的文字（支持英文→中文场景）
        styled: list[tuple[TextBox, ReplaceRule, str, TextStyle]] = []
        for tb, rule, new_text in matched:
            style = self.detector.detect(image_bgr, tb, rule.style, new_text=new_text)
            styled.append((tb, rule, new_text, style))

        # 2. 擦除所有命中框
        boxes_to_erase = [t[0] for t in styled]
        erased = self._erase_text(image_bgr, boxes_to_erase, inpaint_algo, dilate_iter)

        if erase_only:
            return erased, len(boxes_to_erase)

        # 3. 重绘新文字
        drawn = self._render_text(erased, styled)
        return drawn, len(styled)

    # ---------- 规则匹配 ----------

    def _match(
        self, boxes: list[TextBox], rules: list[ReplaceRule], image_filename: str
    ) -> list[tuple[TextBox, ReplaceRule, str]]:
        """对每个 OCR 框应用所有命中规则：exact 取最高优先级整框替换，
        contains/regex 依次叠加。样式取优先级最高的命中规则。"""
        fname = basename_lower(image_filename) if image_filename else ""
        matched = []
        for tb in boxes:
            hits = self._all_hits(tb.text, rules, fname)
            if not hits:
                continue
            new_text = self._apply_rules(tb.text, hits)
            if new_text != tb.text:
                matched.append((tb, hits[0], new_text))
        return matched

    def _all_hits(
        self, text: str, rules: list[ReplaceRule], fname: str
    ) -> list[ReplaceRule]:
        """返回所有命中规则，按 (单图>全局, 精确>包含>正则, 行号) 升序排序。"""
        if not text:
            return []
        candidates = []  # (scope, mode_rank, idx, rule)
        for i, rule in enumerate(rules):
            if not self._rule_applies(rule, fname):
                continue
            if not self._rule_matches(text, rule):
                continue
            scope = 2 if not rule.is_global() else 1
            mode_rank = {"exact": 3, "contains": 2, "regex": 1}.get(
                rule.match_mode, 2
            )
            candidates.append((scope, mode_rank, i, rule))
        candidates.sort(key=lambda c: (c[0], c[1], c[2]))
        return [c[3] for c in candidates]

    def _apply_rules(self, text: str, hits: list[ReplaceRule]) -> str:
        """exact 命中则取最高优先级整框替换；否则 contains/regex 依次叠加。"""
        for rule in hits:
            if rule.match_mode == "exact":
                return rule.new_text
        result = text
        for rule in hits:
            result = self._apply_replace(result, rule)
        return result

    @staticmethod
    def _rule_applies(rule: ReplaceRule, fname: str) -> bool:
        if rule.is_global():
            return True
        return basename_lower(rule.image_pattern) == fname

    @staticmethod
    def _rule_matches(text: str, rule: ReplaceRule) -> bool:
        mode = rule.match_mode
        if mode == "exact":
            return text.strip() == rule.old_text
        if mode == "regex":
            try:
                return re.search(rule.old_text, text) is not None
            except re.error:
                return False
        # contains（默认）
        return rule.old_text in text

    @staticmethod
    def _apply_replace(text: str, rule: ReplaceRule) -> str:
        mode = rule.match_mode
        if mode == "exact":
            return rule.new_text
        if mode == "regex":
            try:
                return re.sub(rule.old_text, rule.new_text, text)
            except re.error:
                return text
        return text.replace(rule.old_text, rule.new_text)

    # ---------- 擦除 ----------

    def _erase_text(
        self,
        img_bgr: np.ndarray,
        boxes: list[TextBox],
        algo: str = "TELEA",
        dilate_iter: int = 2,
    ) -> np.ndarray:
        h, w = img_bgr.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        for tb in boxes:
            pts = tb.box.astype(np.int32).reshape(-1, 1, 2)
            cv2.fillPoly(mask, [pts], 255)
        # 膨胀吞掉抗锯齿边缘
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        mask = cv2.dilate(mask, kernel, iterations=dilate_iter)
        flag = cv2.INPAINT_NS if algo.upper() == "NS" else cv2.INPAINT_TELEA
        return cv2.inpaint(img_bgr, mask, 3, flag)

    # ---------- 重绘 ----------

    def _render_text(
        self,
        img_bgr: np.ndarray,
        styled: list[tuple[TextBox, ReplaceRule, str, TextStyle]],
    ) -> np.ndarray:
        from PIL import Image, ImageDraw

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(img_rgb)
        overlay = Image.new("RGBA", pil.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for tb, rule, new_text, style in styled:
            color_rgb = style.font_color or (0, 0, 0)
            color_rgba = (int(color_rgb[0]), int(color_rgb[1]), int(color_rgb[2]), 255)
            font_path = style.font_path
            init_size = style.font_size or 16
            font, actual_size = self._fit_font(
                draw, new_text, font_path, init_size, tb.bbox_rect
            )
            self._draw_centered(draw, tb, new_text, font, color_rgba, actual_size)

        pil = Image.alpha_composite(pil.convert("RGBA"), overlay).convert("RGB")
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    def _fit_font(self, draw, text, font_path, init_size, rect):
        """二分查找最大可放下字号。返回 (font, size)。"""
        from PIL import ImageFont

        x, y, w, h = rect
        if w <= 0 or h <= 0:
            return ImageFont.load_default(), 8

        lo, hi = 6, 300
        best_font = None
        best_size = init_size
        while lo <= hi:
            mid = (lo + hi) // 2
            font = self._load_font(font_path, mid)
            lines = self._wrap_text(draw, text, font, w * 0.92)
            if not lines:
                lines = [""]
            line_h = int(mid * 1.25)
            total_h = line_h * len(lines)
            max_line_w = max((draw.textlength(l, font=font) for l in lines), default=0)
            if total_h <= h * 0.92 and max_line_w <= w * 0.92:
                best_font = font
                best_size = mid
                lo = mid + 1
            else:
                hi = mid - 1

        if best_font is None:
            best_size = 6
            best_font = self._load_font(font_path, 6)
        return best_font, best_size

    @staticmethod
    def _load_font(font_path: str | None, size: int):
        from PIL import ImageFont

        if font_path and os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    @staticmethod
    def _wrap_text(draw, text: str, font, max_w: float) -> list[str]:
        """按字符贪心装箱换行。支持显式 \\n。"""
        lines: list[str] = []
        for seg in text.split("\n"):
            cur = ""
            for ch in seg:
                trial = cur + ch
                if draw.textlength(trial, font=font) <= max_w:
                    cur = trial
                else:
                    if cur:
                        lines.append(cur)
                    cur = ch
            lines.append(cur)
        return lines

    def _draw_centered(self, draw, tb: TextBox, text: str, font, color_rgba, size: int):
        x, y, w, h = tb.bbox_rect
        lines = self._wrap_text(draw, text, font, w * 0.92)
        if not lines:
            lines = [text]
        line_h = int(size * 1.25)
        total_h = line_h * len(lines)
        start_y = y + (h - total_h) // 2
        for i, line in enumerate(lines):
            lw = draw.textlength(line, font=font)
            cx = x + (w - lw) / 2
            ty = start_y + i * line_h
            draw.text((cx, ty), line, font=font, fill=color_rgba)
