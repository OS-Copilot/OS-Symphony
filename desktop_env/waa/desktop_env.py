from __future__ import annotations

import logging
import os
import re
import subprocess
import time
import json
from typing import Callable, Any, Optional, Tuple
from typing import List, Dict, Union


import gymnasium as gym

from desktop_env.waa.controllers.python import PythonController
from desktop_env.waa.controllers.setup import SetupController
from desktop_env.waa.providers.provider import WindowsDockerProvider
from desktop_env.waa.evaluators import metrics, getters

logger = logging.getLogger("desktopenv.env")

Metric = Callable[[Any, Any], float]
Getter = Callable[[gym.Env, Dict[str, Any]], Any]

def _fix_pyautogui_less_than_bug(command: str) -> str:
    """
    Fix PyAutoGUI '<' character bug by converting it to hotkey("shift", ',') calls.
    
    This fixes the known PyAutoGUI issue where typing '<' produces '>' instead.
    References:
    - https://github.com/asweigart/pyautogui/issues/198
    - https://github.com/xlang-ai/OSWorld/issues/257
    
    Args:
        command (str): The original pyautogui command
        
    Returns:
        str: The fixed command with '<' characters handled properly
    """
    # Pattern to match press('<') or press('\u003c') calls  
    press_pattern = r'pyautogui\.press\(["\'](?:<|\\u003c)["\']\)'

    # Handle press('<') calls
    def replace_press_less_than(match):
        return 'pyautogui.hotkey("shift", ",")'
    
    # First handle press('<') calls
    command = re.sub(press_pattern, replace_press_less_than, command)

    # Pattern to match typewrite calls with quoted strings
    typewrite_pattern = r'pyautogui\.write\((["\'])(.*?)\1\)'
    
    # Then handle typewrite calls
    def process_typewrite_match(match):
        quote_char = match.group(1)
        content = match.group(2)
        
        # Preprocess: Try to decode Unicode escapes like \u003c to actual '<'
        # This handles cases where '<' is represented as escaped Unicode
        try:
            # Attempt to decode unicode escapes
            decoded_content = content.encode('utf-8').decode('unicode_escape')
            content = decoded_content
        except UnicodeDecodeError:
            # If decoding fails, proceed with original content to avoid breaking existing logic
            pass  # English comment: Graceful degradation - fall back to original content if decoding fails
        
        # Check if content contains '<'
        if '<' not in content:
            return match.group(0)
        
        # Split by '<' and rebuild
        parts = content.split('<')
        result_parts = []
        
        for i, part in enumerate(parts):
            if i == 0:
                # First part
                if part:
                    result_parts.append(f"pyautogui.write({quote_char}{part}{quote_char})")
            else:
                # Add hotkey for '<' and then typewrite for the rest
                result_parts.append('pyautogui.hotkey("shift", ",")')
                if part:
                    result_parts.append(f"pyautogui.write({quote_char}{part}{quote_char})")
        
        return '; '.join(result_parts)
    
    command = re.sub(typewrite_pattern, process_typewrite_match, command)
    
    return command

