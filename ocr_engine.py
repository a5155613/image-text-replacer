"""RapidOCR 3.x 封装。防御性兼容 3.x 对象返回与旧版 list 返回。"""
from __future__ import annotations

import numpy as np

from models import TextBox


class OcrEngine:
    def __init__(self):
        # 延迟导入，避免 GUI 启动时即加载模型（约 27MB）
        from rapidocr import RapidOCR

        self.engine = RapidOCR()

    def recognize(self, image_path: str) -> list[TextBox]:
        """识别单张图片，返回 TextBox 列表。"""
        result = self.engine(image_path)
        return self._parse(result)

    def recognize_array(self, image_array: np.ndarray) -> list[TextBox]:
        """识别内存中的图片（BGR 或文件路径兼容）。"""
        result = self.engine(image_array)
        return self._parse(result)

    @staticmethod
    def _parse(result) -> list[TextBox]:
        if result is None:
            return []

        # 3.x 对象形式：result.boxes / result.txts / result.scores
        boxes = getattr(result, "boxes", None)
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is not None and txts is not None:
            out: list[TextBox] = []
            for i, box in enumerate(boxes):
                if box is None:
                    continue
                text = txts[i] if i < len(txts) else ""
                score = scores[i] if scores and i < len(scores) else 0.0
                out.append(
                    TextBox(
                        box=np.array(box, dtype=np.float32).reshape(-1, 2),
                        text=str(text),
                        score=float(score),
                    )
                )
            return out

        # 旧版 list 形式：[(box, text, score), ...]
        if isinstance(result, (list, tuple)):
            out = []
            for item in result:
                if item is None:
                    continue
                if len(item) < 3:
                    continue
                box, text, score = item[0], item[1], item[2]
                out.append(
                    TextBox(
                        box=np.array(box, dtype=np.float32).reshape(-1, 2),
                        text=str(text),
                        score=float(score),
                    )
                )
            return out

        return []

    def visualize(self, image_path: str, save_path: str | None = None):
        """生成可视化（标注 bbox）。3.x 提供 result.vis()。"""
        result = self.engine(image_path)
        vis = getattr(result, "vis", None)
        if vis is None:
            return None
        try:
            return vis(save_path) if save_path else vis()
        except TypeError:
            return vis
