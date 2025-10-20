import sys
import os
import requests
import json
import time

# 从文件中读取提示词
with open('第一章生成提示词.txt', 'r', encoding='utf-8') as f:
    prompt = f.read()

# API配置
api_url = "https://api-inference.modelscope.cn/v1/chat/completions"
api_key = "ms-9a61af32-7d87-4983-bbb0-d6f50344f993"  # ModelScope API密钥
model_name = "Qwen/Qwen3-VL-30B-A3B-Instruct"

# 请求数据
data = {
    "model": model_name,
    "messages": [
        {
            "role": "user",
            "content": prompt
        }
    ],
    "max_tokens": 5000,
    "temperature": 0.7,
    "top_p": 0.9,
    "stream": False
}

# 请求头
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

print("开始生成第一章...")
start_time = time.time()

try:
    # 发送请求
    response = requests.post(api_url, headers=headers, json=data)
    
    # 检查响应状态
    if response.status_code == 200:
        result = response.json()
        content = result['choices'][0]['message']['content']
        
        # 保存生成的章节
        os.makedirs('novels', exist_ok=True)
        with open('novels/第1章.txt', 'w', encoding='utf-8') as f:
            f.write(content)
        
        end_time = time.time()
        print(f"第一章生成完成！耗时: {end_time - start_time:.2f}秒")
        print(f"字数: {len(content)}字")
        print("内容已保存到 novels/第1章.txt")
        
        # 打印前200字作为预览
        print("\n内容预览:")
        print(content[:200] + "...")
        
    else:
        print(f"请求失败，状态码: {response.status_code}")
        print(f"错误信息: {response.text}")
        
except Exception as e:
    print(f"生成过程中出错: {str(e)}")