class DesktopEnv(gym.Env):
    def __init__(
        self,
        path_to_vm: str, # 这里传入 storage 路径
        path_to_vm_backup: str, # 新增：传入 backup 路径
        action_space: str = "computer_13",
        cache_dir: str = "cache",
        screen_size: Tuple[int] = (1920, 1080),
        headless: bool = True,
        require_a11y_tree: bool = True,
        provider_name: str = "docker", # 默认为 docker
        proxy: str = ""
    ):
        self.screen_size = screen_size
        self.headless = headless
        self.require_a11y_tree = require_a11y_tree
        self.action_space = action_space
        self.cache_dir_base = cache_dir
        
        # 初始化 Provider
        if provider_name == "docker":
            self.provider = WindowsDockerProvider(
                vm_storage_path=path_to_vm,
                vm_backup_path=path_to_vm_backup,
                ram_size="8G", # 可以参数化
                cpu_cores="8"
            )
        else:
            raise NotImplementedError("Only docker provider is implemented for this refactor.")

        # 启动环境 (Start)
        # 注意：这里会自动分配端口并启动容器
        logger.info("Initializing Environment and starting Docker container...")
        # self.provider.start_emulator(headless=self.headless)
        
        # 获取动态分配的端口
        # conn_info = self.provider.get_connection_info() 
        self.vm_ip = '127.0.0.1'
        self.server_port = 5000
        self.rdp_port = 3389
        self.chromium_port = 9222
        logger.info(f"Environment started at {self.vm_ip}:{self.server_port}")

        # 初始化控制器
        # 注意：PythonController 需要适配动态端口。
        # 如果原本的 PythonController 只接受 ip，你需要修改它接受 port，或者把 ip 传为 "127.0.0.1:PORT"
        # 假设 PythonController 构造函数支持 server_port 参数 (参考 Linux 版)
        self.controller = PythonController(vm_ip=self.vm_ip, server_port=self.server_port)
        
        # SetupController 通常用于文件传输等，可能也需要端口
        self.setup_controller = SetupController(vm_ip=self.vm_ip, server_port=self.server_port, chromium_port=self.chromium_port, cache_dir=self.cache_dir_base, proxy=proxy)

        self._traj_no = -1
        self._step_no = 0
        self.action_history = []

    @property
    def vm_platform(self):
        return self.controller.get_vm_platform()

    @property
    def vm_screen_size(self):
        size_json = self.controller.get_vm_screen_size()
        return size_json["width"], size_json["height"]
    
    def _wait_emulator(self):
        """
        Continuously calls `get_probe` until it returns True, indicating the VM is ready.
        Polls every 5 seconds up to a specified maximum retry limit.
        """
        max_attempts = 20
        attempt = 0

        while attempt < max_attempts:
            if self.controller.get_probe(): # Check if VM is ready
                logger.info("VM is up and ready.")
                return True
            
            logger.info("VM not ready yet. Retrying in 5 seconds...")
            time.sleep(5)  # Wait for 5 seconds before retrying
            attempt += 1

        logger.error("VM did not become ready after %d attempts.", max_attempts)
        return False

    def _get_vm_ip(self):
        return self.vm_ip

    def _save_state(self):
        # TODO: test this
        logger.error("Not implemented! Saving state is not supported for remote VMs!")

    def _get_screenshot(self):
        screenshot = None
        # Get the screenshot and save to the image_path
        max_retries = 20
        for _ in range(max_retries):
            screenshot = self.controller.get_screenshot()
            if screenshot is not None:
                break
            print("Retrying to get screenshot...")
            time.sleep(1)

        if screenshot is None:
            logger.error("Failed to get screenshot!")

        # Resize image to self.screen_size
        try:
            from PIL import Image
            import io
            
            # Create image object from byte stream
            image = Image.open(io.BytesIO(screenshot))
            print(f'[WindowsAgentArena]: origin size: {image.height},{image.width}')
            # Resize
            resized_image = image.resize(self.screen_size, Image.LANCZOS)
            
            # Convert resized image back to byte stream
            buffer = io.BytesIO()
            resized_image.save(buffer, format="PNG")
            screenshot = buffer.getvalue() # bytes
        except Exception as e:
            logger.error(f"Failed to resize screenshot: {e}")
        return screenshot

    def _get_obs(self):
        screenshot = self._get_screenshot()
        
        accessibility_tree = None
        terminal = None
        
        obs = self.controller.get_obs_winagent()
        if obs is not None:
            window_image, window_title, window_rect, window_names_str, computer_clipboard, human_input = obs
            window_image = None
            human_input = None
            
            return {
                "screenshot": screenshot,
                "accessibility_tree": accessibility_tree,
                "terminal": terminal,
                "instruction": self.instruction,
                "window_title": window_title,
                "window_rect": window_rect,
                "window_image": window_image,
                "window_names_str": window_names_str,
                "computer_clipboard": computer_clipboard,
                "human_input": human_input
            }
        else:
            return None
        # print("terminal done")
        # print("LOG: Observation collected")
        

    def _set_task_info(self, task_config: Dict[str, Any]):
        self.task_id: str = task_config["id"]
        self.cache_dir: str = os.path.join(self.cache_dir_base, self.task_id)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.instruction = task_config["instruction"]
        self.config = task_config["config"] if "config" in task_config else []

        # evaluator dict
        # func -> metric function string, or list of metric function strings
        # conj -> conjunction of multiple metrics if func is a list with length > 1, "and"/"or"
        # result -> result getter config, or list of result getter configs
        # expected (optional) -> expected getter config, or list of expected getter configs
        # options (optional) -> metric options, or list of metric options
        # if func is a str list, then result, expected (if exists), options (if exists) should also be lists of the same length
        # even if one of the metrics does not need expected or options field, it should be included in the list with None
        self.evaluator = task_config["evaluator"]
        self.metric: Metric = [getattr(metrics, func) for func in self.evaluator["func"]] \
            if isinstance(self.evaluator["func"], list) \
            else getattr(metrics, self.evaluator["func"])
        self.metric_conj: str = self.evaluator.get("conj", "and")  # take conjunction of multiple metrics
        if "result" in self.evaluator and len(self.evaluator["result"]) > 0:
            self.result_getter: Getter = [getattr(getters, "get_{:}".format(res["type"])) for res in
                                          self.evaluator["result"]] \
                if isinstance(self.evaluator["result"], list) \
                else getattr(getters, "get_{:}".format(self.evaluator["result"]["type"]))
        else:
            self.result_getter = [None] * len(self.metric) \
                if isinstance(self.metric, list) \
                else None

        if "expected" in self.evaluator and len(self.evaluator["expected"]) > 0:
            self.expected_getter: Getter = [getattr(getters, "get_{:}".format(exp["type"])) if exp else None for exp in
                                            self.evaluator["expected"]] \
                if isinstance(self.evaluator["expected"], list) \
                else getattr(getters, "get_{:}".format(self.evaluator["expected"]["type"]))
        else:
            self.expected_getter = [None] * len(self.metric) \
                if isinstance(self.metric, list) \
                else None
        self.metric_options: Union[List[Dict[str, Any]], Dict[str, Any]] = [opt if opt else {} for opt in
                                                                            self.evaluator["options"]] \
            if isinstance(self.evaluator.get("options", {}), list) \
            else self.evaluator["options"] \
            if "options" in self.evaluator \
            else [{}] * len(self.metric) \
            if isinstance(self.metric, list) \
            else {}

        assert (not isinstance(self.evaluator["func"], list)
                or (len(self.metric) == len(self.result_getter) == len(self.expected_getter) == len(
                    self.metric_options)))

    def reset(self, task_config: Optional[Dict[str, Any]] = None, seed=None, options=None):
        logger.info("Resetting environment...")

        self._traj_no += 1
        self._step_no = 0
        self.action_history.clear()

        # 核心修改：调用 Provider 的回滚逻辑
        # 这会触发 Stop -> Replace Files -> Start -> Wait
        logger.info("Reverting VM snapshot (Restarting Docker)...")
        self.provider.revert_to_snapshot()
        
        # 容器重启后，端口可能会变（取决于 revert 实现，如果 stop 后 restart，端口可能需要重新获取）
        # 在上面的 Provider 实现中，revert 内部调用了 start_emulator，会重新分配端口
        conn_info = self.provider.get_connection_info()
        self.server_port = conn_info["server_port"]
        self.rdp_port = conn_info["rdp_port"]
        self.chromium_port = conn_info["chromium_port"]

        # 更新 Controller 的端口信息
        logger.info(f"New session started at port {self.server_port}")
        self.controller.update_connection_info(self.vm_ip, self.server_port)
        self.setup_controller.update_connection_info(self.vm_ip, server_port=self.server_port, chromium_port=self.chromium_port)

        # 设置任务配置 (和之前逻辑一样)
        if task_config is not None:
            self.setup_controller.reset_cache_dir(self.cache_dir_base) # 注意路径
            self._set_task_info(task_config)
            self.setup_controller.setup(self.config)

        time.sleep(5) # 给一点额外的缓冲时间

        return

    def resize_action(self, action):
        # Extract all x,y coordinates and resize them
        import re
        
        # Get source and target dimensions
        src_width, src_height = self.screen_size
        dst_width, dst_height = self.vm_screen_size
        
        # Calculate scaling ratios
        scale_x = dst_width / src_width
        scale_y = dst_height / src_height
        
        # Use regex to find all coordinate pairs in the form x,y including decimal forms
        # This pattern will match forms like 100,200 or 10.5,20.3, regardless of parentheses
        pattern = r'(\d+\.?\d*)\s*,\s*(\d+\.?\d*)'
        
        def replace_coords(match):
            x = float(match.group(1))
            y = float(match.group(2))
            
            # Scale coordinates proportionally
            new_x = x * scale_x
            new_y = y * scale_y
            
            # Maintain original format
            return f'{new_x}, {new_y}'
        
        # Replace all found coordinate pairs
        resized_action = re.sub(pattern, replace_coords, action)
        
        print(f"Original action: {action}")
        print(f"Resized action: {resized_action}")
        
        return resized_action


    def step(self, action, pause=0.5):
        self._step_no += 1
        self.action_history.append(action)

        reward = 0  # todo: Define reward calculation for each example
        done = False  # todo: Define episode termination condition for each example
        info = {}
        # handle the special actions
        if action in ['WAIT', 'FAIL', 'DONE']:
            if action == 'WAIT':
                time.sleep(pause)
            elif action == 'FAIL':
                done = True
                info = {"fail": True}
            elif action == 'DONE':
                done = True
                info = {"done": True}
        else:
            if self.action_space == "computer_13":
                # the set of all possible actions defined in the action representation
                self.controller.execute_action(action)
            elif self.action_space == "pyautogui":
                if action in ['WAIT', 'FAIL', 'DONE']:
                    self.controller.execute_action(action)
                else:
                    # the set of all possible python commands insides `pyautogui`
                    if self.vm_screen_size != self.screen_size:
                        action = self.resize_action(action)
                    if type(action) == str:
                        # Fix PyAutoGUI '<' character bug before execution
                        fixed_command = _fix_pyautogui_less_than_bug(action)
                        self.controller.execute_python_command(fixed_command)

            elif self.action_space == "code_block":
                self.controller.execute_python_windows_command(action)
            else:
                raise ValueError("Unknown action space: {}".format(self.action_space))
        # wait a little before taking the next observation
        
        time.sleep(pause)
        
        try_time = 30
        observation = self._get_obs()
        while try_time > 0:
            logger.error("Observation is None. Waiting a little to do next step.")
            time.sleep(15)
            observation = self._get_obs()
            if observation is not None:
                break
            try_time -= 1

        return observation, reward, done, info
    
    def evaluate(self):
        """
        Evaluate whether the task is successfully completed.
        """

        self.setup_controller.setup(self.evaluator.get("postconfig", []))

        # logger.info(f"ACTION HISTORY: {self.action_history}")

        # No infeasible!
        # if self.evaluator['func'] == "infeasible":
        #     if len(self.action_history) > 0 and self.action_history[-1] == "FAIL":
        #         # logger.info("Infeasible task and last agent action = FAIL")
        #         return 1
        #     else:
        #         # logger.info("Infeasible task but last agent action != FAIL")
        #         return 0
        # else:
        #     if len(self.action_history) > 0 and self.action_history[-1] == "FAIL":
        #         # logger.info("Feasible task but last agent = FAIL")
        #         return 0

        if type(self.metric) == list:
            results = []
            for idx, metric in enumerate(self.metric):
                try:
                    config = self.evaluator["result"][idx]
                    result_state = self.result_getter[idx](self, config)
                except FileNotFoundError:
                    logger.error("File not found!")
                    if self.metric_conj == 'and':
                        return 0

                expected = self.evaluator["expected"][idx]
                expected_state = self.expected_getter[idx](self, expected) if expected else None

                metric: int = metric(result_state, expected_state,
                                     **self.metric_options[idx]) if expected_state is not None \
                    else metric(result_state, **self.metric_options[idx])

                if self.metric_conj == 'and' and float(metric) == 0.0:
                    return 0
                elif self.metric_conj == 'or' and float(metric) == 1.0:
                    return 1
                else:
                    results.append(metric)
            return sum(results) / len(results) if self.metric_conj == 'and' else max(results)
        else:
            try:
                result_state = self.result_getter(self, self.evaluator["result"])
            except FileNotFoundError:
                logger.error("File not found!")
                return 0
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                return 0
            expected_state = self.expected_getter(self, self.evaluator["expected"]) if "expected" in self.evaluator \
                else None

            metric: float = self.metric(result_state, expected_state,
                                        **self.metric_options) if expected_state is not None \
                else self.metric(result_state, **self.metric_options)
            
        if isinstance(metric, (float, int, bool)):
            return metric
        else:
            logger.error("Task metric value produced is neither numeric nor boolean: returning 0 instead")
            return 0

    def render(self, mode='rgb_array'):
        if mode == 'rgb_array':
            return self._get_screenshot()
        else:
            raise ValueError('Unsupported render mode: {}'.format(mode))

    def close(self):
        logger.info("Stopping emulator...")
        self.provider.stop_emulator()

