#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试第一章生成效果的脚本
"""

import sys
import os
import json

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from 写小说软件_08 import CompactNovelGeneratorApp
from PyQt5.QtWidgets import QApplication

def test_first_chapter_generation():
    """测试第一章生成效果"""
    # 创建应用
    app = QApplication(sys.argv)
    
    # 创建主窗口
    window = CompactNovelGeneratorApp()
    
    # 获取大纲内容
    outline = window.outline_text.toPlainText()
    print("大纲内容:")
    print(outline[:200] + "..." if len(outline) > 200 else outline)
    print("\n" + "="*50 + "\n")
    
    # 模拟生成第一章的提示词
    title = window.novel_title_input.text().strip()
    title = title if title else "未命名小说"
    
    # 构建提示词
    prompt = f"请根据以下小说大纲生成《{title}》的第1章内容：\n"
    prompt += outline + "\n\n"
    
    # 添加第一章特殊要求
    prompt += "【第一章特殊要求】\n"
    prompt += "1. 开篇必须在3秒内抓住读者注意力，使用以下三种开头类型之一：\n"
    prompt += "   a) 冲突型开头：直接让主角面临危机或矛盾，不做铺垫\n"
    prompt += "   b) 悬念型开头：用反常细节制造疑问，不解释只呈现不合理场景\n"
    prompt += "   c) 情绪共鸣型开头：用细腻细节唤起读者情感，快速代入主角心境\n"
    prompt += "2. 主角出场要有鲜明特点，通过具体行动展示性格而非描述\n"
    prompt += "3. 在前500字内必须出现一个异常事件或转折点\n"
    prompt += "4. 设置至少2个谜团或伏笔，为后续章节埋下线索\n"
    prompt += "5. 结尾要留下强烈悬念，让读者迫切想知道后续发展\n"
    prompt += "6. 避免平铺直叙的背景介绍，将背景信息融入情节发展中\n"
    prompt += "7. 使用生动的感官描写（视觉、听觉、触觉等）营造氛围\n"
    prompt += "8. 对话要简洁有力，每句对话都要推动情节或展示人物性格\n"
    prompt += "9. 开篇避免使用天气描写、环境描写等常见套路，除非与情节直接相关\n"
    prompt += "10. 确保第一段就出现核心冲突或悬念，不要慢慢铺垫\n\n"
    
    # 添加章节具体要求
    prompt += f"章节具体要求：\n"
    prompt += f"- 保持{window.pov_combo.currentText()}视角\n"
    prompt += f"- 使用{window.lang_combo.currentText()}风格\n"
    prompt += f"- 节奏：{window.rhythm_combo.currentText()}\n"
    prompt += f"- 字数：约3000字\n"
    prompt += f"- 重要：请使用纯中文生成章节内容，不要包含任何英文内容\n"
    
    # 添加通用写作技巧要求
    prompt += "\n【写作技巧要求】\n"
    prompt += "1. 每个段落都要有明确目的，要么推动情节，要么塑造人物，要么营造氛围\n"
    prompt += "2. 使用'展示而非告知'的写作手法，通过具体行动和细节展示信息\n"
    prompt += "3. 控制信息释放节奏，不要一次性揭示所有信息\n"
    prompt += "4. 确保每个场景都有开头、发展和结尾\n"
    prompt += "5. 使用多样化的句式结构，避免单调重复\n"
    
    print("生成的第一章提示词:")
    print(prompt)
    
    # 保存提示词到文件
    with open("第一章生成提示词.txt", "w", encoding="utf-8") as f:
        f.write(prompt)
    
    print("\n提示词已保存到 '第一章生成提示词.txt' 文件")
    print("请使用此提示词在API工具中测试生成效果")

if __name__ == "__main__":
    test_first_chapter_generation()