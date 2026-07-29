"""头像替换：PIL 形状蒙版贴合 + OpenCV HoughCircles 自动检测。

贴合流程：
    新头像 → 缩放到 rect 大小 → 按 shape 生成 L 蒙版（边缘轻羽化） → putalpha → paste 到原图。

中文路径头像用 np.fromfile + cv2.imdecode 读再转 PIL，规避 PIL 对中文路径的不支持。
"""
from __future__ import annotations

import os

import cv2
import numpy as np

from models import AvatarReplace


class AvatarEditor:
    SHAPE_CIRCLE = "circle"
    SHAPE_ROUNDED = "rounded"
    SHAPE_SQUARE = "square"
    _SHAPES = (SHAPE_CIRCLE, SHAPE_ROUNDED, SHAPE_SQUARE)

    def replace(
        self,
        image_bgr: np.ndarray,
        rect: tuple[int, int, int, int],
        avatar_path: str,
        shape: str = "circle",
        feather: int = 1,
    ) -> np.ndarray:
        """在 image_bgr 的 rect 区域贴合 avatar_path 指定的新头像。返回新图（不修改原图）。

        shape: circle(椭圆内切) / rounded(圆角矩形) / square(整矩形)
        feather: 蒙版边缘羽化像素数（0=硬边，1-2=轻微抗锯齿）
        """
        x, y, w, h = rect
        if w <= 0 or h <= 0 or not avatar_path or not os.path.exists(avatar_path):
            return image_bgr

        shape = shape if shape in self._SHAPES else self.SHAPE_CIRCLE

        from PIL import Image, ImageDraw

        # 1. 读新头像（中文路径安全）→ RGBA → 缩放到 rect
        avatar = self._load_avatar(avatar_path, (w, h))
        if avatar is None:
            return image_bgr
        if avatar.mode != "RGBA":
            avatar = avatar.convert("RGBA")

        # 2. 形状蒙版（L 模式，255=保留）
        mask = Image.new("L", (w, h), 0)
        md = ImageDraw.Draw(mask)
        if shape == self.SHAPE_CIRCLE:
            md.ellipse((0, 0, w - 1, h - 1), fill=255)
        elif shape == self.SHAPE_ROUNDED:
            radius = max(4, min(w, h) // 5)  # 圆角半径取短边的 1/5
            md.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
        else:  # square
            md.rectangle((0, 0, w - 1, h - 1), fill=255)

        # 轻羽化边缘，避免锯齿/生硬
        if feather and feather > 0:
            mask_np = np.array(mask)
            k = max(3, feather * 2 + 1)
            mask_np = cv2.GaussianBlur(mask_np, (k, k), 0)
            mask = Image.fromarray(mask_np, mode="L")

        avatar.putalpha(mask)

        # 3. 把原图(BGR)转 RGBA，paste 新头像，再转回 BGR
        img_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(img_rgb).convert("RGBA")
        # 边界裁剪：避免越界
        ih, iw = image_bgr.shape[:2]
        px, py = max(0, int(x)), max(0, int(y))
        paste_x, paste_y = px, py
        # 若 rect 越界右下，裁剪 avatar
        aw, ah = avatar.size
        if paste_x + aw > iw:
            aw = iw - paste_x
        if paste_y + ah > ih:
            ah = ih - paste_y
        if aw <= 0 or ah <= 0:
            return image_bgr
        if (aw, ah) != avatar.size:
            avatar = avatar.crop((0, 0, aw, ah))

        pil.paste(avatar, (paste_x, paste_y), avatar)
        out_rgb = pil.convert("RGB")
        return cv2.cvtColor(np.array(out_rgb), cv2.COLOR_RGB2BGR)

    def detect(
        self,
        image_bgr: np.ndarray,
        min_r: int = 15,
        max_r: int = 80,
        param2: int = 20,
    ) -> list[tuple[int, int, int]]:
        """HoughCircles 检测圆形头像。返回 [(x, y, r), ...] 按投票强度降序。

        param2 为累加器阈值，越小越敏感（候选多但易误检），默认 20 在清晰圆边缘下
        较稳。复杂背景可能漏检/误检，仅作辅助，建议手动框选为主。
        """
        h, w = image_bgr.shape[:2]
        if h == 0 or w == 0:
            return []
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 5)
        # dp=1 累加器与原图同分辨率；minDist 至少 2*min_r 避免重叠
        min_dist = max(2 * min_r, 30)
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1.0,
            minDist=min_dist,
            param1=100,
            param2=param2,
            minRadius=min_r,
            maxRadius=max_r,
        )
        if circles is None:
            return []
        circles = np.round(circles[0]).astype(int)  # (N, 3): x, y, r
        # 按检测置信度（HoughCircles 返回顺序即投票强度）保留前 30 个
        return [(int(c[0]), int(c[1]), int(c[2])) for c in circles[:30]]

    def apply_ops(
        self,
        image_bgr: np.ndarray,
        ops: list[AvatarReplace],
        image_filename: str,
    ) -> tuple[np.ndarray, int]:
        """对单图依次应用所有命中的头像操作。返回 (新图, 命中数)。

        命中条件：op.image_pattern 为 "*" 或与文件 basename（小写）相等。
        """
        if not ops:
            return image_bgr, 0
        fname = os.path.basename(image_filename).lower() if image_filename else ""
        out = image_bgr
        count = 0
        for op in ops:
            if not AvatarReplace.applies(op.image_pattern, fname):
                continue
            out = self.replace(out, op.rect, op.avatar_path, op.shape)
            count += 1
        return out, count

    # ---------- 内部 ----------

    @staticmethod
    def _load_avatar(path: str, size: tuple[int, int]):
        """读头像图并缩放到 size。中文路径安全。"""
        try:
            data = np.fromfile(path, dtype=np.uint8)
            if data.size == 0:
                return None
            bgr = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
            if bgr is None:
                return None
        except Exception:
            return None

        from PIL import Image

        # 处理透明通道：若原图带 alpha，保留；否则转 BGR→RGB
        if bgr.ndim == 2:
            pil = Image.fromarray(bgr, mode="L").convert("RGBA")
        elif bgr.shape[2] == 4:
            bgra = bgr
            rgba = cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA)
            pil = Image.fromarray(rgba, mode="RGBA")
        else:
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb, mode="RGB").convert("RGBA")

        # 居中正方形裁剪后再缩放，避免长宽比失真
        w, h = pil.size
        side = min(w, h)
        if w != h:
            left = (w - side) // 2
            top = (h - side) // 2
            pil = pil.crop((left, top, left + side, top + side))
        return pil.resize(size, Image.LANCZOS)
