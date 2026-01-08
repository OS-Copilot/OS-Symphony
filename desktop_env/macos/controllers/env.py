import logging
import os
import yaml
import paramiko
import time
import subprocess
from pathlib import Path
import json
import psutil
import docker
import platform
from typing import Optional
from filelock import FileLock
import importlib
import uuid
import tempfile
from desktop_env.macos.utils.basic import reset_applications, transform_pyautogui_line
from desktop_env.macos.launcher.docker.restart_docker import docker_reset_container, docker_start_container, container_exists, docker_remove_container, docker_run_container, DOCKER_RUN_SCRIPT_PATH

import shlex

logger = logging.getLogger("desktopenv.providers.macos")
LOCK_TIMEOUT = 1000

class MacOSEnv:
    def __init__(
        self,
        path_to_vm: str = "/nvme/yangbowen/vm_stroage/macos/mac_hdd_ng_copy.img",
        path_to_base_vm="/nvme/yangbowen/vm_stroage/macos/BaseSystem.img", 
        provider_name: str = "docker",
        action_space="pyautogui"
    ):
        """
        Initialize the MacOSEnv class. Reads configurations from the provided YAML file.
        """
        self.mode = provider_name
        self.action_space = action_space

        # SSH config
        self.username = 'pipiwu'
        self.password = '1234'
        self.host_ip = "127.0.0.1"
        self.ssh_port = -1  # map to port 10022 on container
        self.vnc_port = -1  # map to port 5901 on container
        self.ssh_port = -1
        
        self.ssh_client = None
        self.sftp_client = None
        self.task = None
        
        # Docker 
        self.client = docker.from_env()
        self.container = None 
        self.ram_size = "8G"
        self.cpu_cores = "4"
        # path to image file
        self.mac_hdd_img_path = path_to_vm
        self.base_system_img_path = path_to_base_vm

        temp_dir = Path(os.getenv('TEMP') if platform.system() == 'Windows' else '/tmp')
        self.lock_file = temp_dir / "mac_docker_port.lck"


    def _get_used_ports(self):
        system_ports = set(conn.laddr.port for conn in psutil.net_connections())
        docker_ports = set()
        try:
            for container in self.client.containers.list():
                ports = container.attrs['NetworkSettings']['Ports']
                if ports:
                    for port_mappings in ports.values():
                        if port_mappings:
                            docker_ports.update(int(p['HostPort']) for p in port_mappings)
        except Exception as e:
            logger.warning(f"Error checking docker ports: {e}")
        return system_ports | docker_ports

    def _get_available_port(self, start_port: int, exclude_ports: set = None) -> int:
        if exclude_ports is None:
            exclude_ports = set()
        used_ports = self._get_used_ports()
        port = start_port
        while port < 65535:
            if port not in used_ports and port not in exclude_ports:
                return port
            port += 1
        raise RuntimeError(f"No free ports available starting from {start_port}")

    def connect_ssh(self):
        """
        Connects to the MacOS docker container via SSH.
        """
        transport = self.ssh_client.get_transport() if self.ssh_client else None
        if self.ssh_client is None or not transport or not transport.is_active():
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                self.ssh_client.connect(self.host_ip, port=self.ssh_port, username=self.username, password=self.password)
                logger.info(f"Connected to {self.host_ip} on port {self.ssh_port}")
            except Exception as e:
                logger.error(f"SSH connection failed: {e}")
                raise e
        else:
            # logger.info("Already connected to the container.")
            pass
        
    def _reset_env(self):
        """
        Reset Environment: Stop old containers -> Allocate ports -> Start new containers -> Wait for SSH
        """
        self._close_env() 

        if self.mode != "docker":
            raise ValueError(f"Unsupported mode: {self.mode}")

        lock = FileLock(str(self.lock_file), timeout=LOCK_TIMEOUT)
        with lock:
            # allocate ports dynamically 
            self.ssh_port = self._get_available_port(10022) 
            self.vnc_port = self._get_available_port(5901, exclude_ports={self.ssh_port})
            
            logger.info(f"Allocated Ports -> SSH: {self.ssh_port}, VNC: {self.vnc_port}")

            # prepare volumes
            volumes = {
                '/tmp/.X11-unix': {'bind': '/tmp/.X11-unix', 'mode': 'rw'},
                self.mac_hdd_img_path: {'bind': '/home/arch/OSX-KVM/mac_hdd_ng_src.img', 'mode': 'rw'},
                self.base_system_img_path: {'bind': '/home/arch/OSX-KVM/BaseSystem_src.img', 'mode': 'rw'}
            }

            # prepare environment variables 
            environment = {
                "EXTRA": "-vnc 0.0.0.0:1,password=off",
                "CPU": "Haswell-noTSX",
                "CPUID_FLAGS": "kvm=on,vendor=GenuineIntel,+invtsc,vmware-cpuid-freq=on",
                "SHORTNAME": "sonoma",
                "USERNAME": self.username,
                "PASSWORD": self.password,
                "RAM_SIZE": self.ram_size,
                "CPU_CORES": self.cpu_cores
            }

            # prepare devices)
            devices = ["/dev/kvm"] if os.path.exists("/dev/kvm") else []
            if not devices:
                logger.warning("/dev/kvm not found. MacOS container might be extremely slow or fail.")

            try:
                logger.info("Starting MacOS container...")
                # start container (equal to docker run command) 
                self.container = self.client.containers.run(
                    image="numbmelon/docker-osx-evalkit-auto:latest",
                    detach=True,       # -d
                    tty=True,          # -t
                    stdin_open=True,   # -i
                    privileged=True,   # KVM usually needs priviledged mode
                    devices=devices,   # --device
                    ports={
                        '10022/tcp': self.ssh_port, # -p host:10022
                        '5901/tcp': self.vnc_port   # -p host:5901
                    },
                    volumes=volumes,       # -v
                    environment=environment # -e
                )
                logger.info(f"Container started with ID: {self.container.short_id}")

            except Exception as e:
                logger.error(f"Failed to start container: {e}")
                self._close_env()
                raise e

        # wait for ssh 
        self._wait_for_ssh_ready()
    
    def _wait_for_ssh_ready(self, timeout=1000):
        logger.info("Waiting for SSH to become available...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                self.connect_ssh()
                logger.info("SSH connection established successfully.")
                return
            except Exception:
                time.sleep(5) # retry every 4 seconds
        
        # timeout
        self._close_env()
        raise TimeoutError("Failed to SSH into the MacOS container after timeout.")
    
    def _close_env(self):
        """clean the environment: close SSH, stop and remove containers"""
        self.close_connection()
        
        if self.container:
            try:
                logger.info(f"Stopping container {self.container.short_id}...")
                self.container.stop(timeout=300)
                logger.info("Removing container...")
                self.container.remove(force=True)
            except Exception as e:
                logger.warning(f"Error stopping container: {e}")
            finally:
                self.container = None
                self.ssh_port = -1
                self.vnc_port = -1

    def get_connection_info(self):
        return {
            "ip": self.host_ip,
            "ssh_port": self.ssh_port,
            "vnc_port": self.vnc_port,
            "username": self.username,
            "password": self.password
        }
    
    def run_command(self, command: str, decode: bool = True):
        if not self.ssh_client:
            self.connect_ssh()
            # raise ValueError("SSH client not connected.")

        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        
        if decode:
            # logger.info(stdout)
            # logger.info(command)
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            return out, err
        else:
            return stdout, stderr  # raw paramiko ChannelFile
    
    def execute_bash_command(self, command: str, decode: bool = True):
        if not self.ssh_client:
            self.connect_ssh()
            # raise ValueError("SSH client not connected.")
        
        out, err = "", ""
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(command)

            if decode:
                # logger.info(stdout)
                # logger.info(command)
                out = stdout.read().decode("utf-8", errors="replace").strip()
                err = stderr.read().decode("utf-8", errors="replace").strip()
                return {
                    "output": out,
                    "error": err,
                    "status": "success"
                }
            else:
                return {
                    "output": stdout,
                    "error": stderr,
                    "status": "success"
                }
        except Exception as e:
            logger.error(f"execute_bash_command failed: {e}")
            return {
                "status": "error",
                "output": out,
                "error": err
            }

        
    def _get_obs(self):
        return {
            "screenshot": self.get_screenshot(),
            "accessibility_tree": None,
            "terminal": None,
            "instruction": None
        }
        
    def step(self, action, pause=2.0):
        if self.task is None:
            logger.info("Task is None, load a task before taking actions.")
            return None, None, None, None
        self.task.step_no += 1
        self.task.action_history.append(action)

        reward = 0  # always 0, keep the same as OSworld do, maybe insert a PRM later
        done = False 
        info = {}

        # handle the special actions
        if action in ['WAIT', 'FAIL', 'DONE'] or (type(action) == dict and action['action_type'] in ['WAIT', 'FAIL', 'DONE']):
            if action == 'WAIT':
                time.sleep(pause)
            elif action == 'FAIL':
                done = True
                info = {"fail": True}
            elif action == 'DONE':
                done = True
                info = {"done": True}

        if self.action_space == "computer_13":
            # the set of all possible actions defined in the action representation
            self.execute_action(action)
        elif self.action_space == "pyautogui":
            if action in ['WAIT', 'FAIL', 'DONE']:
                pass
            else:
                self.execute_python_command(action)

        time.sleep(pause)
        observation = self._get_obs()

        return observation, reward, done, info
    
    def execute_action(self, action):
        # TODO
        pass
    
    # def execute_python_command(self, action: str):
    #     if self.task is None:
    #         # Strip and convert multiline code into one-liner
    #         clean_action = "; ".join(
    #             line.strip() for line in action.strip().splitlines() if line.strip()
    #         )
    #         python_cmd = f"import pyautogui; import time; pyautogui.FAILSAFE = False; import pynput; {clean_action}"
    #     else:
    #         clean_lines = []
    #         for line in action.strip().splitlines():
    #             stripped = line.strip()
    #             if not stripped or stripped.startswith("#"):
    #                 continue
    #             if (
    #                 "pyautogui.write" in stripped
    #                 or "pyautogui.typewrite" in stripped
    #             ):
    #                 clean_lines.append("pyautogui.keyUp('shift')")
    #             clean_lines.append(stripped)

    #         clean_action = "; ".join(clean_lines)
    #         python_cmd = self.task.pkgs_prefix.format(command=clean_action)
            
    #     full_cmd = f"sudo python3 -c \"{python_cmd}\""
    #     stdout, _ = self.run_command(full_cmd)
    #     logger.info(f"{python_cmd} exec output: " + stdout)
    #     logger.info(_)
    
    def execute_python_command(self, action: str):
        """
        Upload a temporary Python script to the remote macOS and execute it safely.
        """

        remote_tmp_path = f"/tmp/task_script_{uuid.uuid4().hex}.py"
        assert self.task is not None
        lines = []
        for line in action.strip().splitlines():
            stripped = line.strip()
            # current_line = line
            if not stripped or stripped.startswith("#"):
                continue
            # if "pyautogui.write" in stripped or "pyautogui.typewrite" in stripped:
            #     indent = line[:len(line) - len(line.lstrip())]
            #     line = f"{indent}pyautogui.keyUp('shift'); {line.lstrip()}"
            # transformed_line = transform_pyautogui_line(line)
            lines.append(line)
        command_block = "\n".join(lines)
        python_code = self.task.pkgs_prefix.format(command=command_block)

        stdout, stderr = "", ""
        try:
            self.connect_sftp()
            with self.sftp_client.open(remote_tmp_path, "w") as remote_script:
                remote_script.write(python_code)

            logger.info(f"Uploaded script to: {remote_tmp_path}")

            full_cmd = f"sudo python3 {remote_tmp_path}"
            stdout, stderr = self.run_command(full_cmd)
            logger.info(f"[exec code] {python_code}")
            logger.info(f"[exec output] {stdout}")
            logger.info(f"[exec error] {stderr}")

            self.run_command(f"rm -f {remote_tmp_path}")
            return {
                "status": "success",
                "output": stdout,
                "error": stderr
            }
        except Exception as e:
            logger.error(f"execute_python_command failed: {e}")
            return {
                "status": "error",
                "output": stdout,
                "error": stderr
            }
        
    def get_screenshot(self, remote_tmp_path: str = "/tmp/fullscreen_dock.png") -> bytes:
        """
        Capture a fullscreen screenshot on the remote macOS system and return it as raw image bytes.

        :param remote_tmp_path: Remote temporary path to store screenshot
        :return: Screenshot image content as bytes (e.g., PNG format); returns b'' on failure
        """
        capture_cmd = f"sudo screencapture -C {remote_tmp_path}"

        try:
            self.connect_ssh()
            logger.info("Executing screencapture command in macOS...")
            stdout, stderr = self.run_command(capture_cmd, decode=False)

            out = stdout.read().decode().strip() if hasattr(stdout, "read") else ""
            err = stderr.read().decode().strip() if hasattr(stderr, "read") else ""
            logger.debug(f"[stdout] {out}")
            logger.debug(f"[stderr] {err}")

            self.connect_sftp()
            with self.sftp_client.open(remote_tmp_path, "rb") as remote_file:
                image_data = remote_file.read()

            logger.info("Screenshot successfully captured and returned.")
            return image_data

        except Exception as e:
            logger.error(f"get_screenshot failed: {e}")
            return b""
        
    def start_recording(self, remote_path="/tmp/screen_recording_test.mp4", resolution="1920x1080", fps=30):
        """
        Starts screen recording on macOS using ffmpeg.
        """
        cmd = f'sudo /usr/local/bin/ffmpeg -y -f avfoundation -framerate {fps} -i "0:none" "{remote_path}" > /dev/null 2>&1 & echo $! > /tmp/ffmpeg_pid'
        # cmd = f'sudo /usr/local/bin/ffmpeg -y -f avfoundation -framerate {fps} -i "0:none" "{remote_path}" &'

        out, err = self.run_command(cmd)
        logger.info(out)
        self.recording_path = remote_path
        self._recording_start_time = time.time()
        logger.info(f"Screen recording started at {remote_path}.")

    def end_recording(self, local_save_path: str):
        """
        Stops screen recording and fetches the file to local path.
        """
        # Find and kill ffmpeg process
        out, err = self.run_command('sudo kill $(cat /tmp/ffmpeg_pid)')
        # logger.info(err)
        logger.info("Stopped screen recording.")

        # Wait briefly to ensure file write is finished
        time.sleep(2)

        # Fetch the file
        remote_path = getattr(self, "recording_path", "/tmp/screen_recording_test.mp4")
        local_path = Path(local_save_path)
        self.connect_sftp()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.sftp_client.get(remote_path, str(local_path))
        logger.info(f"Recording saved to {local_save_path}")
        
    def connect_sftp(self):
        self.connect_ssh()
        if self.sftp_client is None:
            self.sftp_client = self.ssh_client.open_sftp()

    def close_connection(self):
        """
        Close all the connection.
        """
        if self.sftp_client:
            self.sftp_client.close()
            self.sftp_client = None
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None
            
    def init_task_info(self, task_json_path: str = None, task_json_config = None):
        if task_json_path:
            path = Path(task_json_path).resolve()
            if not path.exists():
                raise FileNotFoundError(f"Task JSON file not found at: {path}")
            self.task: Optional[TaskController] = TaskController(json_path=path)
        else:
            self.task: Optional[TaskController] = TaskController(json_config=task_json_config)
            
    def init_task(self, task_json_path: str = None, task_json_config = None):
        
        def disable_caps_lock():
            jxa_script = '''
            ObjC.import("IOKit");

            (() => {
                var ioConnect = Ref();
                var state = Ref();

                $.IOServiceOpen(
                    $.IOServiceGetMatchingService(
                        $.kIOMasterPortDefault,
                        $.IOServiceMatching($.kIOHIDSystemClass)
                    ),
                    $.mach_task_self_,
                    $.kIOHIDParamConnectType,
                    ioConnect
                );

                $.IOHIDGetModifierLockState(ioConnect, $.kIOHIDCapsLockState, state);
                if (state[0]) {
                    $.IOHIDSetModifierLockState(ioConnect, $.kIOHIDCapsLockState, 0);
                }

                $.IOServiceClose(ioConnect);
            })();
            '''.strip()

            stdout, _ = self.run_command(f"osascript -l JavaScript -e {shlex.quote(jxa_script)}")
            logger.info("====Close Caps Lock====")
            logger.info(stdout)
            logger.info(_)

        time.sleep(30) # wait for turn on
        disable_caps_lock()
        
        self.init_task_info(task_json_path, task_json_config)
        if self.task is None:
            raise ValueError("TaskController was not initialized.")

        if (not self.task.config) or len(self.task.config) == 0:
            return
        
        for step in self.task.config:
            step_type = step.get("type")
            parameters = step.get("parameters", {})
            logger.info(f"[Task Set Up] type: {step_type}, parameter: {parameters}, task is setting up!")
            if step_type == "cmd":
                commands = parameters.get("command", [])
                for cmd in commands:
                    stdout, _ = self.run_command(cmd)
                    logger.info(f"[Task Set Up]: CMD {cmd} is done!")
                    logger.info(stdout)
                    # logger.info(_)
            else:
                try:
                    basic_utils = importlib.import_module("desktop_env.macos.utils.basic")
                    if hasattr(basic_utils, step_type):
                        func = getattr(basic_utils, step_type)
                        logger.info(f"Executing: {step_type} with {parameters}")
                        func(self, **parameters)
                        logger.info(f"[Task Set Up]: Basic utils setup is done!")
                    else:
                        logger.warning(f"Function '{step_type}' not found in utils.basic")
                except Exception as e:
                    logger.error(f"Error executing step '{step_type}': {e}")


    def evaluate_task(self):
        """
        Evaluate the task using the evaluation spec provided in `self.task.evaluator`.

        This function executes a list of getter functions and evaluates their outputs
        using metric functions, as specified in the evaluator config.

        Returns:
            bool: True if all/any evaluations pass based on the configured logical conjunction.
        """
        if not self.task or not self.task.evaluator:
            logger.warning("No evaluator found in task.")
            return False

        evaluator = self.task.evaluator
        func_list = evaluator.get("func", [])
        expected_list = evaluator.get("expected", [])
        param_list = evaluator.get("parameters", [{}] * len(func_list))
        conj = evaluator.get("conj", "and")

        if not (len(func_list) == len(expected_list) == len(param_list)):
            raise ValueError("Evaluator 'func', 'parameters', and 'expected' lists must be the same length.")

        results = []
        
        # Reset the applications
        reset_applications(self, self.task.related_apps)

        for func_name, params, expected in zip(func_list, param_list, expected_list):
            # Load the getter function from evaluators.getter (already imported in __init__.py)
            try:
                evaluators_getter = importlib.import_module("desktop_env.macos.evaluators.getter")
                getter_func = getattr(evaluators_getter, func_name)
                # logger.info(getter_func)
            except AttributeError as e:
                logger.error(f"Getter function '{func_name}' not found in 'evaluators': {e}")
                results.append(False)
                continue

            # Execute the getter function
            try:
                output = getter_func(self, **params)
            except Exception as e:
                logger.error(f"Error calling getter '{func_name}': {e}")
                results.append(False)
                continue

            # Evaluate the result using the metric function
            try:
                metric_type = expected.get("type")
                metric_func_name = expected["rules"]["func"]
                metric_params = expected["rules"]["parameters"]

                metric_module = importlib.import_module(f"desktop_env.macos.evaluators.metrics.{metric_type}")
                metric_func = getattr(metric_module, metric_func_name)

                # Call the metric function with correct parameter format
                if isinstance(metric_params, list):
                    match = metric_func(output, *metric_params)
                elif isinstance(metric_params, dict):
                    match = metric_func(output, **metric_params)
                else:
                    match = metric_func(output, metric_params)

                results.append(match)
                logger.info(f"[Evaluation] {func_name} => {output} vs {metric_func_name}({metric_params}) => {match}")

            except Exception as e:
                logger.error(f"Evaluation failed for '{func_name}': {e}")
                results.append(False)

        # Combine results based on conjunction type: 'and' or 'or'
        return all(results) if conj == "and" else any(results)

class TaskController:
    def __init__(self, json_path: Path = None, pkgs_prefix: str = "from AppKit import NSBundle; app_info = NSBundle.mainBundle().infoDictionary(); app_info[\"LSBackgroundOnly\"] = \"1\"; import pyautogui; import time; import pynput; import keyboard; pyautogui.FAILSAFE = False; import os; proxy_url = 'http://10.1.8.5:23128'; os.environ['http_proxy'] = proxy_url; os.environ['https_proxy'] = proxy_url; os.environ['HTTP_PROXY'] = proxy_url; os.environ['HTTPS_PROXY'] = proxy_url; {command}", json_config=None):
        if json_path:
            self.json_path = Path(json_path)
        else:
            self.json_path = None
        if json_config is None:
            self.task = self._load_task()
        else:
            self.task = json_config

        self.task_id = self.task.get("id")
        self.system_img = self.task.get("system_img", "default")
        self.instruction = self.task.get("instruction", "")
        self.config = self.task.get("config", [])
        self.related_apps = self.task.get("related_apps", [])
        self.evaluator = self.task.get("evaluator", {})
        
        self.step_no = 0
        self.action_history = []
        self.pkgs_prefix = pkgs_prefix
        

    def _load_task(self):
        if not self.json_path.exists():
            logger.error(f"Task JSON file not found: {self.json_path}")
            raise FileNotFoundError(f"Missing task definition file: {self.json_path}")

        with open(self.json_path, 'r', encoding='utf-8') as f:
            task_data = json.load(f)
            logger.info(f"Loaded task from {self.json_path}")
            return task_data

    def get_config_steps(self):
        return self.config

    def get_evaluator_spec(self):
        return self.evaluator

    def get_instruction(self):
        return self.instruction

    def get_related_apps(self):
        return self.related_apps
    