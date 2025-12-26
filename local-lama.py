# f:\code\腾讯元器智能体get代理\local-lama.py - 真正可用的Ollama版本
import requests
import json
import time
import logging
from flask import Flask, render_template_string, Response, request
from threading import Thread
from queue import Queue

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 全局变量
response_queue = Queue()
full_response = ""
is_receiving = False

def update_response(content):
    global full_response
    full_response += content
    response_queue.put(content)
    logger.info(f"添加响应: {content[:50]}...")

# Ollama API流式响应函数 - 修复版本
def stream_response_from_api(user_text=None):
    global is_receiving
    is_receiving = True
    logger.info("开始接收Ollama API响应...")
    update_response("开始接收Ollama API响应...<br>")
    
    # Ollama API配置
    server_ip = '172.27.22.133'  # 修改为你的Ollama服务器IP地址
    # server_ip = 'http://127.0.0.1
    url = f'http://{server_ip}:11434/api/generate'
    
    # 默认文本
    default_text = "Hello, how are you?"
    mytext = user_text if user_text else default_text
    
    # 请求数据 - 使用你的模型
    data = {
        "model": "english-expert:latest",  # 你可以修改为其他模型名称
        "prompt": mytext,
        "stream": True
    }
    
    logger.info(f"发送请求到Ollama，模型: {data['model']}, 文本: {mytext[:50]}...")
    update_response(f"使用模型: {data['model']}<br>")
    
    try:
        # 首先检查Ollama服务是否可用
        try:
            check_url = f'http://{server_ip}:11434/api/tags'
            check_response = requests.get(check_url, timeout=5)
            if check_response.status_code == 200:
                models = check_response.json().get('models', [])
                model_names = [model.get('name', '') for model in models]
                logger.info(f"可用模型: {model_names}")
                
                # 检查指定模型是否存在
                if data['model'] not in model_names:
                    available_models = ', '.join(model_names)
                    error_msg = f"模型 '{data['model']}' 不存在。可用模型: {available_models}"
                    logger.error(error_msg)
                    update_response(f"错误: {error_msg}<br>")
                    is_receiving = False
                    return
            else:
                logger.warning(f"无法获取模型列表，状态码: {check_response.status_code}")
        except Exception as e:
            logger.warning(f"检查Ollama服务时出错: {e}")
            update_response(f"警告: 无法检查Ollama服务状态: {e}<br>")
        
        # 发送流式请求
        with requests.post(url, json=data, stream=True, timeout=120) as response:
            response.raise_for_status()
            logger.info(f"Ollama响应状态码: {response.status_code}")
            update_response("正在接收流式响应...<br>")
            
            # 处理流式响应
            chunk_count = 0
            for line in response.iter_lines():
                if line:
                    chunk_count += 1
                    
                    try:
                        chunk_str = line.decode('utf-8').strip()
                        logger.debug(f"收到chunk {chunk_count}: {chunk_str[:100]}...")
                        
                        # 解析JSON响应
                        chunk_data = json.loads(chunk_str)
                        
                        # 提取响应内容
                        if 'response' in chunk_data:
                            content = chunk_data['response']
                            if content:
                                # 处理换行符
                                content_display = content.replace('\n', '<br>')
                                update_response(content_display)
                        
                        # 检查是否完成
                        if chunk_data.get('done', False):
                            logger.info("响应生成完成")
                            update_response("<br>响应生成完成<br>")
                            break
                            
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON解析错误: {e}, 原始数据: {chunk_str[:100]}...")
                        # 如果不是有效的JSON，可能是原始文本
                        update_response(f"[原始数据: {chunk_str[:100]}...]<br>")
                    except Exception as e:
                        logger.error(f"处理chunk时出错: {e}")
                        update_response(f"[处理错误: {e}]<br>")
            
            if chunk_count == 0:
                logger.warning("未收到任何有效响应数据")
                update_response("<br>警告: 未收到任何有效响应数据<br>")
            else:
                update_response(f"<br>流式响应接收完成，共处理 {chunk_count} 个数据块<br>")
                
    except requests.exceptions.Timeout as e:
        error_msg = f"请求超时 (120秒): {e}"
        logger.error(error_msg)
        update_response(f"<br>错误: {error_msg}<br>")
        
    except requests.exceptions.ConnectionError as e:
        error_msg = f"连接错误: 无法连接到Ollama服务 (127.0.0.1:11434)。请确保Ollama正在运行: {e}"
        logger.error(error_msg)
        update_response(f"<br>错误: {error_msg}<br>")
        
    except requests.exceptions.RequestException as e:
        error_msg = f"请求出错: {e}"
        logger.error(error_msg)
        update_response(f"<br>错误: {error_msg}<br>")
        
    except Exception as e:
        error_msg = f"发生错误: {e}"
        logger.error(error_msg, exc_info=True)
        update_response(f"<br>错误: {error_msg}<br>")
    finally:
        is_receiving = False
        logger.info("Ollama流式响应处理结束")

