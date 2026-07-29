"""批量处理编排：QThread 子类，串联 头像替换 → OCR → 编辑 → 保存，发进度信号。

中文路径用 imdecode/imencode + tofile，规避 cv2.imread/imwrite 不支持中文路径的问题。

每张图流程：
    读图 → 应用匹配的 avatar_ops（头像替换，不需 OCR）
         → OCR → 文字替换（擦除+重绘）
         → 保存
"""
from __future__ import annotations

import os

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from avatar_editor import AvatarEditor
from image_editor import ImageEditor
from models import AvatarReplace, ReplaceRule, TaskResult
from ocr_engine import OcrEngine


class BatchProcessor(QThread):
    progress = Signal(int, int, str)  # current, total, filename
    finished_all = Signal(list)  # list[TaskResult]
    log = Signal(str)

    def __init__(
        self,
        image_paths: list[str],
        rules: list[ReplaceRule],
        output_dir: str,
        ocr_engine: OcrEngine | None = None,
        editor: ImageEditor | None = None,
        avatar_ops: list[AvatarReplace] | None = None,
        avatar_editor: AvatarEditor | None = None,
        inpaint_algo: str = "TELEA",
        dilate_iter: int = 2,
        erase_only: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.image_paths = list(image_paths)
        self.rules = rules
        self.output_dir = output_dir
        self.inpaint_algo = inpaint_algo
        self.dilate_iter = dilate_iter
        self.erase_only = erase_only
        self.avatar_ops = list(avatar_ops) if avatar_ops else []
        self._ocr = ocr_engine
        self._editor = editor or ImageEditor()
        self._avatar_editor = avatar_editor or AvatarEditor()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        results: list[TaskResult] = []
        total = len(self.image_paths)
        os.makedirs(self.output_dir, exist_ok=True)

        for i, img_path in enumerate(self.image_paths):
            if self._cancel:
                self.log.emit("[停止] 用户取消")
                break
            fname = os.path.basename(img_path)
            self.progress.emit(i, total, fname)
            try:
                if self._ocr is None:
                    self._ocr = OcrEngine()

                # 中文路径安全读取
                img = cv2.imdecode(
                    np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR
                )
                if img is None:
                    raise ValueError("无法读取图片（格式不支持或路径无效）")

                # 1. 先应用头像替换（不需 OCR）
                img, av_count = self._avatar_editor.apply_ops(
                    img, self.avatar_ops, fname
                )

                # 2. OCR + 文字替换
                text_count = 0
                if self.rules:
                    boxes = self._ocr.recognize_array(img)
                    img, text_count = self._editor.replace(
                        img,
                        boxes,
                        self.rules,
                        image_filename=fname,
                        inpaint_algo=self.inpaint_algo,
                        dilate_iter=self.dilate_iter,
                        erase_only=self.erase_only,
                    )

                out_path = self._build_output_path(img_path)
                ext = os.path.splitext(out_path)[1] or ".png"
                ok, buf = cv2.imencode(ext, img)
                if not ok:
                    raise ValueError("图片编码失败")
                buf.tofile(out_path)

                results.append(
                    TaskResult(
                        image_path=img_path,
                        output_path=out_path,
                        success=True,
                        replaced_count=text_count,
                        avatar_count=av_count,
                    )
                )
                self.log.emit(
                    f"[OK] {fname}：头像 {av_count} 处，文字 {text_count} 处 → "
                    f"{os.path.basename(out_path)}"
                )
            except Exception as e:
                results.append(
                    TaskResult(
                        image_path=img_path,
                        output_path=None,
                        success=False,
                        replaced_count=0,
                        error=str(e),
                    )
                )
                self.log.emit(f"[失败] {fname}：{e}")

        self.progress.emit(total, total, "")
        self.finished_all.emit(results)

    def _build_output_path(self, img_path: str) -> str:
        base, ext = os.path.splitext(os.path.basename(img_path))
        suffix = "_erased" if self.erase_only else "_replaced"
        return os.path.join(self.output_dir, f"{base}{suffix}{ext or '.png'}")
