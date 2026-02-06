import base64
import json
import logging
import time
import os
import re
import io
from typing import Dict, List, Tuple, Any

from openai import OpenAI
from PIL import Image

logger = logging.getLogger("desktopenv.agent")

class GLM4VAgent:
    def __init__(
        self,
        model: str = "GLM-4.5V",
        base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        api_key: str = os.environ.get("GLM_API_KEY", "dummy"),
        max_tokens: int = 4096,
        top_p: float = 0.9,
        temperature: float = 0.001,
        max_image_history_length: int = 5, # 也就是保留最近多少步历史
        screen_width: int = 1920,
        screen_height: int = 1080
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.temperature = temperature
        self.max_image_history_length = max_image_history_length

        self.screen_height = screen_height
        self.screen_width = screen_width

        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

        # 状态管理
        self.history: List[str] = []        # 存储 LLM 的原始文本回复
        self.history_images: List[str] = [] # 存储原始截图数据
        self.memory: str = "[]"             # 存储 Agent 的 Memory JSON 字符串

    def predict(self, instruction: str, obs: Dict) -> Tuple[dict, Any]:
        """
        核心预测函数
        Args:
            instruction: 任务指令
            obs: 包含 'screenshot' (bytes) 的字典
        Returns:
            raw_response: LLM 原始回复
            parsed_action: 解析后的动作代码 (例如: click(box_2d=[...]))
        """
        current_screenshot = obs["screenshot"]

        current_img_b64 = base64.b64encode(current_screenshot).decode("utf-8")


        # 2. 构建 Prompt (包含 Action Space, History, Memory, Current Image)
        content = self._get_pc_prompt(
            instruction, 
            self.history, 
            self.memory, 
            self.history_images
        )
        
        # 添加当前帧
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{current_img_b64}"}})
        
        messages = [{"role": "user", "content": content}]

        # 3. 调用 API
        response = self._call_llm(messages)
        logger.info(f"GLM Output: {response}")

        # 4. 解析结果
        """
        {
            "action": action_raw, 
            "action_text": action_text, 
            "memory": memory,
            "pyautogui_code": pyautogui_code
        }
        """
        parsed = self._parse_response(response)
        
        # 5. 更新状态
        if parsed["memory"]:
            self.memory = parsed["memory"]
        
        self.history.append(response)
        self.history_images.append(current_img_b64)

        # 维护历史长度
        if len(self.history) > self.max_image_history_length:
            self.history_images = self.history_images[-self.max_image_history_length:]

        response = {"response": response} | parsed
        return response, parsed["pyautogui_code"]

    def reset(self):
        self.history = []
        self.history_images = []
        self.memory = "[]"
        logger.info("GLM4VAgent reset.")

    def _call_llm(self, messages):
        for _ in range(3):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p
                )
                return resp.choices[0].message.content
            except Exception as e:
                logger.error(f"API Error: {e}")
                time.sleep(1)
        return ""

    def _parse_response(self, response):
        """
        解析 GLM 输出，提取 Memory 并将 Action 转换为 PyAutoGUI 代码。
        """
        # 1. 提取 Action 字符串
        pattern_box = r"<\|begin_of_box\|>(.*?)<\|end_of_box\|>"
        match = re.search(pattern_box, response)
        action_raw = match.group(1).strip() if match else None

        if not action_raw:
            downgraded_pattern = r"[\w_]+\([^)]*\)"
            matched = re.findall(downgraded_pattern, response)
            action_raw = matched[0] if matched else None

        action_text = action_raw
        if action_text:
            action_text = (
                action_text.replace(" <|begin_of_box|> ", "")
                .replace(" <|end_of_box|> ", "")
                .replace("<|begin_of_box|>", "")
                .replace("<|end_of_box|>", "")
            )

        # 2. 提取 Memory
        memory_pattern = r"Memory:(.*?)$"
        memory_match = re.search(memory_pattern, response, re.DOTALL)
        memory = memory_match.group(1).strip() if memory_match else "[]"

        # 3. 将 Action 转换为 PyAutoGUI 代码
        pyautogui_code = []
        if action_text:
            try:
                # 解析函数名和参数: "click(start_box='[100,200]')"
                func_name = action_text.split("(")[0].strip()
                # 提取括号内的内容
                args_str = action_text[len(func_name)+1 : -1]
                
                # 简单的参数解析 (key='value')
                # 注意：这里使用 ast.literal_eval 处理值可能更安全，但正则更宽容
                kwargs = {}
                if args_str:
                    # 匹配 key='value' 或 key="value"
                    arg_pattern = r"(\w+)=(['\"])(.*?)\2"
                    for k, _, v in re.findall(arg_pattern, args_str):
                        kwargs[k] = v
                    
                    # 备用：处理数字参数如 step=5
                    num_pattern = r"(\w+)=(\d+)"
                    for k, v in re.findall(num_pattern, args_str):
                        if k not in kwargs:
                            kwargs[k] = int(v)

                code = self._map_action_to_pyautogui(func_name, kwargs)
                if code:
                    pyautogui_code.append(code)
            except Exception as e:
                logger.error(f"Failed to parse action '{action_text}': {e}")
                pyautogui_code.append("FAIL")

        return {
            "action": action_text, 
            "memory": memory,
            "func_name": func_name,
            "func_params": kwargs,
            "pyautogui_code": pyautogui_code
        }

    def _map_action_to_pyautogui(self, action_name: str, kwargs: Dict) -> str:
        """
        将解析出的动作和参数映射为 PyAutoGUI 代码字符串。
        """
        def _get_coords(box_str):
            # 解析 '[x,y]' -> x, y (0-999 scale) -> real_x, real_y
            try:
                # 移除方括号并分割
                clean = box_str.replace('[', '').replace(']', '')
                x, y = map(int, clean.split(','))
                # 转换坐标 (0-999 -> 屏幕像素)
                real_x = int(x / 1000 * self.screen_width)
                real_y = int(y / 1000 * self.screen_height)
                return real_x, real_y
            except:
                return 0, 0

        code = ""
        
        if action_name in ["left_click", "right_click", "middle_click", "left_double_click"]:
            x, y = _get_coords(kwargs.get("start_box", "[0,0]"))
            
            if action_name == "left_click":
                code = f"pyautogui.click({x}, {y})"
            elif action_name == "right_click":
                code = f"pyautogui.rightClick({x}, {y})"
            elif action_name == "middle_click":
                code = f"pyautogui.middleClick({x}, {y})"
            elif action_name == "left_double_click":
                code = f"pyautogui.doubleClick({x}, {y})"

        elif action_name == "hover":
            x, y = _get_coords(kwargs.get("start_box", "[0,0]"))
            code = f"pyautogui.moveTo({x}, {y})"

        elif action_name == "left_drag":
            # 拖拽需要起点和终点
            x1, y1 = _get_coords(kwargs.get("start_box", "[0,0]"))
            x2, y2 = _get_coords(kwargs.get("end_box", "[0,0]"))
            # 先移动到起点，再拖拽到终点
            code = f"pyautogui.moveTo({x1}, {y1}); pyautogui.dragTo({x2}, {y2}, duration=0.5)"

        elif action_name == "key":
            keys_raw = kwargs.get("keys", "")
            # 处理组合键，例如 "ctrl+c" -> pyautogui.hotkey('ctrl', 'c')
            keys = keys_raw.split('+')
            keys_str = ", ".join([f"'{k.strip().lower()}'" for k in keys])
            if len(keys) > 1:
                code = f"pyautogui.hotkey({keys_str})"
            else:
                code = f"pyautogui.press({keys_str})"

        elif action_name == "type":
            content = kwargs.get("content", "")
            # 转义单引号
            content = content.replace("'", "\\'")
            code = f"pyautogui.write('{content}')"

        elif action_name == "scroll":
            # 假设 step=1 对应 scroll 100 像素
            x, y = _get_coords(kwargs.get("start_box", "[0,0]"))
            step = int(kwargs.get("step", 5))
            direction = kwargs.get("direction", "down")
            clicks = step * 100
            if direction == "down":
                clicks = -clicks
            code = f"pyautogui.click({x}, {y}); pyautogui.scroll({clicks})"

        elif action_name == "WAIT":
            code = "time.sleep(1.0)"
        
        elif action_name == "DONE":
            code = "DONE"
            
        elif action_name == "FAIL":
            code = "FAIL"

        return code

    def _get_pc_prompt(self, task, history, memory, history_images_urls):
        action_space = """
### {left,right,middle}_click
Call rule: `{left,right,middle}_click(start_box='[x,y]', element_info='')`
Description: Click at coordinates [x,y] (0-999).

### hover
Call rule: `hover(start_box='[x,y]', element_info='')`
Description: Move mouse to [x,y].

### left_double_click
Call rule: `left_double_click(start_box='[x,y]', element_info='')`

### left_drag
Call rule: `left_drag(start_box='[x1,y1]', end_box='[x2,y2]', element_info='')`

### key
Call rule: `key(keys='')`
Description: Press keys (e.g., 'ctrl+c', 'enter').

### type
Call rule: `type(content='')`
Description: Type text into focused field.

### scroll
Call rule: `scroll(start_box='[x,y]', direction='down|up', step=5)`

### WAIT
Call rule: `WAIT()`

### DONE
Call rule: `DONE()`

### FAIL
Call rule: `FAIL()`
"""
        HEAD = f"""You are a GUI Agent. Respond to user requests by performing GUI operations. Coordinates are 0-999.

# Task:
{task}

# Task Platform
Ubuntu

# Action Space
{action_space}

# Historical Actions and Current Memory
History:"""

        TAIL = f"""
Memory:
{memory}

# Output Format
Plain text explanation with action(param='...')
Memory:
[{{"key": "value"}}, ...]

# Notes
- I'll give you recent history screenshots (shrunk) and action steps.
- Put key info in Memory.
- Password: "password".
- Output format must be strictly followed.

Current Screenshot:
"""
        
        # 构建历史文本 + 历史图片混合内容
        content = []
        current_text = HEAD
        
        total_steps = len(history)
        img_count = len(history_images_urls)
        
        # 逻辑：历史文本全部显示，但只有最近几步配有图片
        for i, raw_resp in enumerate(history):
            step_num = i + 1
            parsed = self._parse_response(raw_resp)
            act = parsed["action"] or "Unknown"
            # 简单提取 Thought (假设 Thought 在 Action 之前)
            thought = raw_resp.split("Memory:")[0].replace(parsed["action"] or "", "").strip()
            
            # 判断这一步是否有对应的历史图片
            # 假设 history_images_urls 对应 history 的最后 img_count 步
            img_idx_in_history = i - (total_steps - img_count)
            
            if img_idx_in_history >= 0 and img_idx_in_history < img_count:
                # 这一步有图片
                current_text += f"\nstep {step_num}: Screenshot:"
                content.append({"type": "text", "text": current_text})
                content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{history_images_urls[img_idx_in_history]}"}})
                current_text = f" Thought: {thought}\nAction: {act}"
            else:
                # 这一步图片太久远，被省略
                current_text += f"\nstep {step_num}: Screenshot:(Omitted) Thought: {thought}\nAction: {act}"

        current_text += TAIL
        content.append({"type": "text", "text": current_text})
        
        return content