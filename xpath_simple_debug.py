import asyncio
import json
import logging
import requests
import websockets

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class ChromeDevToolsClient:
    def __init__(self):
        self.websocket = None
        self.message_id = 1
        self.response_waiting = {}
    
    async def connect(self, ws_url):
        try:
            self.websocket = await websockets.connect(ws_url)
            logger.info("Chrome调试连接成功")
            # 启动消息处理任务
            self.message_task = asyncio.create_task(self._process_messages())
            return True
        except Exception as e:
            logger.error(f"连接Chrome调试端口失败: {str(e)}")
            return False
    
    async def _process_messages(self):
        try:
            while self.websocket:
                message = await self.websocket.recv()
                response = json.loads(message)
                msg_id = response.get('id')
                
                if msg_id in self.response_waiting:
                    self.response_waiting[msg_id].set_result(response)
        except Exception as e:
            logger.error(f"消息处理异常: {str(e)}")
    
    async def send_command(self, method, params=None):
        if not self.websocket:
            logger.error("WebSocket连接未建立")
            return None
        
        msg_id = self.message_id
        self.message_id += 1
        
        command = {
            'id': msg_id,
            'method': method,
            'params': params or {}
        }
        
        # 创建一个Future对象来等待响应
        future = asyncio.Future()
        self.response_waiting[msg_id] = future
        
        try:
            # 发送命令
            await self.websocket.send(json.dumps(command))
            # 等待响应，设置超时
            response = await asyncio.wait_for(future, timeout=10)
            return response
        except asyncio.TimeoutError:
            logger.error(f"命令 {method} 超时")
            return None
        except Exception as e:
            logger.error(f"发送命令异常: {str(e)}")
            return None
        finally:
            # 清理等待字典
            if msg_id in self.response_waiting:
                del self.response_waiting[msg_id]
    
    async def execute_script(self, script):
        # 将JavaScript代码用函数包装，这样就能正确使用return语句
        fixed_script = f"(function() {{ {script} }})()"
        result = await self.send_command(
            "Runtime.evaluate",
            {
                "expression": fixed_script,
                "returnByValue": True,
                "awaitPromise": True
            }
        )
        return result
    
    async def close(self):
        if hasattr(self, 'message_task'):
            self.message_task.cancel()
        
        if self.websocket:
            try:
                await self.websocket.close()
                logger.info("WebSocket连接已关闭")
            except Exception as e:
                logger.error(f"关闭WebSocket连接异常: {str(e)}")
        self.websocket = None

