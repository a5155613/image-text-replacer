"""头像替换算法冒烟测试：造图 → replace → detect → apply_ops，断言像素变化。"""
from __future__ import annotations

import os
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from avatar_editor import AvatarEditor  # noqa: E402
from models import AvatarReplace  # noqa: E402


def build_scene(path: str):
    """白底 + 左上红色实心圆（模拟头像），右下角一段文字色块。"""
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((20, 20, 80, 80), fill=(220, 40, 40))  # 红圆，bbox=(20,20,60,60)
    d.rectangle((140, 140, 180, 180), fill=(0, 0, 0))  # 右下黑块（非头像）
    img.save(path)


def build_avatar(path: str):
    """新头像：60x60 蓝色填充。"""
    img = Image.new("RGB", (120, 120), (40, 120, 220))  # 故意非正方形尺寸，测裁剪
    img.save(path)


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="avatar_test_")
    scene = os.path.join(tmp, "scene.png")
    avatar = os.path.join(tmp, "avatar.png")
    build_scene(scene)
    build_avatar(avatar)

    editor = AvatarEditor()
    scene_bgr = cv2.imdecode(np.fromfile(scene, dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = scene_bgr.shape[:2]
    assert (h, w) == (200, 200)

    # ---------- 1. replace (circle) ----------
    out = editor.replace(scene_bgr, (20, 20, 60, 60), avatar, "circle")
    # 圆心 (50,50) 应变为蓝色（新头像）
    px_center = out[50, 50].tolist()
    assert px_center == [220, 120, 40], f"圆心应变为蓝色 BGR，实际 {px_center}"
    # 圆外但 bbox 内的角点 (22,22) 应保持白（角在圆外）
    px_corner = out[22, 22].tolist()
    assert px_corner == [255, 255, 255], f"圆外角点应仍白色，实际 {px_corner}"
    # 右下黑块不变
    px_blk = out[160, 160].tolist()
    assert px_blk == [0, 0, 0], f"右下黑块应不变，实际 {px_blk}"
    print(f"[OK] replace(circle): 圆心变蓝 {px_center}, 圆外角点仍白 {px_corner}")

    # ---------- 2. replace (square) ----------
    out_sq = editor.replace(scene_bgr, (20, 20, 60, 60), avatar, "square")
    # 方形：整个 rect 区域都应是蓝
    assert out_sq[22, 22].tolist() == [220, 120, 40], "方形模式下 rect 角点应变蓝"
    print("[OK] replace(square): rect 角点已变蓝")

    # ---------- 3. detect ----------
    circles = editor.detect(scene_bgr, min_r=15, max_r=80)
    assert circles, "应至少检测到一个圆"
    # 取最接近 (50,50) 的圆
    best = min(circles, key=lambda c: (c[0] - 50) ** 2 + (c[1] - 50) ** 2)
    dx, dy, dr = abs(best[0] - 50), abs(best[1] - 50), abs(best[2] - 30)
    assert dx < 8 and dy < 8 and dr < 8, f"检测圆偏离过大: {best}"
    print(f"[OK] detect: 命中圆 ({best[0]},{best[1]}) r={best[2]} 接近 (50,50) r=30")

    # ---------- 4. apply_ops（全局 + 单图）----------
    op_global = AvatarReplace(image_pattern="*", rect=(20, 20, 60, 60),
                              avatar_path=avatar, shape="circle")
    op_single = AvatarReplace(image_pattern="other.png", rect=(140, 140, 40, 40),
                              avatar_path=avatar, shape="square")
    # 对 scene.png：global 命中，single 不命中
    out2, count = editor.apply_ops(scene_bgr, [op_global, op_single], "scene.png")
    assert count == 1, f"apply_ops 应命中 1 条（仅 global），实际 {count}"
    assert out2[50, 50].tolist() == [220, 120, 40], "apply_ops 后圆心应变蓝"
    # 右下黑块应未被替换（single 未命中）
    assert out2[160, 160].tolist() == [0, 0, 0], "未命中 op 不应影响右下黑块"
    print(f"[OK] apply_ops: 命中 {count} 条（global 生效，单图未命中）")

    # ---------- 5. apply_ops 越界保护 ----------
    op_oob = AvatarReplace(image_pattern="*", rect=(180, 180, 60, 60),
                           avatar_path=avatar, shape="square")
    out3, c3 = editor.apply_ops(scene_bgr, [op_oob], "scene.png")
    assert c3 == 1
    # 越界部分应被裁剪，不崩溃；可访问像素 (199,199)
    _ = out3[199, 199]
    print("[OK] apply_ops 越界裁剪无异常")

    print("\n全部冒烟测试通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
