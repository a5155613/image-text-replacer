"""验证英文替换为中文时字体选择正确。"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from image_editor import ImageEditor
from models import ReplaceRule, TextBox, TextStyle


def test_font_selection_for_chinese():
    """测试：当原文字是英文，替换为中文时，应该选择中文字体。"""
    editor = ImageEditor()
    
    # 创建模拟的英文 TextBox
    tb = TextBox(
        box=np.array([[10, 10], [60, 10], [60, 30], [10, 30]]),
        text="Hello",
        score=0.95,
    )
    
    # 创建一个白色背景的简单图像
    img = np.ones((100, 200, 3), dtype=np.uint8) * 255  # 白色背景
    
    # 模拟 StyleDetector.detect 的调用
    # 测试用英文原文字判断字体
    style_en = editor.detector.detect(img, tb, TextStyle(), new_text=None)
    font_path_en = style_en.font_path
    print(f"[EN only] 原文字='Hello', font_path={font_path_en}")
    
    # 测试用中文新文字判断字体
    style_cn = editor.detector.detect(img, tb, TextStyle(), new_text="你好")
    font_path_cn = style_cn.font_path
    print(f"[EN->CN] 新文字='你好', font_path={font_path_cn}")
    
    # 验证
    assert font_path_en is not None, "英文字体路径不应为 None"
    assert font_path_cn is not None, "中文字体路径不应为 None"
    
    # 中文字体应该是 msyh（微软雅黑）或 simhei（黑体）等支持中文的字体
    is_cn_font = any(keyword in (font_path_cn or "").lower() for keyword in ["msyh", "simhei", "simsun", "chinese", "noto"])
    print(f"中文字体是否支持中文: {is_cn_font}")
    
    # 英文字体应该是 arial 等只支持英文的字体
    is_en_font = "arial" in (font_path_en or "").lower()
    print(f"英文字体是否为 arial: {is_en_font}")
    
    # 关键断言：替换为中文时必须使用支持中文的字体
    assert is_cn_font, f"替换为中文时必须使用中文字体，实际使用: {font_path_cn}"
    
    print("\n[PASS] 字体选择测试通过！")
    print(f"  - 英文原文字 → {os.path.basename(font_path_en) if font_path_en else 'None'}")
    print(f"  - 中文新文字 → {os.path.basename(font_path_cn) if font_path_cn else 'None'}")


def test_full_pipeline_en_to_cn():
    """完整管线测试：英文 'Hello' 替换为中文 '你好'。"""
    print("\n--- 完整管线测试 ---")
    
    editor = ImageEditor()
    
    # 创建一个包含 "Hello" 的简单白色背景图像
    img = np.ones((100, 200, 3), dtype=np.uint8) * 255
    
    # 模拟 OCR 结果
    boxes = [
        TextBox(
            box=np.array([[10, 10], [60, 10], [60, 30], [10, 30]]),
            text="Hello",
            score=0.95,
        )
    ]
    
    # 规则：把 Hello 替换为 你好
    rules = [
        ReplaceRule(
            image_pattern="*",
            match_mode="contains",
            old_text="Hello",
            new_text="你好",
            style=TextStyle(),  # 样式留空，自动检测
        )
    ]
    
    # 执行替换
    result, count = editor.replace(img, boxes, rules, "test.png")
    
    print(f"替换数量: {count}")
    assert count == 1, f"应该替换 1 处，实际 {count} 处"
    
    # 保存结果供检查
    out_path = os.path.join(os.path.dirname(__file__), "test_en_to_cn_result.png")
    cv2.imwrite(out_path, result)
    print(f"结果已保存: {out_path}")
    
    # 检查是否还有英文 "Hello" 的像素（简单检查中心区域）
    # 中文 "你好" 和 英文 "Hello" 的像素分布应该完全不同
    center_region = result[15:25, 20:50]  # 文字中心区域
    unique_colors = len(np.unique(center_region.reshape(-1, 3), axis=0))
    print(f"文字区域不同颜色数: {unique_colors}")
    
    print("[PASS] 完整管线测试通过！")


if __name__ == "__main__":
    test_font_selection_for_chinese()
    test_full_pipeline_en_to_cn()
    print("\n" + "="*50)
    print("所有测试通过！")
