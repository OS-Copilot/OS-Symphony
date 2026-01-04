#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IMAGE_PATH="${SCRIPT_DIR}/../../system_image/mac_hdd_ng_copy.img"
IMAGE_PATH="$(realpath "$IMAGE_PATH")"

# sudo docker run -it \
#     --name evalkit \
#     --device /dev/kvm \
#     -p 50921:10021 \
#     -v /mnt/wslg/.X11-unix:/tmp/.X11-unix \
#     -e "DISPLAY=${DISPLAY:-:0.0}" \
#     -e GENERATE_UNIQUE=true \
#     -e CPU='Haswell-noTSX' \
#     -e CPUID_FLAGS='kvm=on,vendor=GenuineIntel,+invtsc,vmware-cpuid-freq=on' \
#     -e MASTER_PLIST_URL='https://raw.githubusercontent.com/sickcodes/osx-serial-generator/master/config-custom-sonoma.plist' \
#     -e SHORTNAME=sonoma \
#     -e "DISABLE_AUDIO=true" \
#     -e "NOPICKER=true" \
#     sickcodes/docker-osx:latest

#     sudo docker run -it \
#     --name evalkit_macos \
#     --device /dev/kvm \
#     -p 50922:10022 \
#     -p 5999:5999 \
#     -v /mnt/wslg/.X11-unix:/tmp/.X11-unix \
#     -e "DISPLAY=${DISPLAY:-:0.0}" \
#     docker-osx:naked-auto

sudo docker run -itd \
    --name evalkit_macos_auto \
    --device /dev/kvm \
    -p 50922:10022 \
    -p 5999:5999 \
    -v /mnt/wslg/.X11-unix:/tmp/.X11-unix \
    -e "DISPLAY=${DISPLAY:-:0.0}" \
    -v "/home/pipiwu/macos_env/Codes/evalkit_macos/system_image/mac_hdd_ng_copy.img:/home/arch/OSX-KVM/mac_hdd_ng_src.img" \
    -v "/home/pipiwu/macos_env/Codes/evalkit_macos/system_image/BaseSystem.img:/home/arch/OSX-KVM/BaseSystem_src.img" \
    -e CPU='Haswell-noTSX' \
    -e CPUID_FLAGS='kvm=on,vendor=GenuineIntel,+invtsc,vmware-cpuid-freq=on' \
    -e SHORTNAME=sonoma \
    -e USERNAME=pipiwu \
    -e PASSWORD='1234' \
    docker-osx-evalkit-auto:latest

# CONTAINER_ID=$(sudo docker ps -q -f "name=evalkit_macos")

# # 如果容器启动成功，则复制 .img 文件
# if [ -n "$CONTAINER_ID" ]; then
#     echo "Container started successfully. Copying image..."
    
#     # 复制 .img 文件到容器内指定路径
#     sudo docker cp "$IMAGE_PATH" "$CONTAINER_ID:/home/arch/OSX-KVM/mac_hdd_ng.img"
    
#     echo "Image copied successfully to /home/arch/OSX-KVM/mac_hdd_ng.img inside the container."
# else
#     echo "Failed to start the container."
# fi

# sudo docker run -it \
#     --name evalkit_macos \
#     --device /dev/kvm \
#     -p 50922:10022 \
#     -p 5999:5999 \
#     -v /mnt/wslg/.X11-unix:/tmp/.X11-unix \
#     -v "${IMAGE_PATH}:/image" \
#     -e "DISPLAY=${DISPLAY:-:0.0}" \
#     -e "IMAGE_PATH=/image" \
#     -e GENERATE_UNIQUE=true \
#     -e CPU='Haswell-noTSX' \
#     -e CPUID_FLAGS='kvm=on,vendor=GenuineIntel,+invtsc,vmware-cpuid-freq=on' \
#     -e MASTER_PLIST_URL='https://raw.githubusercontent.com/sickcodes/osx-serial-generator/master/config-custom-sonoma.plist' \
#     -e SHORTNAME=sonoma \
#     -e "DISABLE_AUDIO=true" \
#     sickcodes/docker-osx:latest