import subprocess
import docker
import logging
import os
import shutil
import time
import socket
import platform
import psutil # 需要 pip install psutil
import requests
from pathlib import Path
from filelock import FileLock

logger = logging.getLogger("desktopenv.providers.docker")
LOCK_TIMEOUT = 10000

class WindowsDockerProvider:
    def __init__(self, 
                 image_name="yang695/winarena:latest", 
                 vm_storage_path="./storage", 
                 vm_backup_path="./storage_backup",
                 ram_size="8G",
                 cpu_cores="4"):
        """
        Args:
            image_name: Docker 镜像名称
            vm_storage_path: 挂载到容器内的运行目录
            vm_backup_path: 干净的快照源目录
        """
        self.client = docker.from_env()
        self.image_name = image_name
        
        # 转换为绝对路径
        self.vm_storage_path = os.path.abspath(vm_storage_path)
        self.vm_backup_path = os.path.abspath(vm_backup_path)
        
        self.ram_size = ram_size
        self.cpu_cores = cpu_cores
        
        # --- 端口状态 ---
        self.container = None
        self.server_port = None    # 映射到容器 5000 (Agent API)
        self.rdp_port = None       # 映射到容器 3389 (RDP)
        self.chromium_port = None  # 映射到容器 9222 (Chrome DevTools) <--- 新增
        
        # 锁文件路径
        temp_dir = Path(os.getenv('TEMP') if platform.system() == 'Windows' else '/tmp')
        self.lock_file = temp_dir / "win_docker_port.lck"

    def _get_used_ports(self):
        """
        获取当前系统所有被占用的端口 (参考 Linux Provider 实现)
        """
        # 1. 获取系统占用的端口
        system_ports = set(conn.laddr.port for conn in psutil.net_connections())
        
        # 2. 获取 Docker 容器映射占用的端口 (防止 Docker 自身未完全释放)
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
        """
        寻找可用端口
        Args:
            start_port: 起始扫描端口
            exclude_ports: 本次分配中已经预选的端口 (避免分配重复)
        """
        if exclude_ports is None:
            exclude_ports = set()

        used_ports = self._get_used_ports()
        port = start_port
        
        # 扫描直到 65535
        while port < 65535:
            if port not in used_ports and port not in exclude_ports:
                return port
            port += 1
            
        raise RuntimeError(f"No free ports available starting from {start_port}")

    def _wait_for_server(self, timeout=180):
        """等待 Windows Agent (5000端口) 启动"""
        start_time = time.time()
        # 注意：这里使用动态分配的 server_port
        url = f"http://127.0.0.1:{self.server_port}/probe" 
        
        logger.info(f"Waiting for Windows Agent at {url}...")
        while time.time() - start_time < timeout:
            try:
                requests.get(url, timeout=2)
                logger.info("Windows Agent is ready!")
                return True
            except requests.exceptions.RequestException:
                time.sleep(2)
        
        # 必须给我启动喽!
        raise TimeoutError("Windows Agent failed to start within timeout.")

    def start_emulator(self, headless=True):
        """
        启动 Docker 容器，动态分配 3 个端口
        """
        try_times = 3
    
        for i in range(try_times):
            lock = FileLock(str(self.lock_file), timeout=LOCK_TIMEOUT)
            # 使用文件锁，防止多进程并行测试时端口冲突
            try:
                with lock:
                    # 1. 动态申请端口
                    self.server_port = self._get_available_port(5000)
                    
                    self.rdp_port = self._get_available_port(
                        3389, 
                        exclude_ports={self.server_port}
                    )
                    
                    self.chromium_port = self._get_available_port(
                        9222, 
                        exclude_ports={self.server_port, self.rdp_port}
                    )

                    self.brower_port = self._get_available_port(
                        5910, 
                        exclude_ports={self.server_port, self.rdp_port, self.chromium_port}
                    )

                    logger.info(f"Allocated ports -> API: {self.server_port}, RDP: {self.rdp_port}, Chrome: {self.chromium_port}, Browser(?): {self.brower_port}")

                    # 2. 准备 Docker 参数
                    devices = []
                    if os.path.exists("/dev/kvm"):
                        devices.append("/dev/kvm")
                    
                    # 添加外网代理
                    environment = {
                        "RAM_SIZE": self.ram_size,
                        "CPU_CORES": self.cpu_cores,
                        "KVM": "Y" if devices else "N",
                        "OPENAI_API_KEY_FOR_CHECK_SETUP": "sk-lZYCt4IDPC0kBJU3wO03KjmNhgE5f4p5MsZQvYBpw2A4i64D",
                        "OPENAI_BASE_URL_FOR_CHECK_SETUP": "https://api.boyuerichdata.opensphereai.com/v1"
                    }

                    # 3. 启动容器
                    logger.info(f"Starting container using storage: {self.vm_storage_path}")
                    self.container = self.client.containers.run(
                        "winarena-v2:latest",
                        detach=True,
                        privileged=True,
                        devices=devices,
                        platform="linux/amd64",
                        cap_add=["NET_ADMIN"],
                        shm_size="500m",
                        ports={
                            '5000': self.server_port,   # Agent API
                            '3389': self.rdp_port,      # RDP
                            '9222': self.chromium_port,  # Chrome DevTools <--- 关键映射
                            '8006': self.brower_port
                        },
                        volumes={
                            self.vm_storage_path: {'bind': '/storage', 'mode': 'rw'}
                        },
                        environment=environment,
                        extra_hosts={"host.docker.internal": "host-gateway"},
                        entrypoint="/bin/bash",
                        command='-c "./entry_setup.sh & tail -f /dev/null"'
                    )
                    
                    # 4. 等待服务就绪
                    self._wait_for_server()
                    return
                
            except Exception as e:
                logger.error(f"Time {i}: Failed to start container: {e}")
                # 如果启动失败，清理残留
                self.stop_emulator()
        
        raise Exception("Windows Agent failed to start within N times.")

    def stop_emulator(self):
        """停止并移除容器"""
        if self.container:
            try:
                logger.info("Stopping container...")
                # 1. 停止容器 (同步操作，会等待直到停止或超时)
                self.container.stop(timeout=300)
                
                logger.info("Removing container...")
                # 2. 删除容器 (同步操作)
                # v=True 删除关联的卷 (如果需要)
                # force=True 强制删除 (即使上面 stop 失败了也能删)
                self.container.remove(force=True) 
                
            except Exception as e:
                logger.warning(f"Error stopping container: {e}")
            finally:
                self.container = None
                # 清空端口记录
                self.server_port = None
                self.rdp_port = None
                self.chromium_port = None

    def revert_to_snapshot(self):
        """
        回滚快照：停止 -> 替换文件 -> 启动
        使用系统级命令 cp 替代 shutil 以确保 VM 镜像文件的完整性和稀疏性。
        """
        logger.info("Reverting snapshot...")
        self.stop_emulator()
        
        try:
            # 1. 清理旧数据 (运行目录)
            if os.path.exists(self.vm_storage_path):
                # 删除旧的运行目录
                # shutil.rmtree 删除目录本身是很可靠的，这里可以保留使用，
                # 或者为了统一风格也可以用 subprocess.run(['rm', '-rf', self.vm_storage_path])
                shutil.rmtree(self.vm_storage_path, ignore_errors=True)
            
            # 2. 从备份恢复
            if os.path.exists(self.vm_backup_path):
                logger.info(f"Restoring from {self.vm_backup_path} to {self.vm_storage_path} ...")
                
                # 判断备份源是文件还是目录，采取不同的 cp 策略
                if os.path.isdir(self.vm_backup_path):
                    subprocess.check_call([
                        'cp', '-r', '--sparse=always', 
                        self.vm_backup_path, 
                        self.vm_storage_path
                    ])

                logger.info("Snapshot files restored successfully.")
            else:
                # 备份不存在的情况
                os.makedirs(self.vm_storage_path, exist_ok=True)
                logger.warning(f"Backup path {self.vm_backup_path} not found, initialized empty storage.")

        except subprocess.CalledProcessError as e:
            logger.error(f"Snapshot revert failed during system copy: {e}")
            raise e
        except Exception as e:
            logger.error(f"Snapshot revert failed: {e}")
            raise e

        self.start_emulator()

    def get_connection_info(self):
        """
        返回完整的连接信息给 DesktopEnv
        """
        if not all([self.server_port, self.rdp_port, self.chromium_port]):
            logger.warning("Ports are not fully allocated yet.")
            
        return {
            "ip": "127.0.0.1",
            "server_port": self.server_port,
            "rdp_port": self.rdp_port,
            "chromium_port": self.chromium_port,  # <--- 返回这个端口
            "browser_port": self.brower_port
        }