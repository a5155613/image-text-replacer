"""端到端：--avatar-ops 无 --config 的批量头像替换。"""
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "venv", "Scripts", "python.exe")


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="av_batch_")
    scene = os.path.join(tmp, "scene.png")
    im = Image.new("RGB", (200, 200), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((20, 20, 80, 80), fill=(220, 40, 40))  # 红圆头像位
    im.save(scene)

    av = os.path.join(tmp, "avatar.png")
    Image.new("RGB", (120, 120), (40, 120, 220)).save(av)  # 蓝色新头像

    ops_path = os.path.join(tmp, "ops.json")
    with open(ops_path, "w", encoding="utf-8") as f:
        json.dump(
            [{"image_pattern": "*", "rect": [20, 20, 60, 60],
              "avatar_path": av, "shape": "circle"}],
            f, ensure_ascii=False,
        )

    out_dir = os.path.join(tmp, "out")
    r = subprocess.run(
        [PY, os.path.join(ROOT, "main.py"), "--batch",
         "--avatar-ops", ops_path, "--images", tmp, "--out", out_dir],
        capture_output=True, text=True, encoding="utf-8",
    )
    print("STDOUT:", r.stdout)
    if r.returncode != 0:
        print("STDERR:", r.stderr)
        return 1

    out_img = os.path.join(out_dir, "scene_replaced.png")
    assert os.path.exists(out_img), f"输出图未生成: {out_img}"

    import cv2
    import numpy as np
    out = cv2.imdecode(np.fromfile(out_img, dtype=np.uint8), cv2.IMREAD_COLOR)
    # 圆心应变蓝（新头像 BGR [220,120,40]）
    px = out[50, 50].tolist()
    assert px == [220, 120, 40], f"圆心应变蓝，实际 {px}"
    # 右下角（圆外）应仍白
    assert out[180, 180].tolist() == [255, 255, 255], "圆外应保持白底"
    print(f"[OK] avatar-only batch: 圆心 {px} 已替换，圆外保持原样")
    return 0


if __name__ == "__main__":
    sys.exit(main())
