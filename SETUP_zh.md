# 🛠️ 环境搭建与配置指南

本文档详细说明了评测所需的三个操作系统环境（Linux、Windows 和 MacOS）的资源下载、启动及网络代理配置流程。

## 1. 资源下载

请根据下表下载所需的 Docker 镜像及虚拟机“黄金镜像”文件。

| 组件               | Linux (OSWorld / SearchEnv)                                  | Windows (WindowsAgentArena)                                  | MacOS (MacOSArena)                                           |
| :----------------- | :----------------------------------------------------------- | :----------------------------------------------------------- | :----------------------------------------------------------- |
| **Docker Image**   | `docker pull happysixd/osworld-docker`                       | `docker pull yang695/winarena:latest`                        | `docker pull numbmelon/docker-osx-evalkit-auto:latest`       |
| **Golden Image**   | **[Ubuntu.qcow2](https://huggingface.co/datasets/xlangai/ubuntu_osworld/resolve/main/Ubuntu.qcow2.zip)** | **[waa.tar.gz](https://huggingface.co/datasets/YYangzzzz/OSSymphony/blob/main/winarena/waa.tar.gz)**<br>*(解压后请将文件夹命名为 `golden_image`)* | **[BaseSystem.img](https://huggingface.co/OpenGVLab/ScaleCUA_Env/blob/main/resources/macos/BaseSystem.img)** + **[mac_hdd_ng.img](https://huggingface.co/OpenGVLab/ScaleCUA_Env/blob/main/resources/macos/mac_hdd_ng.img)** |
| **Start Script**   | `crucial_scripts/start_osworld_container.sh`                 | `crucial_scripts/start_waa_container.sh`                     | `crucial_scripts/start_Macosarena_container.sh`              |
| **Cleanup Script** | `crucial_scripts/remove_all_osworld_container.sh`            | `crucial_scripts/remove_all_waa_conntainer.sh`               | `crucial_scripts/remove_all_Macosarena_container.sh`         |

### 注意事项：

1.  **必要环境：** Linux 环境同时也作为 Searcher 的运行环境，因此是**必须**的。
2.  **启动脚本：** 上表提供的 "Start Script" 用于开启单台虚拟机进行调试与配置（如配置代理）。
    *   **操作：** 请在使用前编辑脚本，填入您本地下载好的黄金镜像路径。
    *   **VNC：** 推荐使用 **RealVNC** 连接虚拟机的 GUI 界面。
3.  **持久化机制：**
    *   **Linux/MacOS：** 在 GUI 界面上的修改**不会**自动反映到原始黄金镜像文件中。
    *   **Windows：** 操作会**直接修改**原始镜像文件。**请务必在一切操作开始之前对原 `golden_image` 文件夹进行备份。**
4.  **清理脚本：** "Cleanup Script" 提供了一键清除评测残留容器的功能。

---

## 2. 全局代理配置

在内网下，网络配置是评测环境中最最关键的一环。我们需要通过启动评测前修改虚拟机内部设置（系统级 + Flask Server 级）+ 启动评测时使用`proxy`参数，来实现**全局代理配置**。

**注意：** 

1. Flask Server 作为开机自启脚本运行，系统级代理对其无效，因此必须单独手动配置。
2. Windows 和 Mac 的代理已经写在了黄金镜像内，如果宿主机环境无需代理，也请注意同样需要参照下述流程来删除代理！

### 🐧 Linux (OSWorld)

Docker 挂载镜像时通常为只读层。为了修改内部的 Flask Server 的 `main.py`，我们需要使用 `libguestfs-tools` 直接向 `.qcow2` 文件注入修改。

**步骤：**

1.  **定位文件：** 在本地代码库中打开 `desktop_env/osworld/server/main.py`。
2.  **编辑代理：** 修改文件顶部的 `proxy_url` 变量为您的代理地址（格式：`http://<ip>:<port>`）。
3.  **安装工具（以 CentOS 为例）：**
    
    ```bash
    sudo yum install libguestfs-tools
    sudo systemctl start libvirtd
    ```
4.  **启动 Guestfish：**以可写模式启动 guestfish：
    
    ```bash
    sudo guestfish -a /path/to/your_vm.qcow2 -i
    ```
5.  **注入文件：**在交互式 shell (`><fs>`) 中执行以下命令以永久修改镜像：
    
    ```bash
    upload desktop_env/osworld/server/main.py /home/user/server/main.py
    ```

6. **查看修改**：在虚拟机内打开 `main.py` ，预期将成功修改![image-20251228164031408](assets/linux_1.png)

> *注：Linux 的系统级代理将在启动评测时通过参数配置，无需修改镜像。*

### 🪟 Windows (WindowsAgentArena)

Windows 镜像直接挂载。在虚拟机内部所做的更改会直接保存到源文件中。**请务必先备份。**

**步骤：**

1. **系统代理：** 进入 **Settings** > **Network & Internet** > **Use a proxy server**，配置 IP 和端口，并在 **Don’t use the proxy server for local addresses** 处打勾✔。

   ![image-20251226184459698](assets/windows_1.png)

2. **Server 代理：** 在虚拟机内打开 `C:\OEM\server\main.py`，找到 `proxy_url` 变量并设置代理地址。

   ![image-20251226184559008](assets/windows_2.png)

#### ⚠️ 重要：镜像过期与重构

Windows 企业评估版镜像存在 90 天有效期（约于 **2026.03.10** 到期）。过期后系统将在开机 1 小时后自动关机，如果您需要评测长程任务（>1h），除作弊方法外需要重新构建黄金镜像。

**重构提示：**

1.  无需重新构建 Docker 镜像，只需重新生成虚拟机黄金镜像。
2.  **Setup 脚本代理：** 重构时，请在 `setup.ps1` 文件顶部添加以下代码，以确保依赖项能正常下载：

    ```powershell
    # 1. 设置你的代理地址 (请根据实际情况修改 IP 和 端口)
    $ProxyHost = "10.1.8.5"  # 替换为你宿主机的 IP 或局域网代理服务器 IP
    $ProxyPort = "23128"     # 替换为你的代理端口 (如 Clash 通常是 7890)
    $ProxyUri = "http://$($ProxyHost):$($ProxyPort)"
    
    Write-Host "正在配置系统代理指向: $ProxyUri ..." -ForegroundColor Cyan
    
    # 2. 配置 PowerShell 也就是 .NET 的默认 Web 代理
    #    这解决了 Invoke-WebRequest, System.Net.WebClient 以及大部分 PowerShell 下载函数的联网问题
    $WebProxy = New-Object System.Net.WebProxy($ProxyUri)
    [System.Net.WebRequest]::DefaultWebProxy = $WebProxy
    
    # 3. 配置环境变量代理
    #    这解决了 Python (pip), Git, Curl 以及其他第三方工具的联网问题
    $env:HTTP_PROXY = $ProxyUri
    $env:HTTPS_PROXY = $ProxyUri
    $env:http_proxy = $ProxyUri
    $env:https_proxy = $ProxyUri
    $env:PIP_TRUSTED_HOST = "pypi.org pypi.python.org files.pythonhosted.org"
    
    # 4. 配置 WinHTTP 代理 (系统级)
    #    某些底层服务或安装程序可能不走用户环境变量，需要用 netsh 配置
    Start-Process -FilePath "netsh" -ArgumentList "winhttp set proxy $ProxyHost`:$ProxyPort" -NoNewWindow -Wait
    
    Write-Host "代理配置完成。" -ForegroundColor Green
    ```
3.  **LibreOffice：** LibreOffice 目前即使配置代理也会下载失败。请在自动化安装完成后手动下载并安装。

### 🍎 MacOS (MacOSArena)

Docker 会创建覆盖层。在 GUI 中所做的更改**不会**自动保存到源 `Mac_hdd_ng.img` 文件中。您必须手动提取修改后的文件。

**步骤：**

1. **系统代理：** 进入 **System Settings** > **Network** > **Ethernet** > **Details** > **Proxies**。分别配置 **HTTP** 和 **HTTPS** 的代理。

   ![image-20251228170510410](assets/Mac_1.png)

2. **保存更改：**将修改后的虚拟机镜像从容器中拷贝出来，作为接下来评测的黄金镜像：

   ```bash
   docker cp <your_container_id>:/home/arch/OSX-KVM/mac_hdd_ng.img <target_path>/mac_hdd_ng_proxy.img
   ```

> *注：MacOS 环境通过 SSH 传输命令，不使用 Flask Server，因此无需配置服务端代码代理。*