# 删除全局变量部分的previous_index
import requests
import json
import time
from flask import Flask, render_template_string, Response, request
from threading import Thread
from queue import Queue

app = Flask(__name__)

# 创建一个队列用于存储流式响应的内容
response_queue = Queue()
# 创建一个变量用于存储完整的响应内容
full_response = ""
# 创建一个标志用于控制是否正在接收响应
is_receiving = False

# 用于更新响应内容的函数
def update_response(content):
    global full_response
    full_response += content
    response_queue.put(content)

# 修改stream_response_from_api函数，移除previous_index相关代码
def stream_response_from_api(user_text=None):
    global is_receiving
    is_receiving = True
    update_response("开始接收API响应...")
    
    # 定义 API 的 URL
    url = 'https://open.hunyuan.tencent.com/openapi/v1/agent/chat/completions'

    # 定义请求头
    headers = {
        'X-Source': 'openapi',
        'Content-Type': 'application/json',
        'Authorization': 'Bearer <元器用户的token>'
    }

    # 定义请求体
    data = {
        "assistant_id": "智能体id",
        "user_id": "username",
        "stream": True,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "hello how are you？"
                    }
                ]
            }
        ]
    }
    # 从配置文件中读取智能体id和token
    assistant_id = "智能体id"
    token = "<元器用户的token>"
    try:
        with open('my.ini', 'r') as f:
            lines = f.readlines()
            for line in lines:
                if line.startswith('assistant_id'):
                    assistant_id = line.split('=')[1].strip()
                elif line.startswith('token'):
                    token = line.split('=')[1].strip()
    except Exception as e:
        error_msg = f"读取配置文件时出错: {e}\n"
        update_response(error_msg)
    
    # 更新请求头中的token
    headers['Authorization'] = f'Bearer {token}'
    # 更新请求体中的智能体id
    data['assistant_id'] = assistant_id

    # 默认文本
    mytext = "Is life so dear or peace so sweet as to be purchased at the price of chains and slavery? Forbid it, Almighty God! I know not what course others may take; but as for me, give me liberty or give me death!"
    
    # 如果有用户通过GET参数传入的文本，则使用它替换默认文本
    if user_text:
        mytext = user_text
        update_response(f"\n使用GET参数传入的文本: {user_text[:50]}...\n")
    
    data['messages'][0]['content'][0]['text'] = mytext

    try:
        # 发送POST请求，启用流式响应
        with requests.post(url, headers=headers, json=data, stream=True) as response:
            response.raise_for_status()
            
            update_response("\n正在接收流式响应...")
            
            # 处理流式响应
            for chunk in response.iter_lines():
                if chunk:
                    # 解码chunk
                    chunk_str = chunk.decode('utf-8')
                    
                    # 处理SSE格式的响应
                    if chunk_str.startswith('data:'):
                        chunk_str = chunk_str[5:].strip()  # 去掉'data: '前缀
                    
                    try:
                        # 尝试解析JSON
                        chunk_data = json.loads(chunk_str)
                        
                        # 根据腾讯元器API的响应格式，提取内容
                        if 'choices' in chunk_data and chunk_data['choices']:
                            choice = chunk_data['choices'][0]
                            # 删除处理index变化的逻辑
                            # 获取生成的内容
                            if 'delta' in choice and 'content' in choice['delta']:
                                content = choice['delta']['content']
                                if '\n' in content:
                                    print("有换行符号")
                                    content = content.replace('\n', '<br>')
                                
                                update_response(content)
                            elif 'message' in choice and 'content' in choice['message']:
                                content = choice['message']['content']
                                update_response(content)
                    except json.JSONDecodeError:
                        # 如果不是有效的JSON，直接添加原始内容
                        update_response(f"非JSON响应: {chunk_str}")
            
            update_response("\n流式响应接收完成")
            
    except requests.exceptions.RequestException as e:
        update_response(f"\n请求出错: {e}")
    except Exception as e:
        update_response(f"\n发生错误: {e}")
    finally:
        is_receiving = False

# 生成事件流的函数
def event_stream():
    while True:
        # 从队列中获取内容
        content = response_queue.get()
        # 以Server-Sent Events格式发送内容
        yield f"data: {content}\n\n"
        # 标记任务完成
        response_queue.task_done()

# 主页面路由
@app.route('/')
def index():
    # 读取HTML模板文件
    with open('my.html', 'r', encoding='utf-8') as f:
        html_template = f.read()
    
    # 检查是否有GET请求参数
    user_text = request.args.get('text')
    
    # 启动流式响应线程，传入用户文本
    if not is_receiving:
        Thread(target=stream_response_from_api, args=(user_text,)).start()
    
    return render_template_string(html_template)

# 流式响应路由
@app.route('/stream')
def stream():
    return Response(event_stream(), content_type='text/event-stream')

# 状态检查路由
@app.route('/status')
def status():
    return {
        'is_receiving': is_receiving,
        'response_length': len(full_response)
    }

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)