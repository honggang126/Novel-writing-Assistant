import sys
import os
import json
import hashlib
import random
import re
import requests
import threading
import time
from datetime import datetime, timedelta, timezone 
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize, QTimer, QUrl, QObject, QEventLoop, QMetaObject, Q_ARG
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QFrame, QDialog, QGridLayout, QTabWidget, QTextEdit,
    QComboBox, QGroupBox, QFormLayout, QFileDialog, QSpinBox, QSplitter, QProgressBar,
    QStackedWidget, QScrollArea, QToolBar, QAction, QMenu, QStatusBar, QToolTip,
    QDialogButtonBox, QCheckBox, QListWidget, QAbstractItemView, QSpacerItem, QSizePolicy
)
from PyQt5.QtGui import (
    QFont, QIcon, QPalette, QColor, QPixmap, QPainter, QBrush, QLinearGradient,
    QFontDatabase
)

# ==================== 小说写作软件部分 ====================

def load_icon_from_url(url, default_icon=None):
    """从URL加载图标，如果失败则返回默认图标"""
    try:
        # 使用requests下载图片
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            pixmap = QPixmap()
            if pixmap.loadFromData(response.content):
                icon = QIcon(pixmap)
                return icon
    except Exception as e:
        print(f"加载图标失败: {str(e)}")
    
    # 如果加载失败，返回默认图标或空图标
    return default_icon if default_icon else QIcon()

class GradientFrame(QFrame):
    """自定义渐变背景框架"""
    def __init__(self, start_color=None, end_color=None, parent=None):
        super().__init__(parent)
        self.start_color = start_color if start_color else QColor(45, 52, 54)
        self.end_color = end_color if end_color else QColor(29, 43, 83)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, self.start_color)
        gradient.setColorAt(1, self.end_color)
        painter.setBrush(gradient)
        painter.drawRect(self.rect())

class ApiCallThread(QThread):
    """API调用线程，支持流式响应"""
    progress = pyqtSignal(int)  # 进度信号
    finished = pyqtSignal(str, str)  # 完成信号，传递响应文本和状态
    error = pyqtSignal(str)  # 错误信号
    content_update = pyqtSignal(str)  # 新增：内容更新信号，用于实时显示生成内容

    def __init__(self, api_type, api_url, api_key, prompt, model_name, api_format=None, custom_headers=None, max_chapter_length=5000):
        super().__init__()
        self.api_type = api_type
        self.api_url = api_url
        self.api_key = api_key
        self.prompt = prompt
        self.model_name = model_name
        self.api_format = api_format
        self.custom_headers = custom_headers
        self.max_chapter_length = max_chapter_length  # 最大章节字数限制
        self.response_text = ""  # 存储响应内容
        self.running = True  # 控制线程运行的标志
        self.last_progress_time = 0  # 上次进度更新时间
        self.last_progress_value = 0  # 上次进度值

    def stop(self):
        """停止API调用线程"""
        print(f"[调试] ApiCallThread.stop方法被调用")
        self.running = False
        self.quit()  # 退出事件循环
        print(f"[调试] ApiCallThread 事件循环已退出")
        # 设置超时，防止无限等待
        if not self.wait(2000):  # 等待2秒
            print(f"[调试] ApiCallThread 未在2秒内停止，强制终止")
            self.terminate()
            self.wait(1000)  # 再等待1秒确保终止
        print(f"[调试] ApiCallThread 已完全停止")
        
    def run(self):
        try:
            print(f"ApiCallThread开始运行，API类型: {self.api_type}")
            if self.api_type == "Ollama":
                self._call_ollama_api()
            elif self.api_type == "SiliconFlow":
                self._call_siliconflow_api()
            elif self.api_type == "ModelScope":
                self._call_modelscope_api()
            elif self.api_type == "自定义":
                self._call_custom_api()
            else:
                error_msg = f"不支持的API类型: {self.api_type}"
                print(error_msg)
                self.error.emit(error_msg)
                return
            
            # 完成所有响应
            print(f"API调用完成，准备触发finished信号，response长度: {len(self.response_text)}")
            print(f"response内容预览: {self.response_text[:100] if self.response_text else 'None'}...")
            
        except Exception as e:
            error_msg = f"API调用出错: {str(e)}"
            print(error_msg)
            import traceback
            print(f"异常堆栈: {traceback.format_exc()}")
            self.error.emit(error_msg)
        finally:
            # 确保无论如何都会触发finished信号
            if not hasattr(self, '_finished_emitted'):
                print(f"在finally块中触发finished信号，response长度: {len(self.response_text)}")
                self.finished.emit(self.response_text, "success")
                self._finished_emitted = True
    
    def _call_ollama_api(self):
        """调用Ollama API"""
        headers = {"Content-Type": "application/json"}
        data = {
            "model": self.model_name,
            "prompt": self.prompt,
            "stream": True,  # 启用流式传输
            "max_tokens": 5000,
            "temperature": 0.7
        }
        
        # 流式请求
        with requests.post(self.api_url, headers=headers, 
                          data=json.dumps(data), stream=True) as response:
            if response.status_code != 200:
                self.error.emit(f"API调用失败: {response.status_code} - 服务器暂时不可用或配置有误")
                return
                
            # 处理流式响应
            total_chars = 0
            for line in response.iter_lines():
                if not self.running:  # 检查是否应该停止
                    return
                    
                if line:
                    # 修复JSON解析错误：尝试直接提取response字段
                    try:
                        # 尝试解析为JSON
                        chunk = json.loads(line.decode('utf-8'))
                        if 'response' in chunk and chunk['response'] is not None:
                            self.response_text += chunk['response']
                            total_chars += len(chunk['response'])
                            # 发送内容更新信号，实现实时显示
                            self.content_update.emit(self.response_text)
                            # 计算进度（假设最大5000字符）
                            progress = min(100, int(total_chars / 5000 * 100))
                            # 限制进度更新频率
                            current_time = time.time()
                            if (progress - self.last_progress_value >= 5 or 
                                current_time - self.last_progress_time >= 1.0):
                                self.progress.emit(progress)
                                self.last_progress_value = progress
                                self.last_progress_time = current_time
                    except json.JSONDecodeError:
                        # 如果不是完整JSON，尝试直接提取文本内容
                        line_str = line.decode('utf-8')
                        if 'response' in line_str:
                            # 尝试提取response内容
                            try:
                                start_idx = line_str.find('"response":"') + len('"response":"')
                                end_idx = line_str.find('"', start_idx)
                                response_chunk = line_str[start_idx:end_idx]
                                self.response_text += response_chunk
                                total_chars += len(response_chunk)
                                # 发送内容更新信号，实现实时显示
                                self.content_update.emit(self.response_text)
                                progress = min(100, int(total_chars / 5000 * 100))
                                self.progress.emit(progress)
                            except:
                                # 如果提取失败，忽略这一行
                                pass
    
    def _call_siliconflow_api(self):
        """调用SiliconFlow API"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": self.prompt
                }
            ],
            "stream": True,  # 启用流式传输
            "max_tokens": 5000,
            "temperature": 0.7
        }
        
        # 流式请求
        with requests.post(self.api_url, headers=headers, 
                          data=json.dumps(data), stream=True) as response:
            if response.status_code != 200:
                self.error.emit(f"API调用失败: {response.status_code} - 服务器暂时不可用或配置有误")
                return
                
            # 处理流式响应
            total_chars = 0
            for line in response.iter_lines():
                if not self.running:  # 检查是否应该停止
                    return
                    
                if line:
                    # 处理SiliconFlow的流式响应格式
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        line_str = line_str[6:]  # 移除"data: "前缀
                        
                    if line_str == "[DONE]":
                        break
                        
                    try:
                        # 尝试解析为JSON
                        chunk = json.loads(line_str)
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            choice = chunk['choices'][0]
                            if 'delta' in choice and 'content' in choice['delta']:
                                content = choice['delta']['content']
                                if content is not None:  # 检查content是否为None
                                    self.response_text += content
                                    total_chars += len(content)
                                    # 发送内容更新信号，实现实时显示
                                    self.content_update.emit(self.response_text)
                                    # 计算进度（假设最大5000字符）
                                    progress = min(100, int(total_chars / 5000 * 100))
                                    # 限制进度更新频率
                                    current_time = time.time()
                                    if (progress - self.last_progress_value >= 5 or 
                                        current_time - self.last_progress_time >= 1.0):
                                        self.progress.emit(progress)
                                        self.last_progress_value = progress
                                        self.last_progress_time = current_time
                    except json.JSONDecodeError:
                        # 如果不是完整JSON，尝试直接提取内容
                        if '"content":"' in line_str:
                            try:
                                start_idx = line_str.find('"content":"') + len('"content":"')
                                end_idx = line_str.find('"', start_idx)
                                content = line_str[start_idx:end_idx]
                                if content is not None:  # 检查content是否为None
                                    self.response_text += content
                                    total_chars += len(content)
                                    # 发送内容更新信号，实现实时显示
                                    self.content_update.emit(self.response_text)
                                    progress = min(100, int(total_chars / 5000 * 100))
                                    self.progress.emit(progress)
                            except:
                                # 如果提取失败，忽略这一行
                                    pass
    
    def _call_modelscope_api(self):
        """调用ModelScope API"""
        print(f"开始调用ModelScope API: {self.api_url}")
        print(f"使用模型: {self.model_name}")
        print(f"API密钥: {self.api_key[:10]}..." if len(self.api_key) > 10 else "API密钥为空")
        
        # 验证API密钥
        if not self.api_key or len(self.api_key.strip()) == 0:
            error_msg = "API密钥为空，请检查ModelScope API配置"
            print(error_msg)
            self.error.emit(error_msg)
            return
        
        try:
            # 设置请求头 - ModelScope API使用特定的认证格式
            headers = {
                "Authorization": f"Bearer {self.api_key.strip()}",
                "Content-Type": "application/json",
                "User-Agent": "ModelScope-Client/1.0"
            }
            
            # 动态计算max_tokens，根据用户设置的字数限制
            # 假设中文字符与token的比例约为1:1.5（保守估计）
            max_chars = self.max_chapter_length  # 直接使用用户设置的值
            max_tokens = int(max_chars * 1.5)  # 转换为token数
            
            # 构建请求数据 - 启用流式传输
            data = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": self.prompt
                    }
                ],
                "max_tokens": max_tokens,  # 动态设置最大token数
                "temperature": 0.7,
                "top_p": 0.9,
                "stream": True  # 启用流式传输
            }
            
            print(f"请求数据: {json.dumps(data, ensure_ascii=False)}")
            print(f"请求头: {headers}")
            
            # 发送流式请求
            print("发送流式API请求...")
            response = requests.post(
                self.api_url,
                headers=headers,
                data=json.dumps(data),
                stream=True,
                timeout=60
            )
            
            print(f"响应状态码: {response.status_code}")
            print(f"响应头: {response.headers}")
            
            if response.status_code != 200:
                error_msg = f"API调用失败: {response.status_code} - 服务器暂时不可用或配置有误"
                try:
                    error_detail = response.json()
                    print(f"错误详情: {error_detail}")
                    if "error" in error_detail:
                        error_msg += f" - {error_detail['error']}"
                    elif "message" in error_detail:
                        error_msg += f" - {error_detail['message']}"
                except:
                    error_msg += f" - {response.text[:200]}"
                print(error_msg)
                self.error.emit(error_msg)
                return
            
            # 处理流式响应
            total_chars = 0
            for line in response.iter_lines():
                if not self.running:  # 检查是否应该停止
                    return
                    
                if line:
                    line_str = line.decode('utf-8')
                    
                    # 处理流式响应格式
                    if line_str.startswith("data: "):
                        line_str = line_str[6:]  # 移除"data: "前缀
                        
                    if line_str == "[DONE]":
                        break
                        
                    try:
                        # 尝试解析为JSON
                        chunk = json.loads(line_str)
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            choice = chunk['choices'][0]
                            if 'delta' in choice and 'content' in choice['delta']:
                                content = choice['delta']['content']
                                if content is not None:  # 检查content是否为None
                                    self.response_text += content
                                    total_chars += len(content)
                                    # 发送内容更新信号，实现实时显示
                                    self.content_update.emit(self.response_text)
                                    # 计算进度（假设最大5000字符）
                                    progress = min(100, int(total_chars / 5000 * 100))
                                    # 限制进度更新频率
                                    current_time = time.time()
                                    if (progress - self.last_progress_value >= 5 or 
                                        current_time - self.last_progress_time >= 1.0):
                                        self.progress.emit(progress)
                                        self.last_progress_value = progress
                                        self.last_progress_time = current_time
                    except json.JSONDecodeError:
                        # 如果不是完整JSON，尝试直接提取内容
                        if '"content":"' in line_str:
                            try:
                                start_idx = line_str.find('"content":"') + len('"content":"')
                                end_idx = line_str.find('"', start_idx)
                                content = line_str[start_idx:end_idx]
                                if content is not None:  # 检查content是否为None
                                    self.response_text += content
                                    total_chars += len(content)
                                    # 发送内容更新信号，实现实时显示
                                    self.content_update.emit(self.response_text)
                                    progress = min(100, int(total_chars / 5000 * 100))
                                    self.progress.emit(progress)
                            except:
                                # 如果提取失败，忽略这一行
                                pass
            
        except requests.exceptions.Timeout:
            error_msg = "API调用超时，可能是网络连接不稳定或服务器响应较慢。请检查网络连接或减小生成长度。"
            print(error_msg)
            self.error.emit(error_msg)
            
        except requests.exceptions.ConnectionError:
            error_msg = "网络连接失败，请检查网络是否正常"
            print(error_msg)
            self.error.emit(error_msg)
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP错误: {str(e)}"
            print(error_msg)
            self.error.emit(error_msg)
            
        except Exception as e:
            error_msg = f"ModelScope API调用错误: {str(e)}"
            print(error_msg)
            import traceback
            print(f"异常堆栈: {traceback.format_exc()}")
            self.error.emit(error_msg)
        # 移除else分支，避免重复发送finished信号
        # finished信号将在run方法的finally块中发送
    
    def _call_custom_api(self):
        """调用自定义API"""
        print(f"开始调用自定义API: {self.api_url}")
        print(f"API格式: {self.api_format}")
        
        try:
            # 解析自定义请求头
            headers = {"Content-Type": "application/json"}
            if self.custom_headers:
                try:
                    custom_headers = json.loads(self.custom_headers)
                    headers.update(custom_headers)
                    print(f"自定义请求头: {headers}")
                except json.JSONDecodeError:
                    print("警告：自定义请求头格式错误，请确保是有效的JSON格式")
                    self.error.emit("自定义请求头格式错误，请确保是有效的JSON格式")
                    return
            else:
                print("使用默认请求头")
            
            # 动态计算max_tokens，根据用户设置的字数限制
            max_chars = self.max_chapter_length  # 直接使用用户设置的值
            max_tokens = int(max_chars * 1.5)  # 转换为token数
            
            # 根据API格式构建请求数据
            if self.api_format == "OpenAI格式":
                data = {
                    "model": self.model_name,
                    "messages": [
                        {
                            "role": "user",
                            "content": self.prompt
                        }
                    ],
                    "stream": True,  # 启用流式传输
                    "max_tokens": max_tokens,  # 动态设置最大token数
                    "temperature": 0.7
                }
            else:  # Ollama格式
                data = {
                    "model": self.model_name,
                    "prompt": self.prompt,
                    "stream": True,  # 启用流式传输
                    "max_tokens": max_tokens,  # 动态设置最大token数
                    "temperature": 0.7
                }
            
            print(f"请求数据: {json.dumps(data, ensure_ascii=False)}")
            
            # 流式请求
            print("发送API请求...")
            with requests.post(self.api_url, headers=headers, 
                              data=json.dumps(data), stream=True) as response:
                print(f"响应状态码: {response.status_code}")
                if response.status_code != 200:
                    error_msg = f"API调用失败: {response.status_code} - 服务器暂时不可用或配置有误"
                    try:
                        error_detail = response.json()
                        print(f"错误详情: {error_detail}")
                        if "error" in error_detail:
                            error_msg += f" - {error_detail['error']}"
                        elif "message" in error_detail:
                            error_msg += f" - {error_detail['message']}"
                    except:
                        error_msg += f" - {response.text[:200]}"
                    print(error_msg)
                    self.error.emit(error_msg)
                    return
                    
                # 处理流式响应
                print("开始处理流式响应...")
                total_chars = 0
                for line in response.iter_lines():
                    if not self.running:  # 检查是否应该停止
                        print("API调用被停止")
                        return
                        
                    if line:
                        # 根据API格式处理响应
                        if self.api_format == "OpenAI格式":
                            # 处理OpenAI格式的流式响应
                            line_str = line.decode('utf-8')
                            if line_str.startswith("data: "):
                                line_str = line_str[6:]  # 移除"data: "前缀
                                
                            if line_str == "[DONE]":
                                print("OpenAI API响应完成")
                                break
                                
                            try:
                                # 尝试解析为JSON
                                chunk = json.loads(line_str)
                                if 'choices' in chunk and len(chunk['choices']) > 0:
                                    choice = chunk['choices'][0]
                                    if 'delta' in choice and 'content' in choice['delta']:
                                        content = choice['delta']['content']
                                        if content is not None:  # 检查content是否为None
                                            self.response_text += content
                                            total_chars += len(content)
                                            # 发送内容更新信号，实现实时显示
                                            self.content_update.emit(self.response_text)
                                            # 计算进度（假设最大5000字符）
                                            progress = min(100, int(total_chars / 5000 * 100))
                                            # 限制进度更新频率
                                            current_time = time.time()
                                            if (progress - self.last_progress_value >= 5 or 
                                                current_time - self.last_progress_time >= 1.0):
                                                self.progress.emit(progress)
                                                self.last_progress_value = progress
                                                self.last_progress_time = current_time
                            except json.JSONDecodeError:
                                # 如果不是完整JSON，尝试直接提取内容
                                if '"content":"' in line_str:
                                    try:
                                        start_idx = line_str.find('"content":"') + len('"content":"')
                                        end_idx = line_str.find('"', start_idx)
                                        content = line_str[start_idx:end_idx]
                                        if content is not None:  # 检查content是否为None
                                            self.response_text += content
                                            total_chars += len(content)
                                            # 发送内容更新信号，实现实时显示
                                            self.content_update.emit(self.response_text)
                                            progress = min(100, int(total_chars / 5000 * 100))
                                            self.progress.emit(progress)
                                    except:
                                        # 如果提取失败，忽略这一行
                                        pass
                        else:  # Ollama格式
                            # 处理Ollama格式的流式响应
                            try:
                                # 尝试解析为JSON
                                chunk = json.loads(line.decode('utf-8'))
                                if 'response' in chunk and chunk['response'] is not None:
                                    self.response_text += chunk['response']
                                    total_chars += len(chunk['response'])
                                    # 发送内容更新信号，实现实时显示
                                    self.content_update.emit(self.response_text)
                                    # 计算进度（假设最大5000字符）
                                    progress = min(100, int(total_chars / 5000 * 100))
                                    # 限制进度更新频率
                                    current_time = time.time()
                                    if (progress - self.last_progress_value >= 5 or 
                                        current_time - self.last_progress_time >= 1.0):
                                        self.progress.emit(progress)
                                        self.last_progress_value = progress
                                        self.last_progress_time = current_time
                            except json.JSONDecodeError:
                                # 如果不是完整JSON，尝试直接提取文本内容
                                line_str = line.decode('utf-8')
                                if 'response' in line_str:
                                    # 尝试提取response内容
                                    try:
                                        start_idx = line_str.find('"response":"') + len('"response":"')
                                        end_idx = line_str.find('"', start_idx)
                                        response_chunk = line_str[start_idx:end_idx]
                                        self.response_text += response_chunk
                                        total_chars += len(response_chunk)
                                        # 发送内容更新信号，实现实时显示
                                        self.content_update.emit(self.response_text)
                                        progress = min(100, int(total_chars / 5000 * 100))
                                        # 限制进度更新频率
                                        current_time = time.time()
                                        if (progress - self.last_progress_value >= 5 or 
                                            current_time - self.last_progress_time >= 1.0):
                                            self.progress.emit(progress)
                                            self.last_progress_value = progress
                                            self.last_progress_time = current_time
                                    except:
                                        # 如果提取失败，忽略这一行
                                        pass
        except Exception as e:
            error_msg = f"自定义API调用错误: {str(e)}"
            print(error_msg)
            self.error.emit(error_msg)
        # 移除else分支，避免重复发送finished信号
        # finished信号将在run方法的finally块中发送
    
    def stop(self):
        """停止API调用线程"""
        print("[调试] ApiCallThread.stop() 被调用")
        self.running = False
        self.quit()  # 退出事件循环
        print("[调试] ApiCallThread 事件循环已退出")
        # 设置超时，防止无限等待
        if not self.wait(2000):  # 等待2秒
            print("[调试] ApiCallThread 未在2秒内停止，强制终止")
            self.terminate()
            self.wait(1000)  # 再等待1秒确保终止
        print("[调试] ApiCallThread 已完全停止")



class AutoSaveThread(QThread):
    """自动保存线程，用于在后台自动保存小说内容"""
    save_complete = pyqtSignal(str)  # 保存完成信号，传递文件路径
    save_error = pyqtSignal(str)  # 保存错误信号
    
    def __init__(self, app, save_interval=30):
        super().__init__()
        self.app = app
        self.save_interval = save_interval  # 保存间隔（秒）
        self.running = False
        self.last_content = ""  # 上次保存的内容
        
    def run(self):
        """运行自动保存线程"""
        self.running = True
        while self.running:
            # 检查是否有内容需要保存
            current_content = self.app.get_current_content()
            if current_content and current_content != self.last_content:
                try:
                    # 保存内容
                    file_path = self.app.save_current_content()
                    if file_path:  # 只有在成功保存且返回文件路径时才更新内容和发送信号
                        self.last_content = current_content
                        self.save_complete.emit(file_path)
                except Exception as e:
                    self.save_error.emit(f"自动保存失败: {str(e)}")
            
            # 等待指定时间
            self.sleep(self.save_interval)
    
    def stop(self):
        """停止自动保存线程"""
        self.running = False
        # 添加超时机制，防止无限等待
        if not self.wait(2000):  # 等待2秒
            self.terminate()  # 强制终止线程

class ChapterGenerator(QThread):
    """章节生成线程，用于批量生成章节"""
    chapter_generated = pyqtSignal(int, str)  # 章节号，章节内容
    progress = pyqtSignal(int, int, int)  # 当前章节，总章节，进度百分比
    finished = pyqtSignal()
    error = pyqtSignal(str, int)  # 错误信息，章节号

    def __init__(self, app, start_chapter, end_chapter, overwrite_existing=False, read_previous_chapter=True):
        super().__init__()
        self.app = app
        self.start_chapter = start_chapter
        self.end_chapter = end_chapter
        self.overwrite_existing = overwrite_existing  # 是否覆盖已存在章节
        self.read_previous_chapter = read_previous_chapter  # 是否读取上一章内容作为上下文
        self.running = True
        self.paused = False
        self.current_chapter = start_chapter
        self.generation_queue = []  # 用于存储待生成的章节信息

    def run(self):
        print(f"[调试] ChapterGenerator.run方法被调用，起始章节: {self.start_chapter}, 结束章节: {self.end_chapter}")
        total_chapters = self.end_chapter - self.start_chapter + 1
        print(f"[调试] 总章节数: {total_chapters}")
        self.progress.emit(self.start_chapter, self.end_chapter, 0)
        print(f"[调试] 已发送进度信号")
        
        # 设置当前章节为起始章节
        self.current_chapter = self.start_chapter
        print(f"[调试] 当前章节设置为: {self.current_chapter}")
        
        # 开始异步生成章节
        print(f"[调试] 准备调用QTimer.singleShot触发_generate_next_chapter")
        QTimer.singleShot(100, self._generate_next_chapter)
        print(f"[调试] QTimer.singleShot已调用")
        
        # 启动事件循环，确保QTimer能正常工作
        print(f"[调试] 启动事件循环")
        self.exec()

    def save_chapter(self, chapter_num, title, content):
        """保存章节内容到文件"""
        # 使用章节保存路径
        chapter_save_path = self.chapter_path if hasattr(self, 'chapter_path') else "zhangjie"
        if not os.path.exists(chapter_save_path):
            try:
                os.makedirs(chapter_save_path)
                print(f"[调试] 创建章节目录: {chapter_save_path}")
            except Exception as e:
                self.error.emit(f"创建章节目录失败: {str(e)}", chapter_num)
                return
        
        # 获取小说标题
        novel_title_input = getattr(self.app, 'novel_title_input', None)
        novel_title = novel_title_input.text().strip() if novel_title_input else "未命名小说"
        
        # 使用简化的命名格式：第X章.txt
        # 不再包含章节标题和小说标题，只使用章节号
        file_name = f"第{chapter_num}章.txt"
        file_path = os.path.join(chapter_save_path, file_name)
        
        # 检查文件是否已存在
        if os.path.exists(file_path):
            # 根据文件行为设置决定如何处理已存在章节
            file_behavior = getattr(self.app, 'file_behavior', "询问")
            
            if file_behavior == "覆盖":
                # 直接覆盖保存
                try:
                    # 处理章节内容，移除可能存在的小说标题
                    processed_content = self._remove_novel_title_from_content(content, novel_title)
                    
                    with open(file_path, 'w', encoding='utf-8') as file:
                        file.write(processed_content)
                    print(f"章节已覆盖保存到: {file_path}")
                except Exception as e:
                    self.error.emit(f"保存章节失败: {str(e)}", chapter_num)
                return
            elif file_behavior == "跳过":
                # 跳过保存
                print(f"第{chapter_num}章已存在，根据设置跳过保存")
                return
            else:  # "询问"
                # 发送信号到主线程，让主线程处理用户选择
                self.app.chapter_to_save = (chapter_num, title, content, file_path)
                self.app.show_overwrite_dialog.emit(chapter_num, file_path)
                return
        
        # 如果文件不存在，直接保存
        try:
            # 处理章节内容，移除可能存在的小说标题
            processed_content = self._remove_novel_title_from_content(content, novel_title)
            
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(processed_content)
            print(f"章节已保存到: {file_path}")
        except Exception as e:
            self.error.emit(f"保存章节失败: {str(e)}", chapter_num)
    
    def extract_chapter_title(self, content):
        """从章节内容中提取章节标题"""
        # 尝试匹配格式：第X章：标题
        match = re.search(r'第\d+章[：:]\s*(.+?)(?:\n|$)', content)
        if match:
            title = match.group(1).strip()
            # 移除标题中可能包含的章节号，如"第四章"、"第4章"等
            title = re.sub(r'第[一二三四五六七八九十\d]+章[：:]?', '', title).strip()
            # 限制标题长度，避免文件名过长
            if len(title) > 20:
                title = title[:20] + "..."
            return self._sanitize_filename(title)
        
        # 尝试匹配Markdown格式：**第X章：标题**
        match = re.search(r'\*\*第\d+章[：:]\s*(.+?)\*\*', content)
        if match:
            title = match.group(1).strip()
            # 移除标题中可能包含的章节号，如"第四章"、"第4章"等
            title = re.sub(r'第[一二三四五六七八九十\d]+章[：:]?', '', title).strip()
            # 限制标题长度，避免文件名过长
            if len(title) > 20:
                title = title[:20] + "..."
            return self._sanitize_filename(title)
        
        # 尝试匹配格式：**《小说名》第X章**
        match = re.search(r'\*\*《.+?》第(\d+)章\*\*', content)
        if match:
            # 对于这种格式，我们使用章节号作为标题的一部分
            chapter_num = match.group(1)
            title = f"第{chapter_num}章"
            return self._sanitize_filename(title)
        
        # 如果没有找到标准格式，尝试匹配其他可能的标题格式
        # 例如：**标题** 或 标题（单独一行）
        lines = content.split('\n')
        for i, line in enumerate(lines[:5]):  # 只检查前5行
            line = line.strip()
            # 匹配**标题**格式
            if line.startswith('**') and line.endswith('**'):
                title = line[2:-2].strip()
                # 移除标题中可能包含的章节号，如"第四章"、"第4章"等
                title = re.sub(r'第[一二三四五六七八九十\d]+章[：:]?', '', title).strip()
                if len(title) > 20:
                    title = title[:20] + "..."
                return self._sanitize_filename(title)
            
            # 如果是单独一行的短文本，可能是标题
            if len(line) > 0 and len(line) < 30 and i < 3:
                # 检查是否包含常见的标题关键词
                if any(keyword in line for keyword in ['章', '回', '节', '卷', '篇']):
                    # 移除标题中可能包含的章节号，如"第四章"、"第4章"等
                    title = re.sub(r'第[一二三四五六七八九十\d]+章[：:]?', '', line).strip()
                    if len(title) > 20:
                        title = title[:20] + "..."
                    return self._sanitize_filename(title)
        
        # 如果都没有找到，返回默认标题
        return "未命名章节"
    
    def _remove_novel_title_from_content(self, content, novel_title):
        """从章节内容中移除小说标题"""
        if not novel_title or not content:
            return content
            
        # 创建小说标题的可能格式
        title_patterns = [
            f"**《{novel_title}》**",  # Markdown格式 - 修复了模式匹配
            f"《{novel_title}》",     # 普通格式
            f"{novel_title}",         # 只有标题名
        ]
        
        # 处理内容，移除小说标题
        lines = content.split('\n')
        processed_lines = []
        
        for line in lines:
            should_remove_line = False
            stripped_line = line.strip()
            
            # 检查是否是小说标题行
            for pattern in title_patterns:
                # 如果行中只有小说标题或者小说标题在行首，则移除整行
                if stripped_line == pattern or stripped_line.startswith(pattern):
                    should_remove_line = True
                    break
            
            # 额外检查：如果行包含**《...》**格式，即使不完全匹配也尝试移除
            if not should_remove_line and '**《' in stripped_line and '》**' in stripped_line:
                # 提取标题名
                match = re.search(r'\*\*《(.+?)》\*\*', stripped_line)
                if match and match.group(1).strip() == novel_title:
                    should_remove_line = True
            
            # 如果不是小说标题行，保留该行
            if not should_remove_line:
                processed_lines.append(line)
        
        return '\n'.join(processed_lines)
    
    def _sanitize_filename(self, filename):
        """清理文件名中的非法字符"""
        # Windows文件名中不允许的字符（注意：这里不包括冒号，因为我们希望在章节标题中保留它）
        illegal_chars = r'[<>"/\\|?*]'
        # 替换非法字符为下划线
        sanitized = re.sub(illegal_chars, '_', filename)
        
        # 移除所有星号
        sanitized = sanitized.replace('*', '')
        
        # 替换中文标点为英文标点
        sanitized = sanitized.replace('·', '_')  # 中文点号替换为下划线
        
        # 移除多余的下划线（连续多个下划线替换为单个）
        sanitized = re.sub(r'_+', '_', sanitized)
        
        # 移除开头和结尾的空格、点和下划线
        sanitized = sanitized.strip(' ._')
        
        # 如果处理后为空，返回默认名称
        if not sanitized:
            return "未命名章节"
        return sanitized
    
    def continue_generation(self):
        """继续生成下一章"""
        # 检查是否已停止
        if not self.running:
            print("[调试] 生成已停止，退出事件循环")
            self.quit()  # 退出事件循环
            self.finished.emit()
            return
            
        # 恢复暂停状态
        self.paused = False
        
        # 如果当前章节已经是最后一章，结束生成
        if self.current_chapter >= self.end_chapter:
            print("[调试] 所有章节生成完成，退出事件循环")
            self.quit()  # 退出事件循环
            self.finished.emit()
            return
        
        # 继续生成下一章
        self.current_chapter += 1
        
        # 重新调用run方法中的生成逻辑
        # 由于我们使用了异步方式，需要手动调用生成逻辑
        self._generate_next_chapter()
    
    def _generate_next_chapter(self):
        """生成下一章的内部方法"""
        print(f"[调试] _generate_next_chapter方法被调用")
        chapter = self.current_chapter
        total_chapters = self.end_chapter - self.start_chapter + 1
        print(f"[调试] 当前章节: {chapter}, 总章节数: {total_chapters}")
        
        # 更新进度
        progress = int((chapter - self.start_chapter) / total_chapters * 100)
        self.progress.emit(chapter, self.end_chapter, progress)
        
        # 检查章节是否已存在
        # 使用最新的文件名格式：第X章.txt 或旧格式 第X章_《小说标题》.txt
        save_path = self.app.save_path
        if not os.path.exists(save_path):
            os.makedirs(save_path)
            
        # 获取小说标题
        title = self.app.novel_title_input.text().strip()
        title = title if title else "未命名小说"
        
        # 首先检查最新格式的文件是否存在
        latest_format_file = os.path.join(save_path, f"第{chapter}章.txt")
        
        # 如果找到了最新格式的文件，使用它
        if os.path.exists(latest_format_file):
            file_path = latest_format_file
        else:
            # 检查新格式的文件是否存在
            new_format_file = os.path.join(save_path, f"第{chapter}章.txt")
            
            # 如果找到了新格式的文件，使用它
            if os.path.exists(new_format_file):
                file_path = new_format_file
            else:
                # 尝试旧格式：第X章：标题_小说标题.txt
                import glob
                pattern = os.path.join(save_path, f"第{chapter}章*_{title}.txt")
                matching_files = glob.glob(pattern)
                
                # 如果没有找到新格式的文件，检查旧格式的文件
                old_format_file = os.path.join(save_path, f"第{chapter}章_{title}.txt")
                if os.path.exists(old_format_file):
                    matching_files.append(old_format_file)
                
                file_path = matching_files[0] if matching_files else None
        
        print(f"检查第{chapter}章文件是否存在: {file_path if file_path else '未找到'}")
        if file_path and os.path.exists(file_path):
            # 根据文件行为设置决定如何处理已存在章节
            file_behavior = getattr(self.app, 'file_behavior', "询问")
            
            if file_behavior == "覆盖":
                print(f"第{chapter}章已存在，根据设置将覆盖生成")
            elif file_behavior == "跳过":
                # 跳过已存在章节
                try:
                    print(f"第{chapter}章已存在，根据设置将跳过生成")
                    with open(file_path, 'r', encoding='utf-8') as file:
                        content = file.read()
                    self.chapter_generated.emit(chapter, content)
                    
                    # 更新进度
                    progress = int((chapter - self.start_chapter + 1) / total_chapters * 100)
                    self.progress.emit(chapter, self.end_chapter, progress)
                    
                    print(f"第{chapter}章已存在，跳过生成")
                    # 继续生成下一章
                    QTimer.singleShot(100, self.continue_generation)
                    return
                except Exception as e:
                    print(f"读取已存在章节失败: {e}")
                    # 如果读取失败，继续生成新章节
                    print(f"将重新生成第{chapter}章")
            else:  # "询问"
                # 如果章节已存在，根据overwrite_existing标志决定是否跳过
                if self.overwrite_existing:
                    print(f"第{chapter}章已存在，根据用户选择将覆盖生成")
                else:
                    # 跳过已存在章节
                    try:
                        print(f"第{chapter}章已存在，准备读取文件内容")
                        with open(file_path, 'r', encoding='utf-8') as file:
                            content = file.read()
                        self.chapter_generated.emit(chapter, content)
                        
                        # 更新进度
                        progress = int((chapter - self.start_chapter + 1) / total_chapters * 100)
                        self.progress.emit(chapter, self.end_chapter, progress)
                        
                        print(f"第{chapter}章已存在，跳过生成")
                        # 继续生成下一章
                        QTimer.singleShot(100, self.continue_generation)
                        return
                    except Exception as e:
                        print(f"读取已存在章节失败: {e}")
                        # 如果读取失败，继续生成新章节
                        print(f"将重新生成第{chapter}章")
        
        try:
            # 获取小说标题（已在上面获取）
            # title = self.app.novel_title_input.text().strip()
            # title = title if title else "未命名小说"
            
            # 在配置的字数范围内随机选择一个目标字数
            target_length = random.randint(self.app.min_chapter_length, self.app.max_chapter_length)
            
            # 读取上一章内容（如果存在且用户选择了该选项）
            previous_chapter_content = ""
            if self.read_previous_chapter and chapter > self.start_chapter:  # 不是第一章且用户选择了读取上一章内容
                prev_chapter = chapter - 1
                save_path = self.app.save_path
                
                # 首先尝试最新格式：第X章.txt
                latest_format_file = os.path.join(save_path, f"第{prev_chapter}章.txt")
                
                # 如果找到了最新格式的文件，使用它
                if os.path.exists(latest_format_file):
                    prev_file_path = latest_format_file
                else:
                    # 尝试新格式：第X章.txt
                    new_format_file = os.path.join(save_path, f"第{prev_chapter}章.txt")
                    
                    # 如果找到了新格式的文件，使用它
                    if os.path.exists(new_format_file):
                        prev_file_path = new_format_file
                    else:
                        # 尝试旧格式：第X章：标题_小说标题.txt
                        import glob
                        pattern = os.path.join(save_path, f"第{prev_chapter}章*_{title}.txt")
                        matching_files = glob.glob(pattern)
                        
                        # 如果没有找到新格式的文件，检查旧格式的文件
                        old_format_file = os.path.join(save_path, f"第{prev_chapter}章_{title}.txt")
                        if os.path.exists(old_format_file):
                            matching_files.append(old_format_file)
                        
                        prev_file_path = matching_files[0] if matching_files else None
                
                if prev_file_path and os.path.exists(prev_file_path):
                    try:
                        with open(prev_file_path, 'r', encoding='utf-8') as file:
                            previous_chapter_content = file.read()
                        print(f"已读取第{prev_chapter}章内容作为上下文，长度: {len(previous_chapter_content)}")
                    except Exception as e:
                        print(f"读取上一章内容失败: {e}")
                else:
                    print(f"未找到第{prev_chapter}章文件，无法读取上一章内容")
            
            # 优化提示词
            prompt = f"请根据以下小说大纲生成《{title}》的第{chapter}章内容：\n"
            prompt += self.app.outline_text.toPlainText() + "\n\n"
            
            # 添加男女主角信息到提示词
            hero_name = self.app.hero_name.text().strip() if self.app.hero_name.text().strip() else "男主角"
            heroine_name = self.app.heroine_name.text().strip() if self.app.heroine_name.text().strip() else "女主角"
            
            prompt += f"【重要角色信息】\n"
            prompt += f"男主角：{hero_name}\n"
            prompt += f"女主角：{heroine_name}\n"
            prompt += f"请确保在章节内容中正确使用以上角色名字，不要混淆男女主角的名字。\n\n"
            
            # 如果有上一章内容，添加到提示词中
            if previous_chapter_content:
                # 获取上一章的最后部分（限制长度以避免提示词过长）
                prev_content_end = previous_chapter_content[-1000:] if len(previous_chapter_content) > 1000 else previous_chapter_content
                prompt += f"上一章（第{chapter-1}章）结尾内容：\n{prev_content_end}\n\n"
                prompt += f"请确保新章节与上一章内容衔接自然，情节连贯。\n\n"
            
            prompt += f"章节具体要求：\n"
            prompt += f"- 保持{self.app.pov_combo.currentText()}视角\n"
            prompt += f"- 使用{self.app.lang_combo.currentText()}风格\n"
            prompt += f"- 节奏：{self.app.rhythm_combo.currentText()}\n"
            prompt += f"- 字数：约{target_length}字\n"
            prompt += f"- 必须在章节开头添加一个吸引人的章节标题，格式为'第{chapter}章：[章节标题]'\n"
            prompt += f"- 章节标题必须独特且能反映本章主要情节，避免重复使用相同标题\n"
            prompt += f"- 章节标题应该简洁明了，不超过15个字，能够概括本章的核心事件或情感变化\n"
            prompt += f"- 重要：不要在章节内容中添加小说标题'《{title}》'，章节内容直接从章节标题开始\n"
            prompt += f"- 特别注意：必须正确使用角色名字，男主角是{hero_name}，女主角是{heroine_name}，不要混淆\n"
            
            # 调用API生成章节 - 使用流式API线程
            api_format = getattr(self.app, 'api_format', None)
            custom_headers = getattr(self.app, 'custom_headers', None)
            
            print(f"生成第{chapter}章: API类型={self.app.api_type}, 模型={self.app.model_name}")
            if self.app.api_type == "自定义":
                print(f"API格式: {api_format}")
                print(f"自定义请求头: {custom_headers}")
            
            # 使用信号槽机制处理API响应，避免阻塞UI
            self.api_thread = ApiCallThread(self.app.api_type, self.app.api_url, self.app.api_key, prompt, self.app.model_name, api_format, custom_headers)
            
            # 创建临时变量来保存当前章节信息，供回调函数使用
            current_chapter_info = {
                'chapter': chapter,
                'title': title,
                'total_chapters': total_chapters
            }
            
            # 定义API完成的回调函数
            def on_api_finished(response_text, status):
                print(f"[调试] API完成回调被调用，状态: {status}, 响应长度: {len(response_text) if response_text else 0}")
                
                if status == "success" and response_text:
                    print(f"[调试] 第{current_chapter_info['chapter']}章生成完成，长度: {len(response_text)}")
                    
                    # 提取章节标题
                    chapter_title = ""
                    lines = response_text.split('\n')
                    for line in lines:
                        line = line.strip()
                        # 检查是否是章节标题行
                        if line.startswith(f"第{current_chapter_info['chapter']}章："):
                            # 提取章节标题（去掉"第X章："前缀）
                            chapter_title = line[len(f"第{current_chapter_info['chapter']}章："):].strip()
                            # 清理标题中的Markdown标记
                            chapter_title = chapter_title.replace('**', '').replace('*', '').strip()
                            # 如果标题太长，截取前15个字符
                            if len(chapter_title) > 15:
                                chapter_title = chapter_title[:15] + "..."
                            break
                    
                    # 如果没有找到章节标题，根据章节内容生成一个
                    if not chapter_title:
                        # 尝试从内容中提取关键信息作为标题
                        content_preview = response_text[:200]  # 取前200字符作为预览
                        # 使用智能标题生成方法
                        chapter_title = self._generate_smart_title(content_preview, current_chapter_info['chapter'])
                    
                    # 保存章节内容
                    try:
                        self.save_chapter(current_chapter_info['chapter'], chapter_title, response_text)
                        print(f"[调试] 第{current_chapter_info['chapter']}章已保存")
                    except Exception as e:
                        print(f"[调试] 保存第{current_chapter_info['chapter']}章失败: {e}")
                    
                    # 发送信号通知主窗口更新UI
                    print(f"[调试] 即将发送chapter_generated信号，章节号: {current_chapter_info['chapter']}, 内容长度: {len(response_text)}")
                    self.chapter_generated.emit(current_chapter_info['chapter'], response_text)
                    print(f"[调试] chapter_generated信号已发送")
                    
                    # 更新进度
                    progress = int((current_chapter_info['chapter'] - self.start_chapter + 1) / current_chapter_info['total_chapters'] * 100)
                    self.progress.emit(current_chapter_info['chapter'], self.end_chapter, progress)
                    
                    # 继续生成下一章
                    QTimer.singleShot(100, self.continue_generation)
                else:
                    print(f"[调试] API响应为空或失败，状态: {status}")
                    self.error.emit(f"第{current_chapter_info['chapter']}章生成为空内容", current_chapter_info['chapter'])
                    # 继续生成下一章
                    QTimer.singleShot(100, self.continue_generation)
            
            # 定义API错误的回调函数
            def on_api_error(error_msg):
                self.error.emit(f"生成第{current_chapter_info['chapter']}章时出错: {error_msg}", current_chapter_info['chapter'])
                # 继续生成下一章
                QTimer.singleShot(100, self.continue_generation)
            
            # 定义内容更新的回调函数
            def on_content_update(content):
                """处理API返回的内容更新，实现实时显示"""
                # 发送批量内容更新信号，以便主窗口可以区分是批量生成还是单章生成
                if hasattr(self.app, 'on_batch_content_update'):
                    self.app.on_batch_content_update(current_chapter_info['chapter'], content)
            
            # 连接信号
            self.api_thread.finished.connect(on_api_finished)
            self.api_thread.error.connect(on_api_error)
            # 新增：连接内容更新信号，实现实时显示
            self.api_thread.content_update.connect(on_content_update)
            self.api_thread.start()
            
            # 暂停当前循环，等待API响应
            self.paused = True
            return
            
        except Exception as e:
            self.error.emit(f"生成第{chapter}章时出错: {str(e)}", chapter)
            # 继续生成下一章
            QTimer.singleShot(100, self.continue_generation)
            
    def _generate_smart_title(self, content_preview, chapter_num):
        """智能生成章节标题，根据内容自动提取关键词"""
        import re
        
        # 尝试从内容中提取关键信息作为标题
        # 1. 尝试提取地点
        location_patterns = [
            r'在([^，。！？\n]{2,8})',
            r'来到([^，。！？\n]{2,8})',
            r'进入([^，。！？\n]{2,8})',
            r'离开([^，。！？\n]{2,8})',
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, content_preview)
            if match:
                location = match.group(1)
                # 过滤掉一些常见的非地点词汇
                if location not in ['时候', '这里', '那里', '哪里', '什么', '怎么', '为什么']:
                    return f"{location}之行"
        
        # 2. 尝试提取事件
        event_patterns = [
            r'发现([^，。！？\n]{2,8})',
            r'找到([^，。！？\n]{2,8})',
            r'遇到([^，。！？\n]{2,8})',
            r'经历([^，。！？\n]{2,8})',
            r'面对([^，。！？\n]{2,8})',
        ]
        
        for pattern in event_patterns:
            match = re.search(pattern, content_preview)
            if match:
                event = match.group(1)
                return f"{event}之事"
        
        # 3. 尝试提取情感或状态
        emotion_patterns = [
            r'感到([^，。！？\n]{2,6})',
            r'心情([^，。！？\n]{2,6})',
            r'觉得([^，。！？\n]{2,6})',
        ]
        
        for pattern in emotion_patterns:
            match = re.search(pattern, content_preview)
            if match:
                emotion = match.group(1)
                return f"{emotion}之心"
        
        # 4. 尝试提取人物对话中的关键词
        dialogue_patterns = [
            r'"([^"]{4,10})"',
            r'"([^"]{4,10})"',
            r'「([^」]{4,10})」',
            r'『([^』]{4,10})』',
        ]
        
        for pattern in dialogue_patterns:
            match = re.search(pattern, content_preview)
            if match:
                dialogue = match.group(1)
                # 如果对话中包含重要信息，可以作为标题
                if any(keyword in dialogue for keyword in ['秘密', '真相', '发现', '危险', '计划', '决定']):
                    return dialogue[:8]  # 限制长度
        
        # 5. 尝试提取关键名词
        noun_patterns = [
            r'([一个两三四五六七八九十]+[^，。！？\n]{2,8})',
            r'([那这此某]+[^，。！？\n]{2,8})',
        ]
        
        for pattern in noun_patterns:
            matches = re.findall(pattern, content_preview)
            if matches:
                # 选择第一个匹配的名词
                noun = matches[0]
                # 过滤掉一些常见的非重要名词
                if noun not in ['一个人', '一件事', '一个地方', '一个时候', '一个晚上']:
                    return f"关于{noun}"
        
        # 6. 如果以上方法都不适用，使用通用标题
        generic_titles = [
            f"第{chapter_num}章：新的开始",
            f"第{chapter_num}章：意外发现",
            f"第{chapter_num}章：重要转折",
            f"第{chapter_num}章：关键决定",
            f"第{chapter_num}章：未知前路",
        ]
        
        # 根据章节号选择一个通用标题
        return generic_titles[chapter_num % len(generic_titles)]

    def _extract_chapter_title(self, content, chapter_num):
        """从章节内容中提取或生成章节标题"""
        # 尝试从内容中提取标题
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            # 检查是否是标题行（可能包含"第X章"或"标题："等）
            if (f"第{chapter_num}章" in line and len(line) > len(f"第{chapter_num}章")) or \
               (line.startswith("标题：") and len(line) > 3) or \
               (line.startswith("章节标题：") and len(line) > 5):
                # 清理标题，去除可能的标记
                title = line.replace(f"第{chapter_num}章", "").replace("标题：", "").replace("章节标题：", "").strip()
                # 去除可能的特殊字符
                title = ''.join(c for c in title if c.isalnum() or c in (' ', '-', '_', '（', '）', '(', ')'))
                if title:
                    return title
        
        # 如果没有找到标题，尝试从第一行非空行获取
        for line in lines:
            if line.strip():
                # 使用第一行作为标题，但限制长度
                title = line.strip()[:20]
                # 去除可能的特殊字符
                title = ''.join(c for c in title if c.isalnum() or c in (' ', '-', '_', '（', '）', '(', ')'))
                if title:
                    return title
        
        # 如果仍然没有合适的标题，使用默认标题
        return f"章节{chapter_num}"

    def stop(self):
        """停止生成"""
        print(f"[调试] ChapterGenerator.stop方法被调用")
        self.running = False
        self.paused = False
        # 清空生成队列
        self.generation_queue = []
        # 停止API调用线程
        if hasattr(self, 'api_thread') and self.api_thread and self.api_thread.isRunning():
            print(f"[调试] 停止API调用线程")
            self.api_thread.stop()
            # 等待线程完全停止，设置超时时间
            if not self.api_thread.wait(3000):  # 等待3秒
                print(f"[调试] API调用线程未在3秒内停止，强制终止")
                self.api_thread.terminate()
                self.api_thread.wait(1000)  # 再等待1秒确保终止
            print(f"[调试] API调用线程已停止")
        # 退出事件循环
        self.quit()
        print(f"[调试] 已调用quit()退出事件循环")
        # 等待事件循环完全退出
        if not self.wait(2000):  # 等待2秒
            print(f"[调试] 事件循环未在2秒内退出，强制终止")
            self.terminate()
        print(f"[调试] ChapterGenerator已完全停止")
        
    def pause(self):
        """暂停生成"""
        self.paused = True
        
    def resume(self):
        """继续生成"""
        self.paused = False

class ApiTestThread(QThread):
    """API测试线程，用于测试API连接是否正常"""
    test_result = pyqtSignal(bool, str)  # 测试结果（成功/失败），消息
    
    def __init__(self, api_type, api_url, api_key, model_name):
        super().__init__()
        self.api_type = api_type
        self.api_url = api_url
        self.api_key = api_key
        self.model_name = model_name
        self.running = True
    
    def run(self):
        """运行API测试"""
        try:
            print(f"API测试线程开始运行，API类型: {self.api_type}")
            print(f"API URL: {self.api_url}")
            print(f"模型: {self.model_name}")
            print(f"API密钥: {self.api_key[:10]}..." if self.api_key and len(self.api_key) > 10 else "API密钥为空或无效")
            
            if self.api_type == "Ollama":
                print("调用Ollama API测试...")
                self._test_ollama_api()
            elif self.api_type == "SiliconFlow":
                print("调用SiliconFlow API测试...")
                self._test_siliconflow_api()
            elif self.api_type == "ModelScope":
                print("调用ModelScope API测试...")
                self._test_modelscope_api()
            else:
                error_msg = f"不支持的API类型: {self.api_type}"
                print(f"API测试失败: {error_msg}")
                self.test_result.emit(False, error_msg)
        except Exception as e:
            error_msg = f"测试过程中发生错误: {str(e)}"
            print(f"API测试异常: {error_msg}")
            import traceback
            print(f"异常堆栈: {traceback.format_exc()}")
            self.test_result.emit(False, error_msg)
    
    def _test_ollama_api(self):
        """测试Ollama API连接"""
        try:
            print(f"开始测试Ollama API...")
            print(f"API URL: {self.api_url}")
            print(f"模型: {self.model_name}")
            
            # 准备请求数据
            data = {
                "model": self.model_name,
                "prompt": "请回复'API连接正常'，不要添加其他内容。",
                "stream": False
            }
            
            print(f"请求数据: {json.dumps(data)}")
            
            # 发送请求
            response = requests.post(self.api_url, json=data, timeout=30)
            
            print(f"响应状态码: {response.status_code}")
            print(f"响应头: {dict(response.headers)}")
            
            # 检查响应状态
            if response.status_code == 200:
                result = response.json()
                print(f"响应数据: {json.dumps(result)}")
                
                if "response" in result:
                    self.test_result.emit(True, "API连接正常")
                    print("Ollama API测试成功")
                else:
                    error_msg = "API响应格式不正确"
                    print(f"Ollama API测试失败: {error_msg}")
                    self.test_result.emit(False, error_msg)
            else:
                error_msg = f"API请求失败，状态码: {response.status_code}"
                try:
                    error_detail = response.json()
                    print(f"错误详情: {json.dumps(error_detail)}")
                    if "error" in error_detail:
                        error_msg += f" - {error_detail['error']}"
                except Exception as e:
                    print(f"解析错误响应失败: {str(e)}")
                    error_msg += f" - {response.text[:100]}"
                
                print(f"Ollama API测试失败: {error_msg}")
                self.test_result.emit(False, error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"网络请求失败: {str(e)}"
            print(f"Ollama API测试失败: {error_msg}")
            self.test_result.emit(False, error_msg)
        except Exception as e:
            error_msg = f"测试失败: {str(e)}"
            import traceback
            print(f"Ollama API测试异常: {error_msg}")
            print(f"异常堆栈: {traceback.format_exc()}")
            self.test_result.emit(False, error_msg)
    
    def _test_siliconflow_api(self):
        """测试SiliconFlow API连接"""
        try:
            print(f"开始测试SiliconFlow API...")
            print(f"API URL: {self.api_url}")
            print(f"模型: {self.model_name}")
            print(f"API密钥: {self.api_key[:10]}..." if self.api_key and len(self.api_key) > 10 else "API密钥为空或无效")
            
            # 验证API密钥
            if not self.api_key or not self.api_key.strip():
                self.test_result.emit(False, "API密钥为空")
                return
            
            # 准备请求数据
            data = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": "请回复'API连接正常'，不要添加其他内容。"}],
                "stream": False
            }
            
            # 准备请求头
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key.strip()}"
            }
            
            print(f"请求数据: {json.dumps(data)}")
            print(f"请求头: {json.dumps({k: v if k != 'Authorization' else 'Bearer ***' for k, v in headers.items()})}")
            
            # 发送请求
            response = requests.post(self.api_url, json=data, headers=headers, timeout=30)
            
            print(f"响应状态码: {response.status_code}")
            print(f"响应头: {dict(response.headers)}")
            
            # 检查响应状态
            if response.status_code == 200:
                result = response.json()
                print(f"响应数据: {json.dumps(result)}")
                
                if "choices" in result and len(result["choices"]) > 0 and "message" in result["choices"][0]:
                    self.test_result.emit(True, "API连接正常")
                    print("SiliconFlow API测试成功")
                else:
                    error_msg = "API响应格式不正确"
                    print(f"SiliconFlow API测试失败: {error_msg}")
                    self.test_result.emit(False, error_msg)
            else:
                error_msg = f"API请求失败，状态码: {response.status_code}"
                try:
                    error_detail = response.json()
                    print(f"错误详情: {json.dumps(error_detail)}")
                    if "error" in error_detail:
                        error_msg += f" - {error_detail['error']}"
                except Exception as e:
                    print(f"解析错误响应失败: {str(e)}")
                    error_msg += f" - {response.text[:100]}"
                
                print(f"SiliconFlow API测试失败: {error_msg}")
                self.test_result.emit(False, error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"网络请求失败: {str(e)}"
            print(f"SiliconFlow API测试失败: {error_msg}")
            self.test_result.emit(False, error_msg)
        except Exception as e:
            error_msg = f"测试失败: {str(e)}"
            import traceback
            print(f"SiliconFlow API测试异常: {error_msg}")
            print(f"异常堆栈: {traceback.format_exc()}")
            self.test_result.emit(False, error_msg)
    
    def _test_modelscope_api(self):
        """测试ModelScope API连接"""
        try:
            print(f"开始测试ModelScope API...")
            print(f"API URL: {self.api_url}")
            print(f"模型: {self.model_name}")
            print(f"API密钥: {self.api_key[:10]}..." if self.api_key and len(self.api_key) > 10 else "API密钥为空或无效")
            
            # 验证API密钥
            if not self.api_key or not self.api_key.strip():
                self.test_result.emit(False, "API密钥为空")
                return
            
            # 准备请求数据
            data = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": "请回复'API连接正常'，不要添加其他内容。"}],
                "max_tokens": 50,
                "temperature": 0.7,
                "top_p": 0.9,
                "stream": False
            }
            
            # 准备请求头 - ModelScope API使用特定的认证格式
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key.strip()}",
                "User-Agent": "ModelScope-Client/1.0"
            }
            
            print(f"请求数据: {json.dumps(data)}")
            print(f"请求头: {json.dumps({k: v if k != 'Authorization' else 'Bearer ***' for k, v in headers.items()})}")
            
            # 发送请求
            response = requests.post(self.api_url, json=data, headers=headers, timeout=30)
            
            print(f"响应状态码: {response.status_code}")
            print(f"响应头: {dict(response.headers)}")
            
            # 检查响应状态
            if response.status_code == 200:
                result = response.json()
                print(f"响应数据: {json.dumps(result)}")
                
                if "choices" in result and len(result["choices"]) > 0 and "message" in result["choices"][0]:
                    self.test_result.emit(True, "API连接正常")
                    print("ModelScope API测试成功")
                else:
                    error_msg = "API响应格式不正确"
                    print(f"ModelScope API测试失败: {error_msg}")
                    self.test_result.emit(False, error_msg)
            else:
                error_msg = f"API请求失败，状态码: {response.status_code}"
                try:
                    error_detail = response.json()
                    print(f"错误详情: {json.dumps(error_detail)}")
                    if "error" in error_detail:
                        error_msg += f" - {error_detail['error']}"
                except Exception as e:
                    print(f"解析错误响应失败: {str(e)}")
                    error_msg += f" - {response.text[:100]}"
                
                print(f"ModelScope API测试失败: {error_msg}")
                self.test_result.emit(False, error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"网络请求失败: {str(e)}"
            print(f"ModelScope API测试失败: {error_msg}")
            self.test_result.emit(False, error_msg)
        except Exception as e:
            error_msg = f"测试失败: {str(e)}"
            import traceback
            print(f"ModelScope API测试异常: {error_msg}")
            print(f"异常堆栈: {traceback.format_exc()}")
            self.test_result.emit(False, error_msg)
    
    def stop(self):
        """停止API测试线程"""
        self.running = False

class SettingsDialog(QDialog):
    """设置对话框，包含API设置和章节字数设置"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedSize(600, 500)
        layout = QVBoxLayout(self)
        
        # 创建选项卡
        self.tab_widget = QTabWidget()
        
        # API设置标签页
        api_tab = QWidget()
        api_layout = QVBoxLayout(api_tab)
        api_layout.setContentsMargins(15, 15, 15, 15)
        api_layout.setSpacing(15)
        
        # API类型选择
        api_type_layout = QFormLayout()
        api_type_layout.setVerticalSpacing(10)
        api_type_layout.setHorizontalSpacing(15)
        
        self.api_type_combo = QComboBox()
        self.api_type_combo.addItems(["Ollama", "SiliconFlow", "ModelScope", "自定义"])
        self.api_type_combo.currentTextChanged.connect(self.update_api_settings)
        api_type_layout.addRow(QLabel("API类型:"), self.api_type_combo)
        
        # API地址设置
        self.api_url_edit = QLineEdit()
        self.api_url_edit.setMinimumWidth(300)
        api_type_layout.addRow(QLabel("API地址:"), self.api_url_edit)
        
        # API密钥设置
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setMinimumWidth(300)
        api_type_layout.addRow(QLabel("API密钥:"), self.api_key_edit)
        
        # 自定义API格式选择（仅在自定义API类型时显示）
        self.api_format_label = QLabel("API格式:")
        self.api_format_combo = QComboBox()
        self.api_format_combo.addItems(["OpenAI格式", "Ollama格式"])
        self.api_format_combo.setCurrentText("OpenAI格式")
        self.api_format_label.hide()  # 初始隐藏
        self.api_format_combo.hide()  # 初始隐藏
        api_type_layout.addRow(self.api_format_label, self.api_format_combo)
        
        # 自定义请求头（仅在自定义API类型时显示）
        self.custom_headers_label = QLabel("自定义请求头:")
        self.custom_headers_edit = QTextEdit()
        self.custom_headers_edit.setPlaceholderText("例如：\n{\n  \"Authorization\": \"Bearer YOUR_API_KEY\",\n  \"Content-Type\": \"application/json\"\n}")
        self.custom_headers_edit.setMaximumHeight(100)
        self.custom_headers_label.hide()  # 初始隐藏
        self.custom_headers_edit.hide()  # 初始隐藏
        api_type_layout.addRow(self.custom_headers_label, self.custom_headers_edit)
        
        # 模型选择
        model_label = QLabel("默认模型:")
        api_type_layout.addRow(model_label)
        
        # 创建模型列表和按钮的水平布局
        model_container_layout = QHBoxLayout()
        
        # 创建模型列表控件，支持拖拽排序
        self.model_list_widget = QListWidget()
        self.model_list_widget.addItems(["qwen:latest"])  # 只保留一个默认模型
        self.model_list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.model_list_widget.setDefaultDropAction(Qt.MoveAction)
        self.model_list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.model_list_widget.setFixedHeight(120)  # 固定高度
        self.model_list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 5px;
                background-color: white;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 5px;
                border-radius: 3px;
                margin: 1px;
            }
            QListWidget::item:selected {
                background-color: #6366F1;
                color: white;
            }
        """)
        self.model_list_widget.currentRowChanged.connect(self.on_model_selected)
        # 添加双击事件处理
        self.model_list_widget.itemDoubleClicked.connect(self.on_model_double_clicked)
        model_container_layout.addWidget(self.model_list_widget, 7)  # 列表占70%宽度
        
        # 创建按钮的垂直布局
        model_button_layout = QVBoxLayout()
        model_button_layout.setSpacing(8)  # 设置按钮间距
        
        # 添加自定义模型按钮（在所有API类型时显示）
        self.add_model_button = QPushButton("添加模型")
        self.add_model_button.setFixedHeight(32)  # 固定高度
        self.add_model_button.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
                background-color: #4F46E5;
                color: white;
                border: none;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #4338CA;
            }
        """)
        self.add_model_button.clicked.connect(self.add_custom_model)
        self.add_model_button.hide()  # 初始隐藏，根据API类型决定是否显示
        model_button_layout.addWidget(self.add_model_button)
        
        # 添加删除模型按钮
        self.remove_model_button = QPushButton("删除模型")
        self.remove_model_button.setFixedHeight(32)  # 固定高度
        self.remove_model_button.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
                background-color: #EF4444;
                color: white;
                border: none;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #DC2626;
            }
        """)
        self.remove_model_button.clicked.connect(self.remove_custom_model)
        self.remove_model_button.hide()  # 初始隐藏，根据API类型决定是否显示
        model_button_layout.addWidget(self.remove_model_button)
        
        # 设置按钮的拉伸因子，使它们均匀分布
        model_button_layout.setStretchFactor(self.add_model_button, 1)
        model_button_layout.setStretchFactor(self.remove_model_button, 1)
        
        # 将按钮布局添加到容器布局
        model_container_layout.addLayout(model_button_layout, 3)  # 按钮占30%宽度
        
        # 将容器布局添加到主布局
        api_type_layout.addRow(model_container_layout)
        
        api_layout.addLayout(api_type_layout)
        
        # 添加提示标签 - 放置在API设置区域下方
        
        # 说明文本 - 放置在模型提示标签之后
        self.api_info_label = QLabel("提示：默认API地址为Ollama本地服务地址\n如需使用其他API服务，请在此处修改")
        self.api_info_label.setFixedHeight(40)  # 固定高度
        self.api_info_label.setStyleSheet("color: #6B7280; font-size: 12px; padding: 5px; background-color: #F9FAFB; border-radius: 4px; border: 1px solid #E5E7EB;")
        api_layout.addWidget(self.api_info_label)
        
        # API测试按钮
        self.test_api_button = QPushButton("测试API连接")
        self.test_api_button.setFixedHeight(36)  # 固定高度
        self.test_api_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                background-color: #4F46E5;
                color: white;
                border: none;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #4338CA;
            }
        """)
        self.test_api_button.clicked.connect(self.test_api_connection)
        api_layout.addWidget(self.test_api_button)
        
        # API测试结果标签
        self.test_result_label = QLabel("")
        self.test_result_label.setFixedHeight(24)  # 固定高度
        self.test_result_label.setStyleSheet("color: #6B7280; font-size: 12px; padding: 2px;")
        api_layout.addWidget(self.test_result_label)
        
        # 初始化设置
        self.update_api_settings()
        
        # 章节设置标签页
        chapter_tab = QWidget()
        chapter_layout = QVBoxLayout(chapter_tab)
        chapter_layout.setContentsMargins(15, 15, 15, 15)
        chapter_layout.setSpacing(15)
        
        # 添加章节字数设置
        chapter_length_layout = QFormLayout()
        chapter_length_layout.setVerticalSpacing(10)
        chapter_length_layout.setHorizontalSpacing(15)
        
        self.min_length_spin = QSpinBox()
        self.min_length_spin.setRange(1000, 10000)
        self.min_length_spin.setValue(3500)
        self.min_length_spin.setSuffix(" 字")
        
        self.max_length_spin = QSpinBox()
        self.max_length_spin.setRange(1000, 10000)
        self.max_length_spin.setValue(5000)
        self.max_length_spin.setSuffix(" 字")
        
        chapter_length_layout.addRow(QLabel("最小字数:"), self.min_length_spin)
        chapter_length_layout.addRow(QLabel("最大字数:"), self.max_length_spin)
        
        chapter_layout.addLayout(chapter_length_layout)
        
        # 章节设置说明
        chapter_info_label = QLabel("设置每章生成内容的字数范围，系统将在此范围内随机选择目标字数")
        chapter_info_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        chapter_layout.addWidget(chapter_info_label)
        
        # 保存设置标签页
        save_tab = QWidget()
        save_layout = QVBoxLayout(save_tab)
        save_layout.setContentsMargins(15, 15, 15, 15)
        save_layout.setSpacing(15)
        
        # 保存路径设置
        save_path_layout = QFormLayout()
        save_path_layout.setVerticalSpacing(10)
        save_path_layout.setHorizontalSpacing(15)
        
        self.save_path_edit = QLineEdit()
        self.save_path_edit.setMinimumWidth(300)
        self.save_path_edit.setPlaceholderText("例如：C:\\Users\\用户名\\Documents\\小说")
        save_path_layout.addRow(QLabel("保存路径:"), self.save_path_edit)
        
        # 浏览按钮
        browse_button = QPushButton("浏览...")
        browse_button.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
                background-color: #4F46E5;
                color: white;
                border: none;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #4338CA;
            }
        """)
        browse_button.clicked.connect(self.browse_save_path)
        
        save_path_layout.addRow(browse_button)
        
        save_layout.addLayout(save_path_layout)
        
        # 保存设置说明
        save_info_label = QLabel("设置小说章节的保存路径，默认为程序目录下的novels文件夹")
        save_info_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        save_layout.addWidget(save_info_label)
        
        # 文件存在时的行为设置
        file_behavior_layout = QFormLayout()
        file_behavior_layout.setVerticalSpacing(10)
        file_behavior_layout.setHorizontalSpacing(15)
        
        self.file_behavior_combo = QComboBox()
        self.file_behavior_combo.addItems(["询问", "跳过", "覆盖"])
        self.file_behavior_combo.setCurrentText("询问")
        file_behavior_layout.addRow(QLabel("文件已存在时:"), self.file_behavior_combo)
        
        save_layout.addLayout(file_behavior_layout)
        
        # 文件行为设置说明
        file_behavior_info_label = QLabel("设置当章节文件已存在时的处理方式：询问-弹出对话框让用户选择；跳过-直接跳过已存在章节；覆盖-直接覆盖已存在章节")
        file_behavior_info_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        save_layout.addWidget(file_behavior_info_label)
        
        # 添加选项卡
        self.tab_widget.addTab(api_tab, "API设置")
        self.tab_widget.addTab(chapter_tab, "章节设置")
        self.tab_widget.addTab(save_tab, "保存设置")
        layout.addWidget(self.tab_widget)
        
        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
        # 设置按钮样式
        buttons.setStyleSheet("""
            QDialogButtonBox QPushButton {
                min-width: 80px;
                min-height: 32px;
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                border: none;
            }
            QDialogButtonBox QPushButton[type="accept"] {
                background-color: #4F46E5;
                color: white;
            }
            QDialogButtonBox QPushButton[type="accept"]:hover {
                background-color: #4338CA;
            }
            QDialogButtonBox QPushButton[type="reject"] {
                background-color: #F3F4F6;
                color: #4B5563;
            }
            QDialogButtonBox QPushButton[type="reject"]:hover {
                background-color: #E5E7EB;
            }
        """)
        
        layout.addWidget(buttons)
    
    def update_api_settings(self):
        """根据API类型更新设置界面"""
        api_type = self.api_type_combo.currentText()
        print(f"切换API类型: {api_type}")
        
        # 保存当前API类型的配置
        if hasattr(self, 'api_type') and hasattr(self, 'api_url') and hasattr(self, 'api_key'):
            try:
                # 加载现有参数
                existing_params = {}
                if os.path.exists("user_params.json"):
                    with open("user_params.json", "r", encoding="utf-8") as f:
                        existing_params = json.load(f)
                
                # 确保api_configs存在
                if "api_configs" not in existing_params:
                    existing_params["api_configs"] = {}
                
                # 保存当前API类型的配置
                existing_params["api_configs"][self.api_type] = {
                    "api_url": self.api_url,
                    "api_key": self.api_key,
                    "model_name": self.model_name,
                    "api_format": self.api_format,
                    "custom_headers": self.custom_headers
                }
                
                # 保存更新后的参数
                with open("user_params.json", "w", encoding="utf-8") as f:
                    json.dump(existing_params, f, ensure_ascii=False, indent=4)
                
                print(f"已保存 {self.api_type} 的配置")
            except Exception as e:
                print(f"保存当前API配置失败: {e}")
        
        # 更新界面
        if api_type == "Ollama":
            # 设置Ollama默认值
            self.api_url_edit.setText("http://localhost:11434/api/generate")
            self.api_key_edit.setEnabled(False)
            self.api_key_edit.setText("")
            self.model_list_widget.clear()
            # 加载保存的自定义模型（如果有）
            custom_models = self.load_custom_models()
            default_models = ["qwen:latest"]  # 只保留一个默认模型
            all_models = default_models + custom_models
            self.model_list_widget.addItems(all_models)
            self.api_info_label.setText("提示：默认API地址为Ollama本地服务地址\n如需使用其他API服务，请在此处修改")
            # 显示添加模型按钮
            self.add_model_button.show()
            # 显示删除模型按钮
            self.remove_model_button.show()
        elif api_type == "SiliconFlow":
            # 设置SiliconFlow默认值
            self.api_url_edit.setText("https://api.siliconflow.cn/v1/chat/completions")
            self.api_key_edit.setEnabled(True)
            self.api_key_edit.setPlaceholderText("请输入您的API密钥")
            self.model_list_widget.clear()
            # 加载保存的自定义SiliconFlow模型（如果有）
            custom_siliconflow_models = self.load_custom_siliconflow_models()
            default_models = ["Qwen/Qwen2.5-7B"]  # 只保留一个默认模型
            all_models = default_models + custom_siliconflow_models
            self.model_list_widget.addItems(all_models)
            self.api_info_label.setText("提示：SiliconFlow API需要有效的API密钥\n请访问https://siliconflow.cn获取API密钥")
            # 显示添加模型按钮
            self.add_model_button.show()
            # 显示删除模型按钮
            self.remove_model_button.show()
        elif api_type == "ModelScope":
            # 设置ModelScope默认值
            self.api_url_edit.setText("https://api-inference.modelscope.cn/v1/chat/completions")
            self.api_key_edit.setEnabled(True)
            self.api_key_edit.setPlaceholderText("请输入您的API密钥")
            self.model_list_widget.clear()
            # 加载保存的自定义ModelScope模型（如果有）
            custom_modelscope_models = self.load_custom_modelscope_models()
            default_models = ["Qwen/Qwen3-VL-30B-A3B-Instruct"]
            all_models = default_models + custom_modelscope_models
            self.model_list_widget.addItems(all_models)
            self.api_info_label.setText("提示：ModelScope API需要有效的API密钥\n请访问https://modelscope.cn获取API密钥")
            # 显示添加模型按钮
            self.add_model_button.show()
            # 显示删除模型按钮
            self.remove_model_button.show()
        elif api_type == "自定义":
            # 设置自定义API默认值
            self.api_url_edit.setText("")
            self.api_url_edit.setPlaceholderText("请输入API地址")
            self.api_key_edit.setEnabled(True)
            self.api_key_edit.setPlaceholderText("请输入API密钥（如需要）")
            self.model_list_widget.clear()
            self.model_list_widget.addItems(["请输入模型名称"])
            self.api_info_label.setText("提示：自定义API允许您连接任何兼容的API服务\n请根据API文档正确配置地址、密钥和模型名称")
            # 显示自定义API选项
            self.api_format_label.show()
            self.api_format_combo.show()
            self.custom_headers_label.show()
            self.custom_headers_edit.show()
            # 显示添加模型按钮
            self.add_model_button.show()
            # 显示删除模型按钮
            self.remove_model_button.show()
        else:
            # 隐藏自定义API选项
            self.api_format_label.hide()
            self.api_format_combo.hide()
            self.custom_headers_label.hide()
            self.custom_headers_edit.hide()
            # 显示添加模型按钮
            self.add_model_button.show()
            # 显示删除模型按钮
            self.remove_model_button.show()
        
        # 尝试加载已保存的该API类型的配置
        try:
            if os.path.exists("user_params.json"):
                with open("user_params.json", "r", encoding="utf-8") as f:
                    params = json.load(f)
                    
                    if "api_configs" in params and api_type in params["api_configs"]:
                        config = params["api_configs"][api_type]
                        self.api_url_edit.setText(config.get("api_url", ""))
                        self.api_key_edit.setText(config.get("api_key", ""))
                        
                        # 设置选中的模型
                        model_name = config.get("model_name", "")
                        if model_name:
                            for i in range(self.model_list_widget.count()):
                                if self.model_list_widget.item(i).text() == model_name:
                                    self.model_list_widget.setCurrentRow(i)
                                    break
                        
                        print(f"已加载 {api_type} 的已保存配置")
        except Exception as e:
            print(f"加载已保存配置失败: {e}")
    
    def browse_save_path(self):
        """浏览保存路径"""
        folder_dialog = QFileDialog(self)
        folder_dialog.setFileMode(QFileDialog.DirectoryOnly)
        folder_dialog.setOption(QFileDialog.ShowDirsOnly, True)
        
        if folder_dialog.exec_() == QFileDialog.Accepted:
            selected_folder = folder_dialog.selectedFiles()[0]
            self.save_path_edit.setText(selected_folder)
    
    def get_settings(self):
        """获取设置值"""
        print("获取设置值...")
        api_type = self.api_type_combo.currentText()
        model_name = self.get_selected_model()
        
        settings = {
            "api_type": api_type,
            "api_url": self.api_url_edit.text(),
            "api_key": self.api_key_edit.text(),
            "model_name": model_name,
            "min_length": self.min_length_spin.value(),
            "max_length": self.max_length_spin.value(),
            "save_path": self.save_path_edit.text() if self.save_path_edit.text() else "novels",
            "file_behavior": self.file_behavior_combo.currentText()
        }
        
        # 如果是自定义API，添加额外配置
        if api_type == "自定义":
            settings["api_format"] = self.api_format_combo.currentText()
            settings["custom_headers"] = self.custom_headers_edit.toPlainText()
        
        print(f"已获取设置: API={api_type}, Model={model_name}, FileBehavior={settings['file_behavior']}")
        return settings
    
    def set_settings(self, settings):
        """设置对话框值"""
        print("设置对话框值...")
        api_type = settings.get("api_type", "Ollama")
        model_name = settings.get("model_name", "deepseek-r1:latest")
        
        print(f"设置参数: API={api_type}, Model={model_name}")
        
        self.api_type_combo.setCurrentText(api_type)
        self.api_url_edit.setText(settings.get("api_url", "http://localhost:11434/api/generate"))
        self.api_key_edit.setText(settings.get("api_key", ""))
        self.min_length_spin.setValue(settings.get("min_length", 3500))
        self.max_length_spin.setValue(settings.get("max_length", 5000))
        self.save_path_edit.setText(settings.get("save_path", "novels"))
        self.file_behavior_combo.setCurrentText(settings.get("file_behavior", "询问"))
        
        # 如果是自定义API，加载额外配置
        if api_type == "自定义":
            self.api_format_combo.setCurrentText(settings.get("api_format", "OpenAI格式"))
            self.custom_headers_edit.setText(settings.get("custom_headers", ""))
        
        self.update_api_settings()
        
        # 设置选中的模型
        for i in range(self.model_list_widget.count()):
            if self.model_list_widget.item(i).text() == model_name:
                self.model_list_widget.setCurrentRow(i)
                print(f"已设置选中的模型: {model_name}")
                break
        else:
            print(f"警告: 未找到模型 {model_name}")
        
        print("对话框值设置完成")
        
    def test_api_connection(self):
        """测试API连接"""
        api_type = self.api_type_combo.currentText()
        api_url = self.api_url_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        model_name = self.get_selected_model()
        
        # 验证输入
        if not api_url:
            self.test_result_label.setText("错误：API地址不能为空")
            self.test_result_label.setStyleSheet("color: #EF4444; font-size: 12px;")
            return
            
        if api_type == "SiliconFlow" and not api_key:
            self.test_result_label.setText("错误：SiliconFlow API需要密钥")
            self.test_result_label.setStyleSheet("color: #EF4444; font-size: 12px;")
            return
            
        # 显示测试中状态
        self.test_result_label.setText("正在测试API连接...")
        self.test_result_label.setStyleSheet("color: #3B82F6; font-size: 12px;")
        self.test_api_button.setEnabled(False)
        QApplication.processEvents()  # 更新UI
        
        # 创建测试线程
        self.api_test_thread = ApiTestThread(api_type, api_url, api_key, model_name)
        self.api_test_thread.test_result.connect(self.on_api_test_result)
        self.api_test_thread.start()
        
    def on_api_test_result(self, success, message):
        """处理API测试结果"""
        print(f"API测试结果: 成功={success}, 消息={message}")
        self.test_api_button.setEnabled(True)
        
        if success:
            self.test_result_label.setText(f"✓ {message}")
            self.test_result_label.setStyleSheet("color: #10B981; font-size: 12px;")
            print("API测试成功")
        else:
            self.test_result_label.setText(f"✗ {message}")
            self.test_result_label.setStyleSheet("color: #EF4444; font-size: 12px;")
            print(f"API测试失败: {message}")
    

        
    def init_auto_save_timer(self):
        """初始化自动保存设置定时器"""
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self.save_all_settings)
        self.auto_save_timer.setSingleShot(True)  # 设置为单次触发
        print("自动保存设置定时器已初始化")
        
    def load_custom_models(self):
        """加载保存的自定义模型列表"""
        custom_models_file = "custom_ollama_models.json"
        try:
            if os.path.exists(custom_models_file):
                with open(custom_models_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("custom_models", [])
        except Exception as e:
            print(f"加载自定义模型失败: {str(e)}")
        return []
        

        

    
    def save_custom_models(self, custom_models):
        """保存自定义模型列表"""
        custom_models_file = "custom_ollama_models.json"
        try:
            with open(custom_models_file, 'w', encoding='utf-8') as f:
                json.dump({"custom_models": custom_models}, f, ensure_ascii=False)
        except Exception as e:
            print(f"保存自定义模型失败: {str(e)}")
            # 创建自定义警告消息框
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("错误")
            msg_box.setText("保存自定义模型失败")
            msg_box.setInformativeText(str(e))
            msg_box.setStandardButtons(QMessageBox.Ok)
            
            # 设置按钮样式
            ok_button = msg_box.button(QMessageBox.Ok)
            if ok_button:
                ok_button.setStyleSheet("""
                    QPushButton {
                        min-width: 80px;
                        min-height: 32px;
                        padding: 6px 16px;
                        border-radius: 4px;
                        font-size: 13px;
                        font-weight: 600;
                        border: none;
                        background-color: #F59E0B;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #D97706;
                    }
                """)
            
            msg_box.exec_()
    
    def load_custom_siliconflow_models(self):
        """加载保存的自定义SiliconFlow模型列表"""
        custom_models_file = "custom_siliconflow_models.json"
        try:
            if os.path.exists(custom_models_file):
                with open(custom_models_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("custom_models", [])
        except Exception as e:
            print(f"加载自定义SiliconFlow模型失败: {str(e)}")
        return []
    
    def save_custom_siliconflow_models(self, custom_models):
        """保存自定义SiliconFlow模型列表"""
        custom_models_file = "custom_siliconflow_models.json"
        try:
            with open(custom_models_file, 'w', encoding='utf-8') as f:
                json.dump({"custom_models": custom_models}, f, ensure_ascii=False)
        except Exception as e:
            print(f"保存自定义SiliconFlow模型失败: {str(e)}")
            # 创建自定义警告消息框
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("错误")
            msg_box.setText("保存自定义SiliconFlow模型失败")
            msg_box.setInformativeText(str(e))
            msg_box.setStandardButtons(QMessageBox.Ok)
            
            # 设置按钮样式
            ok_button = msg_box.button(QMessageBox.Ok)
            if ok_button:
                ok_button.setStyleSheet("""
                    QPushButton {
                        min-width: 80px;
                        min-height: 32px;
                        padding: 6px 16px;
                        border-radius: 4px;
                        font-size: 13px;
                        font-weight: 600;
                        border: none;
                        background-color: #F59E0B;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #D97706;
                    }
                """)
            
            msg_box.exec_()
    
    def load_custom_modelscope_models(self):
        """加载保存的自定义ModelScope模型列表"""
        custom_models_file = "custom_modelscope_models.json"
        try:
            if os.path.exists(custom_models_file):
                with open(custom_models_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("custom_models", [])
        except Exception as e:
            print(f"加载自定义ModelScope模型失败: {str(e)}")
        return []
    
    def save_custom_modelscope_models(self, custom_models):
        """保存自定义ModelScope模型列表"""
        custom_models_file = "custom_modelscope_models.json"
        try:
            with open(custom_models_file, 'w', encoding='utf-8') as f:
                json.dump({"custom_models": custom_models}, f, ensure_ascii=False)
        except Exception as e:
            print(f"保存自定义ModelScope模型失败: {str(e)}")
            # 创建自定义警告消息框
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("错误")
            msg_box.setText("保存自定义ModelScope模型失败")
            msg_box.setInformativeText(str(e))
            msg_box.setStandardButtons(QMessageBox.Ok)
            
            # 设置按钮样式
            ok_button = msg_box.button(QMessageBox.Ok)
            if ok_button:
                ok_button.setStyleSheet("""
                    QPushButton {
                        min-width: 80px;
                        min-height: 32px;
                        padding: 6px 16px;
                        border-radius: 4px;
                        font-size: 13px;
                        font-weight: 600;
                        border: none;
                        background-color: #F59E0B;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #D97706;
                    }
                """)
            
            msg_box.exec_()
    
    def add_custom_model(self):
        """添加自定义模型"""
        # 获取当前API类型
        api_type = self.api_type_combo.currentText()
        
        # 创建输入对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("添加自定义模型")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # 添加输入框
        input_layout = QHBoxLayout()
        input_label = QLabel("模型名称:")
        model_input = QLineEdit()
        
        # 根据API类型添加不同的说明
        if api_type == "Ollama":
            info_label = QLabel("请输入您下载的Ollama模型名称，例如：\n- llama3:latest\n- codellama:7b\n- phi3:mini")
            model_input.setPlaceholderText("例如: llama3:latest")
        elif api_type == "SiliconFlow":
            info_label = QLabel("请输入SiliconFlow模型名称，例如：\n- Qwen/Qwen2.5-72B\n- deepseek-ai/deepseek-v2.5\n- THUDM/glm-4-9b-chat")
            model_input.setPlaceholderText("例如: Qwen/Qwen2.5-72B")
        elif api_type == "ModelScope":
            info_label = QLabel("请输入ModelScope模型名称，例如：\n- Qwen/Qwen2.5-72B-Instruct\n- Qwen/Qwen1.5-7B-Chat\n- deepseek-ai/deepseek-v2.5")
            model_input.setPlaceholderText("例如: Qwen/Qwen2.5-72B-Instruct")
        else:
            info_label = QLabel("当前API类型不支持添加自定义模型")
            layout.addWidget(info_label)
            buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
            buttons.rejected.connect(dialog.reject)
            
            # 设置按钮样式
            buttons.setStyleSheet("""
                QDialogButtonBox QPushButton {
                    min-width: 80px;
                    min-height: 32px;
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    border: none;
                    background-color: #F3F4F6;
                    color: #4B5563;
                }
                QDialogButtonBox QPushButton:hover {
                    background-color: #E5E7EB;
                }
            """)
            
            layout.addWidget(buttons)
            dialog.exec_()
            return
            
        info_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        layout.addWidget(info_label)
        
        input_layout.addWidget(input_label)
        input_layout.addWidget(model_input)
        layout.addLayout(input_layout)
        
        # 添加按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        
        # 设置按钮样式
        buttons.setStyleSheet("""
            QDialogButtonBox QPushButton {
                min-width: 80px;
                min-height: 32px;
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                border: none;
            }
            QDialogButtonBox QPushButton[type="accept"] {
                background-color: #4F46E5;
                color: white;
            }
            QDialogButtonBox QPushButton[type="accept"]:hover {
                background-color: #4338CA;
            }
            QDialogButtonBox QPushButton[type="reject"] {
                background-color: #F3F4F6;
                color: #4B5563;
            }
            QDialogButtonBox QPushButton[type="reject"]:hover {
                background-color: #E5E7EB;
            }
        """)
        
        layout.addWidget(buttons)
        
        # 显示对话框
        if dialog.exec_() == QDialog.Accepted:
            model_name = model_input.text().strip()
            if model_name:
                # 根据API类型设置默认模型列表和加载/保存函数
                if api_type == "Ollama":
                    default_models = ["qwen:latest"]
                    custom_models = self.load_custom_models()
                    save_function = self.save_custom_models
                elif api_type == "SiliconFlow":
                    default_models = ["Qwen/Qwen2.5-7B"]  # 只保留一个默认模型
                    custom_models = self.load_custom_siliconflow_models()
                    save_function = self.save_custom_siliconflow_models
                elif api_type == "ModelScope":
                    default_models = ["Qwen/Qwen3-VL-30B-A3B-Instruct"]
                    custom_models = self.load_custom_modelscope_models()
                    save_function = self.save_custom_modelscope_models
                
                # 检查是否已存在
                if model_name in custom_models:
                    # 创建自定义信息消息框
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Information)
                    msg_box.setWindowTitle("提示")
                    msg_box.setText("该模型已存在于列表中")
                    msg_box.setInformativeText(f"模型 '{model_name}' 已经在自定义模型列表中，无需重复添加")
                    msg_box.setStandardButtons(QMessageBox.Ok)
                    
                    # 设置按钮样式
                    ok_button = msg_box.button(QMessageBox.Ok)
                    if ok_button:
                        ok_button.setStyleSheet("""
                            QPushButton {
                                min-width: 80px;
                                min-height: 32px;
                                padding: 6px 16px;
                                border-radius: 4px;
                                font-size: 13px;
                                font-weight: 600;
                                border: none;
                                background-color: #4F46E5;
                                color: white;
                            }
                            QPushButton:hover {
                                background-color: #4338CA;
                            }
                        """)
                    
                    msg_box.exec_()
                    return
                
                # 检查是否在默认模型中
                if model_name in default_models:
                    # 创建自定义信息消息框
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Information)
                    msg_box.setWindowTitle("提示")
                    msg_box.setText("该模型已在默认列表中")
                    msg_box.setInformativeText(f"模型 '{model_name}' 已经在默认模型列表中，无需重复添加")
                    msg_box.setStandardButtons(QMessageBox.Ok)
                    
                    # 设置按钮样式
                    ok_button = msg_box.button(QMessageBox.Ok)
                    if ok_button:
                        ok_button.setStyleSheet("""
                            QPushButton {
                                min-width: 80px;
                                min-height: 32px;
                                padding: 6px 16px;
                                border-radius: 4px;
                                font-size: 13px;
                                font-weight: 600;
                                border: none;
                                background-color: #4F46E5;
                                color: white;
                            }
                            QPushButton:hover {
                                background-color: #4338CA;
                            }
                        """)
                    
                    msg_box.exec_()
                    return
                
                # 添加新模型
                custom_models.append(model_name)
                save_function(custom_models)
                
                # 更新模型列表
                self.model_list_widget.clear()
                all_models = default_models + custom_models
                self.model_list_widget.addItems(all_models)
                
                # 创建自定义信息消息框
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Information)
                msg_box.setWindowTitle("成功")
                msg_box.setText("模型添加成功")
                msg_box.setInformativeText(f"模型 '{model_name}' 已成功添加到列表中")
                msg_box.setStandardButtons(QMessageBox.Ok)
                
                # 设置按钮样式
                ok_button = msg_box.button(QMessageBox.Ok)
                if ok_button:
                    ok_button.setStyleSheet("""
                        QPushButton {
                            min-width: 80px;
                            min-height: 32px;
                            padding: 6px 16px;
                            border-radius: 4px;
                            font-size: 13px;
                            font-weight: 600;
                            border: none;
                            background-color: #4F46E5;
                            color: white;
                        }
                        QPushButton:hover {
                            background-color: #4338CA;
                        }
                    """)
                
                msg_box.exec_()
    
    def on_model_selected(self, row):
        """当选择模型时触发"""
        # 可以在这里添加选择模型时的逻辑
        pass
    
    def remove_custom_model(self):
        """删除选中的模型（包括默认模型和自定义模型）"""
        # 获取当前选中的模型
        current_row = self.model_list_widget.currentRow()
        if current_row < 0:
            # 创建自定义信息消息框
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle("提示")
            msg_box.setText("请先选择要删除的模型")
            msg_box.setInformativeText("请从列表中选择一个模型后再执行删除操作")
            msg_box.setStandardButtons(QMessageBox.Ok)
            
            # 设置按钮样式
            ok_button = msg_box.button(QMessageBox.Ok)
            if ok_button:
                ok_button.setStyleSheet("""
                    QPushButton {
                        min-width: 80px;
                        min-height: 32px;
                        padding: 6px 16px;
                        border-radius: 4px;
                        font-size: 13px;
                        font-weight: 600;
                        border: none;
                        background-color: #4F46E5;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #4338CA;
                    }
                """)
            
            msg_box.exec_()
            return
            
        model_name = self.model_list_widget.item(current_row).text()
        
        # 获取当前API类型
        api_type = self.api_type_combo.currentText()
        
        # 根据API类型设置默认模型列表和加载/保存函数
        if api_type == "Ollama":
            default_models = ["qwen:latest"]
            custom_models = self.load_custom_models()
            save_function = self.save_custom_models
        elif api_type == "SiliconFlow":
            default_models = ["Qwen/Qwen2.5-7B"]  # 只保留一个默认模型
            custom_models = self.load_custom_siliconflow_models()
            save_function = self.save_custom_siliconflow_models
        elif api_type == "ModelScope":
            default_models = ["Qwen/Qwen3-VL-30B-A3B-Instruct"]
            custom_models = self.load_custom_modelscope_models()
            save_function = self.save_custom_modelscope_models
        else:
            return
        
        # 检查是否为默认模型
        if model_name in default_models:
            # 删除默认模型
            confirm_box = QMessageBox()
            confirm_box.setWindowTitle("确认删除")
            confirm_box.setText(f"'{model_name}' 是默认模型，确定要删除吗？")
            confirm_box.setInformativeText("删除后将无法恢复，除非重新添加。")
            
            # 设置按钮样式
            confirm_box.setStyleSheet("""
                QPushButton {
                    min-width: 80px;
                    min-height: 32px;
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    border: none;
                }
                QPushButton[text="是"] {
                    background-color: #EF4444;
                    color: white;
                }
                QPushButton[text="是"]:hover {
                    background-color: #DC2626;
                }
                QPushButton[text="否"] {
                    background-color: #F3F4F6;
                    color: #374151;
                }
                QPushButton[text="否"]:hover {
                    background-color: #E5E7EB;
                }
            """)
            
            yes_button = confirm_box.addButton("是", QMessageBox.YesRole)
            no_button = confirm_box.addButton("否", QMessageBox.NoRole)
            
            confirm_box.exec_()
            
            if confirm_box.clickedButton() != yes_button:
                return
        
        # 从自定义模型列表中删除（如果是自定义模型）
        if model_name in custom_models:
            custom_models.remove(model_name)
            save_function(custom_models)
        
        # 从列表控件中删除
        self.model_list_widget.takeItem(current_row)
        
        # 创建自定义信息消息框
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("成功")
        msg_box.setText("模型删除成功")
        msg_box.setInformativeText(f"模型 '{model_name}' 已成功从列表中删除")
        msg_box.setStandardButtons(QMessageBox.Ok)
        
        # 设置按钮样式
        ok_button = msg_box.button(QMessageBox.Ok)
        if ok_button:
            ok_button.setStyleSheet("""
                QPushButton {
                    min-width: 80px;
                    min-height: 32px;
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    border: none;
                    background-color: #4F46E5;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #4338CA;
                }
            """)
        
        msg_box.exec_()
    
    def get_selected_model(self):
        """获取当前选中的模型"""
        # 如果有选中的项目，返回选中的模型
        if self.model_list_widget.currentRow() >= 0:
            return self.model_list_widget.currentItem().text()
        # 否则返回第一个模型（默认模型）
        elif self.model_list_widget.count() > 0:
            return self.model_list_widget.item(0).text()
        else:
            return ""
            
    def on_model_double_clicked(self, item):
        """当双击模型时，将其设置为默认模型"""
        # 获取当前双击的模型
        model_name = item.text()
        current_row = self.model_list_widget.row(item)
        
        # 如果已经是第一个模型（默认模型），则无需操作
        if current_row == 0:
            # 创建自定义信息消息框
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle("提示")
            msg_box.setText("模型已是默认")
            msg_box.setInformativeText(f"模型 '{model_name}' 已经是默认模型，无需重复设置")
            msg_box.setStandardButtons(QMessageBox.Ok)
            
            # 设置按钮样式
            ok_button = msg_box.button(QMessageBox.Ok)
            if ok_button:
                ok_button.setStyleSheet("""
                    QPushButton {
                        min-width: 80px;
                        min-height: 32px;
                        padding: 6px 16px;
                        border-radius: 4px;
                        font-size: 13px;
                        font-weight: 600;
                        border: none;
                        background-color: #4F46E5;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #4338CA;
                    }
                """)
            
            msg_box.exec_()
            return
            
        # 获取当前项目
        current_item = self.model_list_widget.takeItem(current_row)
        
        # 将其插入到第一个位置
        self.model_list_widget.insertItem(0, current_item)
        
        # 选中新插入的项目
        self.model_list_widget.setCurrentRow(0)
        
        # 显示提示信息
        # 创建自定义信息消息框
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("设置默认模型")
        msg_box.setText("默认模型设置成功")
        msg_box.setInformativeText(f"已将 '{model_name}' 设置为默认模型")
        msg_box.setStandardButtons(QMessageBox.Ok)
        
        # 设置按钮样式
        ok_button = msg_box.button(QMessageBox.Ok)
        if ok_button:
            ok_button.setStyleSheet("""
                QPushButton {
                    min-width: 80px;
                    min-height: 32px;
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    border: none;
                    background-color: #4F46E5;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #4338CA;
                }
            """)
        
        msg_box.exec_()
        
        # 更新当前使用的模型
        self.model_name = model_name
        
        # 保存模型设置
        self.save_model_settings()
    
    def save_model_settings(self):
        """保存模型设置"""
        # 获取当前API类型
        api_type = self.api_type_combo.currentText()
        
        # 获取所有模型名称
        models = []
        for i in range(self.model_list_widget.count()):
            models.append(self.model_list_widget.item(i).text())
        
        # 根据API类型保存模型设置
        if api_type == "Ollama":
            # 分离默认模型和自定义模型
            default_models = ["qwen:latest"]
            custom_models = [model for model in models if model not in default_models]
            self.save_custom_models(custom_models)
        elif api_type == "SiliconFlow":
            # 分离默认模型和自定义模型
            default_models = ["Qwen/Qwen2.5-7B"]
            custom_models = [model for model in models if model not in default_models]
            self.save_custom_siliconflow_models(custom_models)
        elif api_type == "ModelScope":
            # 分离默认模型和自定义模型
            default_models = ["Qwen/Qwen3-VL-30B-A3B-Instruct"]
            custom_models = [model for model in models if model not in default_models]
            self.save_custom_modelscope_models(custom_models)
    
    def accept(self):
        """重写accept方法，在用户点击确定按钮时保存所有设置"""
        # 保存模型设置
        self.save_model_settings()
        # 调用父类的accept方法关闭对话框
        super().accept()

class CompactNovelGeneratorApp(QMainWindow):
    """紧凑型小说生成器主应用"""
    # 添加处理覆盖对话框的信号
    show_overwrite_dialog = pyqtSignal(int, str)  # 章节号，文件路径
    
    def __init__(self):
        print("[调试] CompactNovelGeneratorApp构造函数开始执行")
        super().__init__()
        print("[调试] QMainWindow初始化完成")
        self.api_type = "Ollama"  # API类型，默认为Ollama
        self.api_url = "http://localhost:11434/api/generate"  # Ollama API默认地址
        self.api_key = ""  # API密钥
        self.model_name = "qwen:latest"  # 默认模型
        self.api_format = None  # API格式，用于自定义API
        self.custom_headers = None  # 自定义请求头，用于自定义API
        self.min_chapter_length = 3500  # 默认最小章节字数
        self.max_chapter_length = 5000  # 默认最大章节字数
        self.file_behavior = "询问"  # 文件存在时的行为，默认为询问
        self.save_path = "novels"  # 默认保存路径
        self.chapter_counter = 1  # 章节计数器
        self.batch_generator = None  # 批量生成线程
        self.auto_save_thread = None  # 自动保存线程
        self.current_chapter_content = ""  # 当前章节内容，用于UI更新
        self.chapter_to_save = None  # 待保存的章节信息 (chapter_num, title, content, file_path)
        self.is_initializing = True  # 初始化标志，避免在初始化时显示提示
        self.auto_save_timer = None  # 自动保存设置定时器
        print("[调试] 基本参数初始化完成，即将调用init_ui()")
        self.init_ui()
        print("[调试] UI初始化完成，即将连接信号")
        # 连接信号到处理方法
        self.show_overwrite_dialog.connect(self.on_show_overwrite_dialog)  # 连接信号到处理方法
        print("[调试] 信号连接完成，即将调用load_parameters()")
        # 加载已保存的参数
        self.load_parameters()
        print("[调试] 参数加载完成，即将调用load_novel_params()")
        # 加载已保存的小说参数
        self.load_novel_params()
        print("[调试] 小说参数加载完成，即将检查并加载已保存的大纲")
        # 检查并加载已保存的大纲
        self.check_and_load_saved_outline()
        print("[调试] 大纲加载完成，即将启动自动保存功能")
        # 启动自动保存功能
        self.start_auto_save()
        print("[调试] 自动保存功能已启动")
        print("[调试] CompactNovelGeneratorApp构造函数执行完成")
        
        # 初始化完成，设置标志为False
        self.is_initializing = False
        
        # 初始化自动保存设置定时器
        self.init_auto_save_timer()
        
        # 加载所有设置
        print("[调试] 正在加载所有设置...")
        self.load_all_settings()
    
    def init_auto_save_timer(self):
        """初始化自动保存设置定时器"""
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self.save_all_settings)
        self.auto_save_timer.setSingleShot(True)  # 设置为单次触发
        print("[调试] 自动保存定时器初始化完成")
    
    def trigger_auto_save_settings(self):
        """触发自动保存设置定时器"""
        if self.auto_save_timer:
            # 如果定时器正在运行，先停止
            if self.auto_save_timer.isActive():
                self.auto_save_timer.stop()
            # 重新启动定时器，5秒后保存
            self.auto_save_timer.start(5000)  # 5秒后保存
    
    def save_all_settings(self):
        """保存所有设置"""
        try:
            print("[调试] 正在保存所有设置...")
            # 保存应用程序参数
            self.save_parameters()
            
            # 保存小说参数
            self.save_novel_params()
            
            # 保存大纲内容
            self.save_outline()
            
            # 保存章节内容
            self.save_current_content()
            
            print("[调试] 所有设置保存完成")
            self.status_bar.showMessage("所有设置已自动保存", 3000)
        except Exception as e:
            print(f"保存所有设置失败: {str(e)}")
            self.status_bar.showMessage(f"保存设置失败: {str(e)}", 3000)
    
    def load_all_settings(self):
        """加载所有设置"""
        try:
            print("[调试] 正在加载所有设置...")
            print(f"[调试] 当前save_path: {self.save_path}")
            
            # 加载应用程序参数
            self.load_parameters()
            
            # 加载小说参数
            self.load_novel_params()
            
            # 加载大纲内容
            self.check_and_load_saved_outline()
            
            # 加载当前章节内容
            self.load_current_chapter_content()
            
            print("[调试] 所有设置加载完成")
            self.status_bar.showMessage("所有设置已加载", 3000)
        except Exception as e:
            print(f"加载所有设置失败: {str(e)}")
            self.status_bar.showMessage(f"加载设置失败: {str(e)}", 3000)
    
    def load_current_chapter_content(self):
        """加载当前章节内容"""
        try:
            # 获取当前章节号
            current_chapter = self.chapter_number.value()
            
            # 获取小说标题
            title = self.novel_title_input.text().strip()
            title = title if title else "未命名小说"
            
            # 首先尝试最新格式：第X章.txt
            latest_format_file = os.path.join(self.save_path, f"第{current_chapter}章.txt")
            
            # 如果找到了最新格式的文件，使用它
            if os.path.exists(latest_format_file):
                chapter_file = latest_format_file
            else:
                # 尝试新格式：第X章.txt
                new_format_file = os.path.join(self.save_path, f"第{current_chapter}章.txt")
                
                # 如果找到了新格式的文件，使用它
                if os.path.exists(new_format_file):
                    chapter_file = new_format_file
                else:
                    # 尝试旧格式：第X章：标题_小说标题.txt
                    import glob
                    pattern = os.path.join(self.save_path, f"第{current_chapter}章*_{title}.txt")
                    matching_files = glob.glob(pattern)
                    
                    # 如果找到了旧格式的文件，使用第一个匹配的文件
                    if matching_files:
                        chapter_file = matching_files[0]
                    else:
                        # 尝试其他可能的旧文件名格式
                        possible_files = [
                            f"第{current_chapter}章.txt",  # 最旧的格式
                            f"第{current_chapter:03d}章.txt",  # 带零的旧格式
                            f"第{current_chapter}章_{title}.txt",  # 带小说标题的格式
                            f"第{current_chapter:03d}章_{title}.txt"  # 带零和小说标题的格式
                        ]
                        
                        chapter_file = None
                        for file_name in possible_files:
                            test_path = os.path.join(self.save_path, file_name)
                            if os.path.exists(test_path):
                                chapter_file = test_path
                                break
            
            # 如果章节文件存在，则加载内容
            if chapter_file and os.path.exists(chapter_file):
                with open(chapter_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.chapter_text.setPlainText(content)
                    print(f"[调试] 已加载第{current_chapter}章内容")
            else:
                print(f"[调试] 未找到第{current_chapter}章文件")
        except Exception as e:
            print(f"加载章节内容失败: {str(e)}")
        
    def load_custom_models(self):
        """加载保存的自定义模型列表"""
        custom_models_file = "custom_ollama_models.json"
        try:
            if os.path.exists(custom_models_file):
                with open(custom_models_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("custom_models", [])
        except Exception as e:
            print(f"加载自定义模型失败: {str(e)}")
        return []
        
    def load_custom_siliconflow_models(self):
        """加载保存的自定义SiliconFlow模型列表"""
        custom_models_file = "custom_siliconflow_models.json"
        try:
            if os.path.exists(custom_models_file):
                with open(custom_models_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("custom_models", [])
        except Exception as e:
            print(f"加载自定义SiliconFlow模型失败: {str(e)}")
        return []
        
    def load_custom_modelscope_models(self):
        """加载保存的自定义ModelScope模型列表"""
        custom_models_file = "custom_modelscope_models.json"
        try:
            if os.path.exists(custom_models_file):
                with open(custom_models_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("custom_models", [])
        except Exception as e:
            print(f"加载自定义ModelScope模型失败: {str(e)}")
        return []
        
    def init_ui(self):
        """初始化用户界面"""
        print("[调试] init_ui方法开始执行")
        self.setWindowTitle("小说生成助手 - 青春版 v2.0")
        # 设置窗口初始大小和位置，允许自由调整
        self.setGeometry(100, 100, 1200, 800)
        # 设置窗口最小尺寸，确保基本功能可见
        self.setMinimumSize(1000, 600)
        print("[调试] 窗口标题和大小设置完成")
        
        # 设置窗口图标（从网络加载）
        icon_url = "https://i.postimg.cc/Ls3Cjj0J/mmexport1729349684603.png"
        app_icon = load_icon_from_url(icon_url)
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        else:
            # 如果网络图标加载失败，尝试使用本地图标
            try:
                self.setWindowIcon(QIcon('红刚封面.ico'))
            except:
                pass
            
        # 创建菜单栏
        self.setup_menu()
        
        # 主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)  # 更小的边距
        main_layout.setSpacing(8)  # 更小的元素间距
        
        # 标题栏 - 更紧凑的设计
        title_frame = GradientFrame(QColor(79, 70, 229), QColor(99, 102, 241))
        title_frame.setFixedHeight(60)  # 更小的高度
        title_layout = QVBoxLayout(title_frame)
        title_layout.setContentsMargins(20, 5, 20, 5)
        title_layout.setSpacing(3)
        
        # 标题和副标题 - 高级艺术字效果
        title_label = QLabel("小说生成助手")
        title_label.setStyleSheet("""
            font-size: 26px;
            font-weight: 800;
            color: white;
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            letter-spacing: 2px;
            word-spacing: 4px;
            text-shadow: 0 2px 10px rgba(0, 0, 0, 0.4);
            background: linear-gradient(135deg, #ffffff 0%, #f0f4ff 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin: 0 10px;
        """)
        title_label.setAlignment(Qt.AlignCenter)
        
        subtitle_label = QLabel("基于大语言模型的智能创作工具")
        subtitle_label.setStyleSheet("""
            font-size: 15px;
            font-weight: 500;
            color: rgba(255, 255, 255, 240);
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            letter-spacing: 1.5px;
            word-spacing: 3px;
            text-shadow: 0 1px 6px rgba(0, 0, 0, 0.3);
            background: linear-gradient(135deg, rgba(255,255,255,0.9) 0%, rgba(240,244,255,0.8) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin: 0 15px;
        """)
        subtitle_label.setAlignment(Qt.AlignCenter)
        
        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)
        
        main_layout.addWidget(title_frame)
        
        # 创建侧边栏和主内容区域
        content_frame = QFrame()
        content_frame.setStyleSheet("background-color: white; border-radius: 6px;")
        content_layout = QHBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # 左侧侧边栏
        sidebar_frame = QFrame()
        sidebar_frame.setFixedWidth(200)
        sidebar_frame.setStyleSheet("""
            QFrame {
                background-color: #F9FAFB;
                border-right: 1px solid #E5E7EB;
                border-top-left-radius: 6px;
                border-bottom-left-radius: 6px;
            }
        """)
        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        
        # 侧边栏按钮
        self.sidebar_input_button = QPushButton("输入设置")
        self.sidebar_input_button.setCheckable(True)
        self.sidebar_input_button.setChecked(True)
        self.sidebar_input_button.setStyleSheet("""
            QPushButton {
                background-color: #6366F1;
                color: white;
                border: none;
                padding: 12px 16px;
                text-align: left;
                font-weight: 600;
                font-size: 14px;
                border-radius: 0px;
            }
            QPushButton:checked {
                background-color: #4F46E5;
            }
            QPushButton:hover {
                background-color: #4F46E5;
            }
        """)
        
        # 小说大纲按钮
        self.sidebar_outline_button = QPushButton("小说大纲")
        self.sidebar_outline_button.setCheckable(True)
        self.sidebar_outline_button.setStyleSheet("""
            QPushButton {
                background-color: #F9FAFB;
                color: #4B5563;
                border: none;
                padding: 12px 16px;
                text-align: left;
                font-weight: 600;
                font-size: 14px;
                border-radius: 0px;
                border-bottom: 1px solid #E5E7EB;
            }
            QPushButton:checked {
                background-color: #6366F1;
                color: white;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        
        # 章节内容按钮
        self.sidebar_chapter_button = QPushButton("单章小说生成")
        self.sidebar_chapter_button.setCheckable(True)
        self.sidebar_chapter_button.setStyleSheet("""
            QPushButton {
                background-color: #F9FAFB;
                color: #4B5563;
                border: none;
                padding: 12px 16px;
                text-align: left;
                font-weight: 600;
                font-size: 14px;
                border-radius: 0px;
                border-bottom: 1px solid #E5E7EB;
            }
            QPushButton:checked {
                background-color: #6366F1;
                color: white;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        
        # 批量生成章节按钮
        self.sidebar_batch_button = QPushButton("批量生成章节")
        self.sidebar_batch_button.setCheckable(True)
        self.sidebar_batch_button.setStyleSheet("""
            QPushButton {
                background-color: #F9FAFB;
                color: #4B5563;
                border: none;
                padding: 12px 16px;
                text-align: left;
                font-weight: 600;
                font-size: 14px;
                border-radius: 0px;
                border-bottom: 1px solid #E5E7EB;
            }
            QPushButton:checked {
                background-color: #6366F1;
                color: white;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        
        # AI润色小说按钮
        self.sidebar_dedup_button = QPushButton("AI润色小说")
        self.sidebar_dedup_button.setCheckable(True)
        self.sidebar_dedup_button.setStyleSheet("""
            QPushButton {
                background-color: #F9FAFB;
                color: #4B5563;
                border: none;
                padding: 12px 16px;
                text-align: left;
                font-weight: 600;
                font-size: 14px;
                border-radius: 0px;
                border-bottom: 1px solid #E5E7EB;
            }
            QPushButton:checked {
                background-color: #6366F1;
                color: white;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        
        # 帮助按钮
        self.sidebar_help_button = QPushButton("帮助")
        self.sidebar_help_button.setCheckable(True)
        self.sidebar_help_button.setStyleSheet("""
            QPushButton {
                background-color: #F9FAFB;
                color: #4B5563;
                border: none;
                padding: 12px 16px;
                text-align: left;
                font-weight: 600;
                font-size: 14px;
                border-radius: 0px;
                border-bottom: 1px solid #E5E7EB;
            }
            QPushButton:checked {
                background-color: #6366F1;
                color: white;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        
        # 设置按钮
        self.sidebar_settings_button = QPushButton("设置")
        self.sidebar_settings_button.setCheckable(True)
        self.sidebar_settings_button.setStyleSheet("""
            QPushButton {
                background-color: #F9FAFB;
                color: #4B5563;
                border: none;
                padding: 12px 16px;
                text-align: left;
                font-weight: 600;
                font-size: 14px;
                border-radius: 0px;
                border-bottom: 1px solid #E5E7EB;
            }
            QPushButton:checked {
                background-color: #6366F1;
                color: white;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        
        # 更新按钮
        self.sidebar_update_button = QPushButton("更新")
        self.sidebar_update_button.setCheckable(True)
        self.sidebar_update_button.setStyleSheet("""
            QPushButton {
                background-color: #F9FAFB;
                color: #4B5563;
                border: none;
                padding: 12px 16px;
                text-align: left;
                font-weight: 600;
                font-size: 14px;
                border-radius: 0px;
                border-bottom: 1px solid #E5E7EB;
            }
            QPushButton:checked {
                background-color: #6366F1;
                color: white;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        
        sidebar_layout.addWidget(self.sidebar_input_button)
        sidebar_layout.addWidget(self.sidebar_outline_button)
        sidebar_layout.addWidget(self.sidebar_chapter_button)
        sidebar_layout.addWidget(self.sidebar_batch_button)
        sidebar_layout.addWidget(self.sidebar_dedup_button)
        sidebar_layout.addWidget(self.sidebar_help_button)
        sidebar_layout.addWidget(self.sidebar_settings_button)
        sidebar_layout.addWidget(self.sidebar_update_button)
        sidebar_layout.addStretch()
        
        # 右侧内容区域
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet("""
            QStackedWidget {
                background-color: white;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }
        """)
        
        # 创建各个功能页面
        self.input_page = QWidget()
        self.outline_page = QWidget()
        self.chapter_page = QWidget()
        self.batch_page = QWidget()
        self.dedup_page = QWidget()
        self.help_page = QWidget()
        self.settings_page = QWidget()
        self.update_page = QWidget()
        
        self.content_stack.addWidget(self.input_page)
        self.content_stack.addWidget(self.outline_page)
        self.content_stack.addWidget(self.chapter_page)
        self.content_stack.addWidget(self.batch_page)
        self.content_stack.addWidget(self.dedup_page)
        self.content_stack.addWidget(self.help_page)
        self.content_stack.addWidget(self.settings_page)
        self.content_stack.addWidget(self.update_page)
        
        # 设置各个页面
        self.setup_input_page()
        self.setup_outline_page()
        self.setup_chapter_page()
        self.setup_batch_page()
        self.setup_polish_page()
        self.setup_help_page()
        self.setup_settings_page()
        self.setup_update_page()
        
        content_layout.addWidget(sidebar_frame)
        content_layout.addWidget(self.content_stack)
        
        # 连接侧边栏按钮事件
        self.sidebar_input_button.clicked.connect(lambda: self.switch_page(0))
        self.sidebar_outline_button.clicked.connect(lambda: self.switch_page(1))
        self.sidebar_chapter_button.clicked.connect(lambda: self.switch_page(2))
        self.sidebar_batch_button.clicked.connect(lambda: self.switch_page(3))
        self.sidebar_dedup_button.clicked.connect(lambda: self.switch_page(4))
        self.sidebar_help_button.clicked.connect(lambda: self.switch_page(5))
        self.sidebar_settings_button.clicked.connect(lambda: self.switch_page(6))
        self.sidebar_update_button.clicked.connect(lambda: self.switch_page(7))
        
        # 添加内容区域到主布局
        main_layout.addWidget(content_frame)
        
        # 底部控制区域 - 更紧凑的设计
        control_frame = QFrame()
        control_frame.setStyleSheet("background-color: #F9FAFB; border-radius: 6px; padding: 5px;")
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(10, 5, 10, 5)
        control_layout.setSpacing(10)
        
        # 模型选择
        model_label = QLabel("模型:")
        model_label.setStyleSheet("color: #374151; font-weight: 600; font-size: 13px;")
        
        self.model_combo = QComboBox()
        # 初始化时先添加一个默认模型，load_parameters方法会重新加载正确的模型列表
        self.model_combo.addItems(["deepseek-r1:7b"])
        
        self.model_combo.currentTextChanged.connect(self.change_model)
        self.model_combo.setMinimumWidth(180)
        self.model_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 6px 10px;
                background-color: white;
                font-size: 13px;
            }
        """)
        
        # 生成按钮
        self.generate_button = QPushButton("生成大纲")
        self.generate_button.setStyleSheet(self.get_button_style())
        self.generate_button.setMinimumHeight(35)
        self.generate_button.setMinimumWidth(100)
        self.generate_button.clicked.connect(self.generate_outline)
        
        # 停止按钮
        self.stop_button = QPushButton("停止")
        self.stop_button.setStyleSheet(self.get_button_style(disabled=False))
        self.stop_button.setMinimumHeight(35)
        self.stop_button.setMinimumWidth(80)
        self.stop_button.setEnabled(True)
        self.stop_button.clicked.connect(self.stop_generation)
        
        # 设置按钮
        self.settings_button = QPushButton("设置")
        self.settings_button.setStyleSheet(self.get_button_style(color="#6B7280"))
        self.settings_button.setMinimumHeight(35)
        self.settings_button.setMinimumWidth(80)
        self.settings_button.clicked.connect(self.show_settings)
        
        control_layout.addWidget(model_label)
        control_layout.addWidget(self.model_combo)
        
        # 添加使用已保存大纲的复选框
        self.use_saved_outline = QCheckBox("使用已保存的大纲")
        self.use_saved_outline.setChecked(True)  # 默认使用已保存的大纲
        self.use_saved_outline.setStyleSheet("""
            QCheckBox {
                color: #4B5563;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        
        control_layout.addWidget(self.use_saved_outline)
        control_layout.addWidget(self.settings_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.generate_button)
        
        # 设置按钮的拉伸因子，使它们均匀分布
        control_layout.setStretchFactor(self.use_saved_outline, 0)
        control_layout.setStretchFactor(self.settings_button, 1)
        control_layout.setStretchFactor(self.stop_button, 1)
        control_layout.setStretchFactor(self.generate_button, 1)
        
        main_layout.addWidget(control_frame)
        
        # 进度条区域
        progress_frame = QFrame()
        progress_frame.setStyleSheet("background-color: #F9FAFB; border-radius: 6px; padding: 5px;")
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(10, 5, 10, 5)
        progress_layout.setSpacing(5)
        
        # 进度标签
        self.progress_label = QLabel("就绪")
        self.progress_label.setStyleSheet("color: #4B5563; font-size: 12px;")
        progress_layout.addWidget(self.progress_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                height: 6px;
                border: none;
                border-radius: 3px;
                background-color: #E5E7EB;
            }
            QProgressBar::chunk {
                background-color: #6366F1;
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)
        
        main_layout.addWidget(progress_frame)
        
        # 状态栏
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #F9FAFB;
                border-top: 1px solid #E5E7EB;
                padding: 6px;
                font-size: 12px;
                color: #4B5563;
            }
        """)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
        
        # 软件状态：正常、忙碌、异常
        self.app_status = "正常"  # 默认状态为正常
        
        # 创建状态标签并添加到状态栏
        self.status_label = QLabel("状态: 正常")
        self.status_label.setStyleSheet("color: #10B981; font-weight: bold;")
        self.status_bar.addPermanentWidget(self.status_label)
        
        self.update_status_display()
        
        # 加载保存的参数
        self.load_parameters()
        self.load_novel_params()
        print("[调试] 参数加载完成")
        
        # 设置初始状态为正常
        self.set_app_status("正常")
        print("[调试] 应用状态设置完成")
        print("[调试] init_ui方法执行完成")

    def switch_page(self, index):
        """切换页面"""
        self.content_stack.setCurrentIndex(index)
        # 更新侧边栏按钮状态
        self.sidebar_input_button.setChecked(index == 0)
        self.sidebar_outline_button.setChecked(index == 1)
        self.sidebar_chapter_button.setChecked(index == 2)
        self.sidebar_batch_button.setChecked(index == 3)
        self.sidebar_dedup_button.setChecked(index == 4)
        self.sidebar_help_button.setChecked(index == 5)
        self.sidebar_settings_button.setChecked(index == 6)
        self.sidebar_update_button.setChecked(index == 7)

    def get_button_style(self, disabled=False, color="#6366F1"):
        """获取按钮样式"""
        if disabled:
            return """
                QPushButton {
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    background-color: #F3F4F6;
                    color: #9CA3AF;
                    border: none;
                }
            """
        else:
            return f"""
                QPushButton {{
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    background-color: {color};
                    color: #FFFFFF;
                    border: none;
                }}
                QPushButton:hover {{
                    background-color: {self._adjust_color(color, -20)};
                }}
                QPushButton:pressed {{
                    background-color: {self._adjust_color(color, -40)};
                }}
            """
    
    def _adjust_color(self, hex_color, amount):
        """调整颜色亮度，用于按钮悬停和点击效果"""
        # 将十六进制颜色转换为RGB
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        # 调整RGB值
        r = max(0, min(255, r + amount))
        g = max(0, min(255, g + amount))
        b = max(0, min(255, b + amount))
        
        # 转换回十六进制
        return f'#{r:02x}{g:02x}{b:02x}'
        
    def update_status_display(self):
        """更新状态栏显示"""
        status_text = f"状态: {self.app_status}"
        
        # 根据状态设置不同的颜色
        if self.app_status == "正常":
            color = "#10B981"  # 绿色
        elif self.app_status == "忙碌":
            color = "#F59E0B"  # 黄色
        elif self.app_status == "异常":
            color = "#EF4444"  # 红色
        else:
            color = "#4B5563"  # 默认灰色
            
        # 在状态栏左侧显示状态
        if hasattr(self, 'status_label'):
            self.status_label.setText(status_text)
            self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        else:
            # 如果状态标签不存在，创建一个
            self.status_label = QLabel(status_text)
            self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            self.status_bar.addPermanentWidget(self.status_label)
            
    def set_app_status(self, status):
        """设置应用程序状态"""
        if status in ["正常", "忙碌", "异常"]:
            self.app_status = status
            self.update_status_display()

    def setup_menu(self):
        """设置菜单栏"""
        menu_bar = self.menuBar()
        
        # 文件菜单
        file_menu = menu_bar.addMenu("文件")
        
        save_action = QAction("保存设置", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_parameters)
        file_menu.addAction(save_action)
        
        export_action = QAction("导出小说", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self.save_result)
        file_menu.addAction(export_action)
        
        # 添加自动保存子菜单
        auto_save_menu = file_menu.addMenu("自动保存")
        
        start_auto_save_action = QAction("启动自动保存", self)
        start_auto_save_action.triggered.connect(self.start_auto_save)
        auto_save_menu.addAction(start_auto_save_action)
        
        stop_auto_save_action = QAction("停止自动保存", self)
        stop_auto_save_action.triggered.connect(self.stop_auto_save)
        auto_save_menu.addAction(stop_auto_save_action)
        
        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        


    def setup_input_page(self):
        """设置输入页面"""
        layout = QVBoxLayout(self.input_page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none;")
        
        # 内容区域 - 紧凑型设计
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(8)
        
        # 小说标题
        title_group = QGroupBox("小说标题")
        title_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        title_layout = QVBoxLayout(title_group)
        
        # 标题输入和生成按钮的水平布局
        title_input_layout = QHBoxLayout()
        
        self.novel_title_input = QLineEdit()
        self.novel_title_input.setPlaceholderText("输入小说标题...")
        self.novel_title_input.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QLineEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        
        # AI生成标题按钮
        self.generate_title_button = QPushButton("AI生成标题")
        self.generate_title_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.generate_title_button.clicked.connect(self.show_title_generation_dialog)
        
        title_input_layout.addWidget(self.novel_title_input)
        title_input_layout.addWidget(self.generate_title_button)
        
        title_layout.addLayout(title_input_layout)
        content_layout.addWidget(title_group)
        
        # 小说背景
        bg_group = QGroupBox("小说背景设定")
        bg_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        bg_layout = QVBoxLayout(bg_group)
        
        # 背景输入和生成按钮的水平布局
        bg_input_layout = QHBoxLayout()
        
        self.bg_text = QTextEdit()
        self.bg_text.setPlaceholderText("描述小说的世界观、时代背景、主要场景等...")
        self.bg_text.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        self.bg_text.setMaximumHeight(100)
        
        # AI生成背景按钮
        self.generate_bg_button = QPushButton("AI生成背景")
        self.generate_bg_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.generate_bg_button.clicked.connect(self.show_background_generation_dialog)
        self.generate_bg_button.setMaximumWidth(120)
        
        bg_input_layout.addWidget(self.bg_text)
        bg_input_layout.addWidget(self.generate_bg_button)
        
        bg_layout.addLayout(bg_input_layout)
        content_layout.addWidget(bg_group)
        
        # 人物设定
        char_group = QGroupBox("人物设定")
        char_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        char_layout = QVBoxLayout(char_group)  # 改为垂直布局
        
        # 添加人物生成按钮
        char_button_layout = QHBoxLayout()
        self.generate_hero_button = QPushButton("AI生成男主角")
        self.generate_hero_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.generate_hero_button.clicked.connect(self.show_hero_generation_dialog)
        
        self.generate_heroine_button = QPushButton("AI生成女主角")
        self.generate_heroine_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.generate_heroine_button.clicked.connect(self.show_heroine_generation_dialog)
        
        char_button_layout.addWidget(self.generate_hero_button)
        char_button_layout.addWidget(self.generate_heroine_button)
        char_button_layout.addStretch()
        char_layout.addLayout(char_button_layout)
        
        # 人物内容区域
        char_content_layout = QHBoxLayout()
        
        # 男主角
        hero_frame = QFrame()
        hero_layout = QFormLayout(hero_frame)
        hero_layout.setVerticalSpacing(8)
        hero_layout.setHorizontalSpacing(10)
        
        self.hero_name = QLineEdit()
        self.hero_name.setPlaceholderText("姓名")
        self.hero_age = QSpinBox()
        self.hero_age.setRange(1, 100)
        self.hero_age.setValue(25)
        self.hero_job = QLineEdit()
        self.hero_job.setPlaceholderText("职业")
        self.hero_family = QLineEdit()
        self.hero_family.setPlaceholderText("家庭背景")
        self.hero_desc = QTextEdit()
        self.hero_desc.setPlaceholderText("人物简介")
        self.hero_desc.setMaximumHeight(60)
        
        hero_layout.addRow("姓名:", self.hero_name)
        hero_layout.addRow("年龄:", self.hero_age)
        hero_layout.addRow("职业:", self.hero_job)
        hero_layout.addRow("家庭:", self.hero_family)
        hero_layout.addRow("简介:", self.hero_desc)
        
        # 女主角
        heroine_frame = QFrame()
        heroine_layout = QFormLayout(heroine_frame)
        heroine_layout.setVerticalSpacing(8)
        heroine_layout.setHorizontalSpacing(10)
        
        self.heroine_name = QLineEdit()
        self.heroine_name.setPlaceholderText("姓名")
        self.heroine_age = QSpinBox()
        self.heroine_age.setRange(1, 100)
        self.heroine_age.setValue(23)
        self.heroine_job = QLineEdit()
        self.heroine_job.setPlaceholderText("职业")
        self.heroine_family = QLineEdit()
        self.heroine_family.setPlaceholderText("家庭背景")
        self.heroine_desc = QTextEdit()
        self.heroine_desc.setPlaceholderText("人物简介")
        self.heroine_desc.setMaximumHeight(60)
        
        heroine_layout.addRow("姓名:", self.heroine_name)
        heroine_layout.addRow("年龄:", self.heroine_age)
        heroine_layout.addRow("职业:", self.heroine_job)
        heroine_layout.addRow("家庭:", self.heroine_family)
        heroine_layout.addRow("简介:", self.heroine_desc)
        
        char_content_layout.addWidget(hero_frame)
        char_content_layout.addWidget(heroine_frame)
        char_layout.addLayout(char_content_layout)
        content_layout.addWidget(char_group)
        
        # 角色关系
        rel_group = QGroupBox("角色关系")
        rel_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        rel_layout = QVBoxLayout(rel_group)
        
        # 添加角色关系输入和生成按钮的水平布局
        rel_button_layout = QHBoxLayout()
        self.rel_text = QTextEdit()
        self.rel_text.setPlaceholderText("描述男主角和女主角的关系，以及与其他角色的关系...")
        self.rel_text.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        self.rel_text.setMaximumHeight(80)
        
        # 添加AI生成角色关系按钮
        self.generate_rel_button = QPushButton("AI生成关系")
        self.generate_rel_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.generate_rel_button.clicked.connect(self.show_relationship_generation_dialog)
        
        rel_button_layout.addWidget(self.rel_text)
        rel_button_layout.addWidget(self.generate_rel_button)
        rel_layout.addLayout(rel_button_layout)
        content_layout.addWidget(rel_group)
        
        # 核心剧情
        plot_group = QGroupBox("核心剧情")
        plot_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        plot_layout = QVBoxLayout(plot_group)
        
        # 添加核心剧情输入和生成按钮的水平布局
        plot_button_layout = QHBoxLayout()
        self.plot_text = QTextEdit()
        self.plot_text.setPlaceholderText("描述小说的主要情节和发展脉络...")
        self.plot_text.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        self.plot_text.setMaximumHeight(100)
        
        # 添加AI生成核心剧情按钮
        self.generate_plot_button = QPushButton("AI生成剧情")
        self.generate_plot_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.generate_plot_button.clicked.connect(self.show_plot_generation_dialog)
        
        plot_button_layout.addWidget(self.plot_text)
        plot_button_layout.addWidget(self.generate_plot_button)
        plot_layout.addLayout(plot_button_layout)
        content_layout.addWidget(plot_group)
        
        # 写作风格
        style_group = QGroupBox("写作风格")
        style_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        style_layout = QGridLayout(style_group)
        
        self.genre_combo = QComboBox()
        self.genre_combo.addItems(["现代", "悬疑", "言情", "玄幻", "奇幻", "科幻", "历史", "武侠", "都市", "校园"])
        self.pov_combo = QComboBox()
        self.pov_combo.addItems(["第一人称", "第三人称", "多视角"])
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["现代白话文", "古风", "幽默诙谐", "文艺清新", "悬疑惊悚"])
        self.rhythm_combo = QComboBox()
        self.rhythm_combo.addItems(["平铺直叙", "循序渐进", "跌宕起伏"])
        self.word_count = QLineEdit()
        self.word_count.setText("300000")
        self.word_count.setPlaceholderText("输入预计字数")
        self.word_count.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QLineEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        
        style_layout.addWidget(QLabel("题材类型:"), 0, 0)
        style_layout.addWidget(self.genre_combo, 0, 1)
        style_layout.addWidget(QLabel("人称视角:"), 0, 2)
        style_layout.addWidget(self.pov_combo, 0, 3)
        style_layout.addWidget(QLabel("语言风格:"), 1, 0)
        style_layout.addWidget(self.lang_combo, 1, 1)
        style_layout.addWidget(QLabel("叙事节奏:"), 1, 2)
        style_layout.addWidget(self.rhythm_combo, 1, 3)
        style_layout.addWidget(QLabel("预计字数:"), 2, 0)
        style_layout.addWidget(self.word_count, 2, 1)
        
        # 设置列的拉伸因子，使布局均匀分布
        style_layout.setColumnStretch(0, 1)  # 第一列标签
        style_layout.setColumnStretch(1, 2)  # 第二列控件
        style_layout.setColumnStretch(2, 1)  # 第三列标签
        style_layout.setColumnStretch(3, 2)  # 第四列控件
        
        content_layout.addWidget(style_group)
        
        # 提示文本
        prompt_group = QGroupBox("生成提示词预览")
        prompt_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        prompt_layout = QVBoxLayout(prompt_group)
        self.prompt_text = QTextEdit()
        self.prompt_text.setReadOnly(True)
        self.prompt_text.setMaximumHeight(120)
        self.prompt_text.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 13px;
                background-color: #F9FAFB;
            }
        """)
        
        prompt_layout.addWidget(self.prompt_text)
        content_layout.addWidget(prompt_group)
        
        # 设置滚动区域内容
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        # 自动生成提示词
        self.update_prompt()
        
        # 当任何输入变化时更新提示词
        self.novel_title_input.textChanged.connect(self.update_prompt)
        self.bg_text.textChanged.connect(self.update_prompt)
        self.hero_name.textChanged.connect(self.update_prompt)
        self.hero_desc.textChanged.connect(self.update_prompt)
        self.heroine_name.textChanged.connect(self.update_prompt)
        self.heroine_desc.textChanged.connect(self.update_prompt)
        self.rel_text.textChanged.connect(self.update_prompt)
        self.plot_text.textChanged.connect(self.update_prompt)
        self.genre_combo.currentTextChanged.connect(self.update_prompt)
        self.pov_combo.currentTextChanged.connect(self.update_prompt)
        self.lang_combo.currentTextChanged.connect(self.update_prompt)
        self.rhythm_combo.currentTextChanged.connect(self.update_prompt)
        self.word_count.textChanged.connect(self.update_prompt)
        
        # 为所有输入框添加自动保存功能
        self.novel_title_input.textChanged.connect(self.auto_save_novel_params)
        self.bg_text.textChanged.connect(self.auto_save_novel_params)
        self.hero_name.textChanged.connect(self.auto_save_novel_params)
        self.hero_age.valueChanged.connect(self.auto_save_novel_params)
        self.hero_job.textChanged.connect(self.auto_save_novel_params)
        self.hero_family.textChanged.connect(self.auto_save_novel_params)
        self.hero_desc.textChanged.connect(self.auto_save_novel_params)
        self.heroine_name.textChanged.connect(self.auto_save_novel_params)
        self.heroine_age.valueChanged.connect(self.auto_save_novel_params)
        self.heroine_job.textChanged.connect(self.auto_save_novel_params)
        self.heroine_family.textChanged.connect(self.auto_save_novel_params)
        self.heroine_desc.textChanged.connect(self.auto_save_novel_params)
        self.rel_text.textChanged.connect(self.auto_save_novel_params)
        self.plot_text.textChanged.connect(self.auto_save_novel_params)
        self.genre_combo.currentTextChanged.connect(self.auto_save_novel_params)
        self.pov_combo.currentTextChanged.connect(self.auto_save_novel_params)
        self.lang_combo.currentTextChanged.connect(self.auto_save_novel_params)
        self.rhythm_combo.currentTextChanged.connect(self.auto_save_novel_params)
        self.word_count.textChanged.connect(self.auto_save_novel_params)
        
        # 当输入变化时触发自动保存
        self.novel_title_input.textChanged.connect(self.trigger_auto_save_settings)
        self.bg_text.textChanged.connect(self.trigger_auto_save_settings)
        self.hero_name.textChanged.connect(self.trigger_auto_save_settings)
        self.hero_age.valueChanged.connect(self.trigger_auto_save_settings)
        self.hero_job.textChanged.connect(self.trigger_auto_save_settings)
        self.hero_family.textChanged.connect(self.trigger_auto_save_settings)
        self.hero_desc.textChanged.connect(self.trigger_auto_save_settings)
        self.heroine_name.textChanged.connect(self.trigger_auto_save_settings)
        self.heroine_age.valueChanged.connect(self.trigger_auto_save_settings)
        self.heroine_job.textChanged.connect(self.trigger_auto_save_settings)
        self.heroine_family.textChanged.connect(self.trigger_auto_save_settings)
        self.heroine_desc.textChanged.connect(self.trigger_auto_save_settings)
        self.rel_text.textChanged.connect(self.trigger_auto_save_settings)
        self.plot_text.textChanged.connect(self.trigger_auto_save_settings)
        self.genre_combo.currentTextChanged.connect(self.trigger_auto_save_settings)
        self.pov_combo.currentTextChanged.connect(self.trigger_auto_save_settings)
        self.lang_combo.currentTextChanged.connect(self.trigger_auto_save_settings)
        self.rhythm_combo.currentTextChanged.connect(self.trigger_auto_save_settings)
        self.word_count.textChanged.connect(self.trigger_auto_save_settings)

    def setup_outline_page(self):
        """设置小说大纲页面"""
        layout = QVBoxLayout(self.outline_page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # 大纲显示区域
        outline_group = QGroupBox("小说大纲")
        outline_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        outline_layout = QVBoxLayout(outline_group)
        self.outline_text = QTextEdit()
        self.outline_text.setReadOnly(False)
        self.outline_text.setMinimumHeight(500)
        self.outline_text.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        # 当大纲内容变化时触发自动保存
        self.outline_text.textChanged.connect(self.trigger_auto_save_settings)
        outline_layout.addWidget(self.outline_text)
        layout.addWidget(outline_group)
        
        # 添加大纲操作按钮
        outline_buttons_layout = QHBoxLayout()
        outline_buttons_layout.setSpacing(8)
        
        self.generate_outline_button = QPushButton("生成大纲")
        self.generate_outline_button.setStyleSheet(self.get_button_style())
        self.generate_outline_button.clicked.connect(self.generate_outline)
        
        self.save_outline_button = QPushButton("保存大纲")
        self.save_outline_button.setStyleSheet(self.get_button_style())
        self.save_outline_button.clicked.connect(self.save_outline)
        
        self.load_outline_button = QPushButton("加载大纲")
        self.load_outline_button.setStyleSheet(self.get_button_style())
        self.load_outline_button.clicked.connect(self.load_saved_outline)
        
        self.show_outline_button = QPushButton("直接显示大纲")
        self.show_outline_button.setStyleSheet(self.get_button_style())
        self.show_outline_button.clicked.connect(self.show_outline_directly)
        
        outline_buttons_layout.addWidget(self.generate_outline_button)
        outline_buttons_layout.addWidget(self.save_outline_button)
        outline_buttons_layout.addWidget(self.load_outline_button)
        outline_buttons_layout.addWidget(self.show_outline_button)
        outline_buttons_layout.addStretch()
        
        layout.addLayout(outline_buttons_layout)
        layout.addStretch()

    def setup_chapter_page(self):
        """设置章节内容页面"""
        layout = QVBoxLayout(self.chapter_page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # 章节显示区域
        chapter_group = QGroupBox("章节内容")
        chapter_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        chapter_layout = QVBoxLayout(chapter_group)
        
        # 章节控制
        chapter_control_layout = QHBoxLayout()
        chapter_control_layout.setSpacing(8)
        
        chapter_label = QLabel("章节号:")
        self.chapter_number = QSpinBox()
        self.chapter_number.setRange(1, 500)
        self.chapter_number.setValue(1)
        self.chapter_number.valueChanged.connect(self.on_chapter_number_changed)
        
        self.generate_chapter_button = QPushButton("单章小说生成")
        self.generate_chapter_button.setStyleSheet(self.get_button_style())
        self.generate_chapter_button.clicked.connect(self.generate_chapter)
        
        self.prev_chapter_button = QPushButton("上一章")
        self.prev_chapter_button.setStyleSheet(self.get_button_style())
        self.prev_chapter_button.setMinimumSize(80, 32)  # 增加按钮最小尺寸
        self.prev_chapter_button.clicked.connect(self.prev_chapter)
        
        self.next_chapter_button = QPushButton("下一章")
        self.next_chapter_button.setStyleSheet(self.get_button_style())
        self.next_chapter_button.setMinimumSize(80, 32)  # 增加按钮最小尺寸
        self.next_chapter_button.clicked.connect(self.next_chapter)
        
        self.save_button = QPushButton("保存章节")
        self.save_button.setStyleSheet(self.get_button_style())
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_result)
        
        chapter_control_layout.addWidget(chapter_label)
        chapter_control_layout.addWidget(self.chapter_number)
        chapter_control_layout.addWidget(self.prev_chapter_button)
        chapter_control_layout.addWidget(self.next_chapter_button)
        
        # 添加读取上一章内容的选项
        self.single_read_previous_chapter_checkbox = QCheckBox("读取上一章内容作为上下文")
        self.single_read_previous_chapter_checkbox.setChecked(True)  # 默认选中
        self.single_read_previous_chapter_checkbox.setStyleSheet("""
            QCheckBox {
                font-size: 13px;
                color: #374151;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        chapter_control_layout.addWidget(self.single_read_previous_chapter_checkbox)
        
        chapter_control_layout.addWidget(self.generate_chapter_button)
        chapter_control_layout.addWidget(self.save_button)
        
        # 设置按钮的拉伸因子，使它们均匀分布
        chapter_control_layout.setStretchFactor(chapter_label, 0)
        chapter_control_layout.setStretchFactor(self.chapter_number, 0)
        chapter_control_layout.setStretchFactor(self.prev_chapter_button, 1)
        chapter_control_layout.setStretchFactor(self.next_chapter_button, 1)
        chapter_control_layout.setStretchFactor(self.single_read_previous_chapter_checkbox, 0)
        chapter_control_layout.setStretchFactor(self.generate_chapter_button, 1)
        chapter_control_layout.setStretchFactor(self.save_button, 1)
        
        self.chapter_text = QTextEdit()
        self.chapter_text.setReadOnly(False)
        self.chapter_text.setMinimumHeight(400)
        self.chapter_text.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        # 设置默认文本（动态效果）
        self.default_text_timer = QTimer()
        self.default_text_timer.timeout.connect(self.update_default_text)
        self.default_text_state = 0
        self.update_default_text()
        
        # 当章节内容变化时触发自动保存
        self.chapter_text.textChanged.connect(self.trigger_auto_save_settings)
        

        
        chapter_layout.addLayout(chapter_control_layout)
        chapter_layout.addWidget(self.chapter_text)
        layout.addWidget(chapter_group)
        layout.addStretch()

    def update_default_text(self):
        """更新默认文本的动态效果"""
        if self.chapter_text.toPlainText() == "小说内容苦思冥想，写作中！！！":
            # 如果当前是默认文本，开始动态效果
            dots = ["", ".", "..", "..."]
            text = f"小说内容苦思冥想，写作中{dots[self.default_text_state % 4]}！！！"
            self.chapter_text.setPlainText(text)
            self.default_text_state += 1
            
            # 启动定时器，每500毫秒更新一次
            self.default_text_timer.start(500)
        else:
            # 如果用户已经输入内容，停止动态效果
            self.default_text_timer.stop()

    def setup_batch_page(self):
        """设置批量生成章节页面"""
        layout = QVBoxLayout(self.batch_page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # 批量生成区域
        batch_group = QGroupBox("批量生成章节")
        batch_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        batch_layout = QGridLayout(batch_group)
        
        batch_layout.addWidget(QLabel("起始章节:"), 0, 0)
        self.start_chapter_spin = QSpinBox()
        self.start_chapter_spin.setRange(1, 500)
        self.start_chapter_spin.setValue(1)
        batch_layout.addWidget(self.start_chapter_spin, 0, 1)
        
        batch_layout.addWidget(QLabel("结束章节:"), 0, 2)
        self.end_chapter_spin = QSpinBox()
        self.end_chapter_spin.setRange(1, 500)
        self.end_chapter_spin.setValue(10)
        batch_layout.addWidget(self.end_chapter_spin, 0, 3)
        
        self.batch_generate_button = QPushButton("开始批量生成")
        self.batch_generate_button.setStyleSheet(self.get_button_style())
        self.batch_generate_button.clicked.connect(self.start_batch_generation)
        batch_layout.addWidget(self.batch_generate_button, 0, 4)
        
        self.batch_stop_button = QPushButton("停止生成")
        self.batch_stop_button.setStyleSheet(self.get_button_style(disabled=True))
        self.batch_stop_button.setEnabled(False)
        self.batch_stop_button.clicked.connect(self.stop_batch_generation)
        batch_layout.addWidget(self.batch_stop_button, 0, 5)
        
        # 设置按钮列的拉伸因子，使按钮均匀分布
        batch_layout.setColumnStretch(0, 0)  # 起始章节标签
        batch_layout.setColumnStretch(1, 0)  # 起始章节SpinBox
        batch_layout.setColumnStretch(2, 0)  # 结束章节标签
        batch_layout.setColumnStretch(3, 0)  # 结束章节SpinBox
        batch_layout.setColumnStretch(4, 1)  # 开始批量生成按钮
        batch_layout.setColumnStretch(5, 1)  # 停止生成按钮
        
        # 添加读取上一章内容的选项
        self.read_previous_chapter_checkbox = QCheckBox("读取上一章内容作为上下文")
        self.read_previous_chapter_checkbox.setChecked(True)  # 默认选中
        self.read_previous_chapter_checkbox.setStyleSheet("""
            QCheckBox {
                font-size: 13px;
                color: #374151;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        batch_layout.addWidget(self.read_previous_chapter_checkbox, 1, 0, 1, 6)
        
        # 批量生成进度条
        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setRange(0, 100)
        self.batch_progress_bar.setValue(0)
        self.batch_progress_bar.setStyleSheet("""
            QProgressBar {
                height: 6px;
                border: none;
                border-radius: 3px;
                background-color: #E5E7EB;
            }
            QProgressBar::chunk {
                background-color: #6366F1;
                border-radius: 3px;
            }
        """)
        batch_layout.addWidget(self.batch_progress_bar, 2, 0, 1, 6)
        
        # 批量生成进度标签
        self.batch_progress_label = QLabel("就绪")
        self.batch_progress_label.setStyleSheet("color: #4B5563; font-size: 12px;")
        batch_layout.addWidget(self.batch_progress_label, 3, 0, 1, 6)
        
        layout.addWidget(batch_group)
        layout.addStretch()

    def setup_polish_page(self):
        """设置AI润色小说章节页面"""
        layout = QVBoxLayout(self.dedup_page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # 添加AI润色选项
        polish_group = QGroupBox("AI润色小说")
        polish_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #1F2937;
                border: 2px solid #E5E7EB;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
                background-color: #F9FAFB;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                background-color: #F9FAFB;
            }
        """)
        
        # 使用垂直布局替代网格布局
        polish_layout = QVBoxLayout(polish_group)
        polish_layout.setSpacing(20)
        polish_layout.setContentsMargins(20, 20, 20, 20)
        
        # 章节选择区域
        chapter_section = QWidget()
        chapter_layout = QHBoxLayout(chapter_section)
        chapter_layout.setContentsMargins(0, 0, 0, 0)
        
        chapter_label = QLabel("选择章节：")
        chapter_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #374151; min-width: 80px;")
        chapter_layout.addWidget(chapter_label)
        
        self.chapter_combo = QComboBox()
        self.chapter_combo.setStyleSheet("""
            QComboBox {
                padding: 10px 15px;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                font-size: 14px;
                background-color: white;
                min-width: 300px;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 6px solid #6B7280;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #D1D5DB;
                selection-background-color: #6366F1;
                selection-color: white;
                padding: 8px;
                font-size: 13px;
            }
        """)
        chapter_layout.addWidget(self.chapter_combo)
        chapter_layout.addStretch()
        
        polish_layout.addWidget(chapter_section)
        
        # 润色提示词区域
        prompt_section = QWidget()
        prompt_layout = QVBoxLayout(prompt_section)
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        
        prompt_label = QLabel("润色提示词：")
        prompt_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #374151;")
        prompt_layout.addWidget(prompt_label)
        
        # 预设提示词选择
        preset_layout = QHBoxLayout()
        preset_layout.setContentsMargins(0, 0, 0, 0)
        
        preset_label = QLabel("预设提示词：")
        preset_label.setStyleSheet("font-size: 13px; color: #6B7280; min-width: 80px;")
        preset_layout.addWidget(preset_label)
        
        self.preset_combo = QComboBox()
        self.preset_combo.setStyleSheet("""
            QComboBox {
                padding: 6px 10px;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                font-size: 13px;
                background-color: white;
                min-width: 200px;
            }
        """)
        
        # 添加预设提示词选项
        self.preset_combo.addItem("请选择预设提示词...", "")
        self.preset_combo.addItem("优化文笔和语言表达", "请优化本章节的文笔和语言表达，使文字更加优美流畅，增强文学性")
        self.preset_combo.addItem("增强情感描写", "请重点增强本章节的情感描写，让人物情感更加细腻真实，增强读者共鸣")
        self.preset_combo.addItem("提高可读性", "请优化本章节的可读性，使语言更加通俗易懂，段落结构更加清晰")
        self.preset_combo.addItem("调整节奏和张力", "请优化本章节的节奏感和戏剧张力，使情节推进更加合理，增强吸引力")
        self.preset_combo.addItem("丰富场景描写", "请丰富本章节的场景描写，让环境更加生动具体，增强画面感")
        self.preset_combo.addItem("优化对话自然度", "请优化本章节的对话内容，使对话更加自然流畅，符合人物性格")
        self.preset_combo.addItem("综合全面优化", "请对本章节进行全面优化，包括文笔、情感、节奏、对话等各个方面")
        
        self.preset_combo.currentTextChanged.connect(self.on_preset_selected)
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addStretch()
        prompt_layout.addLayout(preset_layout)
        
        self.polish_prompt_text = QTextEdit()
        self.polish_prompt_text.setPlaceholderText("请输入润色提示词，或从上方选择预设提示词...")
        self.polish_prompt_text.setMaximumHeight(100)
        self.polish_prompt_text.setStyleSheet("""
            QTextEdit {
                padding: 12px;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                font-size: 14px;
                background-color: white;
                line-height: 1.5;
            }
        """)
        prompt_layout.addWidget(self.polish_prompt_text)
        
        polish_layout.addWidget(prompt_section)
        
        # 按钮区域
        button_section = QWidget()
        button_layout = QHBoxLayout(button_section)
        button_layout.setContentsMargins(0, 0, 0, 0)
        
        self.polish_button = QPushButton("开始润色")
        self.polish_button.setStyleSheet(self.get_button_style())
        self.polish_button.clicked.connect(self.start_polish_chapter)
        self.polish_button.setMinimumHeight(45)
        self.polish_button.setMinimumWidth(120)
        button_layout.addWidget(self.polish_button)
        
        self.save_polish_button = QPushButton("保存润色结果")
        self.save_polish_button.setStyleSheet(self.get_button_style(disabled=True))
        self.save_polish_button.setEnabled(False)
        self.save_polish_button.clicked.connect(self.save_polished_chapter)
        self.save_polish_button.setMinimumHeight(45)
        self.save_polish_button.setMinimumWidth(120)
        button_layout.addWidget(self.save_polish_button)
        
        button_layout.addStretch()
        polish_layout.addWidget(button_section)
        
        # 润色结果预览区域
        preview_section = QWidget()
        preview_layout = QVBoxLayout(preview_section)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        preview_label = QLabel("润色结果预览：")
        preview_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #374151;")
        preview_layout.addWidget(preview_label)
        
        self.polish_preview_text = QTextEdit()
        self.polish_preview_text.setReadOnly(True)
        self.polish_preview_text.setStyleSheet("""
            QTextEdit {
                padding: 15px;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                font-size: 14px;
                background-color: #F8F9FA;
                min-height: 350px;
                line-height: 1.6;
            }
        """)
        preview_layout.addWidget(self.polish_preview_text)
        
        polish_layout.addWidget(preview_section)
        
        # 润色说明
        polish_info = QLabel("💡 AI润色功能可以对已有章节进行优化，提高文笔质量。润色后的章节会保存为新文件，在原文件名后加'新'字，不会覆盖原文件。")
        polish_info.setStyleSheet("font-size: 13px; color: #6B7280; margin-top: 10px; padding: 12px; background-color: #F0F9FF; border-radius: 6px; border: 1px solid #BAE6FD;")
        polish_info.setWordWrap(True)
        polish_layout.addWidget(polish_info)
        
        layout.addWidget(polish_group)
        layout.addStretch()
        
        # 初始化章节列表
        self.load_chapter_list()
    
    def load_chapter_list(self):
        """加载章节列表"""
        self.chapter_combo.clear()
        
        # 获取保存目录
        save_path = getattr(self, 'save_path', 'novels')
        if not os.path.exists(save_path):
            return
            
        # 查找所有章节文件
        chapter_files = []
        for file_name in os.listdir(save_path):
            if file_name.startswith("第") and file_name.endswith("章.txt"):
                chapter_files.append(file_name)
        
        # 按章节号排序
        chapter_files.sort(key=lambda x: self.extract_chapter_number(x))
        
        # 添加到下拉框
        for file_name in chapter_files:
            self.chapter_combo.addItem(file_name)
    
    def extract_chapter_number(self, file_name):
        """从文件名中提取章节号"""
        import re
        match = re.search(r'第(\d+)章', file_name)
        if match:
            return int(match.group(1))
        return 0
    
    def start_polish_chapter(self):
        """开始润色章节"""
        # 检查章节选择
        if self.chapter_combo.currentText() == "":
            QMessageBox.warning(self, "没有选择章节", "请先选择要润色的章节")
            return
            
        # 检查润色提示词
        polish_prompt = self.polish_prompt_text.toPlainText().strip()
        if not polish_prompt:
            QMessageBox.warning(self, "没有润色提示", "请输入润色提示词")
            return
            
        # 检查API配置
        if not self.api_key or not self.api_url:
            QMessageBox.warning(self, "API配置错误", "请先配置API密钥和地址")
            return
            
        # 更新UI状态
        self.polish_button.setEnabled(False)
        self.save_polish_button.setEnabled(False)
        self.status_bar.showMessage("正在润色章节...")
        
        # 读取章节内容
        chapter_file = self.chapter_combo.currentText()
        save_path = getattr(self, 'save_path', 'novels')
        file_path = os.path.join(save_path, chapter_file)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                chapter_content = f.read()
        except Exception as e:
            QMessageBox.critical(self, "读取章节失败", f"无法读取章节文件: {str(e)}")
            self.polish_button.setEnabled(True)
            return
            
        # 构建润色prompt
        prompt = f"请对以下小说章节进行润色优化：\n\n"
        prompt += f"【原章节内容】\n{chapter_content}\n\n"
        prompt += f"【润色要求】\n{polish_prompt}\n\n"
        prompt += f"【润色说明】\n"
        prompt += f"1. 保持原章节的核心情节和人物设定不变\n"
        prompt += f"2. 重点优化文笔、语言表达和可读性\n"
        prompt += f"3. 增强情感描写和场景氛围\n"
        prompt += f"4. 提高对话的自然度和表现力\n"
        prompt += f"5. 保持章节长度与原章节相近\n"
        prompt += f"6. 使用纯中文输出，不要包含任何英文内容\n"
        
        # 创建API调用线程
        self.polish_thread = ApiCallThread(self.api_type, self.api_url, self.api_key, prompt, self.model_name,
                                         api_format=self.api_format, custom_headers=self.custom_headers)
        self.polish_thread.finished.connect(self.on_polish_finished)
        self.polish_thread.error.connect(self.on_polish_error)
        self.polish_thread.start()
        
        # 保存润色相关信息
        self.current_polish_chapter = chapter_file
        self.original_chapter_content = chapter_content
    
    def on_polish_finished(self, response_text, status):
        """润色完成回调"""
        try:
            # 更新UI状态
            self.polish_button.setEnabled(True)
            self.save_polish_button.setEnabled(True)
            self.status_bar.showMessage("润色完成")
            
            # 显示润色结果
            self.polish_preview_text.setPlainText(response_text)
            self.polished_content = response_text
            
            # 显示成功提示
            QMessageBox.information(self, "润色完成", "章节润色已完成，请查看预览结果")
            
            # 调试信息：打印按钮状态
            print(f"润色完成：保存按钮状态 = {self.save_polish_button.isEnabled()}")
            
        except Exception as e:
            print(f"润色完成回调出错: {e}")
            self.status_bar.showMessage("润色处理出错")
    
    def on_preset_selected(self, text):
        """预设提示词选择事件"""
        if text == "请选择预设提示词...":
            # 清空提示词输入框
            self.polish_prompt_text.clear()
            return
            
        # 获取当前选中的提示词内容
        current_data = self.preset_combo.currentData()
        if current_data:
            # 设置到提示词输入框
            self.polish_prompt_text.setPlainText(current_data)
            
            # 显示提示信息
            self.status_bar.showMessage(f"已选择预设提示词：{text}", 3000)
    
    def on_polish_error(self, error_msg):
        """润色出错回调"""
        # 更新UI状态
        self.polish_button.setEnabled(True)
        self.save_polish_button.setEnabled(False)
        self.status_bar.showMessage("润色失败")
        
        # 显示错误信息
        QMessageBox.critical(self, "润色失败", f"润色过程中出现错误：{error_msg}")
    
    def save_polished_chapter(self):
        """保存润色后的章节"""
        if not hasattr(self, 'polished_content') or not self.polished_content:
            QMessageBox.warning(self, "没有润色内容", "请先完成章节润色")
            return
            
        if not hasattr(self, 'current_polish_chapter'):
            QMessageBox.warning(self, "章节信息错误", "无法获取章节信息")
            return
            
        # 询问用户是否保存
        reply = QMessageBox.question(self, "保存润色结果", 
                                    "是否保存润色后的章节？\n\n"
                                    "注意：润色后的章节将保存为新文件，不会覆盖原章节。",
                                    QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.No:
            return
            
        # 构建新文件名（在原文件名后加"新"字）
        original_file = self.current_polish_chapter
        new_file = original_file.replace("章.txt", "章新.txt")
        
        # 直接使用指定的保存路径
        save_path = self.chapter_path if hasattr(self, 'chapter_path') else "zhangjie"
        
        # 确保目录存在
        if not os.path.exists(save_path):
            os.makedirs(save_path)
            print(f"[调试] 创建保存目录: {save_path}")
        
        new_file_path = os.path.join(save_path, new_file)
        
        # 检查文件是否已存在
        if os.path.exists(new_file_path):
            reply = QMessageBox.question(self, "文件已存在", 
                                        f"文件 {new_file} 已存在，是否覆盖？",
                                        QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
        
        try:
            # 保存润色后的内容
            with open(new_file_path, 'w', encoding='utf-8') as f:
                f.write(self.polished_content)
            
            # 显示成功消息
            QMessageBox.information(self, "保存成功", 
                                  f"润色后的章节已保存为：{new_file}")
            
            # 重置状态
            self.save_polish_button.setEnabled(False)
            self.polish_preview_text.clear()
            
            if hasattr(self, 'polished_content'):
                del self.polished_content
            if hasattr(self, 'current_polish_chapter'):
                del self.current_polish_chapter
            if hasattr(self, 'original_chapter_content'):
                del self.original_chapter_content
                
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存润色章节失败：{str(e)}")

    def update_prompt(self):
        """更新提示词文本"""
        # 获取小说标题
        title = self.novel_title_input.text().strip()
        title = title if title else "未命名小说"
        
        # 获取题材类型
        genre = self.genre_combo.currentText() if hasattr(self, 'genre_combo') else "现代"
        
        # 构建提示词 - 使用黄金结构
        prompt = f"请根据以下设定创作小说《{title}》：\n\n"
        
        # 模块0：吸引人的开头（定"第一印象"，让读者一秒入坑）
        prompt += "### 零、吸引人的开头（第一印象）\n"
        prompt += "- 开篇钩子：请设计一个能立即抓住读者注意力的开场事件或场景，要求具体、生动、有画面感\n"
        prompt += "- 悬念设置：在开头部分埋下1-2个核心悬念，引发读者好奇心，并说明这些悬念将在何时揭晓\n"
        prompt += "- 情感冲击：设计一个能引发读者强烈情感共鸣的开头场景，描述具体的情感反应和读者心理预期\n"
        prompt += "- 节奏把控：确保开头节奏紧凑，避免冗长铺垫，快速进入主线，建议在500字内完成背景介绍\n"
        prompt += "- 独特视角：通过独特的叙事角度或场景设置，让故事从开始就与众不同，具体说明视角特点\n\n"
        
        # 模块1：基础设定（定"故事底色"，避免混乱）
        prompt += "### 一、基础设定（故事底色）\n"
        prompt += f"- 题材&子类型：{genre}\n"
        prompt += f"- 时代&世界观：{self.bg_text.toPlainText()}\n"
        prompt += "- 核心场景：请根据故事背景选择3-5个主要发生地点，每个场景应自带氛围感，能暗示故事冲突，并说明场景在故事中的作用\n"
        prompt += "- 时间设定：明确故事发生的时间跨度，以及关键时间节点\n"
        prompt += "- 社会环境：描述故事发生的社会背景、文化氛围和价值观念，这些将如何影响人物行为\n\n"
        
        # 模块2：核心冲突（定"故事张力"，这是吸引读者的关键）
        prompt += "### 二、核心冲突（故事张力）\n"
        prompt += "- 表层冲突（主角的显性目标）：请明确主角想要达成的具体目标，包括目标的具体表现形式和达成标准\n"
        prompt += "- 深层冲突（目标背后的隐性动机）：请描述主角追求目标的内在原因，包括心理需求、过往经历和价值观影响\n"
        prompt += "- 冲突升级点：请设计3-4个让冲突变难的转折点，每个转折点要说明触发事件、影响和主角的反应\n"
        prompt += "- 内外冲突交织：说明主角如何同时应对外部挑战和内心矛盾，以及这些冲突如何相互影响\n\n"
        
        # 模块3：立体人物（定"读者共情点"，人物活了故事才活）
        prompt += "### 三、立体人物（读者共情点）\n"
        prompt += f"- 主角：{self.hero_name.text()}，{self.hero_age.value()}岁，职业是{self.hero_job.text()}，家庭背景为{self.hero_family.text()}。性格特点：{self.hero_desc.toPlainText()}\n"
        prompt += f"  - 核心动机：请描述主角行动的核心驱动力，包括短期动机和长期动机\n"
        prompt += f"  - 致命弱点：请描述主角的弱点或恐惧，以及这些弱点如何在故事中制造冲突\n"
        prompt += f"  - 初始状态vs目标状态：请描述主角的起点和期望达成的状态，以及转变过程的关键节点\n"
        prompt += f"  - 成长弧线：设计主角在故事中的心理变化轨迹，包括关键转折点和最终变化\n"
        prompt += f"- 女主角：{self.heroine_name.text()}，{self.heroine_age.value()}岁，职业是{self.heroine_job.text()}，家庭背景为{self.heroine_family.text()}。性格特点：{self.heroine_desc.toPlainText()}\n"
        prompt += f"  - 与主角关系：详细描述女主角与主角的关系发展轨迹，包括关键转折点\n"
        prompt += f"  - 个人成长：设计女主角在故事中的成长变化，以及这些变化如何影响主线剧情\n"
        prompt += f"- 反派/对手：请设计非脸谱化的反派，避免为坏而坏，要有合理的动机和背景故事\n"
        prompt += f"  - 反派动机：详细描述反派的行为动机，包括价值观、过往经历和目标\n"
        prompt += f"  - 与主角关系：说明反派与主角的关联，以及这种关系如何加剧冲突\n"
        prompt += f"- 关键配角：请描述2-3个关键配角的功能和与主角的情感连接，每个配角要有明确的作用\n"
        prompt += f"  - 配角作用：说明每个配角在故事中的具体功能，如推动情节、揭示主题、对比主角等\n"
        prompt += f"  - 配角成长：设计配角的成长变化，以及这些变化如何影响主角和主线剧情\n\n"
        
        # 模块4：节奏设计（定"追更欲"，避免读者弃文）
        prompt += "### 四、节奏设计（追更欲）\n"
        prompt += "- 开头（前3章/10%内容）：请设计钩子事件，打破主角的日常，详细描述事件经过和直接影响\n"
        prompt += "  - 第1章：介绍主角日常，暗示潜在问题，结尾出现钩子事件\n"
        prompt += "  - 第2章：主角应对钩子事件，发现更大问题，引入关键配角\n"
        prompt += "  - 第3章：主角做出初步决定，进入新环境，面临第一个挑战\n"
        prompt += "- 中间（30%-70%内容）：请设置伪解答、反转和情感爆发点\n"
        prompt += "  - 上升阶段（30%-50%）：主角尝试解决问题，遭遇挫折，发现新线索\n"
        prompt += "  - 中点转折（50%）：重大发现或事件，改变故事方向，提高风险\n"
        prompt += "  - 下降阶段（50%-70%）：主角应对新挑战，关系变化，准备最终对决\n"
        prompt += "- 高潮（70%-90%内容）：请设计主角的终极选择，必须放弃一样重要的东西\n"
        prompt += "  - 最终对决：主角与反派的直接冲突，揭示所有悬念\n"
        prompt += "  - 终极选择：主角面临的艰难抉择，说明选择的原因和后果\n"
        prompt += "  - 高潮余波：描述高潮事件的直接后果和影响\n"
        prompt += "- 结尾（90%-100%内容）：请设计闭环+余韵或开放钩子\n"
        prompt += "  - 情节收束：解决主要情节线，说明人物最终状态\n"
        prompt += "  - 主题升华：通过具体场景或对话，点明故事主题\n"
        prompt += "  - 情感余韵：描述读者在故事结束后的情感体验\n"
        prompt += "  - 续作空间：如有必要，设计可能的续作线索\n\n"
        
        # 模块5：类型化亮点（定"差异化"，避免和其他小说撞脸）
        prompt += "### 五、类型化亮点（差异化）\n"
        if "悬疑" in genre:
            prompt += "- 请埋3条互相交织的线索，最后所有线索指向同一个真相\n"
            prompt += "  - 线索1：明线，读者和主角都能看到，但容易被误导\n"
            prompt += "  - 线索2：暗线，隐藏在细节中，需要仔细观察才能发现\n"
            prompt += "  - 线索3：情感线，通过人物关系变化暗示真相\n"
        elif "言情" in genre:
            prompt += "- 请设计反套路互动，避免俗套的情感发展\n"
            prompt += "  - 初遇反套路：打破常见的浪漫相遇模式\n"
            prompt += "  - 矛盾设计：创造独特的情感冲突，超越简单的误会\n"
            prompt += "  - 关系发展：设计非线性的情感发展轨迹，有进有退\n"
        elif "玄幻" in genre or "奇幻" in genre:
            prompt += "- 请设计独特的能力设定，避免与现有作品雷同\n"
            prompt += "  - 能力来源：详细解释能力的起源和原理\n"
            prompt += "  - 能力限制：明确能力的边界和代价，增加真实感\n"
            prompt += "  - 能力成长：设计能力的发展轨迹，与主角成长相呼应\n"
        else:
            prompt += "- 请设计本题材特有的亮点，增强故事记忆点\n"
            prompt += "  - 题材创新：在传统题材基础上加入新元素\n"
            prompt += "  - 表现手法：使用独特的叙事技巧或表现形式\n"
            prompt += "  - 主题深度：挖掘题材深层含义，提供新的思考角度\n"
        prompt += f"- 角色关系：{self.rel_text.toPlainText()}\n"
        prompt += f"- 核心剧情：{self.plot_text.toPlainText()}\n\n"
        
        # 模块6：章节规划（定"写作蓝图"，确保每章都有价值）
        prompt += "### 六、章节规划（写作蓝图）\n"
        prompt += "- 请设计至少15个关键章节，每个章节都要有明确的目的和价值\n"
        prompt += "- 每章应包含：章节标题、核心事件、人物变化、情节推进、悬念设置\n"
        prompt += "- 章节之间要有逻辑连贯性，前一章为后一章铺垫，后一章解答前一章悬念\n"
        prompt += "- 关键章节要详细设计，包括场景、对话、行动和内心活动\n\n"
        
        # 写作风格要求
        prompt += "### 七、写作风格要求\n"
        prompt += f"- 人称视角：{self.pov_combo.currentText()}\n"
        prompt += f"- 语言风格：{self.lang_combo.currentText()}\n"
        prompt += f"- 叙事节奏：{self.rhythm_combo.currentText()}\n"
        prompt += f"- 预计字数：约{self.word_count.text()}字\n"
        prompt += "- 描写手法：请说明将使用的主要描写技巧，如环境描写、心理描写、动作描写等\n"
        prompt += "- 对话风格：设计符合人物性格的对话特点，避免千篇一律\n"
        prompt += "- 情感表达：说明如何通过文字传达情感，引发读者共鸣\n\n"
        
        # 小说大纲要求
        prompt += "请按照以上黄金结构生成小说大纲，确保：\n"
        prompt += "0. 开头必须精彩，用钩子事件迅速抓住读者注意力\n"
        prompt += "1. 冲突前置，别铺垫太久，在第一章就引入核心冲突\n"
        prompt += "2. 人物有弱点，比完美更吸引人，弱点要推动情节发展\n"
        prompt += "3. 每个情节节点都要回答读者会关心什么，同时制造新的悬念\n"
        prompt += "4. 大纲要详细具体，每个情节点都要有具体的场景和事件描述\n"
        prompt += "5. 人物关系要复杂立体，避免简单的善恶二元对立\n"
        prompt += "6. 情感线索要清晰，与主线剧情紧密结合\n"
        prompt += "7. 重要：请使用纯中文生成大纲，不要包含任何英文内容\n\n"
        
        # 更新提示词文本框
        self.prompt_text.setText(prompt)

    def change_model(self, model_name):
        """更改使用的模型"""
        self.model_name = model_name
        # 更新状态栏显示当前模型名称
        self.status_bar.showMessage(f"已切换到模型: {model_name}")
        
        # 更新当前API配置中的模型名称
        try:
            # 加载现有参数
            existing_params = {}
            if os.path.exists("user_params.json"):
                with open("user_params.json", "r", encoding="utf-8") as f:
                    existing_params = json.load(f)
            
            # 确保api_configs存在
            if "api_configs" not in existing_params:
                existing_params["api_configs"] = {}
            
            # 确保当前API类型配置存在
            if self.api_type not in existing_params["api_configs"]:
                existing_params["api_configs"][self.api_type] = {}
            
            # 更新模型名称
            existing_params["api_configs"][self.api_type]["model_name"] = model_name
            
            # 保存更新后的参数
            with open("user_params.json", "w", encoding="utf-8") as f:
                json.dump(existing_params, f, ensure_ascii=False, indent=4)
            
            print(f"已更新模型配置: {self.api_type} -> {model_name}")
        except Exception as e:
            print(f"更新模型配置失败: {e}")

    def generate_outline(self):
        """生成小说大纲"""
        # 检查必要的输入
        if not self.bg_text.toPlainText() or not self.plot_text.toPlainText():
            QMessageBox.warning(self, "输入不完整", "请填写小说背景和核心剧情")
            return
            
        # 检查是否使用已保存的大纲
        if hasattr(self, 'use_saved_outline') and self.use_saved_outline.isChecked():
            # 尝试加载已保存的大纲
            if self.load_saved_outline():
                self.status_bar.showMessage("已加载上次生成的小说大纲")
                # 加载成功后直接返回，不生成新大纲
                return
            else:
                # 如果加载失败，提示用户并继续生成新大纲
                QMessageBox.information(self, "大纲不存在", "未找到已保存的大纲，将生成新的大纲")
        
        self.status_bar.showMessage("正在生成小说大纲...")
        self.generate_button.setEnabled(False)
        self.stop_button.setEnabled(True)  # 点击生成大纲按钮后启用停止按钮
        self.set_app_status("忙碌")
        
        # 显示进度条
        self.progress_bar.setValue(0)
        self.progress_label.setText("正在生成大纲...")
        
        # 创建API调用线程
        # 改进大纲生成的prompt，包含更多上下文信息
        title = self.novel_title_input.text().strip()
        title = title if title else "未命名小说"
        
        # 获取小说背景和核心剧情
        background = self.bg_text.toPlainText()
        plot = self.plot_text.toPlainText()
        
        # 构建详细的大纲生成prompt
        prompt = f"请为小说《{title}》生成详细的大纲。\n\n"
        prompt += f"小说背景：{background}\n\n"
        prompt += f"核心剧情：{plot}\n\n"
        prompt += "请生成一个完整的小说大纲，包含以下内容：\n"
        prompt += "1. 故事梗概（200-300字）\n"
        prompt += "2. 主要人物介绍（主角、配角及其关系）\n"
        prompt += "3. 故事结构（开端、发展、高潮、结局）\n"
        prompt += "4. 主要情节线（至少3条）\n"
        prompt += "5. 情感发展线（主角情感变化）\n"
        prompt += "6. 关键转折点和冲突\n"
        prompt += "7. 每章内容概要（至少10章）\n\n"
        prompt += "要求：\n"
        prompt += "- 大纲要详细具体，每个情节点都要有具体的场景和事件描述\n"
        prompt += "- 人物关系要复杂立体，避免简单的善恶二元对立\n"
        prompt += "- 情感线索要清晰，与主线剧情紧密结合\n"
        prompt += "- 重要：请使用纯中文生成大纲，不要包含任何英文内容\n"
        
        self.api_thread = ApiCallThread(self.api_type, self.api_url, self.api_key, prompt, self.model_name,
                                       api_format=self.api_format, custom_headers=self.custom_headers)
        self.api_thread.finished.connect(self.on_outline_ready)
        self.api_thread.error.connect(self.on_api_error)
        self.api_thread.progress.connect(self.on_progress)
        # 新增：连接内容更新信号，实现实时显示
        self.api_thread.content_update.connect(self.on_outline_content_update)
        self.api_thread.start()

    def generate_chapter(self):
        """生成章节内容"""
        if not self.outline_text.toPlainText():
            QMessageBox.warning(self, "没有大纲", "请先生成小说大纲")
            return
            
        self.status_bar.showMessage(f"正在生成第{self.chapter_number.value()}章...")
        self.generate_chapter_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.set_app_status("忙碌")
        
        # 获取小说标题
        title = self.novel_title_input.text().strip()
        title = title if title else "未命名小说"
        
        # 在配置的字数范围内随机选择一个目标字数
        target_length = random.randint(self.min_chapter_length, self.max_chapter_length)
        self.status_bar.showMessage(f"生成第{self.chapter_number.value()}章，目标字数: {target_length}字")
        
        # 显示进度条
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"正在生成第{self.chapter_number.value()}章...")
        
        # 优化提示词
        prompt = f"请根据以下小说大纲生成《{title}》的第{self.chapter_number.value()}章内容：\n"
        prompt += self.outline_text.toPlainText() + "\n\n"
        
        # 如果是第一章，添加特殊要求
        if self.chapter_number.value() == 1:
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
            prompt += "【情感冲突要求】\n"
            prompt += "11. 必须包含'虐妻一时爽，追妻火葬场'元素，情节要狗血且富有张力\n"
            prompt += "12. 主角与女主角之间要有误解、伤害与情感纠葛，为后续追妻情节埋下伏笔\n"
            prompt += "13. 设计至少一个让读者心疼女主角的场景，展现主角的冷漠或误解\n"
            prompt += "14. 在情感冲突中埋下后悔与救赎的种子，为后续追妻火葬场做铺垫\n\n"
        
        # 如果用户选择了读取上一章内容，并且当前章节不是第一章，则读取上一章内容
        if hasattr(self, 'single_read_previous_chapter_checkbox') and self.single_read_previous_chapter_checkbox.isChecked() and self.chapter_number.value() > 1:
            prev_chapter = self.chapter_number.value() - 1
            
            # 尝试多种可能的文件名格式
            possible_files = [
                f"第{prev_chapter}章.txt",  # 旧格式
                f"第{prev_chapter:03d}章.txt"  # 带零的旧格式
            ]
            
            prev_file_path = None
            for file_name in possible_files:
                test_path = os.path.join(self.save_path, file_name)
                if os.path.exists(test_path):
                    prev_file_path = test_path
                    break
            
            if prev_file_path and os.path.exists(prev_file_path):
                try:
                    with open(prev_file_path, 'r', encoding='utf-8') as file:
                        prev_content = file.read()
                        # 只取上一章的最后1000个字符，避免上下文过长
                        prev_content = prev_content[-1000:] if len(prev_content) > 1000 else prev_content
                        prompt += f"上一章结尾内容：\n{prev_content}\n\n"
                        prompt += f"请确保新章节与上一章内容衔接自然，情节连贯。\n\n"
                        print(f"已读取第{prev_chapter}章内容作为上下文")
                except Exception as e:
                    print(f"读取上一章内容失败: {e}")
            else:
                print(f"未找到第{prev_chapter}章文件")
        
        prompt += f"章节具体要求：\n"
        prompt += f"- 保持{self.pov_combo.currentText()}视角\n"
        prompt += f"- 使用{self.lang_combo.currentText()}风格\n"
        prompt += f"- 节奏：{self.rhythm_combo.currentText()}\n"
        prompt += f"- 字数：约{target_length}字\n"
        prompt += f"- 重要：请使用纯中文生成章节内容，不要包含任何英文内容\n"
        
        # 添加情感冲突要求
        prompt += "\n【情感冲突要求】\n"
        prompt += "1. 必须包含'虐妻一时爽，追妻火葬场'元素，情节要狗血且富有张力\n"
        prompt += "2. 主角与女主角之间要有误解、伤害与情感纠葛，为后续追妻情节埋下伏笔\n"
        prompt += "3. 设计至少一个让读者心疼女主角的场景，展现主角的冷漠或误解\n"
        prompt += "4. 在情感冲突中埋下后悔与救赎的种子，为后续追妻火葬场做铺垫\n"
        prompt += "5. 情感冲突要激烈但不过度，保持角色性格的一致性\n"
        prompt += "6. 每章都要有情感张力，让读者感受到'虐'的痛苦和'追'的渴望\n"
        
        # 添加通用写作技巧要求
        prompt += "\n【写作技巧要求】\n"
        prompt += "1. 每个段落都要有明确目的，要么推动情节，要么塑造人物，要么营造氛围\n"
        prompt += "2. 使用'展示而非告知'的写作手法，通过具体行动和细节展示信息\n"
        prompt += "3. 控制信息释放节奏，不要一次性揭示所有信息\n"
        prompt += "4. 确保每个场景都有开头、发展和结尾\n"
        prompt += "5. 使用多样化的句式结构，避免单调重复\n"
        
        # 添加口语化写作要求
        prompt += "\n【口语化写作要求】\n"
        prompt += "1. 使用自然流畅的口语化表达，避免过于书面化的词语\n"
        prompt += "2. 减少华丽修饰词和形容词堆砌，保持简洁有力\n"
        prompt += "3. 对话要贴近生活，使用人们日常交流的语言风格\n"
        prompt += "4. 避免使用过于复杂的句式和生僻词汇\n"
        prompt += "5. 叙述部分要像讲故事一样自然，不要有明显的AI写作痕迹\n"
        prompt += "6. 适当使用口语化的语气词和感叹词，增强真实感\n"
        prompt += "7. 避免过度解释和心理描写，让读者自行感受\n"
        
        # 如果不是第一章，添加章节衔接要求
        if self.chapter_number.value() > 1:
            prompt += "\n【章节衔接要求】\n"
            prompt += "1. 开头要与上一章结尾自然衔接\n"
            prompt += "2. 适当回顾上一章关键信息，但避免重复\n"
            prompt += "3. 推进至少一个主要情节线\n"
            prompt += "4. 引入新的冲突或发展现有冲突\n"
            prompt += "5. 结尾要为下一章做好铺垫\n"
        
        # 输出API调用信息，用于调试
        print(f"正在调用API: 类型={self.api_type}, URL={self.api_url}, 模型={self.model_name}")
        if self.api_type == "自定义":
            print(f"API格式: {self.api_format}")
            print(f"自定义请求头: {self.custom_headers}")
            
        # 创建API调用线程，传递最大章节字数限制
        self.api_thread = ApiCallThread(self.api_type, self.api_url, self.api_key, prompt, self.model_name, 
                                       api_format=self.api_format, custom_headers=self.custom_headers,
                                       max_chapter_length=self.max_chapter_length)
        self.api_thread.finished.connect(self.on_chapter_ready)
        self.api_thread.error.connect(self.on_api_error)
        self.api_thread.progress.connect(self.on_progress)
        # 新增：连接内容更新信号，实现实时显示
        self.api_thread.content_update.connect(self.on_content_update)
        self.api_thread.start()

    def prev_chapter(self):
        """切换到上一章"""
        current = self.chapter_number.value()
        if current > 1:
            self.chapter_number.setValue(current - 1)
            # 加载已保存章节内容
            self.load_chapter_content()

    def next_chapter(self):
        """切换到下一章"""
        current = self.chapter_number.value()
        if current < 500:
            self.chapter_number.setValue(current + 1)
            # 加载已保存章节内容
            self.load_chapter_content()
            
    def on_chapter_number_changed(self, value):
        """章节号改变时的处理函数"""
        print(f"[调试] 章节号改变为: {value}")
        
        # 如果正在初始化，不显示提示
        if hasattr(self, 'is_initializing') and self.is_initializing:
            print(f"[调试] 正在初始化中，跳过章节号改变处理")
            return
            
        try:
            # 获取小说标题
            title = self.novel_title_input.text().strip()
            if not title:
                title = "未命名小说"
            
            # 确保保存目录存在
            if not hasattr(self, 'save_path') or not self.save_path:
                self.save_path = "novels"
            
            if not os.path.exists(self.save_path):
                try:
                    os.makedirs(self.save_path)
                    print(f"[调试] 创建保存目录: {self.save_path}")
                except Exception as e:
                    print(f"[调试] 创建保存目录失败: {e}")
                    self.status_bar.showMessage(f"创建保存目录失败: {str(e)}")
                    return
            
            # 尝试多种可能的文件名格式
            possible_files = [
                f"第{value}章.txt",  # 旧格式
                f"第{value:03d}章.txt"  # 带零的旧格式
            ]
            
            file_path = None
            for file_name in possible_files:
                test_path = os.path.join(self.save_path, file_name)
                if os.path.exists(test_path):
                    file_path = test_path
                    break
            
            # 如果所有格式都不存在，使用新格式作为默认路径
            if file_path is None:
                file_path = os.path.join(self.save_path, f"第{value}章.txt")
            
            # 检查文件是否存在
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as file:
                        content = file.read()
                        self.chapter_text.setPlainText(content)
                        self.save_button.setEnabled(True)
                        self.status_bar.showMessage(f"已加载第{value}章内容")
                        print(f"[调试] 成功加载第{value}章内容")
                except Exception as e:
                    print(f"[调试] 加载章节内容失败: {e}")
                    self.status_bar.showMessage(f"加载第{value}章内容失败")
                    # 显示错误提示
                    QMessageBox.warning(self, "加载失败", f"加载第{value}章内容失败: {str(e)}")
            else:
                # 如果文件不存在，清空文本框
                self.chapter_text.clear()
                self.save_button.setEnabled(False)
                self.status_bar.showMessage(f"第{value}章尚未生成")
                print(f"[调试] 第{value}章文件不存在: {file_path}")
                # 不显示提示信息，避免频繁弹窗
        except Exception as e:
            print(f"[调试] 章节号改变处理失败: {e}")
            self.status_bar.showMessage(f"切换章节失败: {str(e)}")
            
    def load_chapter_content(self):
        """加载当前章节的内容"""
        # 获取小说标题
        title = self.novel_title_input.text().strip()
        if not title:
            title = "未命名小说"
        
        # 构建文件路径
        chapter_num = self.chapter_number.value()
        
        # 尝试多种可能的文件名格式
        possible_files = [
            f"第{chapter_num}章.txt",  # 旧格式
            f"第{chapter_num:03d}章.txt"  # 带零的旧格式
        ]
        
        file_path = None
        for file_name in possible_files:
            test_path = os.path.join(self.save_path, file_name)
            if os.path.exists(test_path):
                file_path = test_path
                break
        
        # 如果所有格式都不存在，使用新格式作为默认路径
        if file_path is None:
            file_path = os.path.join(self.save_path, f"第{chapter_num}章.txt")
        
        # 检查文件是否存在
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    self.chapter_text.setPlainText(content)
                    self.save_button.setEnabled(True)
                    self.status_bar.showMessage(f"已加载第{chapter_num}章内容")
            except Exception as e:
                print(f"加载章节内容失败: {e}")
                self.status_bar.showMessage(f"加载第{chapter_num}章内容失败")
                # 显示错误提示
                QMessageBox.warning(self, "加载失败", f"加载第{chapter_num}章内容失败: {str(e)}")
        else:
            # 如果文件不存在，清空文本框
            self.chapter_text.clear()
            self.save_button.setEnabled(False)
            self.status_bar.showMessage(f"第{chapter_num}章尚未生成")
            # 不显示提示信息，避免频繁弹窗

    def stop_generation(self):
        """停止当前生成任务"""
        if hasattr(self, 'api_thread') and self.api_thread.isRunning():
            print("[调试] 正在停止API调用线程")
            self.api_thread.stop()
            # 等待线程完全停止
            if not self.api_thread.wait(3000):  # 等待3秒
                print("[调试] API调用线程未在3秒内停止，强制终止")
                self.api_thread.terminate()
                self.api_thread.wait(1000)  # 再等待1秒确保终止
            print("[调试] API调用线程已停止")
            self.status_bar.showMessage("生成已停止")
            self.generate_button.setEnabled(True)  # 停止后重新启用生成按钮
            self.generate_chapter_button.setEnabled(True)
            self.stop_button.setEnabled(False)  # 停止后禁用停止按钮
            self.set_app_status("正常")

    def start_batch_generation(self):
        """开始批量生成章节"""
        print("[调试] start_batch_generation被调用")
        
        if not self.outline_text.toPlainText():
            print("[调试] 大纲为空，显示警告")
            QMessageBox.warning(self, "没有大纲", "请先生成小说大纲")
            return
        
        print(f"[调试] 大纲内容: {self.outline_text.toPlainText()[:100]}...")
            
        start_chapter = self.start_chapter_spin.value()
        end_chapter = self.end_chapter_spin.value()
        
        print(f"[调试] 起始章节: {start_chapter}, 结束章节: {end_chapter}")
        
        if start_chapter > end_chapter:
            print("[调试] 起始章节大于结束章节，显示错误")
            QMessageBox.warning(self, "参数错误", "起始章节不能大于结束章节")
            return
        
        # 如果已经有批量生成线程在运行，先停止它
        if hasattr(self, 'batch_generator') and self.batch_generator and self.batch_generator.isRunning():
            print("[调试] 检测到已有批量生成线程在运行，先停止它")
            self.stop_batch_generation()
            
        # 检查是否已有已生成的章节
        title = self.novel_title_input.text().strip()
        if not title:
            title = "未命名小说"
            
        existing_chapters = []
        for chapter in range(start_chapter, end_chapter + 1):
            # 尝试多种可能的文件名格式
            possible_files = [
                f"第{chapter}章.txt",  # 旧格式
                f"第{chapter:03d}章.txt"  # 带零的旧格式
            ]
            
            chapter_exists = False
            if os.path.exists(self.save_path):
                for file_name in possible_files:
                    file_path = os.path.join(self.save_path, file_name)
                    if os.path.exists(file_path):
                        existing_chapters.append(chapter)
                        chapter_exists = True
                        break
        
        # 默认设置为跳过已存在章节
        overwrite_existing = False
        
        # 如果有已存在的章节，询问用户如何处理
        if existing_chapters:
            existing_text = ", ".join([f"第{ch}章" for ch in existing_chapters])
            if len(existing_chapters) > 3:
                existing_text = f"第{existing_chapters[0]}章到第{existing_chapters[-1]}章"
                
            msg_box = QMessageBox()
            msg_box.setWindowTitle("已存在章节")
            msg_box.setText(f"检测到已生成的章节: {existing_text}")
            msg_box.setInformativeText("您希望如何处理这些章节？")
            
            # 设置按钮样式
            msg_box.setStyleSheet("""
                QPushButton {
                    min-width: 100px;
                    min-height: 32px;
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    border: none;
                }
                QPushButton[text="覆盖已存在章节"] {
                    background-color: #4F46E5;
                    color: white;
                }
                QPushButton[text="覆盖已存在章节"]:hover {
                    background-color: #4338CA;
                }
                QPushButton[text="跳过已存在章节"] {
                    background-color: #F59E0B;
                    color: white;
                }
                QPushButton[text="跳过已存在章节"]:hover {
                    background-color: #D97706;
                }
                QPushButton[text="取消"] {
                    background-color: #F3F4F6;
                    color: #374151;
                }
                QPushButton[text="取消"]:hover {
                    background-color: #E5E7EB;
                }
            """)
            
            overwrite_button = msg_box.addButton("覆盖已存在章节", QMessageBox.AcceptRole)
            skip_button = msg_box.addButton("跳过已存在章节", QMessageBox.DestructiveRole)
            cancel_button = msg_box.addButton("取消", QMessageBox.RejectRole)
            
            msg_box.exec_()
            
            if msg_box.clickedButton() == overwrite_button:
                # 覆盖已存在章节，设置标志为True
                overwrite_existing = True
            elif msg_box.clickedButton() == skip_button:
                # 跳过已存在章节，设置标志为False
                overwrite_existing = False
                QMessageBox.information(self, "跳过已存在章节", f"将从第{start_chapter}章开始生成，已存在的章节将被跳过")
            else:
                # 用户取消
                return
        
        total_chapters = end_chapter - start_chapter + 1
        if total_chapters > 100:
            # 创建自定义确认对话框
            confirm_box = QMessageBox()
            confirm_box.setWindowTitle("确认批量生成")
            confirm_box.setText(f"您将生成{total_chapters}章，这可能需要较长时间。")
            confirm_box.setInformativeText("确定要继续吗？")
            
            # 设置按钮样式
            confirm_box.setStyleSheet("""
                QPushButton {
                    min-width: 80px;
                    min-height: 32px;
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    border: none;
                }
                QPushButton[text="是"] {
                    background-color: #4F46E5;
                    color: white;
                }
                QPushButton[text="是"]:hover {
                    background-color: #4338CA;
                }
                QPushButton[text="否"] {
                    background-color: #F3F4F6;
                    color: #374151;
                }
                QPushButton[text="否"]:hover {
                    background-color: #E5E7EB;
                }
            """)
            
            yes_button = confirm_box.addButton("是", QMessageBox.YesRole)
            no_button = confirm_box.addButton("否", QMessageBox.NoRole)
            
            confirm_box.exec_()
            
            if confirm_box.clickedButton() != yes_button:
                return
        
        # 初始化批量生成状态
        self.batch_progress_bar.setValue(0)
        self.batch_progress_label.setText(f"准备生成章节 {start_chapter} 到 {end_chapter}")
        self.batch_generate_button.setEnabled(False)
        self.batch_stop_button.setEnabled(True)
        self.batch_stop_button.setStyleSheet(self.get_button_style())
        
        # 获取用户选择的"读取上一章内容"选项
        read_previous_chapter = self.read_previous_chapter_checkbox.isChecked()
        
        # 打印API配置信息
        print(f"[调试] API配置: 类型={self.api_type}, URL={self.api_url}, 模型={self.model_name}")
        if self.api_type == "自定义":
            print(f"[调试] API格式: {getattr(self, 'api_format', 'None')}")
            print(f"[调试] 自定义请求头: {getattr(self, 'custom_headers', 'None')}")
        
        # 创建批量生成线程
        print("[调试] 创建ChapterGenerator实例")
        self.batch_generator = ChapterGenerator(self, start_chapter, end_chapter, overwrite_existing, read_previous_chapter)
        
        print("[调试] 连接信号")
        # 先断开所有可能存在的连接，避免重复连接导致的问题
        try:
            self.batch_generator.chapter_generated.disconnect()
            self.batch_generator.progress.disconnect()
            self.batch_generator.finished.disconnect()
            self.batch_generator.error.disconnect()
        except:
            pass  # 如果没有连接，忽略错误
            
        # 重新连接信号
        self.batch_generator.chapter_generated.connect(self.on_chapter_generated)
        self.batch_generator.progress.connect(self.on_batch_progress)
        self.batch_generator.finished.connect(self.on_batch_finished)
        self.batch_generator.error.connect(self.on_batch_error)
        
        print("[调试] 启动线程")
        self.batch_generator.start()
        print("[调试] 批量生成线程已启动")
        
        self.status_bar.showMessage(f"开始批量生成章节 {start_chapter}-{end_chapter}")
        self.set_app_status("忙碌")

    def stop_batch_generation(self):
        """停止批量生成"""
        if hasattr(self, 'batch_generator') and self.batch_generator and self.batch_generator.isRunning():
            print("[调试] 正在停止批量生成线程")
            self.batch_generator.stop()
            # 等待线程完全停止
            if not self.batch_generator.wait(3000):  # 等待3秒
                print("[调试] 批量生成线程未在3秒内停止，强制终止")
                self.batch_generator.terminate()
                self.batch_generator.wait(1000)  # 再等待1秒确保终止
            print("[调试] 批量生成线程已停止")
            
            # 断开所有信号连接，避免内存泄漏
            try:
                self.batch_generator.chapter_generated.disconnect()
                self.batch_generator.progress.disconnect()
                self.batch_generator.finished.disconnect()
                self.batch_generator.error.disconnect()
            except:
                pass  # 如果没有连接，忽略错误
                
            # 清理线程对象
            self.batch_generator = None
            
            self.batch_progress_label.setText("批量生成已停止")
            self.batch_generate_button.setEnabled(True)
            self.batch_stop_button.setEnabled(False)
            self.status_bar.showMessage("批量生成已停止")
            self.set_app_status("正常")
        else:
            print("[调试] 批量生成线程未运行或已停止")

    def on_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)
        if value < 100:
            self.progress_label.setText(f"生成中... {value}%")
        else:
            self.progress_label.setText("生成完成")
            
    def on_chapter_generated(self, chapter_num, content):
        """处理单个章节生成完成"""
        print(f"[调试] on_chapter_generated被调用，章节号: {chapter_num}, 内容长度: {len(content) if content else 0}")
        print(f"[调试] 内容预览: {content[:100] if content else 'None'}...")
        
        # 检查是否是批量生成过程中的实时更新
        # 如果是批量生成，则已经在on_batch_content_update中处理了UI更新，这里不需要重复处理
        if hasattr(self, 'batch_generator') and self.batch_generator and self.batch_generator.isRunning():
            print(f"[调试] 批量生成过程中的实时更新，跳过重复UI处理")
            return
        
        # 无论用户正在查看哪个章节，都更新内容
        self.chapter_number.setValue(chapter_num)  # 切换到当前生成的章节
        print(f"[调试] 已切换到章节 {chapter_num}")
        
        # 使用打字机效果显示内容
        self.typewriter_effect.start_typing(content)
        print(f"[调试] 已使用打字机效果显示章节内容，内容长度: {len(content)}")
        
        # 保存当前章节内容，确保UI更新时能正确显示
        self.current_chapter_content = content
        print(f"[调试] 已保存内容到current_chapter_content变量")
        
        self.save_button.setEnabled(True)
        print(f"[调试] 已启用保存按钮")
        
        # 强制更新UI
        self.chapter_text.update()
        self.chapter_text.repaint()
        print(f"[调试] 已强制更新UI")
        
        self.status_bar.showMessage(f"第{chapter_num}章生成完成")
        print(f"[调试] 已更新状态栏")

    def on_batch_progress(self, current_chapter, end_chapter, progress):
        """更新批量生成进度"""
        # 确保UI更新在主线程中执行
        QMetaObject.invokeMethod(self.batch_progress_bar, "setValue", Qt.QueuedConnection, Q_ARG(int, progress))
        QMetaObject.invokeMethod(self.batch_progress_label, "setText", Qt.QueuedConnection, Q_ARG(str, f"正在生成第 {current_chapter} 章 (共 {end_chapter} 章) - {progress}%"))
        QMetaObject.invokeMethod(self.status_bar, "showMessage", Qt.QueuedConnection, Q_ARG(str, f"批量生成中: 第{current_chapter}/{end_chapter}章 ({progress}%)"))

    def on_batch_finished(self):
        """批量生成完成"""
        print("[调试] 批量生成完成，调用stop_batch_generation方法")
        
        # 确保所有API线程已正确停止
        if hasattr(self, 'batch_generator') and self.batch_generator:
            if hasattr(self.batch_generator, 'api_thread') and self.batch_generator.api_thread:
                if self.batch_generator.api_thread.isRunning():
                    print("[调试] 批量生成器的API线程仍在运行，尝试停止")
                    self.batch_generator.api_thread.stop()
                    if not self.batch_generator.api_thread.wait(2000):  # 等待2秒
                        print("[调试] 批量生成器的API线程未在2秒内停止，强制终止")
                        self.batch_generator.api_thread.terminate()
                        self.batch_generator.api_thread.wait(1000)  # 再等待1秒确保终止
                    print("[调试] 批量生成器的API线程已停止")
                else:
                    print("[调试] 批量生成器的API线程已停止")
        
        # 确保批量生成线程已正确停止
        if hasattr(self, 'batch_generator') and self.batch_generator and self.batch_generator.isRunning():
            self.batch_generator.stop()
            if not self.batch_generator.wait(3000):  # 等待3秒
                print("[调试] 批量生成线程未在3秒内停止，强制终止")
                self.batch_generator.terminate()
                self.batch_generator.wait(1000)  # 再等待1秒确保终止
        
        # 断开所有信号连接，避免内存泄漏
        if hasattr(self, 'batch_generator') and self.batch_generator:
            try:
                self.batch_generator.chapter_generated.disconnect()
                self.batch_generator.progress.disconnect()
                self.batch_generator.finished.disconnect()
                self.batch_generator.error.disconnect()
            except:
                pass  # 如果没有连接，忽略错误
                
            # 清理线程对象
            self.batch_generator = None
        
        self.batch_progress_label.setText("批量生成完成！")
        self.batch_generate_button.setEnabled(True)
        self.batch_stop_button.setEnabled(False)
        self.batch_stop_button.setStyleSheet(self.get_button_style(disabled=True))
        self.status_bar.showMessage("批量生成完成 - 所有章节已生成并保存！")
        self.set_app_status("正常")

    def on_batch_error(self, error_msg, chapter_num):
        """批量生成出错"""
        self.batch_progress_label.setText(f"第{chapter_num}章出错: {error_msg}")
        self.status_bar.showMessage(f"第{chapter_num}章出错: {error_msg}")
        self.set_app_status("异常")
        
        # 确保API线程已正确停止
        if hasattr(self, 'batch_generator') and self.batch_generator:
            if hasattr(self.batch_generator, 'api_thread') and self.batch_generator.api_thread:
                if self.batch_generator.api_thread.isRunning():
                    print("[调试] 批量生成器的API线程仍在运行，尝试停止")
                    self.batch_generator.api_thread.stop()
                    if not self.batch_generator.api_thread.wait(2000):  # 等待2秒
                        print("[调试] 批量生成器的API线程未在2秒内停止，强制终止")
                        self.batch_generator.api_thread.terminate()
                        self.batch_generator.api_thread.wait(1000)  # 再等待1秒确保终止
                    print("[调试] 批量生成器的API线程已停止")
                else:
                    print("[调试] 批量生成器的API线程已停止")
        
        # 确保批量生成线程已正确停止
        if hasattr(self, 'batch_generator') and self.batch_generator and self.batch_generator.isRunning():
            self.batch_generator.stop()
            if not self.batch_generator.wait(3000):  # 等待3秒
                print("[调试] 批量生成线程未在3秒内停止，强制终止")
                self.batch_generator.terminate()
                self.batch_generator.wait(1000)  # 再等待1秒确保终止
        
        # 断开所有信号连接，避免内存泄漏
        if hasattr(self, 'batch_generator') and self.batch_generator:
            try:
                self.batch_generator.chapter_generated.disconnect()
                self.batch_generator.progress.disconnect()
                self.batch_generator.finished.disconnect()
                self.batch_generator.error.disconnect()
            except:
                pass  # 如果没有连接，忽略错误
                
            # 清理线程对象
            self.batch_generator = None
        
        # 可以选择继续生成后续章节
        self.status_bar.showMessage(f"第{chapter_num}章生成失败: {error_msg} - 批量生成已停止")

    def on_outline_ready(self, response, status):
        """处理大纲生成完成的回调函数"""
        self.generate_button.setEnabled(True)  # 生成完成后重新启用生成按钮
        self.stop_button.setEnabled(False)  # 生成完成后禁用停止按钮
        
        try:
            self.outline_text.setPlainText(response)
            self.status_bar.showMessage("小说大纲生成完成")
            QMessageBox.information(self, "成功", "小说大纲生成完成！")
            self.generate_chapter_button.setEnabled(True)
            self.save_button.setEnabled(True)
            self.set_app_status("正常")
            
            # 保存生成的大纲
            self.save_outline(response)
            
            # 重置进度条
            self.progress_bar.setValue(100)
            self.progress_label.setText("大纲生成完成")
            
            # 注释掉切换到输出标签页的代码，因为该类没有tabs属性
            # self.tabs.setCurrentIndex(1)
        except Exception as e:
            self.on_api_error(f"解析API响应失败: {str(e)}")
            
    def save_outline(self, outline_content):
        """保存小说大纲到文件"""
        # 获取小说标题
        title = self.novel_title_input.text().strip()
        if not title:
            title = "未命名小说"
            
        # 创建大纲保存目录
        outline_dir = os.path.join(self.save_path, "outlines")
        # 确保使用正确的路径分隔符
        outline_dir = os.path.normpath(outline_dir)
        
        # 添加调试信息
        print(f"[调试] 保存大纲到目录: {outline_dir}")
        print(f"[调试] 当前save_path: {self.save_path}")
        
        if not os.path.exists(outline_dir):
            try:
                os.makedirs(outline_dir)
                print(f"[调试] 创建大纲目录: {outline_dir}")
            except Exception as e:
                print(f"创建大纲目录失败: {e}")
                return
                
        # 生成大纲文件名
        outline_file = os.path.join(outline_dir, f"{title}_outline.txt")
        # 确保使用正确的路径分隔符
        outline_file = os.path.normpath(outline_file)
        
        # 检查outline_content的类型，确保是字符串
        if not isinstance(outline_content, str):
            print(f"警告：大纲内容不是字符串类型，而是{type(outline_content)}，尝试转换为字符串")
            try:
                outline_content = str(outline_content)
            except Exception as e:
                print(f"大纲内容转换失败: {e}")
                outline_content = "大纲生成失败，请检查API配置和网络连接"
        
        # 如果内容为空，添加提示信息
        if not outline_content or outline_content.strip() == "":
            outline_content = "大纲生成失败，请检查API配置和网络连接"
        
        try:
            with open(outline_file, 'w', encoding='utf-8') as file:
                file.write(outline_content)
            print(f"大纲已保存到: {outline_file}")
        except Exception as e:
            print(f"保存大纲失败: {e}")
            
    def check_and_load_saved_outline(self):
        """检查并加载已保存的大纲"""
        # 检查outlines目录是否存在
        outlines_dir = os.path.join(self.save_path, "outlines")
        if not os.path.exists(outlines_dir):
            print(f"[调试] outlines目录不存在: {outlines_dir}")
            return
            
        # 获取所有大纲文件
        outline_files = [f for f in os.listdir(outlines_dir) if f.endswith("_outline.txt") or f.endswith("大纲.txt")]
        if not outline_files:
            print("[调试] 没有找到已保存的大纲文件")
            return
            
        # 如果有多个大纲文件，选择最新的一个
        if len(outline_files) > 1:
            # 按修改时间排序，选择最新的
            outline_files.sort(key=lambda f: os.path.getmtime(os.path.join(outlines_dir, f)), reverse=True)
            
        # 获取最新大纲文件的完整路径
        latest_outline = os.path.join(outlines_dir, outline_files[0])
        print(f"[调试] 找到最新大纲文件: {latest_outline}")
        
        # 从文件名提取小说标题
        if latest_outline.endswith("_outline.txt"):
            title = os.path.basename(latest_outline).replace("_outline.txt", "")
        elif latest_outline.endswith("大纲.txt"):
            title = os.path.basename(latest_outline).replace("大纲.txt", "")
        else:
            title = os.path.basename(latest_outline).split('.')[0]  # 默认去除扩展名
        
        # 设置小说标题
        self.novel_title_input.setText(title)
        
        # 加载大纲内容
        try:
            with open(latest_outline, 'r', encoding='utf-8') as file:
                outline_content = file.read()
                
            # 将大纲内容设置到文本框
            self.outline_text.setPlainText(outline_content)
            self.generate_chapter_button.setEnabled(True)
            self.save_button.setEnabled(True)
            
            # 注释掉切换到输出标签页的代码，因为该类没有tabs属性
            # self.tabs.setCurrentIndex(1)
            
            print(f"[调试] 已自动加载大纲: {title}")
            print(f"[调试] 大纲内容长度: {len(outline_content)} 字符")
            print(f"[调试] 大纲内容预览: {outline_content[:200]}...")
            self.status_bar.showMessage(f"已自动加载大纲: {title}")
        except Exception as e:
            print(f"[调试] 加载大纲失败: {e}")
            self.status_bar.showMessage(f"加载大纲失败: {e}")
    
    def show_outline_directly(self):
        """直接显示大纲内容到文本框"""
        # 获取小说标题
        title = self.novel_title_input.text().strip()
        if not title:
            title = "重生之我成了高冷男神"  # 默认使用已知的小说标题
            self.novel_title_input.setText(title)
            
        # 构建大纲文件路径
        outline_file = os.path.join(self.save_path, "outlines", f"{title}_outline.txt")
        outline_file = os.path.normpath(outline_file)
        
        print(f"[直接显示] 尝试加载大纲文件: {outline_file}")
        print(f"[直接显示] save_path: {self.save_path}")
        print(f"[直接显示] 小说标题: {title}")
        
        # 检查大纲文件是否存在
        if not os.path.exists(outline_file):
            print(f"[直接显示] 大纲文件不存在: {outline_file}")
            # 检查目录是否存在
            outline_dir = os.path.join(self.save_path, "outlines")
            outline_dir = os.path.normpath(outline_dir)
            if os.path.exists(outline_dir):
                print(f"[直接显示] 大纲目录存在，包含文件: {os.listdir(outline_dir)}")
            else:
                print(f"[直接显示] 大纲目录不存在: {outline_dir}")
            return False
            
        try:
            with open(outline_file, 'r', encoding='utf-8') as file:
                outline_content = file.read()
                
            # 将大纲内容设置到文本框
            self.outline_text.setPlainText(outline_content)
            self.generate_chapter_button.setEnabled(True)
            self.save_button.setEnabled(True)
            
            print(f"[直接显示] 大纲内容已显示到文本框")
            print(f"[直接显示] 大纲内容长度: {len(outline_content)} 字符")
            print(f"[直接显示] 大纲内容预览: {outline_content[:200]}...")
            self.status_bar.showMessage(f"大纲内容已显示")
            return True
        except Exception as e:
            print(f"[直接显示] 加载大纲失败: {e}")
            self.status_bar.showMessage(f"加载大纲失败: {e}")
            return False

    def load_saved_outline(self):
        """加载已保存的小说大纲"""
        # 获取小说标题
        title = self.novel_title_input.text().strip()
        if not title:
            title = "未命名小说"
            
        # 构建大纲文件路径 - 使用正确的路径分隔符
        outline_file = os.path.join(self.save_path, "outlines", f"{title}_outline.txt")
        # 确保使用正确的路径分隔符
        outline_file = os.path.normpath(outline_file)
        
        # 添加调试信息
        print(f"[调试] 尝试加载大纲文件: {outline_file}")
        print(f"[调试] save_path: {self.save_path}")
        print(f"[调试] 小说标题: {title}")
        
        # 检查大纲文件是否存在
        if not os.path.exists(outline_file):
            print(f"[调试] 大纲文件不存在: {outline_file}")
            # 检查目录是否存在
            outline_dir = os.path.join(self.save_path, "outlines")
            outline_dir = os.path.normpath(outline_dir)
            if os.path.exists(outline_dir):
                print(f"[调试] 大纲目录存在，包含文件: {os.listdir(outline_dir)}")
            else:
                print(f"[调试] 大纲目录不存在: {outline_dir}")
            return False
            
        try:
            with open(outline_file, 'r', encoding='utf-8') as file:
                outline_content = file.read()
                
            # 将大纲内容设置到文本框
            self.outline_text.setPlainText(outline_content)
            self.generate_chapter_button.setEnabled(True)
            self.save_button.setEnabled(True)
            
            # 注释掉切换到输出标签页的代码，因为该类没有tabs属性
            # self.tabs.setCurrentIndex(1)
            
            return True
        except Exception as e:
            print(f"加载大纲失败: {e}")
            return False

    def on_content_update(self, content):
        """处理API返回的内容更新，实现实时显示"""
        # 直接设置章节内容到文本框
        self.chapter_text.setPlainText(content)
        # 保存当前内容，确保UI更新时能正确显示
        self.current_chapter_content = content
        # 强制更新UI
        self.chapter_text.update()
        self.chapter_text.repaint()
        # 更新状态栏，显示当前生成字数
        self.status_bar.showMessage(f"正在生成第{self.chapter_number.value()}章... 已生成 {len(content)} 字")
        # 滚动到底部，显示最新内容
        self.chapter_text.verticalScrollBar().setValue(self.chapter_text.verticalScrollBar().maximum())
        
    def on_outline_content_update(self, content):
        """处理大纲生成时的内容更新，实现实时显示"""
        # 更新大纲文本框内容，实现实时显示效果
        self.outline_text.setPlainText(content)
        # 强制更新UI
        self.outline_text.update()
        self.outline_text.repaint()
        # 更新状态栏，显示当前生成字数
        self.status_bar.showMessage(f"正在生成大纲... 已生成 {len(content)} 字")
        # 滚动到底部，显示最新内容
        self.outline_text.verticalScrollBar().setValue(self.outline_text.verticalScrollBar().maximum())
        
    def on_batch_content_update(self, chapter_num, content):
        """处理批量生成时的内容更新，实现实时显示"""
        # 切换到当前生成的章节
        self.chapter_number.setValue(chapter_num)
        # 直接设置章节内容到文本框
        self.chapter_text.setPlainText(content)
        # 保存当前内容，确保UI更新时能正确显示
        self.current_chapter_content = content
        # 强制更新UI
        self.chapter_text.update()
        self.chapter_text.repaint()
        # 更新状态栏，显示当前生成字数
        self.status_bar.showMessage(f"正在批量生成第{chapter_num}章... 已生成 {len(content)} 字")
        # 滚动到底部，显示最新内容
        self.chapter_text.verticalScrollBar().setValue(self.chapter_text.verticalScrollBar().maximum())

    def on_show_overwrite_dialog(self, chapter_num, file_path):
        """显示覆盖对话框，让用户选择是否覆盖已存在的章节文件"""
        if not self.chapter_to_save:
            return
            
        chapter_num, title, content, file_path = self.chapter_to_save
        
        # 只有在文件行为设置为"询问"时才显示对话框
        if self.file_behavior != "询问":
            # 如果设置为"覆盖"，直接保存
            if self.file_behavior == "覆盖":
                try:
                    with open(file_path, 'w', encoding='utf-8') as file:
                        file.write(content)
                    self.status_bar.showMessage(f"第{chapter_num}章已覆盖保存")
                    print(f"章节已覆盖保存到: {file_path}")
                except Exception as e:
                    self.status_bar.showMessage(f"保存章节失败: {str(e)}")
                    print(f"保存章节失败: {str(e)}")
            # 如果设置为"跳过"，不做任何操作
            elif self.file_behavior == "跳过":
                self.status_bar.showMessage(f"跳过第{chapter_num}章")
                print(f"根据设置跳过第{chapter_num}章")
            
            # 清空待保存的章节信息
            self.chapter_to_save = None
            return
        
        # 显示对话框询问用户是否覆盖
        confirm_box = QMessageBox()
        confirm_box.setWindowTitle("章节已存在")
        confirm_box.setText(f"第{chapter_num}章已存在，是否覆盖？")
        confirm_box.setInformativeText(f"文件路径: {file_path}")
        
        # 设置按钮样式
        confirm_box.setStyleSheet("""
            QPushButton {
                min-width: 80px;
                min-height: 32px;
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                border: none;
            }
            QPushButton[text="是"] {
                background-color: #F59E0B;
                color: white;
            }
            QPushButton[text="是"]:hover {
                background-color: #D97706;
            }
            QPushButton[text="否"] {
                background-color: #F3F4F6;
                color: #374151;
            }
            QPushButton[text="否"]:hover {
                background-color: #E5E7EB;
            }
        """)
        
        yes_button = confirm_box.addButton("是", QMessageBox.YesRole)
        no_button = confirm_box.addButton("否", QMessageBox.NoRole)
        
        confirm_box.exec_()
        
        if confirm_box.clickedButton() == yes_button:
            # 用户选择覆盖，保存文件
            try:
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(content)
                self.status_bar.showMessage(f"第{chapter_num}章已保存")
                print(f"章节已保存到: {file_path}")
            except Exception as e:
                self.status_bar.showMessage(f"保存章节失败: {str(e)}")
                print(f"保存章节失败: {str(e)}")
        else:
            # 用户选择不覆盖，显示状态栏消息
            self.status_bar.showMessage(f"跳过第{chapter_num}章")
            print(f"用户选择跳过第{chapter_num}章")
        
        # 清空待保存的章节信息
        self.chapter_to_save = None

    def on_chapter_ready(self, response, status):
        """处理章节生成完成的回调函数"""
        print(f"on_chapter_ready被调用，response长度: {len(response) if response else 0}, status: {status}")
        print(f"response内容预览: {response[:100] if response else 'None'}...")
        print(f"当前章节号: {self.chapter_number.value()}")
        
        self.generate_chapter_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        
        try:
            # 检查response是否为空
            if not response or not response.strip():
                print("警告：response为空")
                empty_msg = "警告：生成的内容为空，请检查API设置或重试。"
                self.chapter_text.setPlainText(empty_msg)
                # 保存当前章节内容，确保UI更新时能正确显示
                self.current_chapter_content = empty_msg
                self.status_bar.showMessage("生成的内容为空，请检查API设置或重试。")
            else:
                print(f"设置章节内容到UI，长度: {len(response)}")
                self.chapter_text.setPlainText(response)
                # 保存当前章节内容，确保UI更新时能正确显示
                self.current_chapter_content = response
                print(f"章节内容已设置到UI")
                print(f"[调试] 设置后立即检查UI内容长度: {len(self.chapter_text.toPlainText())}")
                
                # 自动保存章节内容
                self.auto_save_chapter()
                
            self.status_bar.showMessage(f"第{self.chapter_number.value()}章生成完成")
            self.save_button.setEnabled(True)
            self.set_app_status("正常")
            
            # 重置进度条
            self.progress_bar.setValue(100)
            self.progress_label.setText(f"第{self.chapter_number.value()}章生成完成")
            
            # 确保API线程已正确停止
            if hasattr(self, 'api_thread') and self.api_thread:
                if self.api_thread.isRunning():
                    print("[调试] API线程仍在运行，尝试停止")
                    self.api_thread.stop()
                    if not self.api_thread.wait(2000):  # 等待2秒
                        print("[调试] API线程未在2秒内停止，强制终止")
                        self.api_thread.terminate()
                        self.api_thread.wait(1000)  # 再等待1秒确保终止
                    print("[调试] API线程已停止")
                else:
                    print("[调试] API线程已停止")
            
            # 使用QTimer延迟更新UI，避免阻塞
            print(f"[调试] 准备调用_update_ui_later")
            QTimer.singleShot(0, self._update_ui_later)
        except Exception as e:
            print(f"on_chapter_ready出错: {str(e)}")
            import traceback
            print(f"异常堆栈: {traceback.format_exc()}")
            self.on_api_error(f"解析API响应失败: {str(e)}")
    
    def auto_save_chapter(self):
        """自动保存当前章节内容"""
        try:
            # 获取章节内容
            content = self.chapter_text.toPlainText()
            if not content:
                return
                
            # 设置章节保存目录为：D:\桌面\xiexs\novels\zhangjie
            chapter_save_path = r"D:\桌面\xiexs\novels\zhangjie"
            if not os.path.exists(chapter_save_path):
                os.makedirs(chapter_save_path)
                print(f"[调试] 创建章节目录: {chapter_save_path}")
                
            # 生成文件名（第章节号）
            chapter_num = self.chapter_number.value()
            # 获取小说标题
            title = self.novel_title_input.text().strip()
            if not title:
                title = "未命名小说"
            
            # 使用简化的命名格式：第X章.txt
            # 不再包含章节标题和小说标题，只使用章节号
            file_name = f"第{chapter_num}章.txt"
            file_path = os.path.join(chapter_save_path, file_name)
            
            # 检查文件是否已存在
            if os.path.exists(file_path):
                # 如果文件已存在，直接跳过保存，不询问用户
                self.status_bar.showMessage(f"第{chapter_num}章已存在，跳过保存")
                return
            
            # 格式化文本，每行约30字或按句号分行
            formatted_content = self.format_text_for_save(content)
            
            # 移除小说标题（如**《你是我唯一的解药》**）
            formatted_content = self._remove_novel_title_from_content(formatted_content, title)
            
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(formatted_content)
                
            self.status_bar.showMessage(f"已自动保存: {file_path}")
            self.chapter_counter += 1  # 计数器递增
            self.set_app_status("正常")
        except Exception as e:
            print(f"自动保存失败: {str(e)}")
            self.status_bar.showMessage(f"自动保存失败: {str(e)}")
            self.set_app_status("异常")

    def _update_ui_later(self):
        """延迟更新UI，避免阻塞"""
        print(f"[调试] _update_ui_later被调用")
        # 确保章节文本内容正确显示
        if hasattr(self, 'current_chapter_content') and self.current_chapter_content:
            print(f"_update_ui_later: 设置章节内容，长度: {len(self.current_chapter_content)}")
            self.chapter_text.setPlainText(self.current_chapter_content)
            print(f"_update_ui_later: 章节内容已设置，当前文本框内容长度: {len(self.chapter_text.toPlainText())}")
            print(f"[调试] 文本框是否可见: {self.chapter_text.isVisible()}")
            print(f"[调试] 文本框是否启用: {self.chapter_text.isEnabled()}")
            print(f"[调试] 文本框位置: {self.chapter_text.pos()}")
            print(f"[调试] 文本框大小: {self.chapter_text.size()}")
        else:
            print(f"_update_ui_later: current_chapter_content不存在或为空")
            print(f"[调试] current_chapter_content存在: {hasattr(self, 'current_chapter_content')}")
            if hasattr(self, 'current_chapter_content'):
                print(f"[调试] current_chapter_content内容: '{self.current_chapter_content}'")
        self.chapter_text.update()
        self.chapter_text.repaint()
        print(f"[调试] UI已更新，最终文本框内容长度: {len(self.chapter_text.toPlainText())}")
    
    def on_outline_ready(self, response, status):
        """处理大纲生成完成的回调函数"""
        print(f"on_outline_ready被调用，response长度: {len(response) if response else 0}, status: {status}")
        
        self.generate_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        
        try:
            # 检查response是否为空
            if not response or not response.strip():
                print("警告：response为空")
                empty_msg = "警告：生成的大纲为空，请检查API设置或重试。"
                self.outline_text.setPlainText(empty_msg)
                self.status_bar.showMessage("生成的大纲为空，请检查API设置或重试。")
                # 保存空大纲到文件
                self.save_outline(empty_msg)
            else:
                print(f"设置大纲内容到UI，长度: {len(response)}")
                self.outline_text.setPlainText(response)
                print(f"大纲内容已设置到UI")
                # 保存大纲到文件
                self.save_outline(response)
                
            self.status_bar.showMessage("大纲生成完成")
            self.save_button.setEnabled(True)
            self.set_app_status("正常")
            
            # 重置进度条
            self.progress_bar.setValue(100)
            self.progress_label.setText("大纲生成完成")
            
            # 确保API线程已正确停止
            if hasattr(self, 'api_thread') and self.api_thread:
                if self.api_thread.isRunning():
                    print("[调试] API线程仍在运行，尝试停止")
                    self.api_thread.stop()
                    if not self.api_thread.wait(2000):  # 等待2秒
                        print("[调试] API线程未在2秒内停止，强制终止")
                        self.api_thread.terminate()
                        self.api_thread.wait(1000)  # 再等待1秒确保终止
                    print("[调试] API线程已停止")
                else:
                    print("[调试] API线程已停止")
        except Exception as e:
            print(f"on_outline_ready出错: {str(e)}")
            import traceback
            print(f"异常堆栈: {traceback.format_exc()}")
            self.on_api_error(f"解析API响应失败: {str(e)}")
    
    def on_api_error(self, error_msg):
        """当API调用出错时调用"""
        # 优化错误提示，提供更友好的建议
        if "API调用超时" in error_msg:
            improved_msg = "API调用超时，可能是网络连接不稳定或服务器响应较慢。\n\n建议：\n1. 检查您的网络连接\n2. 稍后重试\n3. 尝试减小生成长度\n4. 如果问题持续，可尝试更换API模型"
            
            error_box = QMessageBox()
            error_box.setWindowTitle("API错误")
            error_box.setText(improved_msg)
            error_box.setIcon(QMessageBox.Critical)
            
            # 设置按钮样式
            error_box.setStyleSheet("""
                QPushButton {
                    min-width: 80px;
                    min-height: 32px;
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    border: none;
                    background-color: #EF4444;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #DC2626;
                }
            """)
            
            error_box.exec_()
        elif "API调用失败" in error_msg:
            improved_msg = "API调用失败，可能是服务器暂时不可用或配置有误。\n\n建议：\n1. 检查API密钥是否正确\n2. 验证API地址是否有效\n3. 确认所选模型是否可用\n4. 稍后重试"
            
            error_box = QMessageBox()
            error_box.setWindowTitle("API错误")
            error_box.setText(improved_msg)
            error_box.setIcon(QMessageBox.Critical)
            
            # 设置按钮样式
            error_box.setStyleSheet("""
                QPushButton {
                    min-width: 80px;
                    min-height: 32px;
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    border: none;
                    background-color: #EF4444;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #DC2626;
                }
            """)
            
            error_box.exec_()
        else:
            # 其他错误保持原样，但添加通用建议
            improved_msg = f"{error_msg}\n\n如果问题持续，请尝试：\n1. 检查网络连接\n2. 验证API设置\n3. 更换模型或调整参数"
            
            error_box = QMessageBox()
            error_box.setWindowTitle("API错误")
            error_box.setText(improved_msg)
            error_box.setIcon(QMessageBox.Critical)
            
            # 设置按钮样式
            error_box.setStyleSheet("""
                QPushButton {
                    min-width: 80px;
                    min-height: 32px;
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    border: none;
                    background-color: #EF4444;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #DC2626;
                }
            """)
            
            error_box.exec_()
            
        self.status_bar.showMessage("API调用失败")
        self.generate_button.setEnabled(True)  # 出错后重新启用生成按钮
        self.generate_chapter_button.setEnabled(True)
        self.stop_button.setEnabled(False)  # 出错后禁用停止按钮
        self.set_app_status("异常")
        
        # 重置进度条
        self.progress_bar.setValue(0)
        self.progress_label.setText("生成失败")
        
        # 确保API线程已正确停止
        if hasattr(self, 'api_thread') and self.api_thread:
            if self.api_thread.isRunning():
                print("[调试] API线程仍在运行，尝试停止")
                self.api_thread.stop()
                if not self.api_thread.wait(3500):  # 等待2秒
                    print("[调试] API线程未在2秒内停止，强制终止")
                    self.api_thread.terminate()
                    self.api_thread.wait(1000)  # 再等待1秒确保终止
                print("[调试] API线程已停止")
            else:
                print("[调试] API线程已停止")

    def format_text_for_save(self, text):
        """格式化文本以便保存，每行约30字或按句号分行，并去除重复内容"""
        if not text:
            return text
            
        # 首先去除重复内容
        text = self._remove_duplicate_content(text)
            
        # 使用列表存储格式化后的行，比字符串拼接更高效
        formatted_lines = []
        current_line = []
        current_length = 0
        line_limit = 30
        
        # 使用迭代器处理文本，避免多次字符串操作
        for char in text:
            current_line.append(char)
            current_length += 1
            
            # 遇到句号、问号、感叹号或达到行长度限制时换行
            if char in '。！？' or current_length >= line_limit:
                formatted_lines.append(''.join(current_line))
                current_line = []
                current_length = 0
        
        # 添加最后一行
        if current_line:
            formatted_lines.append(''.join(current_line))
            
        return "\n".join(formatted_lines)
    
    def _remove_duplicate_content(self, text):
        """去除文本中的重复内容"""
        # 首先按段落分割文本
        paragraphs = text.split('\n')
        
        # 去除空段落
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        # 使用字典记录已经出现过的段落
        seen_paragraphs = {}
        unique_paragraphs = []
        
        for paragraph in paragraphs:
            # 计算段落的哈希值作为唯一标识
            paragraph_hash = hash(paragraph)
            
            # 如果段落长度太短（小于10个字符），可能是标题或特殊格式，保留
            if len(paragraph) < 10:
                unique_paragraphs.append(paragraph)
                continue
                
            # 如果段落已经出现过，跳过
            if paragraph_hash in seen_paragraphs:
                # 移除了调试日志输出
                continue
                
            # 否则记录并保留
            seen_paragraphs[paragraph_hash] = True
            unique_paragraphs.append(paragraph)
        
        # 重新组合段落
        deduplicated_text = '\n'.join(unique_paragraphs)
        
        # 进一步检测并去除句子级别的重复
        deduplicated_text = self._remove_duplicate_sentences(deduplicated_text)
        
        return deduplicated_text
    
    def _remove_duplicate_sentences(self, text):
        """检测并去除文本中重复的句子"""
        # 按句子分割文本（保留句号等标点）
        sentences = re.split(r'([。！？])', text)
        
        # 重新组合句子和标点
        processed_sentences = []
        i = 0
        while i < len(sentences):
            if i + 1 < len(sentences):
                sentence = sentences[i] + sentences[i+1]  # 句子+标点
                i += 2
            else:
                sentence = sentences[i]
                i += 1
                
            # 跳过空句子
            if not sentence.strip():
                continue
                
            # 检查是否与前面的句子重复
            is_duplicate = False
            for j in range(len(processed_sentences) - 1, max(-1, len(processed_sentences) - 5), -1):
                # 计算相似度
                similarity = self._calculate_similarity(sentence, processed_sentences[j])
                if similarity > 0.8:  # 相似度阈值
                    # 移除了调试日志输出
                    is_duplicate = True
                    break
                    
            if not is_duplicate:
                processed_sentences.append(sentence)
                
        return ''.join(processed_sentences)
    
    def _calculate_similarity(self, text1, text2):
        """计算两个文本的相似度（基于共同的词汇比例）"""
        # 简单的相似度计算，基于共同的词汇比例
        words1 = set(text1)
        words2 = set(text2)
        
        if not words1 or not words2:
            return 0
            
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
        

    
    def get_current_content(self):
        """获取当前编辑的内容，用于自动保存"""
        return self.chapter_text.toPlainText()
    
    def save_current_content(self):
        """保存当前编辑的内容，用于自动保存"""
        # 获取小说标题
        title = self.novel_title_input.text().strip()
        if not title:
            title = "未命名小说"
        
        # 创建保存目录（如果不存在）
        if not os.path.exists(self.save_path):
            try:
                os.makedirs(self.save_path)
            except Exception as e:
                raise Exception(f"创建保存目录失败: {str(e)}")
        
        # 自动生成文件名
        chapter_num = self.chapter_number.value()
        
        # 从章节内容中提取章节标题
        content = self.chapter_text.toPlainText()
        chapter_title = self.extract_chapter_title(content) if content else "未命名章节"
        
        # 使用简化的命名格式：第X章.txt
        # 不再包含章节标题和小说标题，只使用章节号
        file_name = f"第{chapter_num}章.txt"
        file_path = os.path.join(self.save_path, file_name)
        
        try:
            if not content:
                return False
            
            # 格式化文本
            formatted_content = self.format_text_for_save(content)
            
            # 保存到文件
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(formatted_content)
            
            return file_path
        except Exception as e:
            raise Exception(f"保存文件失败: {str(e)}")
    
    def extract_chapter_title(self, content):
        """从章节内容中提取章节标题"""
        # 尝试匹配格式：第X章：标题
        match = re.search(r'第\d+章[：:]\s*(.+?)(?:\n|$)', content)
        if match:
            title = match.group(1).strip()
            # 限制标题长度，避免文件名过长
            if len(title) > 20:
                title = title[:20] + "..."
            return title
        
        # 如果没有找到标准格式，尝试匹配其他可能的标题格式
        # 例如：**标题** 或 标题（单独一行）
        lines = content.split('\n')
        for i, line in enumerate(lines[:5]):  # 只检查前5行
            line = line.strip()
            # 匹配**标题**格式
            if line.startswith('**') and line.endswith('**'):
                title = line[2:-2].strip()
                if len(title) > 20:
                    title = title[:20] + "..."
                return title
            
            # 如果是单独一行的短文本，可能是标题
            if len(line) > 0 and len(line) < 30 and i < 3:
                # 检查是否包含常见的标题关键词
                if any(keyword in line for keyword in ['章', '回', '节', '卷', '篇']):
                    if len(line) > 20:
                        line = line[:20] + "..."
                    return line
        
        # 如果都没有找到，返回默认标题
        return "未命名章节"
    
    def start_auto_save(self):
        """启动自动保存线程"""
        # 如果已有自动保存线程在运行，先停止它
        if hasattr(self, 'auto_save_thread') and self.auto_save_thread and self.auto_save_thread.running:
            self.stop_auto_save()
        
        # 创建并启动新的自动保存线程
        self.auto_save_thread = AutoSaveThread(self, save_interval=30)  # 每30秒保存一次
        self.auto_save_thread.save_complete.connect(self.on_auto_save_complete)
        self.auto_save_thread.save_error.connect(self.on_auto_save_error)
        self.auto_save_thread.start()
        self.status_bar.showMessage("自动保存已启动")
    
    def stop_auto_save(self):
        """停止自动保存线程"""
        if hasattr(self, 'auto_save_thread') and self.auto_save_thread:
            self.auto_save_thread.stop()
            self.auto_save_thread = None
            self.status_bar.showMessage("自动保存已停止")
    
    def on_auto_save_complete(self, file_path):
        """自动保存完成回调"""
        self.status_bar.showMessage(f"自动保存完成: {os.path.basename(file_path)}")
    
    def on_auto_save_error(self, error_msg):
        """自动保存错误回调"""
        self.status_bar.showMessage(error_msg)
        # 创建自定义警告消息框
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("自动保存错误")
        msg_box.setText("自动保存过程中发生错误")
        msg_box.setInformativeText(error_msg)
        msg_box.setStandardButtons(QMessageBox.Ok)
        
        # 设置按钮样式
        ok_button = msg_box.button(QMessageBox.Ok)
        if ok_button:
            ok_button.setStyleSheet("""
                QPushButton {
                    min-width: 80px;
                    min-height: 32px;
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    border: none;
                    background-color: #F59E0B;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #D97706;
                }
            """)
        
        msg_box.exec_()
            
    def save_result(self):
        """保存小说章节结果"""
        try:
            # 获取章节内容
            content = self.chapter_text.toPlainText()
            if not content:
                # 创建自定义警告消息框
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Warning)
                msg_box.setWindowTitle("警告")
                msg_box.setText("没有可保存的内容")
                msg_box.setInformativeText("请先生成或输入章节内容后再尝试保存")
                msg_box.setStandardButtons(QMessageBox.Ok)
                
                # 设置按钮样式
                ok_button = msg_box.button(QMessageBox.Ok)
                if ok_button:
                    ok_button.setStyleSheet("""
                        QPushButton {
                            min-width: 80px;
                            min-height: 32px;
                            padding: 6px 16px;
                            border-radius: 4px;
                            font-size: 13px;
                            font-weight: 600;
                            border: none;
                            background-color: #F59E0B;
                            color: white;
                        }
                        QPushButton:hover {
                            background-color: #D97706;
                        }
                    """)
                
                msg_box.exec_()
                return
                
            # 确保保存目录存在
            if not os.path.exists(self.save_path):
                os.makedirs(self.save_path)
                
            # 生成文件名（第章节号）
            chapter_num = self.chapter_number.value()
            
            # 使用简化的命名格式：第X章.txt
            # 不再包含章节标题和小说标题，只使用章节号
            file_name = f"第{chapter_num}章.txt"
            file_path = os.path.join(self.save_path, file_name)
            
            # 检查文件是否已存在
            if os.path.exists(file_path):
                # 如果文件已存在，直接跳过保存，不询问用户
                self.status_bar.showMessage(f"第{chapter_num}章已存在，跳过保存")
                return
            
            # 格式化文本，每行约30字或按句号分行
            formatted_content = self.format_text_for_save(content)
            
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(formatted_content)
                
            self.status_bar.showMessage(f"已保存: {file_path}")
            self.chapter_counter += 1  # 计数器递增
            self.set_app_status("正常")
        except Exception as e:
            # 创建自定义错误消息框
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("保存错误")
            msg_box.setText("保存文件时出错")
            msg_box.setInformativeText(str(e))
            msg_box.setStandardButtons(QMessageBox.Ok)
            
            # 设置按钮样式
            ok_button = msg_box.button(QMessageBox.Ok)
            if ok_button:
                ok_button.setStyleSheet("""
                    QPushButton {
                        min-width: 80px;
                        min-height: 32px;
                        padding: 6px 16px;
                        border-radius: 4px;
                        font-size: 13px;
                        font-weight: 600;
                        border: none;
                        background-color: #EF4444;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #DC2626;
                    }
                """)
            
            msg_box.exec_()
            self.status_bar.showMessage("保存失败")
            self.set_app_status("异常")
            


    def save_parameters(self):
        """保存当前参数到配置文件"""
        print("开始保存参数...")
        
        # 使用绝对路径
        user_params_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_params.json")
        
        # 首先尝试加载现有的参数
        existing_params = {}
        if os.path.exists(user_params_path):
            try:
                with open(user_params_path, "r", encoding="utf-8") as f:
                    existing_params = json.load(f)
                print("已加载现有参数")
            except Exception as e:
                print(f"加载现有参数失败: {e}")
        
        # 创建多API配置结构
        if "api_configs" not in existing_params:
            existing_params["api_configs"] = {}
            print("创建新的api_configs结构")
        
        # 保存当前API配置
        print(f"保存 {self.api_type} 的配置...")
        existing_params["api_configs"][self.api_type] = {
            "api_url": self.api_url,
            "api_key": self.api_key,
            "model_name": self.model_name,
            "api_format": self.api_format,
            "custom_headers": self.custom_headers
        }
        print(f"已保存 {self.api_type} 的配置: {existing_params['api_configs'][self.api_type]}")
        
        # 保存当前选中的API类型和其他通用参数
        params = {
            "current_api_type": self.api_type,
            "api_configs": existing_params["api_configs"],
            "min_chapter_length": self.min_chapter_length,
            "max_chapter_length": self.max_chapter_length,
            "save_path": self.save_path,
            "file_behavior": self.file_behavior
        }
        
        try:
            with open(user_params_path, "w", encoding="utf-8") as f:
                json.dump(params, f, ensure_ascii=False, indent=4)
            print("参数保存成功")
            self.status_bar.showMessage("设置已保存")
            # 创建自定义信息消息框
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle("保存成功")
            msg_box.setText("应用程序设置已保存")
            msg_box.setInformativeText("您的设置已成功保存到配置文件中")
            msg_box.setStandardButtons(QMessageBox.Ok)
            
            # 设置按钮样式
            ok_button = msg_box.button(QMessageBox.Ok)
            if ok_button:
                ok_button.setStyleSheet("""
                    QPushButton {
                        min-width: 80px;
                        min-height: 32px;
                        padding: 6px 16px;
                        border-radius: 4px;
                        font-size: 13px;
                        font-weight: 600;
                        border: none;
                        background-color: #4F46E5;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #4338CA;
                    }
                """)
            
            # 显示消息框
            msg_box.show()
            
            # 设置0.25秒后自动关闭消息框
            QTimer.singleShot(250, msg_box.accept)
            
            self.set_app_status("正常")
        except Exception as e:
            print(f"保存参数失败: {e}")
            # 创建自定义错误消息框
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("保存失败")
            msg_box.setText("保存设置时出错")
            msg_box.setInformativeText(str(e))
            msg_box.setStandardButtons(QMessageBox.Ok)
            
            # 设置按钮样式
            ok_button = msg_box.button(QMessageBox.Ok)
            if ok_button:
                ok_button.setStyleSheet("""
                    QPushButton {
                        min-width: 80px;
                        min-height: 32px;
                        padding: 6px 16px;
                        border-radius: 4px;
                        font-size: 13px;
                        font-weight: 600;
                        border: none;
                        background-color: #EF4444;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #DC2626;
                    }
                """)
            
            msg_box.exec_()
            self.status_bar.showMessage("保存设置失败")
            self.set_app_status("异常")

    def load_parameters(self):
        """从配置文件加载参数"""
        print("开始加载参数...")
        try:
            # 使用绝对路径
            user_params_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_params.json")
            if os.path.exists(user_params_path):
                with open(user_params_path, "r", encoding="utf-8") as f:
                    params = json.load(f)
                    print("已加载参数文件")
                    
                    # 检查是否是新的配置格式（包含api_configs）
                    if "api_configs" in params:
                        # 新格式：加载当前选中的API类型
                        self.api_type = params.get("current_api_type", "Ollama")
                        print(f"当前API类型: {self.api_type}")
                        
                        # 加载当前API类型的配置
                        current_api_config = params["api_configs"].get(self.api_type, {})
                        self.api_url = current_api_config.get("api_url", "http://localhost:11434/api/generate")
                        self.api_key = current_api_config.get("api_key", "")
                        self.model_name = current_api_config.get("model_name", "deepseek-r1:latest")
                        self.api_format = current_api_config.get("api_format", None)
                        self.custom_headers = current_api_config.get("custom_headers", None)
                        print(f"已加载 {self.api_type} 的配置: URL={self.api_url}, Model={self.model_name}")
                    else:
                        # 旧格式：直接加载参数
                        self.api_type = params.get("api_type", "Ollama")
                        self.api_url = params.get("api_url", "http://localhost:11434/api/generate")
                        self.api_key = params.get("api_key", "")
                        self.model_name = params.get("model_name", "deepseek-r1:latest")
                        self.api_format = params.get("api_format", None)
                        self.custom_headers = params.get("custom_headers", None)
                        print(f"已加载旧格式参数: API={self.api_type}, Model={self.model_name}")
                    
                    # 加载通用参数
                    self.min_chapter_length = params.get("min_chapter_length", 3500)
                    self.max_chapter_length = params.get("max_chapter_length", 5000)
                    self.save_path = params.get("save_path", "novels")
                    self.file_behavior = params.get("file_behavior", "询问")
                    print(f"已加载通用参数: 章节长度={self.min_chapter_length}-{self.max_chapter_length}, 保存路径={self.save_path}, 文件行为={self.file_behavior}")
                    
                    # 根据API类型更新模型选择下拉框
                    if self.api_type == "SiliconFlow":
                        self.model_combo.clear()
                        self.model_combo.addItems(["Qwen/Qwen3-8B", "Qwen/Qwen2.5-7B"])
                        print("已加载SiliconFlow模型列表")
                    elif self.api_type == "Ollama":
                        # 加载默认模型和自定义模型
                        self.model_combo.clear()
                        default_models = ["qwen:latest"]
                        custom_models = self.load_custom_models()
                        all_models = default_models + custom_models
                        self.model_combo.addItems(all_models)
                        print(f"已加载Ollama模型列表: {all_models}")
                    elif self.api_type == "ModelScope":
                        # 加载默认模型和自定义ModelScope模型
                        self.model_combo.clear()
                        default_models = ["Qwen/Qwen3-VL-30B-A3B-Instruct"]
                        custom_models = self.load_custom_modelscope_models()
                        all_models = default_models + custom_models
                        self.model_combo.addItems(all_models)
                        print(f"已加载ModelScope模型列表: {all_models}")
                    else:
                        # 其他API类型使用默认模型列表
                        self.model_combo.clear()
                        self.model_combo.addItems(["deepseek-r1:latest", "llama2:latest", "mistral:latest", "qwen:latest"])
                        print("已加载默认模型列表")
                    
                    # 设置当前选中的模型
                    if self.model_name:
                        index = self.model_combo.findText(self.model_name)
                        if index >= 0:
                            self.model_combo.setCurrentIndex(index)
                            print(f"已设置当前模型: {self.model_name}")
                        else:
                            print(f"警告: 未找到模型 {self.model_name}，使用默认模型")
                    
                    print("参数加载完成")
            else:
                print("参数文件不存在，使用默认参数")
        except Exception as e:
            print(f"加载参数失败: {e}")
            # 使用默认参数
            self.api_type = "Ollama"
            self.api_url = "http://localhost:11434/api/generate"
            self.api_key = ""
            self.model_name = "deepseek-r1:latest"
            self.api_format = None
            self.custom_headers = None
            self.min_chapter_length = 3500
            self.max_chapter_length = 5000
            self.save_path = "novels"
            
            # 更新UI
            self.model_combo.setCurrentText(self.model_name)
            # 更新状态栏显示当前模型名称
            self.status_bar.showMessage(f"已切换到模型: {self.model_name}")
            self.set_app_status("正常")
        except Exception as e:
            print(f"加载参数失败: {e}")
            self.set_app_status("异常")

    def show_title_generation_dialog(self):
        """显示AI生成标题对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("AI生成小说标题")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(400)
        
        layout = QVBoxLayout(dialog)
        
        # 标题类型选择
        type_group = QGroupBox("小说类型")
        type_layout = QVBoxLayout(type_group)
        
        self.title_type_combo = QComboBox()
        self.title_type_combo.addItems([
            "现代言情", "都市生活", "古装言情", "玄幻奇幻", "武侠仙侠", 
            "科幻末世", "悬疑推理", "历史军事", "游戏竞技", "青春校园",
            "耽美同人", "灵异奇谈", "商战职场", "豪门世家", "穿越重生"
        ])
        self.title_type_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QComboBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        type_layout.addWidget(self.title_type_combo)
        
        # 关键词输入
        keyword_group = QGroupBox("关键词（可选）")
        keyword_layout = QVBoxLayout(keyword_group)
        
        self.keyword_input = QTextEdit()
        self.keyword_input.setPlaceholderText("输入关键词，用逗号分隔，例如：霸道总裁, 甜宠, 先婚后爱...")
        self.keyword_input.setMaximumHeight(80)
        self.keyword_input.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        keyword_layout.addWidget(self.keyword_input)
        
        # 生成数量
        count_group = QGroupBox("生成数量")
        count_layout = QHBoxLayout(count_group)
        
        self.title_count_spin = QSpinBox()
        self.title_count_spin.setRange(1, 10)
        self.title_count_spin.setValue(5)
        self.title_count_spin.setStyleSheet("""
            QSpinBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QSpinBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        
        count_layout.addWidget(QLabel("生成标题数量:"))
        count_layout.addWidget(self.title_count_spin)
        count_layout.addStretch()
        
        # 生成结果
        result_group = QGroupBox("生成结果")
        result_layout = QVBoxLayout(result_group)
        
        self.title_result_list = QListWidget()
        self.title_result_list.setStyleSheet("""
            QListWidget {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #E5E7EB;
            }
            QListWidget::item:selected {
                background-color: #EBF5FF;
                color: #1E40AF;
            }
        """)
        result_layout.addWidget(self.title_result_list)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.generate_title_button = QPushButton("生成标题")
        self.generate_title_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        
        self.use_title_button = QPushButton("使用选中标题")
        self.use_title_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #6366F1;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #4F46E5;
            }
            QPushButton:pressed {
                background-color: #4338CA;
            }
        """)
        self.use_title_button.setEnabled(False)
        
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #F3F4F6;
                color: #4B5563;
                border: none;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        
        button_layout.addWidget(self.generate_title_button)
        button_layout.addWidget(self.use_title_button)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        
        # 添加所有组件到主布局
        layout.addWidget(type_group)
        layout.addWidget(keyword_group)
        layout.addWidget(count_group)
        layout.addWidget(result_group)
        layout.addLayout(button_layout)
        
        # 连接信号
        self.generate_title_button.clicked.connect(lambda: self.generate_titles(dialog))
        self.use_title_button.clicked.connect(lambda: self.use_selected_title(dialog))
        self.cancel_button.clicked.connect(dialog.reject)
        self.title_result_list.itemSelectionChanged.connect(self.on_title_selection_changed)
        
        # 显示对话框
        dialog.exec_()
        
    def generate_titles(self, dialog):
        """生成小说标题"""
        # 获取用户输入
        title_type = self.title_type_combo.currentText()
        keywords = self.keyword_input.toPlainText().strip()
        count = self.title_count_spin.value()
        
        # 构建提示词
        prompt = f"请生成{count}个{title_type}类型的小说标题"
        if keywords:
            prompt += f"，包含以下关键词：{keywords}"
        prompt += "。请只返回标题，每个标题一行，不要添加编号或其他内容。"
        
        # 禁用生成按钮，显示加载状态
        self.generate_title_button.setEnabled(False)
        self.generate_title_button.setText("生成中...")
        self.title_result_list.clear()
        self.title_result_list.addItem("正在生成标题，请稍候...")
        
        # 创建API调用线程
        self.title_thread = ApiCallThread(
            self.api_type, 
            self.api_url, 
            self.api_key, 
            prompt, 
            self.model_name,
            self.api_format,
            self.custom_headers
        )
        
        # 连接信号
        self.title_thread.finished.connect(lambda response, status: self.on_titles_generated(response, status, dialog))
        self.title_thread.error.connect(lambda error: self.on_title_generation_error(error, dialog))
        
        # 启动线程
        self.title_thread.start()
        
    def on_titles_generated(self, response, status, dialog):
        """处理标题生成完成"""
        # 恢复按钮状态
        self.generate_title_button.setEnabled(True)
        self.generate_title_button.setText("生成标题")
        
        if status == "success":
            # 清空结果列表
            self.title_result_list.clear()
            
            # 处理响应，提取标题
            titles = response.strip().split('\n')
            for title in titles:
                title = title.strip()
                if title:
                    # 去除可能的编号前缀
                    title = re.sub(r'^\d+[\.\)]\s*', '', title)
                    self.title_result_list.addItem(title)
            
            # 如果没有生成任何标题，显示提示
            if self.title_result_list.count() == 0:
                self.title_result_list.addItem("未能生成有效标题，请重试")
        else:
            self.title_result_list.clear()
            self.title_result_list.addItem(f"生成失败: {response}")
    
    def on_title_generation_error(self, error, dialog):
        """处理标题生成错误"""
        # 恢复按钮状态
        self.generate_title_button.setEnabled(True)
        self.generate_title_button.setText("生成标题")
        
        # 显示错误信息
        self.title_result_list.clear()
        self.title_result_list.addItem(f"生成失败: {error}")
    
    def on_title_selection_changed(self):
        """处理标题选择变化"""
        # 如果有选中的标题，启用使用按钮
        has_selection = bool(self.title_result_list.selectedItems())
        self.use_title_button.setEnabled(has_selection)
    
    def use_selected_title(self, dialog):
        """使用选中的标题"""
        # 获取选中的标题
        selected_items = self.title_result_list.selectedItems()
        if selected_items:
            selected_title = selected_items[0].text()
            # 设置到标题输入框
            self.novel_title_input.setText(selected_title)
            # 关闭对话框
            dialog.accept()

    def show_background_generation_dialog(self):
        """显示AI生成小说背景对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("AI生成小说背景")
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(500)
        
        layout = QVBoxLayout(dialog)
        
        # 背景类型选择
        type_group = QGroupBox("背景类型")
        type_layout = QVBoxLayout(type_group)
        
        self.bg_type_combo = QComboBox()
        self.bg_type_combo.addItems([
            "现代都市", "古代宫廷", "玄幻修仙", "未来科幻", "校园青春",
            "商战职场", "乡村田园", "异世大陆", "末世废土", "虚拟游戏",
            "魔法学院", "江湖武侠", "星际战争", "民国时期", "架空历史"
        ])
        self.bg_type_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QComboBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        type_layout.addWidget(self.bg_type_combo)
        
        # 时代设定
        era_group = QGroupBox("时代设定")
        era_layout = QVBoxLayout(era_group)
        
        self.era_combo = QComboBox()
        self.era_combo.addItems([
            "古代", "近代", "现代", "未来", "架空"
        ])
        self.era_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QComboBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        era_layout.addWidget(self.era_combo)
        
        # 地点设定
        location_group = QGroupBox("地点设定")
        location_layout = QVBoxLayout(location_group)
        
        self.location_combo = QComboBox()
        self.location_combo.addItems([
            "东方", "西方", "混合", "架空世界", "宇宙"
        ])
        self.location_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QComboBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        location_layout.addWidget(self.location_combo)
        
        # 关键元素
        elements_group = QGroupBox("关键元素（可选）")
        elements_layout = QVBoxLayout(elements_group)
        
        self.elements_input = QTextEdit()
        self.elements_input.setPlaceholderText("输入希望包含的关键元素，用逗号分隔，例如：魔法、科技、修仙、机甲...")
        self.elements_input.setMaximumHeight(80)
        self.elements_input.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        elements_layout.addWidget(self.elements_input)
        
        # 生成结果
        result_group = QGroupBox("生成结果")
        result_layout = QVBoxLayout(result_group)
        
        self.bg_result_text = QTextEdit()
        self.bg_result_text.setReadOnly(True)
        self.bg_result_text.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
        """)
        result_layout.addWidget(self.bg_result_text)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.generate_bg_dialog_button = QPushButton("生成背景")
        self.generate_bg_dialog_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        
        self.use_bg_button = QPushButton("使用此背景")
        self.use_bg_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #6366F1;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #4F46E5;
            }
            QPushButton:pressed {
                background-color: #4338CA;
            }
        """)
        self.use_bg_button.setEnabled(False)
        
        self.cancel_bg_button = QPushButton("取消")
        self.cancel_bg_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #F3F4F6;
                color: #4B5563;
                border: none;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        
        button_layout.addWidget(self.generate_bg_dialog_button)
        button_layout.addWidget(self.use_bg_button)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_bg_button)
        
        # 添加所有组件到主布局
        layout.addWidget(type_group)
        layout.addWidget(era_group)
        layout.addWidget(location_group)
        layout.addWidget(elements_group)
        layout.addWidget(result_group)
        layout.addLayout(button_layout)
        
        # 连接信号
        self.generate_bg_dialog_button.clicked.connect(lambda: self.generate_background(dialog))
        self.use_bg_button.clicked.connect(lambda: self.use_generated_background(dialog))
        self.cancel_bg_button.clicked.connect(dialog.reject)
        
        # 显示对话框
        dialog.exec_()
        
    def generate_background(self, dialog):
        """生成小说背景"""
        # 获取用户输入
        bg_type = self.bg_type_combo.currentText()
        era = self.era_combo.currentText()
        location = self.location_combo.currentText()
        elements = self.elements_input.toPlainText().strip()
        
        # 构建提示词
        prompt = f"请为小说生成一个详细的背景设定，背景类型为{bg_type}，时代设定为{era}，地点设定为{location}"
        if elements:
            prompt += f"，包含以下关键元素：{elements}"
        prompt += "。请描述世界观、时代背景、主要场景、社会结构等，内容要丰富详细，大约300-500字。"
        
        # 禁用生成按钮，显示加载状态
        self.generate_bg_dialog_button.setEnabled(False)
        self.generate_bg_dialog_button.setText("生成中...")
        self.bg_result_text.clear()
        self.bg_result_text.setPlainText("正在生成背景设定，请稍候...")
        
        # 创建API调用线程
        self.bg_thread = ApiCallThread(
            self.api_type, 
            self.api_url, 
            self.api_key, 
            prompt, 
            self.model_name,
            self.api_format,
            self.custom_headers
        )
        
        # 连接信号
        self.bg_thread.finished.connect(lambda response, status: self.on_background_generated(response, status, dialog))
        self.bg_thread.error.connect(lambda error: self.on_background_generation_error(error, dialog))
        
        # 启动线程
        self.bg_thread.start()
        
    def on_background_generated(self, response, status, dialog):
        """处理背景生成完成"""
        # 恢复按钮状态
        self.generate_bg_dialog_button.setEnabled(True)
        self.generate_bg_dialog_button.setText("生成背景")
        
        if status == "success":
            # 显示生成的背景
            self.bg_result_text.setPlainText(response)
            # 启用使用按钮
            self.use_bg_button.setEnabled(True)
        else:
            self.bg_result_text.setPlainText(f"生成失败: {response}")
            # 禁用使用按钮
            self.use_bg_button.setEnabled(False)
    
    def on_background_generation_error(self, error, dialog):
        """处理背景生成错误"""
        # 恢复按钮状态
        self.generate_bg_dialog_button.setEnabled(True)
        self.generate_bg_dialog_button.setText("生成背景")
        
        # 显示错误信息
        self.bg_result_text.setPlainText(f"生成失败: {error}")
        # 禁用使用按钮
        self.use_bg_button.setEnabled(False)
    
    def use_generated_background(self, dialog):
        """使用生成的背景"""
        # 获取生成的背景
        generated_bg = self.bg_result_text.toPlainText()
        if generated_bg and not generated_bg.startswith("生成失败"):
            # 设置到背景输入框
            self.bg_text.setPlainText(generated_bg)
            # 关闭对话框
            dialog.accept()

    def show_hero_generation_dialog(self):
        """显示AI生成男主角对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("AI生成男主角")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(600)
        
        layout = QVBoxLayout(dialog)
        
        # 人物类型选择
        type_group = QGroupBox("人物类型")
        type_layout = QVBoxLayout(type_group)
        
        self.hero_type_combo = QComboBox()
        self.hero_type_combo.addItems([
            "霸道总裁", "温柔暖男", "阳光少年", "成熟稳重", "桀骜不驯",
            "腹黑谋士", "忠犬型", "高冷禁欲", "幽默风趣", "学霸精英",
            "军人警察", "医生律师", "明星艺人", "运动员", "艺术家"
        ])
        self.hero_type_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QComboBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        type_layout.addWidget(self.hero_type_combo)
        
        # 年龄范围
        age_group = QGroupBox("年龄范围")
        age_layout = QHBoxLayout(age_group)
        
        self.hero_min_age = QSpinBox()
        self.hero_min_age.setRange(18, 80)
        self.hero_min_age.setValue(22)
        self.hero_min_age.setStyleSheet("""
            QSpinBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QSpinBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        
        self.hero_max_age = QSpinBox()
        self.hero_max_age.setRange(18, 80)
        self.hero_max_age.setValue(35)
        self.hero_max_age.setStyleSheet("""
            QSpinBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QSpinBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        
        age_layout.addWidget(QLabel("最小年龄:"))
        age_layout.addWidget(self.hero_min_age)
        age_layout.addWidget(QLabel("最大年龄:"))
        age_layout.addWidget(self.hero_max_age)
        age_layout.addStretch()
        
        # 职业选择
        job_group = QGroupBox("职业选择")
        job_layout = QVBoxLayout(job_group)
        
        self.hero_job_combo = QComboBox()
        self.hero_job_combo.addItems([
            "不限", "企业CEO", "医生", "律师", "教授", "军人", "警察", 
            "明星", "作家", "画家", "摄影师", "厨师", "运动员", "程序员",
            "设计师", "建筑师", "企业家", "科学家", "音乐家", "自由职业"
        ])
        self.hero_job_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QComboBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        job_layout.addWidget(self.hero_job_combo)
        
        # 性格特点
        personality_group = QGroupBox("性格特点（可选）")
        personality_layout = QVBoxLayout(personality_group)
        
        self.hero_personality_input = QTextEdit()
        self.hero_personality_input.setPlaceholderText("输入希望的性格特点，用逗号分隔，例如：冷静、果断、有责任心...")
        self.hero_personality_input.setMaximumHeight(80)
        self.hero_personality_input.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        personality_layout.addWidget(self.hero_personality_input)
        
        # 生成结果
        result_group = QGroupBox("生成结果")
        result_layout = QVBoxLayout(result_group)
        
        self.hero_result_text = QTextEdit()
        self.hero_result_text.setReadOnly(True)
        self.hero_result_text.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
        """)
        result_layout.addWidget(self.hero_result_text)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.generate_hero_dialog_button = QPushButton("生成男主角")
        self.generate_hero_dialog_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        
        self.use_hero_button = QPushButton("使用此设定")
        self.use_hero_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #6366F1;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #4F46E5;
            }
            QPushButton:pressed {
                background-color: #4338CA;
            }
        """)
        self.use_hero_button.setEnabled(False)
        
        self.cancel_hero_button = QPushButton("取消")
        self.cancel_hero_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #F3F4F6;
                color: #4B5563;
                border: none;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        
        button_layout.addWidget(self.generate_hero_dialog_button)
        button_layout.addWidget(self.use_hero_button)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_hero_button)
        
        # 添加所有组件到主布局
        layout.addWidget(type_group)
        layout.addWidget(age_group)
        layout.addWidget(job_group)
        layout.addWidget(personality_group)
        layout.addWidget(result_group)
        layout.addLayout(button_layout)
        
        # 连接信号
        self.generate_hero_dialog_button.clicked.connect(lambda: self.generate_hero(dialog))
        self.use_hero_button.clicked.connect(lambda: self.use_generated_hero(dialog))
        self.cancel_hero_button.clicked.connect(dialog.reject)
        
        # 显示对话框
        dialog.exec_()
        
    def generate_hero(self, dialog):
        """生成男主角"""
        # 获取用户输入
        hero_type = self.hero_type_combo.currentText()
        min_age = self.hero_min_age.value()
        max_age = self.hero_max_age.value()
        job = self.hero_job_combo.currentText()
        personality = self.hero_personality_input.toPlainText().strip()
        
        # 构建提示词
        prompt = f"请生成一个男主角的详细设定，人物类型为{hero_type}"
        if job != "不限":
            prompt += f"，职业为{job}"
        prompt += f"，年龄在{min_age}到{max_age}岁之间"
        if personality:
            prompt += f"，具有以下性格特点：{personality}"
        prompt += "。请提供姓名、年龄、职业、家庭背景和人物简介，内容要丰富详细，大约200-300字。"
        
        # 禁用生成按钮，显示加载状态
        self.generate_hero_dialog_button.setEnabled(False)
        self.generate_hero_dialog_button.setText("生成中...")
        self.hero_result_text.clear()
        self.hero_result_text.setPlainText("正在生成男主角设定，请稍候...")
        
        # 创建API调用线程
        self.hero_thread = ApiCallThread(
            self.api_type, 
            self.api_url, 
            self.api_key, 
            prompt, 
            self.model_name,
            self.api_format,
            self.custom_headers
        )
        
        # 连接信号
        self.hero_thread.finished.connect(lambda response, status: self.on_hero_generated(response, status, dialog))
        self.hero_thread.error.connect(lambda error: self.on_hero_generation_error(error, dialog))
        
        # 启动线程
        self.hero_thread.start()
        
    def on_hero_generated(self, response, status, dialog):
        """处理男主角生成完成"""
        # 恢复按钮状态
        self.generate_hero_dialog_button.setEnabled(True)
        self.generate_hero_dialog_button.setText("生成男主角")
        
        if status == "success":
            # 显示生成的男主角设定
            self.hero_result_text.setPlainText(response)
            # 启用使用按钮
            self.use_hero_button.setEnabled(True)
        else:
            self.hero_result_text.setPlainText(f"生成失败: {response}")
            # 禁用使用按钮
            self.use_hero_button.setEnabled(False)
    
    def on_hero_generation_error(self, error, dialog):
        """处理男主角生成错误"""
        # 恢复按钮状态
        self.generate_hero_dialog_button.setEnabled(True)
        self.generate_hero_dialog_button.setText("生成男主角")
        
        # 显示错误信息
        self.hero_result_text.setPlainText(f"生成失败: {error}")
        # 禁用使用按钮
        self.use_hero_button.setEnabled(False)
    
    def use_generated_hero(self, dialog):
        """使用生成的男主角设定"""
        # 获取生成的男主角设定
        generated_hero = self.hero_result_text.toPlainText()
        if generated_hero and not generated_hero.startswith("生成失败"):
            # 尝试解析生成的文本并填充到表单
            self.parse_and_fill_hero_info(generated_hero)
            # 关闭对话框
            dialog.accept()
    
    def parse_and_fill_hero_info(self, hero_text):
        """解析并填充男主角信息"""
        # 简单的文本解析，实际应用中可能需要更复杂的解析逻辑
        lines = hero_text.split('\n')
        for line in lines:
            line = line.strip()
            if "姓名：" in line or "姓名:" in line:
                name = line.split("：")[-1].split(":")[-1].strip()
                if name:
                    self.hero_name.setText(name)
            elif "年龄：" in line or "年龄:" in line:
                try:
                    age_str = line.split("：")[-1].split(":")[-1].strip()
                    age = int(''.join(filter(str.isdigit, age_str)))
                    if 1 <= age <= 100:
                        self.hero_age.setValue(age)
                except:
                    pass
            elif "职业：" in line or "职业:" in line:
                job = line.split("：")[-1].split(":")[-1].strip()
                if job:
                    self.hero_job.setText(job)
            elif "家庭：" in line or "家庭:" in line or "家庭背景：" in line or "家庭背景:" in line:
                family = line.split("：")[-1].split(":")[-1].strip()
                if family:
                    self.hero_family.setText(family)
        
        # 将整个文本作为人物简介
        self.hero_desc.setPlainText(hero_text)

    def show_heroine_generation_dialog(self):
        """显示AI生成女主角对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("AI生成女主角")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(600)
        
        layout = QVBoxLayout(dialog)
        
        # 人物类型选择
        type_group = QGroupBox("人物类型")
        type_layout = QVBoxLayout(type_group)
        
        self.heroine_type_combo = QComboBox()
        self.heroine_type_combo.addItems([
            "温柔善良", "独立坚强", "活泼开朗", "高冷女神", "可爱俏皮",
            "成熟优雅", "聪明机智", "单纯可爱", "腹黑御姐", "邻家女孩",
            "职场女强人", "文艺青年", "学霸女神", "运动少女", "艺术家"
        ])
        self.heroine_type_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QComboBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        type_layout.addWidget(self.heroine_type_combo)
        
        # 年龄范围
        age_group = QGroupBox("年龄范围")
        age_layout = QHBoxLayout(age_group)
        
        self.heroine_min_age = QSpinBox()
        self.heroine_min_age.setRange(18, 80)
        self.heroine_min_age.setValue(20)
        self.heroine_min_age.setStyleSheet("""
            QSpinBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QSpinBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        
        self.heroine_max_age = QSpinBox()
        self.heroine_max_age.setRange(18, 80)
        self.heroine_max_age.setValue(32)
        self.heroine_max_age.setStyleSheet("""
            QSpinBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QSpinBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        
        age_layout.addWidget(QLabel("最小年龄:"))
        age_layout.addWidget(self.heroine_min_age)
        age_layout.addWidget(QLabel("最大年龄:"))
        age_layout.addWidget(self.heroine_max_age)
        age_layout.addStretch()
        
        # 职业选择
        job_group = QGroupBox("职业选择")
        job_layout = QVBoxLayout(job_group)
        
        self.heroine_job_combo = QComboBox()
        self.heroine_job_combo.addItems([
            "不限", "企业CEO", "医生", "律师", "教授", "设计师", "编辑", 
            "明星", "作家", "画家", "摄影师", "模特", "主持人", "翻译",
            "心理咨询师", "营养师", "企业家", "科学家", "音乐家", "自由职业"
        ])
        self.heroine_job_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QComboBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        job_layout.addWidget(self.heroine_job_combo)
        
        # 性格特点
        personality_group = QGroupBox("性格特点（可选）")
        personality_layout = QVBoxLayout(personality_group)
        
        self.heroine_personality_input = QTextEdit()
        self.heroine_personality_input.setPlaceholderText("输入希望的性格特点，用逗号分隔，例如：温柔、善良、独立、坚强...")
        self.heroine_personality_input.setMaximumHeight(80)
        self.heroine_personality_input.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        personality_layout.addWidget(self.heroine_personality_input)
        
        # 生成结果
        result_group = QGroupBox("生成结果")
        result_layout = QVBoxLayout(result_group)
        
        self.heroine_result_text = QTextEdit()
        self.heroine_result_text.setReadOnly(True)
        self.heroine_result_text.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
        """)
        result_layout.addWidget(self.heroine_result_text)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.generate_heroine_dialog_button = QPushButton("生成女主角")
        self.generate_heroine_dialog_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        
        self.use_heroine_button = QPushButton("使用此设定")
        self.use_heroine_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #6366F1;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #4F46E5;
            }
            QPushButton:pressed {
                background-color: #4338CA;
            }
        """)
        self.use_heroine_button.setEnabled(False)
        
        self.cancel_heroine_button = QPushButton("取消")
        self.cancel_heroine_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #F3F4F6;
                color: #4B5563;
                border: none;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        
        button_layout.addWidget(self.generate_heroine_dialog_button)
        button_layout.addWidget(self.use_heroine_button)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_heroine_button)
        
        # 添加所有组件到主布局
        layout.addWidget(type_group)
        layout.addWidget(age_group)
        layout.addWidget(job_group)
        layout.addWidget(personality_group)
        layout.addWidget(result_group)
        layout.addLayout(button_layout)
        
        # 连接信号
        self.generate_heroine_dialog_button.clicked.connect(lambda: self.generate_heroine(dialog))
        self.use_heroine_button.clicked.connect(lambda: self.use_generated_heroine(dialog))
        self.cancel_heroine_button.clicked.connect(dialog.reject)
        
        # 显示对话框
        dialog.exec_()
        
    def generate_heroine(self, dialog):
        """生成女主角"""
        # 获取用户输入
        heroine_type = self.heroine_type_combo.currentText()
        min_age = self.heroine_min_age.value()
        max_age = self.heroine_max_age.value()
        job = self.heroine_job_combo.currentText()
        personality = self.heroine_personality_input.toPlainText().strip()
        
        # 构建提示词
        prompt = f"请生成一个女主角的详细设定，人物类型为{heroine_type}"
        if job != "不限":
            prompt += f"，职业为{job}"
        prompt += f"，年龄在{min_age}到{max_age}岁之间"
        if personality:
            prompt += f"，具有以下性格特点：{personality}"
        prompt += "。请提供姓名、年龄、职业、家庭背景和人物简介，内容要丰富详细，大约200-300字。"
        
        # 禁用生成按钮，显示加载状态
        self.generate_heroine_dialog_button.setEnabled(False)
        self.generate_heroine_dialog_button.setText("生成中...")
        self.heroine_result_text.clear()
        self.heroine_result_text.setPlainText("正在生成女主角设定，请稍候...")
        
        # 创建API调用线程
        self.heroine_thread = ApiCallThread(
            self.api_type, 
            self.api_url, 
            self.api_key, 
            prompt, 
            self.model_name,
            self.api_format,
            self.custom_headers
        )
        
        # 连接信号
        self.heroine_thread.finished.connect(lambda response, status: self.on_heroine_generated(response, status, dialog))
        self.heroine_thread.error.connect(lambda error: self.on_heroine_generation_error(error, dialog))
        
        # 启动线程
        self.heroine_thread.start()
        
    def on_heroine_generated(self, response, status, dialog):
        """处理女主角生成完成"""
        # 恢复按钮状态
        self.generate_heroine_dialog_button.setEnabled(True)
        self.generate_heroine_dialog_button.setText("生成女主角")
        
        if status == "success":
            # 显示生成的女主角设定
            self.heroine_result_text.setPlainText(response)
            # 启用使用按钮
            self.use_heroine_button.setEnabled(True)
        else:
            self.heroine_result_text.setPlainText(f"生成失败: {response}")
            # 禁用使用按钮
            self.use_heroine_button.setEnabled(False)
    
    def on_heroine_generation_error(self, error, dialog):
        """处理女主角生成错误"""
        # 恢复按钮状态
        self.generate_heroine_dialog_button.setEnabled(True)
        self.generate_heroine_dialog_button.setText("生成女主角")
        
        # 显示错误信息
        self.heroine_result_text.setPlainText(f"生成失败: {error}")
        # 禁用使用按钮
        self.use_heroine_button.setEnabled(False)
    
    def use_generated_heroine(self, dialog):
        """使用生成的女主角设定"""
        # 获取生成的女主角设定
        generated_heroine = self.heroine_result_text.toPlainText()
        if generated_heroine and not generated_heroine.startswith("生成失败"):
            # 尝试解析生成的文本并填充到表单
            self.parse_and_fill_heroine_info(generated_heroine)
            # 关闭对话框
            dialog.accept()
    
    def parse_and_fill_heroine_info(self, heroine_text):
        """解析并填充女主角信息"""
        # 简单的文本解析，实际应用中可能需要更复杂的解析逻辑
        lines = heroine_text.split('\n')
        for line in lines:
            line = line.strip()
            if "姓名：" in line or "姓名:" in line:
                name = line.split("：")[-1].split(":")[-1].strip()
                if name:
                    self.heroine_name.setText(name)
            elif "年龄：" in line or "年龄:" in line:
                try:
                    age_str = line.split("：")[-1].split(":")[-1].strip()
                    age = int(''.join(filter(str.isdigit, age_str)))
                    if 1 <= age <= 100:
                        self.heroine_age.setValue(age)
                except:
                    pass
            elif "职业：" in line or "职业:" in line:
                job = line.split("：")[-1].split(":")[-1].strip()
                if job:
                    self.heroine_job.setText(job)
            elif "家庭：" in line or "家庭:" in line or "家庭背景：" in line or "家庭背景:" in line:
                family = line.split("：")[-1].split(":")[-1].strip()
                if family:
                    self.heroine_family.setText(family)
        
        # 将整个文本作为人物简介
        self.heroine_desc.setPlainText(heroine_text)

    def show_relationship_generation_dialog(self):
        """显示AI生成角色关系对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("AI生成角色关系")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(600)
        
        layout = QVBoxLayout(dialog)
        
        # 关系类型选择
        type_group = QGroupBox("关系类型")
        type_layout = QVBoxLayout(type_group)
        
        self.rel_type_combo = QComboBox()
        self.rel_type_combo.addItems([
            "青梅竹马", "欢喜冤家", "一见钟情", "日久生情", "暗恋成真",
            "破镜重圆", "师生恋", "办公室恋情", "网恋奔现", "契约恋人",
            "前世今生", "重生重逢", "穿越相遇", "系统绑定", "宿敌变情人"
        ])
        self.rel_type_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QComboBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        type_layout.addWidget(self.rel_type_combo)
        
        # 关系发展阶段
        stage_group = QGroupBox("关系发展阶段")
        stage_layout = QVBoxLayout(stage_group)
        
        self.rel_stage_combo = QComboBox()
        self.rel_stage_combo.addItems([
            "初识阶段", "暧昧阶段", "热恋阶段", "磨合阶段", "稳定阶段",
            "危机阶段", "分离阶段", "重逢阶段", "复合阶段", "婚姻阶段"
        ])
        self.rel_stage_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QComboBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        stage_layout.addWidget(self.rel_stage_combo)
        
        # 关系特点
        traits_group = QGroupBox("关系特点")
        traits_layout = QVBoxLayout(traits_group)
        
        self.rel_traits_input = QTextEdit()
        self.rel_traits_input.setPlaceholderText("输入希望的关系特点，用逗号分隔，例如：甜蜜、虐心、治愈、成长...")
        self.rel_traits_input.setMaximumHeight(80)
        self.rel_traits_input.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        traits_layout.addWidget(self.rel_traits_input)
        
        # 其他角色关系
        others_group = QGroupBox("其他角色关系（可选）")
        others_layout = QVBoxLayout(others_group)
        
        self.rel_others_input = QTextEdit()
        self.rel_others_input.setPlaceholderText("描述与其他角色的关系，例如：朋友、家人、竞争对手等...")
        self.rel_others_input.setMaximumHeight(80)
        self.rel_others_input.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        others_layout.addWidget(self.rel_others_input)
        
        # 生成结果
        result_group = QGroupBox("生成结果")
        result_layout = QVBoxLayout(result_group)
        
        self.rel_result_text = QTextEdit()
        self.rel_result_text.setReadOnly(True)
        self.rel_result_text.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
        """)
        result_layout.addWidget(self.rel_result_text)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.generate_rel_dialog_button = QPushButton("生成关系")
        self.generate_rel_dialog_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        
        self.use_rel_button = QPushButton("使用此关系")
        self.use_rel_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #6366F1;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #4F46E5;
            }
            QPushButton:pressed {
                background-color: #4338CA;
            }
        """)
        self.use_rel_button.setEnabled(False)
        
        self.cancel_rel_button = QPushButton("取消")
        self.cancel_rel_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #F3F4F6;
                color: #4B5563;
                border: none;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        
        button_layout.addWidget(self.generate_rel_dialog_button)
        button_layout.addWidget(self.use_rel_button)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_rel_button)
        
        # 添加所有组件到主布局
        layout.addWidget(type_group)
        layout.addWidget(stage_group)
        layout.addWidget(traits_group)
        layout.addWidget(others_group)
        layout.addWidget(result_group)
        layout.addLayout(button_layout)
        
        # 连接信号
        self.generate_rel_dialog_button.clicked.connect(lambda: self.generate_relationship(dialog))
        self.use_rel_button.clicked.connect(lambda: self.use_generated_relationship(dialog))
        self.cancel_rel_button.clicked.connect(dialog.reject)
        
        # 显示对话框
        dialog.exec_()
        
    def generate_relationship(self, dialog):
        """生成角色关系"""
        # 获取用户输入
        rel_type = self.rel_type_combo.currentText()
        rel_stage = self.rel_stage_combo.currentText()
        rel_traits = self.rel_traits_input.toPlainText().strip()
        rel_others = self.rel_others_input.toPlainText().strip()
        
        # 获取角色信息
        hero_name = self.hero_name.text().strip() if self.hero_name.text().strip() else "男主角"
        heroine_name = self.heroine_name.text().strip() if self.heroine_name.text().strip() else "女主角"
        hero_age = self.hero_age.value()
        heroine_age = self.heroine_age.value()
        hero_job = self.hero_job.text().strip() if self.hero_job.text().strip() else "未知"
        heroine_job = self.heroine_job.text().strip() if self.heroine_job.text().strip() else "未知"
        hero_family = self.hero_family.text().strip() if self.hero_family.text().strip() else "普通家庭"
        heroine_family = self.heroine_family.text().strip() if self.heroine_family.text().strip() else "普通家庭"
        hero_desc = self.hero_desc.toPlainText().strip() if self.hero_desc.toPlainText().strip() else "性格温和"
        heroine_desc = self.heroine_desc.toPlainText().strip() if self.heroine_desc.toPlainText().strip() else "性格温柔"
        
        # 构建提示词
        prompt = f"请生成一段角色关系描述，关系类型为{rel_type}，关系发展阶段为{rel_stage}"
        if rel_traits:
            prompt += f"，具有以下关系特点：{rel_traits}"
        if rel_others:
            prompt += f"，同时描述以下其他角色关系：{rel_others}"
        
        # 添加角色信息
        prompt += f"\n\n角色信息：\n"
        prompt += f"男主角：{hero_name}，{hero_age}岁，职业是{hero_job}，家庭背景为{hero_family}。性格特点：{hero_desc}\n"
        prompt += f"女主角：{heroine_name}，{heroine_age}岁，职业是{heroine_job}，家庭背景为{heroine_family}。性格特点：{heroine_desc}\n"
        
        prompt += f"\n请基于以上角色信息，详细描述{hero_name}和{heroine_name}之间的关系发展，以及与其他角色的互动，内容要丰富生动，大约200-300字。"
        
        # 禁用生成按钮，显示加载状态
        self.generate_rel_dialog_button.setEnabled(False)
        self.generate_rel_dialog_button.setText("生成中...")
        self.rel_result_text.clear()
        self.rel_result_text.setPlainText("正在生成角色关系描述，请稍候...")
        
        # 创建API调用线程
        self.rel_thread = ApiCallThread(
            self.api_type, 
            self.api_url, 
            self.api_key, 
            prompt, 
            self.model_name,
            self.api_format,
            self.custom_headers
        )
        
        # 连接信号
        self.rel_thread.finished.connect(lambda response, status: self.on_relationship_generated(response, status, dialog))
        self.rel_thread.error.connect(lambda error: self.on_relationship_generation_error(error, dialog))
        
        # 启动线程
        self.rel_thread.start()
        
    def on_relationship_generated(self, response, status, dialog):
        """处理角色关系生成完成"""
        # 恢复按钮状态
        self.generate_rel_dialog_button.setEnabled(True)
        self.generate_rel_dialog_button.setText("生成关系")
        
        if status == "success":
            # 显示生成的角色关系
            self.rel_result_text.setPlainText(response)
            # 启用使用按钮
            self.use_rel_button.setEnabled(True)
        else:
            self.rel_result_text.setPlainText(f"生成失败: {response}")
            # 禁用使用按钮
            self.use_rel_button.setEnabled(False)
    
    def on_relationship_generation_error(self, error, dialog):
        """处理角色关系生成错误"""
        # 恢复按钮状态
        self.generate_rel_dialog_button.setEnabled(True)
        self.generate_rel_dialog_button.setText("生成关系")
        
        # 显示错误信息
        self.rel_result_text.setPlainText(f"生成失败: {error}")
        # 禁用使用按钮
        self.use_rel_button.setEnabled(False)
    
    def use_generated_relationship(self, dialog):
        """使用生成的角色关系"""
        # 获取生成的角色关系
        generated_rel = self.rel_result_text.toPlainText()
        if generated_rel and not generated_rel.startswith("生成失败"):
            # 设置到角色关系输入框
            self.rel_text.setPlainText(generated_rel)
            # 关闭对话框
            dialog.accept()

    def show_plot_generation_dialog(self):
        """显示AI生成核心剧情对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("AI生成核心剧情")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(600)
        
        layout = QVBoxLayout(dialog)
        
        # 剧情类型选择
        type_group = QGroupBox("剧情类型")
        type_layout = QVBoxLayout(type_group)
        
        self.plot_type_combo = QComboBox()
        self.plot_type_combo.addItems([
            "成长逆袭", "破镜重圆", "复仇计划", "悬疑解谜", "冒险探索",
            "宫廷斗争", "商战风云", "校园青春", "都市职场", "历史传奇",
            "奇幻冒险", "科幻未来", "异世穿越", "重生逆袭", "系统任务"
        ])
        self.plot_type_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QComboBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        type_layout.addWidget(self.plot_type_combo)
        
        # 剧情节奏
        rhythm_group = QGroupBox("剧情节奏")
        rhythm_layout = QVBoxLayout(rhythm_group)
        
        self.plot_rhythm_combo = QComboBox()
        self.plot_rhythm_combo.addItems([
            "平铺直叙", "循序渐进", "跌宕起伏", "高潮迭起", "张弛有度",
            "快节奏", "慢节奏", "前松后紧", "前紧后松", "节奏多变"
        ])
        self.plot_rhythm_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QComboBox:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        rhythm_layout.addWidget(self.plot_rhythm_combo)
        
        # 关键事件
        events_group = QGroupBox("关键事件（可选）")
        events_layout = QVBoxLayout(events_group)
        
        self.plot_events_input = QTextEdit()
        self.plot_events_input.setPlaceholderText("输入希望包含的关键事件，用逗号分隔，例如：相遇、误会、分离、重逢...")
        self.plot_events_input.setMaximumHeight(80)
        self.plot_events_input.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        events_layout.addWidget(self.plot_events_input)
        
        # 剧情转折
        twist_group = QGroupBox("剧情转折（可选）")
        twist_layout = QVBoxLayout(twist_group)
        
        self.plot_twist_input = QTextEdit()
        self.plot_twist_input.setPlaceholderText("输入希望的剧情转折，例如：身份揭秘、意外事件、真相大白...")
        self.plot_twist_input.setMaximumHeight(80)
        self.plot_twist_input.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
            QTextEdit:focus {
                border: 1px solid #6366F1;
                background-color: #FFFFFF;
            }
        """)
        twist_layout.addWidget(self.plot_twist_input)
        
        # 生成结果
        result_group = QGroupBox("生成结果")
        result_layout = QVBoxLayout(result_group)
        
        self.plot_result_text = QTextEdit()
        self.plot_result_text.setReadOnly(True)
        self.plot_result_text.setStyleSheet("""
            QTextEdit {
                padding: 8px 12px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 14px;
                background-color: #F9FAFB;
            }
        """)
        result_layout.addWidget(self.plot_result_text)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.generate_plot_dialog_button = QPushButton("生成剧情")
        self.generate_plot_dialog_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        
        self.use_plot_button = QPushButton("使用此剧情")
        self.use_plot_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #6366F1;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #4F46E5;
            }
            QPushButton:pressed {
                background-color: #4338CA;
            }
        """)
        self.use_plot_button.setEnabled(False)
        
        self.cancel_plot_button = QPushButton("取消")
        self.cancel_plot_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                background-color: #F3F4F6;
                color: #4B5563;
                border: none;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        
        button_layout.addWidget(self.generate_plot_dialog_button)
        button_layout.addWidget(self.use_plot_button)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_plot_button)
        
        # 添加所有组件到主布局
        layout.addWidget(type_group)
        layout.addWidget(rhythm_group)
        layout.addWidget(events_group)
        layout.addWidget(twist_group)
        layout.addWidget(result_group)
        layout.addLayout(button_layout)
        
        # 连接信号
        self.generate_plot_dialog_button.clicked.connect(lambda: self.generate_plot(dialog))
        self.use_plot_button.clicked.connect(lambda: self.use_generated_plot(dialog))
        self.cancel_plot_button.clicked.connect(dialog.reject)
        
        # 显示对话框
        dialog.exec_()
        
    def generate_plot(self, dialog):
        """生成核心剧情"""
        # 获取用户输入
        plot_type = self.plot_type_combo.currentText()
        plot_rhythm = self.plot_rhythm_combo.currentText()
        plot_events = self.plot_events_input.toPlainText().strip()
        plot_twist = self.plot_twist_input.toPlainText().strip()
        
        # 获取前面章节的内容作为上下文
        previous_chapters_content = self._get_previous_chapters_content()
        
        # 构建提示词
        prompt = f"请根据前面章节的内容，生成一段核心剧情描述，剧情类型为{plot_type}，剧情节奏为{plot_rhythm}"
        
        # 如果有前面章节内容，添加到提示词中
        if previous_chapters_content:
            prompt += f"\n\n【前面章节内容回顾】\n{previous_chapters_content}\n\n"
            prompt += "请确保新生成的核心剧情与前面章节内容衔接自然，情节连贯，逻辑合理。\n"
        
        # 添加男女主角信息
        hero_name = self.hero_name.text().strip() if self.hero_name.text().strip() else "男主角"
        heroine_name = self.heroine_name.text().strip() if self.heroine_name.text().strip() else "女主角"
        
        prompt += f"\n【重要角色信息】\n"
        prompt += f"男主角：{hero_name}\n"
        prompt += f"女主角：{heroine_name}\n"
        prompt += f"请确保在核心剧情中正确使用以上角色名字，不要混淆男女主角的名字。\n\n"
        
        if plot_events:
            prompt += f"【用户指定的关键事件】\n{plot_events}\n\n"
        if plot_twist:
            prompt += f"【用户指定的剧情转折】\n{plot_twist}\n\n"
            
        prompt += "请详细描述小说的主要情节和发展脉络，包括起承转合，内容要丰富生动，逻辑连贯，与前面章节内容自然衔接，大约300-400字。"
        
        # 禁用生成按钮，显示加载状态
        self.generate_plot_dialog_button.setEnabled(False)
        self.generate_plot_dialog_button.setText("生成中...")
        self.plot_result_text.clear()
        self.plot_result_text.setPlainText("正在生成核心剧情描述，请稍候...")
        
        # 创建API调用线程
        self.plot_thread = ApiCallThread(
            self.api_type, 
            self.api_url, 
            self.api_key, 
            prompt, 
            self.model_name,
            self.api_format,
            self.custom_headers
        )
        
        # 连接信号
        self.plot_thread.finished.connect(lambda response, status: self.on_plot_generated(response, status, dialog))
        self.plot_thread.error.connect(lambda error: self.on_plot_generation_error(error, dialog))
        
        # 启动线程
        self.plot_thread.start()
        
    def on_plot_generated(self, response, status, dialog):
        """处理核心剧情生成完成"""
        # 恢复按钮状态
        self.generate_plot_dialog_button.setEnabled(True)
        self.generate_plot_dialog_button.setText("生成剧情")
        
        if status == "success":
            # 显示生成的核心剧情
            self.plot_result_text.setPlainText(response)
            # 启用使用按钮
            self.use_plot_button.setEnabled(True)
        else:
            self.plot_result_text.setPlainText(f"生成失败: {response}")
            # 禁用使用按钮
            self.use_plot_button.setEnabled(False)
    
    def on_plot_generation_error(self, error, dialog):
        """处理核心剧情生成错误"""
        # 恢复按钮状态
        self.generate_plot_dialog_button.setEnabled(True)
        self.generate_plot_dialog_button.setText("生成剧情")
        
        # 显示错误信息
        self.plot_result_text.setPlainText(f"生成失败: {error}")
        # 禁用使用按钮
        self.use_plot_button.setEnabled(False)
    
    def use_generated_plot(self, dialog):
        """使用生成的核心剧情"""
        # 获取生成的核心剧情
        generated_plot = self.plot_result_text.toPlainText()
        if generated_plot and not generated_plot.startswith("生成失败"):
            # 设置到核心剧情输入框
            self.plot_text.setPlainText(generated_plot)
            # 关闭对话框
            dialog.accept()
    
    def _get_previous_chapters_content(self):
        """获取前面章节的内容作为上下文"""
        try:
            chapters_content = []
            
            # 检查novels目录是否存在
            if not os.path.exists("novels"):
                return ""
            
            # 获取所有章节文件
            chapter_files = []
            for file in os.listdir("novels"):
                if file.startswith("第") and file.endswith(".txt"):
                    # 提取章节号
                    try:
                        chapter_num = int(file.replace("第", "").replace("章.txt", ""))
                        chapter_files.append((chapter_num, file))
                    except ValueError:
                        continue
            
            # 按章节号排序
            chapter_files.sort(key=lambda x: x[0])
            
            # 只获取前3章的内容（避免提示词过长）
            for chapter_num, filename in chapter_files[:3]:
                file_path = os.path.join("novels", filename)
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            # 限制每章内容长度（避免提示词过长）
                            if len(content) > 500:
                                content = content[:500] + "..."
                            chapters_content.append(f"第{chapter_num}章：{content}")
            
            if chapters_content:
                return "\n".join(chapters_content)
            else:
                return ""
                
        except Exception as e:
            print(f"获取前面章节内容时出错: {e}")
            return ""

    def show_settings(self):
        """显示设置对话框"""
        print("显示设置对话框...")
        dialog = SettingsDialog(self)
        
        # 准备设置参数，兼容新旧格式
        settings_params = {
            "api_type": self.api_type,
            "api_url": self.api_url,
            "api_key": self.api_key,
            "model_name": self.model_name,
            "api_format": self.api_format,
            "custom_headers": self.custom_headers,
            "min_length": self.min_chapter_length,
            "max_length": self.max_chapter_length,
            "save_path": self.save_path,
            "file_behavior": self.file_behavior
        }
        
        print(f"准备设置参数: API={self.api_type}, Model={self.model_name}")
        dialog.set_settings(settings_params)
        
        if dialog.exec_() == QDialog.Accepted:
            print("用户确认设置")
            settings = dialog.get_settings()
            self.api_type = settings["api_type"]
            self.api_url = settings["api_url"]
            self.api_key = settings["api_key"]
            self.model_name = settings["model_name"]
            self.api_format = settings.get("api_format", None)
            self.custom_headers = settings.get("custom_headers", None)
            self.min_chapter_length = settings["min_length"]
            self.max_chapter_length = settings["max_length"]
            # 兼容旧版本设置，如果存在save_path则使用，否则使用新的路径设置
            if "save_path" in settings:
                self.save_path = settings["save_path"]
                # 自动生成大纲和章节路径
                self.outline_path = os.path.join(self.save_path, "outlines")
                self.chapter_path = os.path.join(self.save_path, "zhangjie")
            else:
                self.outline_path = settings["outline_path"]
                self.chapter_path = settings["chapter_path"]
                # 保持save_path向后兼容
                self.save_path = self.chapter_path
            self.file_behavior = settings["file_behavior"]
            
            print(f"已更新设置: API={self.api_type}, Model={self.model_name}")
            
            # 更新UI
            # 根据API类型更新模型选择下拉框
            if self.api_type == "SiliconFlow":
                self.model_combo.clear()
                # 加载默认模型和自定义SiliconFlow模型
                default_models = ["Qwen/Qwen3-8B", "Qwen/Qwen2.5-7B"]
                custom_models = self.load_custom_siliconflow_models()
                all_models = default_models + custom_models
                self.model_combo.addItems(all_models)
                print(f"已更新SiliconFlow模型列表: {all_models}")
            elif self.api_type == "Ollama":
                # 加载默认模型和自定义模型
                self.model_combo.clear()
                default_models = ["qwen:latest"]
                custom_models = self.load_custom_models()
                all_models = default_models + custom_models
                self.model_combo.addItems(all_models)
                print(f"已更新Ollama模型列表: {all_models}")
            elif self.api_type == "ModelScope":
                # 加载默认模型和自定义ModelScope模型
                self.model_combo.clear()
                default_models = ["Qwen/Qwen3-VL-30B-A3B-Instruct"]
                custom_models = self.load_custom_modelscope_models()
                all_models = default_models + custom_models
                self.model_combo.addItems(all_models)
                print(f"已更新ModelScope模型列表: {all_models}")
            else:
                # 其他API类型使用默认模型列表
                self.model_combo.clear()
                self.model_combo.addItems(["qwen:latest"])
                print("已更新默认模型列表")
            
            self.model_combo.setCurrentText(self.model_name)
            print(f"已设置当前模型: {self.model_name}")
            
            # 保存设置
            self.save_parameters()
            
            # 更新状态栏显示当前模型名称
            self.status_bar.showMessage(f"已切换到模型: {self.model_name}")
            self.status_bar.showMessage(f"设置已更新，章节字数范围: {self.min_chapter_length}-{self.max_chapter_length}字")
            self.set_app_status("正常")
            print("设置保存完成")
        else:
            print("用户取消设置")

    def load_novel_params(self):
        """从JSON文件加载上次保存的小说参数"""
        try:
            if os.path.exists("novel_params.json"):
                with open('novel_params.json', 'r', encoding='utf-8') as f:
                    params = json.load(f)
                    self.novel_title_input.setText(params.get('title', ''))
                    self.bg_text.setPlainText(params.get('background', ''))
                    
                    # 男主角参数
                    hero = params.get('hero', {})
                    self.hero_name.setText(hero.get('name', ''))
                    self.hero_age.setValue(hero.get('age', 25))
                    self.hero_job.setText(hero.get('job', ''))
                    self.hero_family.setText(hero.get('family', ''))
                    self.hero_desc.setPlainText(hero.get('desc', ''))
                    
                    # 女主角参数
                    heroine = params.get('heroine', {})
                    self.heroine_name.setText(heroine.get('name', ''))
                    self.heroine_age.setValue(heroine.get('age', 23))
                    self.heroine_job.setText(heroine.get('job', ''))
                    self.heroine_family.setText(heroine.get('family', ''))
                    self.heroine_desc.setPlainText(heroine.get('desc', ''))
                    
                    # 其他参数
                    self.rel_text.setPlainText(params.get('relationship', ''))
                    self.plot_text.setPlainText(params.get('plot', ''))
                    self.pov_combo.setCurrentText(params.get('pov', '第一人称'))
                    self.lang_combo.setCurrentText(params.get('language', '现代白话文'))
                    self.rhythm_combo.setCurrentText(params.get('rhythm', '平铺直叙'))
                    self.word_count.setText(str(params.get('word_count', 300000)))
                    
                    # 加载章节号 - 确保UI元素被正确更新
                    chapter_number = params.get('chapter_number', 1)
                    self.chapter_number.setValue(chapter_number)
                    print(f"[调试] 已加载章节号: {chapter_number}")
                    
                    # 更新提示词
                    self.update_prompt()
                    
                    # 加载最后一章的内容（仅在文件存在时加载）
                    chapter_num = self.chapter_number.value()
                    file_name = f"第{chapter_num}章.txt"
                    file_path = os.path.join(self.save_path, file_name)
                    
                    # 只有在文件存在时才加载内容
                    if os.path.exists(file_path):
                        self.load_chapter_content()
                        
                    print(f"[调试] 小说参数加载完成，当前章节号: {self.chapter_number.value()}")
        except Exception as e:
            print(f"加载小说参数失败: {e}")

    def save_all_settings(self):
        """自动保存所有设置和输入内容"""
        try:
            # 保存应用程序参数
            self.save_parameters()
            
            # 保存小说参数
            self.save_novel_params()
            
            # 保存大纲内容（如果有）
            outline_content = self.outline_text.toPlainText()
            if outline_content:
                self.save_outline(outline_content)
            
            # 保存当前章节内容（如果有）
            chapter_content = self.chapter_text.toPlainText()
            if chapter_content:
                self.save_current_content()
                
            print("所有设置和内容已自动保存")
            self.status_bar.showMessage("所有设置和内容已自动保存")
        except Exception as e:
            print(f"自动保存设置失败: {e}")
            self.status_bar.showMessage(f"自动保存失败: {str(e)}")

    def auto_save_novel_params(self):
        """自动保存小说参数到JSON文件"""
        try:
            # 使用已有的save_novel_params方法保存参数
            self.save_novel_params()
            print("小说参数已自动保存")
        except Exception as e:
            print(f"自动保存小说参数失败: {e}")

    def save_novel_params(self):
        """保存小说参数到JSON文件"""
        novel_params = {
            "title": self.novel_title_input.text(),
            "background": self.bg_text.toPlainText(),
            "hero": {
                "name": self.hero_name.text(),
                "age": self.hero_age.value(),
                "job": self.hero_job.text(),
                "family": self.hero_family.text(),
                "desc": self.hero_desc.toPlainText()
            },
            "heroine": {
                "name": self.heroine_name.text(),
                "age": self.heroine_age.value(),
                "job": self.heroine_job.text(),
                "family": self.heroine_family.text(),
                "desc": self.heroine_desc.toPlainText()
            },
            "relationship": self.rel_text.toPlainText(),
            "plot": self.plot_text.toPlainText(),
            "pov": self.pov_combo.currentText(),
            "language": self.lang_combo.currentText(),
            "rhythm": self.rhythm_combo.currentText(),
            "word_count": int(self.word_count.text()) if self.word_count.text().isdigit() else 300000,
            "chapter_number": self.chapter_number.value()
        }
        try:
            with open('novel_params.json', 'w', encoding='utf-8') as f:
                json.dump(novel_params, f, ensure_ascii=False, indent=4)
            print("小说参数已自动保存")
        except Exception as e:
            print(f"保存小说参数失败: {e}")

    def show_about(self):
        """显示关于对话框"""
        about_text = """
        <h2>小说生成助手 - 青春版 v2.0</h2>
        <p><b>版本:</b> v2.0</p>
        <p><b>发布日期:</b> 2025年1月</p>
        <p><b>开发团队:</b> DeepSeek AI</p>
        <p><b>技术支持:</b> 基于Ollama API和PyQt5开发</p>
        <p><b>功能特点:</b> 支持多种大语言模型，帮助创作者快速生成小说内容</p>
        <p><b>适用系统:</b> Windows 10/11, macOS, Linux</p>
        <p><b>更新内容:</b> 优化软件性能，解决卡顿问题</p>
        <p><b>下载地址:</b></p>
        <ul>
            <li>Gitee仓库：<a href="https://gitee.com/du_honggang/activation-codes/blob/master/xiaoshuoxiezuoai">https://gitee.com/du_honggang/activation-codes/blob/master/xiaoshuoxiezuoai</a></li>
            <li>百度网盘：<a href="https://pan.baidu.com/s/1T98ndzqQSUQQkxdV8SN1VQ?pwd=ydcu">https://pan.baidu.com/s/1T98ndzqQSUQQkxdV8SN1VQ?pwd=ydcu</a></li>
        </ul>
        <p><b>联系方式:</b></p>
        <ul>
            <li>QQ交流群：1035396790</li>
            <li>邮箱：286059063@qq.com</li>
            <li>工作时间：周一至周五 9:00-18:00</li>
        </ul>
        <p><b>特别感谢:</b> 感谢所有测试用户的宝贵反馈和建议</p>
        <p>© 2025 DeepSeek AI. 保留所有权利。</p>
        """
        QMessageBox.about(self, "关于", about_text)
        
    def show_usage(self):
        """显示使用方法对话框"""
        usage_text = """
        <h2>软件使用方法</h2>
        <h3>一、基础设置</h3>
        <ol>
            <li><b>API设置</b>：在"设置"菜单中配置API类型、URL和密钥</li>
            <li><b>模型选择</b>：从下拉菜单中选择适合的AI模型</li>
            <li><b>保存路径</b>：设置生成内容的保存位置</li>
            <li><b>推荐服务</b>：可用硅基流动云服务（免费api） <a href="https://cloud.siliconflow.cn/i/0Kxk74sG">https://cloud.siliconflow.cn/i/0Kxk74sG</a></li>
        </ol>
        
        <h3>二、小说创作流程</h3>
        <ol>
            <li><b>填写基本信息</b>：
                <ul>
                    <li>小说标题：输入您想要创作的小说名称</li>
                    <li>小说背景：描述世界观、时代背景、主要场景</li>
                    <li>人物设定：填写主角和配角的基本信息</li>
                    <li>角色关系：描述人物之间的关系</li>
                    <li>核心剧情：规划故事的主要情节</li>
                </ul>
            </li>
            <li><b>选择写作风格</b>：
                <ul>
                    <li>题材类型：选择小说的题材</li>
                    <li>人称视角：选择叙事视角</li>
                    <li>语言风格：选择语言表达风格</li>
                    <li>叙事节奏：选择故事节奏</li>
                    <li>预计字数：设置小说总字数</li>
                </ul>
            </li>
            <li><b>生成大纲</b>：
                <ul>
                    <li>点击"生成大纲"按钮</li>
                    <li>系统会根据您填写的信息生成小说大纲</li>
                    <li>可以编辑和调整大纲内容</li>
                </ul>
            </li>
            <li><b>生成章节</b>：
                <ul>
                    <li>选择要生成的章节号</li>
                    <li>可选择是否读取上一章内容作为参考</li>
                    <li>点击"生成章节"按钮</li>
                    <li>系统会根据大纲生成章节内容</li>
                </ul>
            </li>
            <li><b>批量生成</b>：
                <ul>
                    <li>设置起始章节和结束章节</li>
                    <li>点击"批量生成章节"按钮</li>
                    <li>系统会自动生成多个章节</li>
                </ul>
            </li>
        </ol>
        
        <h3>三、高级功能</h3>
        <ol>
            <li><b>自定义提示词</b>：
                <ul>
                    <li>在提示词预览区域可以查看和编辑提示词</li>
                    <li>自定义提示词可以获得更符合预期的生成结果</li>
                </ul>
            </li>
            <li><b>章节管理</b>：
                <ul>
                    <li>使用上一章/下一章按钮切换章节</li>
                    <li>可以加载已保存的章节内容进行编辑</li>
                </ul>
            </li>
            <li><b>设置保存</b>：
                <ul>
                    <li>软件会自动保存您的设置</li>
                    <li>下次启动时会自动加载上次的设置</li>
                </ul>
            </li>
        </ol>
        
        <h3>四、常见问题</h3>
        <ol>
            <li><b>生成内容质量不佳</b>：
                <ul>
                    <li>尝试调整提示词内容</li>
                    <li>更换更适合的AI模型</li>
                    <li>完善人物设定和剧情规划</li>
                </ul>
            </li>
            <li><b>章节衔接不自然</b>：
                <ul>
                    <li>生成新章节时勾选"读取上一章内容"选项</li>
                    <li>在提示词中强调章节间的连贯性</li>
                </ul>
            </li>
            <li><b>API调用失败</b>：
                <ul>
                    <li>检查API设置是否正确</li>
                    <li>确认网络连接正常</li>
                    <li>验证API密钥是否有效</li>
                </ul>
            </li>
            <li><b>软件启动缓慢</b>：
                <ul>
                    <li>检查网络连接是否正常</li>
                    <li>关闭不必要的后台程序</li>
                    <li>确保系统资源充足</li>
                </ul>
            </li>
        </ol>
        """
        
        # 创建自定义对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("使用方法")
        dialog.setMinimumSize(600, 500)  # 设置最小尺寸
        dialog.resize(700, 600)  # 设置初始大小
        
        # 创建主布局
        layout = QVBoxLayout(dialog)
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # 创建内容标签
        content_label = QLabel(usage_text)
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.RichText)
        content_label.setOpenExternalLinks(True)  # 允许打开外部链接
        content_label.setContentsMargins(20, 20, 20, 20)  # 设置内容边距
        
        # 将内容标签设置为滚动区域的部件
        scroll_area.setWidget(content_label)
        
        # 将滚动区域添加到布局
        layout.addWidget(scroll_area)
        
        # 创建按钮框
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        
        # 设置按钮样式
        button_box.setStyleSheet("""
            QDialogButtonBox QPushButton {
                min-width: 80px;
                min-height: 32px;
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                border: none;
                background-color: #4F46E5;
                color: white;
            }
            QDialogButtonBox QPushButton:hover {
                background-color: #4338CA;
            }
        """)
        
        layout.addWidget(button_box)
        
        # 显示对话框
        dialog.exec_()
    
    def setup_help_page(self):
        """设置帮助页面"""
        layout = QVBoxLayout(self.help_page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("帮助中心")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #1F2937;
                margin-bottom: 10px;
            }
        """)
        layout.addWidget(title_label)
        
        # 创建选项卡
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                background-color: white;
            }
            QTabWidget::tab-bar {
                alignment: center;
            }
            QTabBar::tab {
                background-color: #F9FAFB;
                border: 1px solid #E5E7EB;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #6366F1;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #F3F4F6;
            }
        """)
        
        # 使用方法选项卡
        usage_tab = QWidget()
        usage_layout = QVBoxLayout(usage_tab)
        usage_layout.setContentsMargins(10, 10, 10, 10)
        
        usage_scroll = QScrollArea()
        usage_scroll.setWidgetResizable(True)
        usage_scroll.setStyleSheet("border: none;")
        
        usage_content = QWidget()
        usage_content_layout = QVBoxLayout(usage_content)
        usage_content_layout.setContentsMargins(10, 10, 10, 10)
        
        usage_text = """
        <h2>软件使用方法</h2>
        <h3>一、基础设置</h3>
        <ol>
            <li><b>API设置</b>：在"设置"菜单中配置API类型、URL和密钥</li>
            <li><b>模型选择</b>：从下拉菜单中选择适合的AI模型</li>
            <li><b>保存路径</b>：设置生成内容的保存位置</li>
            <li><b>推荐服务</b>：可用硅基流动云服务（免费api） <a href="https://cloud.siliconflow.cn/i/0Kxk74sG">https://cloud.siliconflow.cn/i/0Kxk74sG</a></li>
        </ol>
        
        <h3>二、小说创作流程</h3>
        <ol>
            <li><b>填写基本信息</b>：
                <ul>
                    <li>小说标题：输入您想要创作的小说名称</li>
                    <li>小说背景：描述世界观、时代背景、主要场景</li>
                    <li>人物设定：填写主角和配角的基本信息</li>
                    <li>角色关系：描述人物之间的关系</li>
                    <li>核心剧情：规划故事的主要情节</li>
                </ul>
            </li>
            <li><b>选择写作风格</b>：
                <ul>
                    <li>题材类型：选择小说的题材</li>
                    <li>人称视角：选择叙事视角</li>
                    <li>语言风格：选择语言表达风格</li>
                    <li>叙事节奏：选择故事节奏</li>
                    <li>预计字数：设置小说总字数</li>
                </ul>
            </li>
            <li><b>生成大纲</b>：
                <ul>
                    <li>点击"生成大纲"按钮</li>
                    <li>系统会根据您填写的信息生成小说大纲</li>
                    <li>可以编辑和调整大纲内容</li>
                </ul>
            </li>
            <li><b>生成章节</b>：
                <ul>
                    <li>选择要生成的章节号</li>
                    <li>可选择是否读取上一章内容作为参考</li>
                    <li>点击"生成章节"按钮</li>
                    <li>系统会根据大纲生成章节内容</li>
                </ul>
            </li>
            <li><b>批量生成</b>：
                <ul>
                    <li>设置起始章节和结束章节</li>
                    <li>点击"批量生成章节"按钮</li>
                    <li>系统会自动生成多个章节</li>
                </ul>
            </li>
        </ol>
        
        <h3>三、高级功能</h3>
        <ol>
            <li><b>自定义提示词</b>：
                <ul>
                    <li>在提示词预览区域可以查看和编辑提示词</li>
                    <li>自定义提示词可以获得更符合预期的生成结果</li>
                </ul>
            </li>
            <li><b>章节管理</b>：
                <ul>
                    <li>使用上一章/下一章按钮切换章节</li>
                    <li>可以加载已保存的章节内容进行编辑</li>
                </ul>
            </li>
            <li><b>设置保存</b>：
                <ul>
                    <li>软件会自动保存您的设置</li>
                    <li>下次启动时会自动加载上次的设置</li>
                </ul>
            </li>
        </ol>
        
        <h3>四、常见问题</h3>
        <ol>
            <li><b>生成内容质量不佳</b>：
                <ul>
                    <li>尝试调整提示词内容</li>
                    <li>更换更适合的AI模型</li>
                    <li>完善人物设定和剧情规划</li>
                </ul>
            </li>
            <li><b>章节衔接不自然</b>：
                <ul>
                    <li>生成新章节时勾选"读取上一章内容"选项</li>
                    <li>在提示词中强调章节间的连贯性</li>
                </ul>
            </li>
            <li><b>API调用失败</b>：
                <ul>
                    <li>检查API设置是否正确</li>
                    <li>确认网络连接正常</li>
                    <li>验证API密钥是否有效</li>
                </ul>
            </li>
            <li><b>软件启动缓慢</b>：
                <ul>
                    <li>检查网络连接是否正常</li>
                    <li>关闭不必要的后台程序</li>
                    <li>确保系统资源充足</li>
                </ul>
            </li>
        </ol>
        """
        
        usage_label = QLabel(usage_text)
        usage_label.setWordWrap(True)
        usage_label.setTextFormat(Qt.RichText)
        usage_label.setOpenExternalLinks(True)
        usage_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                line-height: 1.6;
                color: #4B5563;
            }
        """)
        usage_content_layout.addWidget(usage_label)
        usage_scroll.setWidget(usage_content)
        usage_layout.addWidget(usage_scroll)
        
        # 关于选项卡
        about_tab = QWidget()
        about_layout = QVBoxLayout(about_tab)
        about_layout.setContentsMargins(10, 10, 10, 10)
        
        about_text = """
        <h2>小说生成助手 - 青春版</h2>
        <p><b>版本:</b> v2.0</p>
        <p><b>开发团队:</b> DeepSeek AI</p>
        <p><b>技术支持:</b> 基于Ollama API和PyQt5开发</p>
        <p><b>功能特点:</b> 支持多种大语言模型，帮助创作者快速生成小说内容</p>
        <p><b>适用系统:</b> Windows 10/11, macOS, Linux</p>
        <p><b>联系方式:</b></p>
        <ul>
            <li>QQ交流群：1035396790</li>
            <li>邮箱：286059063@qq.com</li>
            <li>工作时间：周一至周五 9:00-18:00</li>
        </ul>
        <p><b>特别感谢:</b> 感谢所有测试用户的宝贵反馈和建议</p>
        <p>© 2025 DeepSeek AI. 保留所有权利。</p>
        """
        
        about_label = QLabel(about_text)
        about_label.setWordWrap(True)
        about_label.setTextFormat(Qt.RichText)
        about_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                line-height: 1.6;
                color: #4B5563;
            }
        """)
        about_layout.addWidget(about_label)
        
        # 添加选项卡
        tab_widget.addTab(usage_tab, "使用方法")
        tab_widget.addTab(about_tab, "关于")
        
        layout.addWidget(tab_widget)
    
    def setup_settings_page(self):
        """设置设置页面 - 直接使用SettingsDialog的功能"""
        layout = QVBoxLayout(self.settings_page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("软件API设置")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #1F2937;
                margin-bottom: 10px;
            }
        """)
        layout.addWidget(title_label)
        
        # 说明文本
        info_label = QLabel("点击下方按钮打开完整设置对话框，该对话框与底部设置按钮功能相同")
        info_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #6B7280;
                margin-bottom: 20px;
                padding: 10px;
                background-color: #F9FAFB;
                border-radius: 6px;
                border: 1px solid #E5E7EB;
            }
        """)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 打开设置对话框按钮
        open_settings_button = QPushButton("打开设置对话框")
        open_settings_button.setStyleSheet("""
            QPushButton {
                padding: 15px 30px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                background-color: #4F46E5;
                color: white;
                border: none;
                min-height: 50px;
            }
            QPushButton:hover {
                background-color: #4338CA;
            }
            QPushButton:pressed {
                background-color: #3730A3;
            }
        """)
        open_settings_button.clicked.connect(self.show_settings)
        layout.addWidget(open_settings_button)
        
        # 添加弹性空间
        layout.addStretch()
    
    def setup_update_page(self):
        """设置更新页面"""
        layout = QVBoxLayout(self.update_page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("软件更新")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #1F2937;
                margin-bottom: 10px;
            }
        """)
        layout.addWidget(title_label)
        
        # 当前版本信息
        version_group = QGroupBox("当前版本信息")
        version_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        version_layout = QVBoxLayout(version_group)
        
        version_info = """
        <p><b>版本号：</b>v2.0</p>
        <p><b>发布日期：</b>2025年1月</p>
        <p><b>更新内容：</b></p>
        <ul>
            <li>优化软件性能，解决卡顿问题</li>
            <li>改进用户界面设计</li>
            <li>增强章节生成稳定性</li>
            <li>修复已知bug</li>
        </ul>
        <p><b>下载地址：</b></p>
        <p>• Gitee仓库：<a href="***">***</a></p>
        <p>• 百度网盘：<a href="***">***</a></p>
        """
        
        version_label = QLabel(version_info)
        version_label.setWordWrap(True)
        version_label.setTextFormat(Qt.RichText)
        version_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                line-height: 1.6;
                color: #4B5563;
            }
        """)
        version_layout.addWidget(version_label)
        layout.addWidget(version_group)
        
        # 检查更新按钮
        check_update_button = QPushButton("检查更新")
        check_update_button.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
        """)
        check_update_button.clicked.connect(self.check_for_updates)
        layout.addWidget(check_update_button)
        
        # 更新日志
        changelog_group = QGroupBox("更新日志")
        changelog_group.setStyleSheet(version_group.styleSheet())
        changelog_layout = QVBoxLayout(changelog_group)
        
        changelog_text = """
        <h3>v2.0 (2025年1月)</h3>
        <ul>
            <li>优化软件性能，解决卡顿问题</li>
            <li>改进用户界面设计</li>
            <li>增强章节生成稳定性</li>
            <li>修复已知bug</li>
        </ul>
        
        <h3>v1.0.0 (2024年12月)</h3>
        <ul>
            <li>初始版本发布</li>
            <li>基础小说生成功能</li>
            <li>用户友好的界面设计</li>
        </ul>
        """
        
        changelog_label = QLabel(changelog_text)
        changelog_label.setWordWrap(True)
        changelog_label.setTextFormat(Qt.RichText)
        changelog_label.setStyleSheet(version_label.styleSheet())
        changelog_layout.addWidget(changelog_label)
        layout.addWidget(changelog_group)
        
        layout.addStretch()
    
    def load_current_settings(self):
        """加载当前设置到设置页面（已弃用）"""
        pass

    def apply_settings(self):
        """应用设置（已弃用）"""
        pass

    def test_api_connection(self):
        """测试API连接（已弃用）"""
        pass

    def browse_save_path(self):
        """浏览保存路径（已弃用）"""
        pass

    def save_app_settings(self):
        """保存应用程序设置"""
        QMessageBox.information(self, "设置已保存", "应用程序设置已成功保存！")
    
    def check_for_updates(self):
        """检查软件更新"""
        # 当前软件版本
        current_version = "2.0"
        
        try:
            # 从Gitee仓库获取最新版本信息
            gitee_version_info = self.get_version_from_gitee()
            
            if gitee_version_info:
                latest_version = gitee_version_info["version"]
                update_description = gitee_version_info.get("update_description", "优化软件性能，解决卡顿问题")
                baidu_download_url = gitee_version_info["baidu_url"]
                
                # 比较版本号
                def compare_versions(v1, v2):
                    """比较两个版本号，返回1表示v1>v2，-1表示v1<v2，0表示相等"""
                    # 清理版本号，只保留数字和点
                    import re
                    v1_clean = re.sub(r'[^\d.]', '', v1)
                    v2_clean = re.sub(r'[^\d.]', '', v2)
                    
                    # 如果清理后为空，使用默认值
                    if not v1_clean:
                        v1_clean = "2.0"
                    if not v2_clean:
                        v2_clean = "2.0"
                    
                    try:
                        v1_parts = [int(x) for x in v1_clean.split('.') if x]
                        v2_parts = [int(x) for x in v2_clean.split('.') if x]
                        
                        # 补齐版本号长度
                        max_len = max(len(v1_parts), len(v2_parts))
                        v1_parts.extend([0] * (max_len - len(v1_parts)))
                        v2_parts.extend([0] * (max_len - len(v2_parts)))
                        
                        for i in range(max_len):
                            if v1_parts[i] > v2_parts[i]:
                                return 1
                            elif v1_parts[i] < v2_parts[i]:
                                return -1
                        return 0
                    except:
                        # 如果转换失败，默认认为版本相同
                        return 0
                
                comparison = compare_versions(current_version, latest_version)
                
                if comparison >= 0:
                    # 当前版本高于或等于Gitee版本，显示最新版本
                    QMessageBox.information(self, "检查更新", 
                        f"当前版本：v{current_version}\n"
                        f"Gitee最新版本：v{latest_version}\n\n"
                        f"更新内容：\n{update_description}\n\n"
                        f"✓ 当前已是最新版本！")
                else:
                    # 当前版本低于Gitee版本，提示更新并自动跳转
                    reply = QMessageBox.question(self, "发现新版本", 
                        f"当前版本：v{current_version}\n"
                        f"最新版本：v{latest_version}\n\n"
                        f"更新内容：\n{update_description}\n\n"
                        f"发现新版本可用，是否立即更新？",
                        QMessageBox.Yes | QMessageBox.No)
                    
                    if reply == QMessageBox.Yes:
                        # 自动打开百度网盘下载链接
                        import webbrowser
                        webbrowser.open(baidu_download_url)
                        QMessageBox.information(self, "更新提示", "浏览器已打开下载页面，请下载最新版本安装包。")
            else:
                QMessageBox.warning(self, "检查更新", "无法连接到Gitee仓库获取版本信息，请检查网络连接。")
                
        except Exception as e:
            QMessageBox.warning(self, "检查更新", f"检查更新时出现错误：{str(e)}")
    
    def get_version_from_gitee(self):
        """从Gitee仓库获取版本信息（真实实现）"""
        import requests
        import json
        import re
        
        try:
            # Gitee仓库信息
            owner = "du_honggang"
            repo = "activation-codes"
            file_path = "xiaoshuoxiezuoai"  # 版本信息文件路径
            
            # Gitee API获取文件内容
            api_url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/contents/{file_path}"
            
            # 发送GET请求（不需要token也可以获取公开仓库的文件内容）
            response = requests.get(api_url, timeout=10)
            
            if response.status_code == 200:
                file_data = response.json()
                
                # 获取文件内容（base64编码）
                content_base64 = file_data.get("content", "")
                
                if content_base64:
                    # 解码base64内容
                    import base64
                    content = base64.b64decode(content_base64).decode('utf-8')
                    
                    print(f"从Gitee获取的内容:\n{content}")  # 调试信息
                    
                    # 解析版本信息文件内容
                    # 读取所有行内容
                    lines = content.strip().split('\n')
                    
                    # 提取版本号（从第一行）
                    first_line = lines[0].strip() if len(lines) > 0 else ""
                    
                    # 使用正则表达式提取版本号
                    version_pattern = r'版本号[：:]\s*([\d.]+)'
                    version_match = re.search(version_pattern, first_line)
                    if version_match:
                        version = version_match.group(1)
                    else:
                        # 如果没有找到版本号，尝试从第一行提取数字版本
                        version_matches = re.findall(r'[\d.]+', first_line)
                        if version_matches:
                            version = version_matches[0]
                        else:
                            version = "2.0"  # 默认版本
                    
                    # 提取更新说明（从第二行）
                    update_description = ""
                    if len(lines) > 1:
                        second_line = lines[1].strip()
                        # 如果第二行包含版本号信息，跳过
                        if not re.search(version_pattern, second_line):
                            update_description = second_line
                    
                    # 如果第二行没有更新说明，尝试从其他行查找
                    if not update_description:
                        for line in lines[1:]:  # 从第二行开始查找
                            line_stripped = line.strip()
                            if line_stripped and not re.search(version_pattern, line_stripped):
                                update_description = line_stripped
                                break
                    
                    # 查找百度网盘链接
                    url_pattern = r'https://pan\.baidu\.com/s/[\w\d?=&-]+'
                    url_match = re.search(url_pattern, content)
                    if url_match:
                        baidu_url = url_match.group(0)
                    else:
                        # 如果没有找到链接，使用默认链接
                        baidu_url = "***"
                    
                    print(f"解析结果 - 版本号: {version}, 更新说明: {update_description}, 链接: {baidu_url}")  # 调试信息
                    
                    return {
                        "version": version,
                        "update_description": update_description,
                        "baidu_url": baidu_url
                    }
                else:
                    # 无法获取文件内容，使用默认值
                    print("无法获取文件内容")
                    return self.get_default_version_info()
            else:
                # API请求失败，使用默认值
                print(f"API请求失败，状态码: {response.status_code}")
                return self.get_default_version_info()
                
        except Exception as e:
            # 出现异常，使用默认值
            print(f"获取Gitee版本信息失败: {e}")
            return self.get_default_version_info()
    
    def get_default_version_info(self):
        """获取默认版本信息（当无法从Gitee获取时使用）"""
        return {
            "version": "2.0",  # 默认版本号
            "baidu_url": "***"  # 默认下载链接
        }
    
    def closeEvent(self, event):
        """窗口关闭事件处理，确保停止自动保存线程并保存所有设置"""
        print("[调试] 应用程序关闭事件触发")
        # 保存所有设置
        print("[调试] 正在保存所有设置...")
        self.save_all_settings()
        
        # 停止自动保存线程
        if hasattr(self, 'auto_save_thread') and self.auto_save_thread is not None:
            print("[调试] 正在停止自动保存线程")
            self.stop_auto_save()
        print("[调试] 应用程序关闭事件处理完成")
        # 调用父类的closeEvent
        super().closeEvent(event)

# ==================== 主程序入口 ====================

if __name__ == "__main__":
    print("程序开始启动...")
    app = QApplication(sys.argv)
    print("QApplication创建成功")
    app.setStyle("Fusion")
    print("设置应用样式为Fusion")
    
    # 改进的字体设置（支持多平台）
    font_families = ["SimHei", "WenQuanYi Micro Hei", "Heiti TC", 
                    "Microsoft YaHei", "SimSun", "Arial Unicode MS"]
    font = QFont()
    for family in font_families:
        if family in QFontDatabase().families():
            font.setFamily(family)
            break
    font.setPointSize(9)  # 更小的字体大小
    app.setFont(font)
    print("字体设置完成")
    
    # 直接创建并显示小说生成器窗口
    print("创建小说生成器窗口...")
    novel_app = CompactNovelGeneratorApp()  # 使用紧凑版
    print("小说生成器窗口创建成功")
    novel_app.show()
    print("小说生成器窗口已显示")
    
    # 添加退出前保存参数的逻辑
    def save_on_exit():
        print("程序退出前保存参数...")
        if novel_app:
            novel_app.save_parameters()
            novel_app.save_novel_params()
    
    # 连接退出事件
    print("连接退出事件...")
    app.aboutToQuit.connect(save_on_exit)
    print("退出事件连接完成")
    
    print("启动应用程序主循环...")
    sys.exit(app.exec_())