# 生成事件流 - 修复版本
def event_stream():
    try:
        while True:
            if not response_queue.empty():
                content = response_queue.get(timeout=0.1)
                yield f"data: {content}\n\n"
            elif not is_receiving:
                # 确保队列清空后再结束
                if response_queue.empty():
                    break
            else:
                time.sleep(0.1)
    except:
        pass

# 主页面路由 - 修复版本
@app.route('/')
def index():
    user_text = request.args.get('text')
    
    # 检查是否有用户文本
    if user_text:
        if not is_receiving:
            logger.info(f"收到用户请求: {user_text[:50]}...")
            thread = Thread(target=stream_response_from_api, args=(user_text,))
            thread.start()
        else:
            logger.warning("正在处理其他请求，忽略新请求")
    
    # 读取HTML模板
    try:
        with open('ollama_web.html', 'r', encoding='utf-8') as f:
            html_template = f.read()
        return render_template_string(html_template)
    except Exception as e:
        logger.error(f"读取HTML模板失败: {e}")
        return f"<h1>Ollama Web界面加载失败: {e}</h1>"

# 流式响应路由
@app.route('/stream')
def stream():
    return Response(event_stream(), mimetype="text/event-stream")

# 状态检查路由
@app.route('/status')
def status():
    return {
        'is_receiving': is_receiving,
        'response_length': len(full_response)
    }

# 输入界面路由
@app.route('/input')
def input_form():
    try:
        html_content = '''
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Ollama 输入界面</title>
            <style>
                body {
                    font-family: 'Microsoft YaHei', Arial, sans-serif;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    line-height: 1.6;
                }
                h1 {
                    color: #333;
                    text-align: center;
                }
                #input-container {
                    margin-bottom: 20px;
                }
                #user-input {
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #ddd;
                    border-radius: 8px;
                    font-size: 16px;
                    margin-bottom: 15px;
                    resize: vertical;
                    min-height: 100px;
                    font-family: inherit;
                    box-sizing: border-box;
                }
                #user-input:focus {
                    border-color: #28a745;
                    outline: none;
                    box-shadow: 0 0 5px rgba(40, 167, 69, 0.3);
                }
                #send-button {
                    padding: 12px 24px;
                    background-color: #28a745;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    cursor: pointer;
                    font-size: 16px;
                    font-weight: bold;
                    transition: background-color 0.3s;
                }
                #send-button:hover {
                    background-color: #218838;
                }
                #send-button:active {
                    transform: translateY(1px);
                }
                .info {
                    margin-top: 20px;
                    padding: 15px;
                    background-color: #f8f9fa;
                    border-left: 4px solid #28a745;
                    border-radius: 4px;
                }
                .shortcut {
                    color: #666;
                    font-size: 14px;
                    margin-top: 10px;
                }
                .model-info {
                    background-color: #e3f2fd;
                    border-left: 4px solid #2196f3;
                    padding: 10px;
                    margin-bottom: 15px;
                    border-radius: 4px;
                }
            </style>
        </head>
        <body>
            <h1>Ollama 智能对话</h1>
            
            <div class="model-info">
                <strong>当前模型:</strong> llama2:latest<br>
                <strong>Ollama服务:</strong> 127.0.0.1:11434
            </div>
            
            <div id="input-container">
                <textarea id="user-input" placeholder="请输入您的问题或指令..." rows="4"></textarea>
                <button id="send-button" onclick="sendToMain()">发送请求</button>
                <div class="shortcut">💡 快捷键：Ctrl + Enter</div>
            </div>
            
            <div class="info">
                <strong>使用说明：</strong><br>
                • 在文本框中输入您的问题<br>
                • 点击"发送请求"按钮或按 Ctrl+Enter<br>
                • 系统将跳转到响应页面显示流式结果<br>
                • 确保Ollama服务正在运行: <code>ollama serve</code>
            </div>
            
            <script>
                function sendToMain() {
                    const userText = document.getElementById('user-input').value.trim();
                    
                    if (userText === '') {
                        alert('请输入内容！');
                        return;
                    }
                    
                    // 编码文本并跳转到主页面
                    const encodedText = encodeURIComponent(userText);
                    window.location.href = `/?text=${encodedText}`;
                }
                
                // Ctrl+Enter 快捷键
                document.getElementById('user-input').addEventListener('keydown', function(event) {
                    if (event.ctrlKey && event.key === 'Enter') {
                        event.preventDefault();
                        sendToMain();
                    }
                });
                
                // 页面加载时聚焦输入框
                window.onload = function() {
                    document.getElementById('user-input').focus();
                };
            </script>
        </body>
        </html>
        '''
        return html_content
    except Exception as e:
        logger.error(f"生成输入界面失败: {e}")
        return f"""
        <h1>输入界面加载失败</h1>
        <p>错误: {e}</p>
        <p>请直接访问: <a href="/?text=hello">测试链接</a></p>
        """

if __name__ == '__main__':
    logger.info("启动Ollama流式响应服务器...")
    logger.info("访问 http://localhost:5000/input 使用输入界面")
    logger.info("或直接访问 http://localhost:5000/?text=你的问题")
    logger.info("确保Ollama服务正在运行: ollama serve")
    app.run(host='0.0.0.0', port=5000, debug=False)

