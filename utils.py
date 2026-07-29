"""公共工具：字体路径探测、颜色格式转换、路径规整。"""
from __future__ import annotations

import os

# Windows 系统字体候选（key -> 路径）
_FONT_CANDIDATES = {
    "msyh": r"C:\Windows\Fonts\msyh.ttc",  # 微软雅黑
    "msyhbd": r"C:\Windows\Fonts\msyhbd.ttc",  # 雅黑粗
    "simsun": r"C:\Windows\Fonts\simsun.ttc",  # 宋体
    "simhei": r"C:\Windows\Fonts\simhei.ttf",  # 黑体
    "arial": r"C:\Windows\Fonts\arial.ttf",
    "arialbd": r"C:\Windows\Fonts\arialbd.ttf",  # Arial 粗
    "consola": r"C:\Windows\Fonts\consola.ttf",
}


def resolve_font(name_or_path: str | None) -> str | None:
    """解析字体名为可用路径。

    支持：绝对/相对路径、纯文件名（在系统 Fonts 目录查）、字体 key（如 msyh / msyh.ttc）。
    返回存在的路径，找不到返回 None。
    """
    if not name_or_path:
        return None
    # 直接是路径且存在
    if os.path.isabs(name_or_path) and os.path.exists(name_or_path):
        return name_or_path
    # 在系统 Fonts 目录按文件名查
    p = os.path.join(r"C:\Windows\Fonts", name_or_path)
    if os.path.exists(p):
        return p
    # 按 key 查（msyh.ttc -> msyh）
    key = os.path.splitext(name_or_path.lower())[0]
    if key in _FONT_CANDIDATES and os.path.exists(_FONT_CANDIDATES[key]):
        return _FONT_CANDIDATES[key]
    return None


def pick_default_font(text: str | None, bold: bool = False) -> str | None:
    """根据文本是否含中文选默认字体路径。"""
    has_cjk = bool(text) and any("\u4e00" <= c <= "\u9fff" for c in text)
    if has_cjk:
        key = "msyhbd" if bold else "msyh"
    else:
        key = "arialbd" if bold else "arial"
    return resolve_font(key)


def bgr_to_rgb(bgr: tuple) -> tuple[int, int, int]:
    return (int(bgr[2]), int(bgr[1]), int(bgr[0]))


def rgb_to_hex(rgb: tuple) -> str:
    return "#{:02X}{:02X}{:02X}".format(int(rgb[0]), int(rgb[1]), int(rgb[2]))


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#").strip()
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def basename_lower(path: str) -> str:
    return os.path.basename(path).lower()


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))
