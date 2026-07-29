"""入口：GUI 模式（默认）或 --batch 无头批量模式。

GUI：
    python main.py

无头批量：
    python main.py --batch --config config.xlsx --images ./imgs --out ./output
    python main.py --batch --config config.xlsx --images 1.png 2.png --out ./out --erase-only
    python main.py --batch --avatar-ops avatar_ops.json --images ./imgs --out ./out
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys


def _load_avatar_ops(path: str):
    """从 JSON 加载头像操作列表。返回 list[AvatarReplace]。"""
    from models import AvatarReplace

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("头像操作 JSON 顶层应为数组")
    ops = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        rect = item.get("rect") or [0, 0, 0, 0]
        if len(rect) != 4:
            raise ValueError(f"第 {i + 1} 条 rect 字段需为 4 元组")
        ops.append(
            AvatarReplace(
                image_pattern=str(item.get("image_pattern", "*")),
                rect=(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])),
                avatar_path=str(item.get("avatar_path", "")),
                shape=str(item.get("shape", "circle")),
            )
        )
    return ops


def run_batch(args) -> int:
    import cv2
    import numpy as np

    import config_loader
    from avatar_editor import AvatarEditor
    from image_editor import ImageEditor
    from ocr_engine import OcrEngine

    # 收集图片
    images: list[str] = []
    for p in args.images:
        if os.path.isdir(p):
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp", "*.tif"):
                images.extend(glob.glob(os.path.join(p, ext)))
        elif os.path.isfile(p):
            images.append(p)
    if not images:
        print("未找到任何图片")
        return 1

    # 规则（可选，有 avatar-ops 时允许无 config）
    rules = []
    if args.config:
        rules = config_loader.load_rules(args.config)
        print(f"加载 {len(rules)} 条文字替换规则：{args.config}")

    # 头像操作
    avatar_ops = []
    if args.avatar_ops:
        avatar_ops = _load_avatar_ops(args.avatar_ops)
        print(f"加载 {len(avatar_ops)} 条头像操作：{args.avatar_ops}")

    if not rules and not avatar_ops:
        print("无有效规则或头像操作（需要 --config 或 --avatar-ops）")
        return 1

    print(f"待处理 {len(images)} 张图片")

    os.makedirs(args.out, exist_ok=True)
    engine = OcrEngine() if rules else None
    editor = ImageEditor()
    avatar_editor = AvatarEditor()

    total = len(images)
    success = 0
    for i, img_path in enumerate(images, 1):
        fname = os.path.basename(img_path)
        print(f"[{i}/{total}] {fname} ...", flush=True)
        try:
            img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                print("  读取失败")
                continue

            # 1. 头像替换
            av_count = 0
            if avatar_ops:
                img, av_count = avatar_editor.apply_ops(img, avatar_ops, fname)

            # 2. 文字替换
            count = 0
            if rules and engine is not None:
                boxes = engine.recognize_array(img)
                img, count = editor.replace(
                    img,
                    boxes,
                    rules,
                    image_filename=fname,
                    erase_only=args.erase_only,
                )

            base, ext = os.path.splitext(fname)
            suffix = "_erased" if args.erase_only else "_replaced"
            out_path = os.path.join(args.out, f"{base}{suffix}{ext or '.png'}")
            ok, buf = cv2.imencode(ext or ".png", img)
            if not ok:
                print("  编码失败")
                continue
            buf.tofile(out_path)
            print(
                f"  → {os.path.basename(out_path)}"
                f"（头像 {av_count} 处，文字 {count} 处）"
            )
            success += 1
        except Exception as e:
            print(f"  失败：{e}")
    print(f"完成：{success}/{total} 张成功")
    return 0


def main():
    parser = argparse.ArgumentParser(description="批量图片文字替换工具")
    parser.add_argument("--batch", action="store_true", help="无头批量模式（不启动 GUI）")
    parser.add_argument("--config", help="配置文件路径（xlsx/csv）")
    parser.add_argument(
        "--avatar-ops", help="头像操作 JSON 文件路径（可单独使用，无需 --config）"
    )
    parser.add_argument("--images", nargs="+", help="图片文件或目录（可多个）")
    parser.add_argument("--out", default="output", help="输出目录（默认 output）")
    parser.add_argument(
        "--erase-only",
        action="store_true",
        help="仅擦除原文字不重绘（用于复杂背景外部精修）",
    )
    args = parser.parse_args()

    if args.batch:
        if not args.images:
            parser.error("--batch 模式需要 --images 参数")
        if not args.config and not args.avatar_ops:
            parser.error("--batch 模式需要 --config 或 --avatar-ops 参数")
        sys.exit(run_batch(args))

    # GUI 模式
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("批量图片文字替换工具")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
