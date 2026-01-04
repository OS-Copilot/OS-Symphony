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
    -e EXTRA="-vnc 0.0.0.0:1,password=off" \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -e CPU='Haswell-noTSX' \
    -e CPUID_FLAGS='kvm=on,vendor=GenuineIntel,+invtsc,vmware-cpuid-freq=on' \
    -v "/nvme/wuzhenyu/system_image/mac_hdd_ng_copy.img:/home/arch/OSX-KVM/mac_hdd_ng_src.img" \
    -v "/nvme/wuzhenyu/system_image/BaseSystem.img:/home/arch/OSX-KVM/BaseSystem_src.img" \
    -e SHORTNAME=sonoma \
    -e USERNAME=pipiwu \
    -e PASSWORD='1234' \
    -e http_proxy="http://wuzhenyu:MmAAByONkSjfmfXsrnq9rqKJPoC7BQMbL1X6pYVJ3tbpPbsmHEHEywYAg1Bd@10.1.20.51:23128" \
    -e https_proxy="http://wuzhenyu:MmAAByONkSjfmfXsrnq9rqKJPoC7BQMbL1X6pYVJ3tbpPbsmHEHEywYAg1Bd@10.1.20.51:23128" \
    -e HTTP_PROXY="http://wuzhenyu:MmAAByONkSjfmfXsrnq9rqKJPoC7BQMbL1X6pYVJ3tbpPbsmHEHEywYAg1Bd@10.1.20.51:23128" \
    -e HTTPS_PROXY="http://wuzhenyu:MmAAByONkSjfmfXsrnq9rqKJPoC7BQMbL1X6pYVJ3tbpPbsmHEHEywYAg1Bd@10.1.20.51:23128" \
    numbmelon/docker-osx-evalkit-auto:latest