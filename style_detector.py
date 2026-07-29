"""原文字样式自动检测：颜色(K-means) / 字号(由bbox高度推算) / 字体(中英分流)。"""
from __future__ import annotations

import cv2
import numpy as np

from models import TextBox, TextStyle
from utils import bgr_to_rgb, clamp, pick_default_font, resolve_font


class StyleDetector:
    def detect(
        self,
        image_bgr: np.ndarray,
        tb: TextBox,
        override: TextStyle | None = None,
        new_text: str | None = None,
    ) -> TextStyle:
        """返回完整 TextStyle：override 中非 None 的用 override，其余自动检测。

        new_text: 替换后的新文字，用于选择合适字体（特别是英文→中文场景）。
                  若为 None，则使用 tb.text（原文字）判断。
        """
        override = override or TextStyle()
        color = override.font_color
        if color is None:
            color = self._detect_color(image_bgr, tb)  # RGB
        # 字号估算用新文字（中文和英文的字号系数不同）
        text_for_size = new_text if new_text is not None else tb.text
        size = override.font_size
        if size is None:
            size = self._estimate_font_size(tb, text_for_size)
        # 字体选择用新文字（关键修复：英文替换为中文时需要用中文字体）
        text_for_font = new_text if new_text is not None else tb.text
        path = override.font_path
        if path is None:
            path = pick_default_font(text_for_font, override.bold)
        else:
            path = resolve_font(path) or pick_default_font(text_for_font, override.bold)
        return TextStyle(
            font_color=color, font_size=size, font_path=path, bold=override.bold
        )

    def _detect_color(self, image_bgr: np.ndarray, tb: TextBox) -> tuple[int, int, int]:
        """K-means(k=2) 分离文字色与背景色，取与外围背景距离更大者为文字色。返回 RGB。"""
        h, w = image_bgr.shape[:2]
        x, y, bw, bh = tb.bbox_rect
        if bw <= 0 or bh <= 0:
            return (0, 0, 0)

        # bbox 内 ROI
        y0, y1 = max(0, y), min(h, y + bh)
        x0, x1 = max(0, x), min(w, x + bw)
        roi = image_bgr[y0:y1, x0:x1]
        if roi.size == 0:
            return (0, 0, 0)
        roi_flat = roi.reshape(-1, 3).astype(np.float32)

        # 外围背景采样：bbox 外扩 m 像素的边框区域
        m = 4
        ex0, ey0 = max(0, x - m), max(0, y - m)
        ex1, ey1 = min(w, x + bw + m), min(h, y + bh + m)
        outer = image_bgr[ey0:ey1, ex0:ex1]
        bg_flat = np.empty((0, 3), dtype=np.float32)
        if outer.size > 0:
            mask_bg = np.ones(outer.shape[:2], dtype=bool)
            bx0 = max(0, x - ex0)
            by0 = max(0, y - ey0)
            bx1 = min(outer.shape[1], x + bw - ex0)
            by1 = min(outer.shape[0], y + bh - ey0)
            if bx1 > bx0 and by1 > by0:
                mask_bg[by0:by1, bx0:bx1] = False
            bg_flat = outer[mask_bg].reshape(-1, 3).astype(np.float32)

        # K-means
        k = min(2, len(roi_flat))
        if k < 1:
            mean_bgr = roi_flat.mean(axis=0)
            return bgr_to_rgb(tuple(mean_bgr))
        try:
            _, labels, centers = cv2.kmeans(
                roi_flat,
                k,
                None,
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0),
                3,
                cv2.KMEANS_PP_CENTERS,
            )
        except cv2.error:
            mean_bgr = roi_flat.mean(axis=0)
            return bgr_to_rgb(tuple(mean_bgr))

        if k == 1:
            text_color = centers[0]
        else:
            if len(bg_flat) > 0:
                bg_mean = bg_flat.mean(axis=0)
                d0 = float(np.linalg.norm(centers[0] - bg_mean))
                d1 = float(np.linalg.norm(centers[1] - bg_mean))
                # 距背景更远的簇为文字色；若两簇距背景都近，取面积小者
                if min(d0, d1) < 1e-3:
                    counts = np.bincount(labels.flatten(), minlength=k)
                    text_color = centers[int(np.argmin(counts))]
                else:
                    text_color = centers[0] if d0 > d1 else centers[1]
            else:
                counts = np.bincount(labels.flatten(), minlength=k)
                text_color = centers[int(np.argmin(counts))]

        return bgr_to_rgb(tuple(text_color))

    def _estimate_font_size(self, tb: TextBox, text: str | None = None) -> int:
        """由 bbox 高度推算 Pillow font size 初值。最终由重绘阶段二分校正。"""
        h = tb.bbox_rect[3]
        if h <= 0:
            return 16
        has_cjk = bool(text) and any("\u4e00" <= c <= "\u9fff" for c in text)
        is_ascii = bool(text) and text.isascii()
        if has_cjk and not is_ascii:
            factor = 0.85  # 纯中文：方块字填满 em
        elif is_ascii and not has_cjk:
            factor = 0.70  # 纯英文：字母高≈0.7em
        else:
            factor = 0.78  # 混排或空
        est = int(h / factor)
        return clamp(est, 8, 200)