def find_chrome_debugging_targets():
    """获取Chrome调试目标列表"""
    try:
        response = requests.get('http://localhost:9222/json')
        if response.status_code == 200:
            targets = response.json()
            logger.info(f"找到 {len(targets)} 个调试目标:")
            
            # 优先选择非DevTools页面
            page_targets = [t for t in targets if t.get('type') == 'page' and not t.get('url', '').startswith('devtools://')]
            devtools_targets = [t for t in targets if t.get('type') == 'page' and t.get('url', '').startswith('devtools://')]
            
            all_targets = page_targets + devtools_targets
            
            for i, target in enumerate(all_targets):
                logger.info(f" {i}: {target.get('title', 'Untitled')} - {target.get('type', 'unknown')} - {target.get('url', 'unknown')}")
            
            # 优先返回非DevTools页面
            if page_targets:
                return page_targets
            return all_targets
        else:
            logger.error(f"获取Chrome调试目标失败，HTTP状态码: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"获取Chrome调试目标异常: {str(e)}")
        return []

async def test_selector(client, selector_name, selector_value):
    """测试选择器 - 修复了响应处理逻辑"""
    logger.info(f"测试选择器 '{selector_name}': {selector_value}")
    
    # 修复JavaScript代码，使用正确的函数包装
    script = f'''
        try {{
            let element = document.querySelector('{selector_value}');
            if (element) {{
                return {{
                    found: true,
                    tagName: element.tagName,
                    id: element.id,
                    className: element.className,
                    innerHTML: element.innerHTML.substring(0, 100),
                    outerHTML: element.outerHTML.substring(0, 200),
                    isVisible: window.getComputedStyle(element).display !== 'none' && 
                               window.getComputedStyle(element).visibility !== 'hidden',
                    isContentEditable: element.isContentEditable,
                    isConnected: element.isConnected,
                    isDisabled: element.disabled !== undefined ? element.disabled : false,
                    isButton: element.tagName.toLowerCase() === 'button' || 
                             element.type === 'button' || 
                             element.type === 'submit' ||
                             element.role === 'button'
                }};
            }} else {{
                return {{ found: false }};
            }}
        }} catch (e) {{
            return {{
                found: false,
                error: e.toString(),
                stack: e.stack || 'No stack trace available'
            }};
        }}
    '''
    
    try:
        result = await client.execute_script(script)
        
        # 打印原始响应以便调试
        logger.debug(f"原始响应: {result}")
        
        # 修复响应处理逻辑，正确处理两层'result'结构
        if result and 'result' in result and 'result' in result['result'] and 'value' in result['result']['result']:
            value = result['result']['result']['value']
            if value.get('found'):
                logger.info(f"成功找到元素!")
                logger.info(f"  标签名: {value.get('tagName')}")
                logger.info(f"  ID: {value.get('id')}")
                logger.info(f"  类名: {value.get('className')}")
                logger.info(f"  可见性: {'可见' if value.get('isVisible') else '不可见'}")
                logger.info(f"  可编辑: {'是' if value.get('isContentEditable') else '否'}")
                logger.info(f"  连接状态: {'已连接' if value.get('isConnected') else '未连接'}")
                logger.info(f"  是否禁用: {'是' if value.get('isDisabled') else '否'}")
                logger.info(f"  是否按钮: {'是' if value.get('isButton') else '否'}")
                logger.info(f"  HTML片段: {value.get('innerHTML')}")
                return True, value  # 返回找到的元素信息
            else:
                logger.warning(f"未找到元素{'，原因: ' + value.get('error', '') if 'error' in value else ''}")
                if 'stack' in value:
                    logger.warning(f"  错误堆栈: {value['stack']}")
                return False, None
        else:
            logger.error(f"未能获取有效的响应结果")
            logger.error(f"  原始响应: {result}")
            return False, None
    except Exception as e:
        logger.error(f"JavaScript执行异常: {str(e)}")
        return False, None

async def input_text_in_element(client, selector_value, text_to_input):
    """在指定的元素中输入文本"""
    logger.info(f"在元素 {selector_value} 中输入文本: {text_to_input}")
    
    # 使用多种方法尝试在可编辑元素中输入文本
    script = f'''
        try {{
            let element = document.querySelector('{selector_value}');
            if (!element) {{
                return {{ success: false, error: '元素未找到' }};
            }}
            
            // 确保元素可见且可编辑
            if (!element.isContentEditable && 
                element.tagName.toLowerCase() !== 'input' && 
                element.tagName.toLowerCase() !== 'textarea') {{
                return {{ success: false, error: '元素不可编辑' }};
            }}
            
            // 方法1: 直接设置innerHTML
            element.innerHTML = '{text_to_input}';
            
            // 方法2: 如果是可编辑元素，也可以使用execCommand模拟用户输入
            if (element.isContentEditable) {{
                // 聚焦到元素
                element.focus();
                
                // 创建Range并选择元素内容
                let range = document.createRange();
                range.selectNodeContents(element);
                let selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                
                // 清除原有内容
                document.execCommand('delete', false, null);
                
                // 插入新文本
                document.execCommand('insertText', false, '{text_to_input}');
            }} else if (element.tagName.toLowerCase() === 'input' || 
                      element.tagName.toLowerCase() === 'textarea') {{
                // 对于input和textarea，直接设置value
                element.value = '{text_to_input}';
                // 触发必要的事件
                element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                element.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
            
            // 验证文本是否成功输入
            let content = element.isContentEditable ? element.textContent : element.value;
            return {{
                success: true,
                inputText: '{text_to_input}',
                actualContent: content.substring(0, 100),
                match: content.includes('{text_to_input}')
            }};
        }} catch (e) {{
            return {{
                success: false,
                error: e.toString(),
                stack: e.stack || 'No stack trace available'
            }};
        }}
    '''
    
    try:
        result = await client.execute_script(script)
        
        # 打印原始响应以便调试
        logger.debug(f"原始响应: {result}")
        
        # 使用修复后的响应处理逻辑
        if result and 'result' in result and 'result' in result['result'] and 'value' in result['result']['result']:
            value = result['result']['result']['value']
            if value.get('success'):
                logger.info(f"文本输入成功!")
                logger.info(f"  输入的文本: {value.get('inputText')}")
                logger.info(f"  实际内容: {value.get('actualContent')}")
                logger.info(f"  内容匹配: {'是' if value.get('match') else '否'}")
                return True
            else:
                logger.error(f"文本输入失败: {value.get('error', '未知错误')}")
                if 'stack' in value:
                    logger.error(f"  错误堆栈: {value['stack']}")
                return False
        else:
            logger.error(f"未能获取有效的响应结果")
            logger.error(f"  原始响应: {result}")
            return False
    except Exception as e:
        logger.error(f"JavaScript执行异常: {str(e)}")
        return False

async def click_element(client, selector_value):
    """点击指定的元素"""
    logger.info(f"尝试点击元素: {selector_value}")
    
    script = f'''
        try {{
            let element = document.querySelector('{selector_value}');
            if (!element) {{
                return {{ success: false, error: '元素未找到' }};
            }}
            
            // 检查元素是否可见
            let isVisible = window.getComputedStyle(element).display !== 'none' && 
                            window.getComputedStyle(element).visibility !== 'hidden';
            if (!isVisible) {{
                return {{ success: false, error: '元素不可见' }};
            }}
            
            // 检查元素是否可点击
            let isDisabled = element.disabled !== undefined ? element.disabled : false;
            if (isDisabled) {{
                return {{ success: false, error: '元素被禁用' }};
            }}
            
            // 尝试多种点击方法
            
            // 方法1: 直接调用click()
            element.click();
            
            // 方法2: 模拟鼠标事件序列
            let events = [
                new MouseEvent('mouseover', {{ bubbles: true, cancelable: true }}),
                new MouseEvent('mousedown', {{ bubbles: true, cancelable: true }}),
                new MouseEvent('mouseup', {{ bubbles: true, cancelable: true }}),
                new MouseEvent('click', {{ bubbles: true, cancelable: true }})
            ];
            
            events.forEach(event => element.dispatchEvent(event));
            
            // 尝试点击父元素（如果是按钮内部的span元素）
            if (element.tagName.toLowerCase() === 'span' && 
                (element.parentElement.tagName.toLowerCase() === 'button' || 
                 element.parentElement.type === 'button' || 
                 element.parentElement.type === 'submit' ||
                 element.parentElement.id === 'yuanbao-send-btn')) {{
                element.parentElement.click();
            }}
            
            return {{ 
                success: true,
                elementInfo: {{
                    tagName: element.tagName,
                    id: element.id,
                    className: element.className,
                    parentTag: element.parentElement ? element.parentElement.tagName : null,
                    parentId: element.parentElement ? element.parentElement.id : null
                }}
            }};
        }} catch (e) {{
            return {{
                success: false,
                error: e.toString(),
                stack: e.stack || 'No stack trace available'
            }};
        }}
    '''
    
    try:
        result = await client.execute_script(script)
        
        # 打印原始响应以便调试
        logger.debug(f"原始响应: {result}")
        
        # 使用修复后的响应处理逻辑
        if result and 'result' in result and 'result' in result['result'] and 'value' in result['result']['result']:
            value = result['result']['result']['value']
            if value.get('success'):
                logger.info(f"点击操作成功!")
                elementInfo = value.get('elementInfo', {})
                logger.info(f"  元素标签: {elementInfo.get('tagName')}")
                logger.info(f"  元素ID: {elementInfo.get('id')}")
                logger.info(f"  父元素标签: {elementInfo.get('parentTag')}")
                logger.info(f"  父元素ID: {elementInfo.get('parentId')}")
                return True
            else:
                logger.error(f"点击操作失败: {value.get('error', '未知错误')}")
                if 'stack' in value:
                    logger.error(f"  错误堆栈: {value['stack']}")
                return False
        else:
            logger.error(f"未能获取有效的响应结果")
            logger.error(f"  原始响应: {result}")
            return False
    except Exception as e:
        logger.error(f"JavaScript执行异常: {str(e)}")
        return False

async def test_js_path(client, js_path):
    """测试JavaScript路径代码 - 修改为与test_selector相同的响应处理逻辑"""
    logger.info("测试JavaScript路径代码...")
    
    # 从document.querySelector("...") 格式提取选择器
    if js_path.startswith("document.querySelector(") and js_path.endswith(")"):
        # 提取引号内的内容
        if js_path[21] in ['"', "'"]:
            quote_char = js_path[21]
            if js_path.endswith(f'{quote_char})'):
                selector_value = js_path[22:-2]  # 提取引号内的选择器
                # 直接使用test_selector函数来处理，因为它已经被验证可以正常工作
                return await test_selector(client, "JS路径提取的选择器", selector_value)
    
    # 如果格式不正确，尝试直接执行JavaScript路径
    script = f'''
        try {{
            let element = {js_path};
            if (element) {{
                return {{
                    found: true,
                    tagName: element.tagName,
                    id: element.id,
                    className: element.className,
                    innerHTML: element.innerHTML.substring(0, 100),
                    outerHTML: element.outerHTML.substring(0, 200),
                    isVisible: window.getComputedStyle(element).display !== 'none' && 
                               window.getComputedStyle(element).visibility !== 'hidden',
                    isContentEditable: element.isContentEditable,
                    isConnected: element.isConnected,
                    isDisabled: element.disabled !== undefined ? element.disabled : false,
                    isButton: element.tagName.toLowerCase() === 'button' || 
                             element.type === 'button' || 
                             element.type === 'submit' ||
                             element.role === 'button'
                }};
            }} else {{
                return {{ found: false }};
            }}
        }} catch (e) {{
            return {{
                found: false,
                error: e.toString(),
                stack: e.stack || 'No stack trace available'
            }};
        }}
    '''
    
    try:
        result = await client.execute_script(script)
        
        # 打印原始响应以便调试
        logger.debug(f"原始响应: {result}")
        
        # 使用与test_selector相同的修复后的响应处理逻辑
        if result and 'result' in result and 'result' in result['result'] and 'value' in result['result']['result']:
            value = result['result']['result']['value']
            if value.get('found'):
                logger.info(f"成功找到元素!")
                logger.info(f"  标签名: {value.get('tagName')}")
                logger.info(f"  ID: {value.get('id')}")
                logger.info(f"  类名: {value.get('className')}")
                logger.info(f"  可见性: {'可见' if value.get('isVisible') else '不可见'}")
                logger.info(f"  可编辑: {'是' if value.get('isContentEditable') else '否'}")
                logger.info(f"  连接状态: {'已连接' if value.get('isConnected') else '未连接'}")
                logger.info(f"  是否禁用: {'是' if value.get('isDisabled') else '否'}")
                logger.info(f"  是否按钮: {'是' if value.get('isButton') else '否'}")
                logger.info(f"  HTML片段: {value.get('innerHTML')}")
                return True, value  # 返回找到的元素信息
            else:
                logger.warning(f"未找到元素{'，原因: ' + value.get('error', '') if 'error' in value else ''}")
                if 'stack' in value:
                    logger.warning(f"  错误堆栈: {value['stack']}")
                return False, None
        else:
            logger.error(f"未能获取有效的响应结果")
            logger.error(f"  原始响应: {result}")
            return False, None
    except Exception as e:
        logger.error(f"JavaScript执行异常: {str(e)}")
        return False, None

async def main():
    # 获取Chrome调试目标
    targets = find_chrome_debugging_targets()
    if not targets:
        logger.error("未找到Chrome调试目标，请确保Chrome已启动并开启调试模式")
        return
    
    # 选择第一个目标
    target = targets[0]
    ws_url = target.get('webSocketDebuggerUrl')
    logger.info(f"连接到目标: {target.get('title', 'Untitled')} - {target.get('url', 'unknown')}")
    
    # 创建客户端并连接
    client = ChromeDevToolsClient()
    
    try:
        # 连接到调试端口
        if not await client.connect(ws_url):
            logger.error("无法连接到Chrome调试端口")
            return
        
        # 等待页面加载完成
        # await asyncio.sleep(3)
        
        # 用户提供的选择器
        css_selector = "#app > div > div.yb-layout__content.agent-layout__content > div > div > div.agent-dialogue__content > div > div.Pane.vertical.Pane1 > div > div.agent-dialogue__content--common__input.agent-chat__input-box > div > div.agent-dialogue__content--common__input-box > div > div > div.style__text-area__wrapper___W6mrC > div.style__text-area__start___z71p8.style__tooltipLiteBox___avW6d > div > div > div > div > p"
        # 要输入的文本
        text_to_input = "Is life so dear or peace so sweet as to be purchased at the price of chains and slavery? Forbid it, Almighty God! I know not what course others may take; but as for me, give me liberty or give me death!"
        # 提交按钮的CSS选择器
        submit_button_css_selector = "#yuanbao-send-btn > span"
        # 反馈元素的CSS选择器
        feedback_css_selector = "#chat-content"
        '''
        # 测试CSS选择器
        found, element_info = await test_selector(client, "CSS选择器", css_selector)
        
        # 如果找到了元素且元素可编辑，尝试输入文本
        if found and element_info and element_info.get('isContentEditable'):
            logger.info("找到可编辑元素，准备输入文本...")
            # 输入文本
            await input_text_in_element(client, css_selector, text_to_input)
        elif found:
            logger.warning("找到元素，但该元素不可编辑，无法输入文本")
        else:
            logger.warning("未找到元素，无法输入文本")
        '''
        # 输入文本
        await input_text_in_element(client, css_selector, text_to_input)
        
        '''
        # JavaScript路径
        js_path = "document.querySelector('#app > div > div.yb-layout__content.agent-layout__content > div > div > div.agent-dialogue__content > div > div.Pane.vertical.Pane1 > div > div.agent-dialogue__content--common__input.agent-chat__input-box > div > div.agent-dialogue__content--common__input-box > div > div > div.style__text-area__wrapper___W6mrC > div.style__text-area__start___z71p8.style__tooltipLiteBox___avW6d > div > div > div > div > p')"
        await test_js_path(client, js_path)
        
        # 测试提交按钮
        logger.info("\n===== 测试提交按钮 =====")
        submit_button_js_path = "document.querySelector(\"#yuanbao-send-btn > span\")"
        
        # 测试提交按钮的JS路径
        found_button, button_info = await test_js_path(client, submit_button_js_path)
        
        # 直接使用CSS选择器测试提交按钮
        if not found_button:

            found_button, button_info = await test_selector(client, "提交按钮CSS选择器", submit_button_css_selector)
        
        # 如果找到了提交按钮，尝试点击它
        if found_button:
            logger.info("找到提交按钮，尝试点击...")
            await click_element(client, submit_button_css_selector)
        else:
            logger.warning("未找到提交按钮，无法执行点击操作")
        '''

        # 点击提交按钮
        await asyncio.sleep(1)
        await click_element(client, submit_button_css_selector)
        
    except KeyboardInterrupt:
        logger.info("用户中断操作")
    except Exception as e:
        logger.error(f"程序异常: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # 关闭连接
        await client.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"主程序异常: {str(e)}")