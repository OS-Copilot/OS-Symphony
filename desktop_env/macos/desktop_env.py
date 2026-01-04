from __future__ import annotations

import logging
import os
import subprocess
import time
import json
from typing import Callable, Any, Optional, Tuple
from typing import List, Dict, Union
from desktop_env.macos.controllers.env import MacOSEnv


import gymnasium as gym

logger = logging.getLogger("desktopenv.env")

class PythonController:
    def __init__(self, macos_env: MacOSEnv):
        self.macos_env = macos_env
    def run_python_script(self, script: str)  -> dict:
        return self.macos_env.execute_python_command(script)
    def run_bash_script(self, script: str, timeout: int = 30, working_dir: Optional[str] = None) -> dict:
        return self.macos_env.execute_bash_command(script)


class DesktopEnv(gym.Env):
    def __init__(
        self,
        path_to_vm: str,
        path_to_base_vm: str,
        action_space: str = "pyautogui",
        provider_name: str = "docker", # 默认为 docker
    ):
        self.macos_env = MacOSEnv(path_to_vm=path_to_vm, path_to_base_vm=path_to_base_vm, provider_name=provider_name, action_space=action_space)
        self.controller = PythonController(self.macos_env)

    # 必要
    def _get_obs(self):
        
        # 只要返回 screenshot 就行, 其余字段可有可无
        return {
            "screenshot": self.macos_env.get_screenshot()
        }

    # 必要 重置环境 + 初始化任务
    def reset(self, task_config: Optional[Dict[str, Any]] = None):
        self.macos_env._reset_env()
        self.macos_env.init_task(task_json_config=task_config)
        return

    # 必要
    def step(self, action, pause=3):
        # observation, reward, done, info = "必要", "没用", "必要", "没用"
        return self.macos_env.step(action, pause)
    
    # 必要
    def evaluate(self):
        return self.macos_env.evaluate_task()

    # 必要, 关闭并杀死docker
    def close(self):
        self.macos_env._close_env()
        return


