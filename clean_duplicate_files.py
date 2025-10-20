import os
import shutil

def clean_duplicate_files(novels_dir="novels"):
    """清理重复的章节文件，只保留包含标题的格式"""
    if not os.path.exists(novels_dir):
        print(f"目录 {novels_dir} 不存在")
        return
    
    # 获取目录中的所有文件
    files = os.listdir(novels_dir)
    
    # 找出所有章节文件
    chapter_files = {}
    for file in files:
        if file.endswith(".txt") and file.startswith("第") and "章" in file:
            # 提取章节号
            parts = file.split("章")
            if len(parts) >= 2:
                chapter_num_str = parts[0][1:]  # 去掉"第"
                try:
                    chapter_num = int(chapter_num_str)
                    if chapter_num not in chapter_files:
                        chapter_files[chapter_num] = []
                    chapter_files[chapter_num].append(file)
                except ValueError:
                    # 处理带标题的文件名格式
                    try:
                        # 尝试从带标题的格式中提取章节号
                        chapter_num_str = parts[0][1:]  # 去掉"第"
                        chapter_num = int(chapter_num_str)
                        if chapter_num not in chapter_files:
                            chapter_files[chapter_num] = []
                        chapter_files[chapter_num].append(file)
                    except ValueError:
                        print(f"无法解析章节号: {file}")
    
    # 处理重复文件
    for chapter_num, file_list in chapter_files.items():
        if len(file_list) > 1:
            print(f"第{chapter_num}章有多个文件:")
            for file in file_list:
                print(f"  - {file}")
            
            # 找出新格式的文件（包含标题）
            new_format_files = [f for f in file_list if "_" in f]
            old_format_files = [f for f in file_list if "_" not in f]
            
            # 保留新格式的文件，删除旧格式的文件
            if new_format_files:
                print(f"保留新格式文件: {new_format_files[0]}")
                for old_file in old_format_files:
                    old_path = os.path.join(novels_dir, old_file)
                    print(f"删除旧格式文件: {old_file}")
                    os.remove(old_path)
            else:
                print(f"没有找到新格式文件，保留: {file_list[0]}")
                # 如果没有新格式文件，保留第一个，删除其余的
                for i in range(1, len(file_list)):
                    old_path = os.path.join(novels_dir, file_list[i])
                    print(f"删除重复文件: {file_list[i]}")
                    os.remove(old_path)
        elif len(file_list) == 1:
            # 处理单个旧格式文件的情况
            file = file_list[0]
            if "_" not in file:  # 如果是旧格式文件
                print(f"发现旧格式文件: {file}")
                # 提取章节号
                parts = file.split("章")
                if len(parts) >= 2:
                    chapter_num_str = parts[0][1:]  # 去掉"第"
                    # 去掉可能存在的.txt后缀
                    if "." in chapter_num_str:
                        chapter_num_str = chapter_num_str.split(".")[0]
                    try:
                        chapter_num = int(chapter_num_str)
                        # 创建新格式文件名
                        new_file_name = f"第{chapter_num:03d}章_未命名小说.txt"
                        new_file_path = os.path.join(novels_dir, new_file_name)
                        old_file_path = os.path.join(novels_dir, file)
                        
                        # 重命名文件
                        print(f"重命名 {file} 为 {new_file_name}")
                        os.rename(old_file_path, new_file_path)
                    except ValueError:
                        print(f"无法解析章节号: {file}")

if __name__ == "__main__":
    clean_duplicate_files()
    print("清理完成")