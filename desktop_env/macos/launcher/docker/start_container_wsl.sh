#!/bin/bash

docker_name=$1
host_port=$2

if [ -z "$docker_name" ] || [ -z "$host_port" ]; then
    echo "Usage: $0 <docker_name> <host_port>"
    exit 1
fi

sudo docker run -itd \
    --name "$docker_name" \
    --device /dev/kvm \
    -p "$host_port":10022 \
    -v /mnt/wslg/.X11-unix:/tmp/.X11-unix \
    -e "DISPLAY=${DISPLAY:-:0.0}" \
    -v "/home/pipiwu/macos_env/Codes/evalkit_macos/system_image/mac_hdd_ng_copy.img:/home/arch/OSX-KVM/mac_hdd_ng_src.img" \
    -v "/home/pipiwu/macos_env/Codes/evalkit_macos/system_image/BaseSystem.img:/home/arch/OSX-KVM/BaseSystem_src.img" \
    -e CPU='Haswell-noTSX' \
    -e CPUID_FLAGS='kvm=on,vendor=GenuineIntel,+invtsc,vmware-cpuid-freq=on' \
    -e SHORTNAME=sonoma \
    -e USERNAME=pipiwu \
    -e PASSWORD='1234' \
    numbmelon/docker-osx-evalkit-auto:latest


# docker run -it \
#     --name evalkit_macos_auto \
#     --device /dev/kvm \
#     -p 50922:10022 \
#     -p 5901:5901 \
#     -e EXTRA="-vnc 0.0.0.0:1,password=off" \
#     -v /tmp/.X11-unix:/tmp/.X11-unix \
#     -v "/nvme/wuzhenyu/system_image/mac_hdd_ng_copy.img:/home/arch/OSX-KVM/mac_hdd_ng_src.img" \
#     -v "/nvme/wuzhenyu/system_image/BaseSystem.img:/home/arch/OSX-KVM/BaseSystem_src.img" \
#     -e CPU='Haswell-noTSX' \
#     -e CPUID_FLAGS='kvm=on,vendor=GenuineIntel,+invtsc,vmware-cpuid-freq=on' \
#     -e SHORTNAME=sonoma \
#     numbmelon/docker-osx-evalkit-auto:latest

# sudo docker run -it \
#     --name evalkit_macos_auto \
#     --device /dev/kvm \
#     -p 50922:10022 \
#     -p 7901:7901 \
#     -e EXTRA="-vnc 0.0.0.0:1,password=off" \
#     -v /tmp/.X11-unix:/tmp/.X11-unix \
#     -v "/home/wuzhenyu/Codes/VLMEvalkit_GUI/system_image/mac_hdd_ng_copy.img:/home/arch/OSX-KVM/mac_hdd_ng_src.img" \
#     -v "/home/wuzhenyu/Codes/VLMEvalkit_GUI/system_image/BaseSystem.img:/home/arch/OSX-KVM/BaseSystem_src.img" \
#     -e CPU='Haswell-noTSX' \
#     -e CPUID_FLAGS='kvm=on,vendor=GenuineIntel,+invtsc,vmware-cpuid-freq=on' \
#     -e SHORTNAME=sonoma \
#     numbmelon/docker-osx-evalkit-auto:latest