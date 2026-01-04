#!/bin/bash

# ==============================================================================
# Script to launch macOS Docker container and wait for SSH availability.
# Note: Connect via RealVNC to the defined vnc_port!
# ==============================================================================

# 1. Configuration Variables
# ------------------------------------------------------------------------------
IMAGE_NAME="numbmelon/docker-osx-evalkit-auto:latest"
CONTAINER_NAME="macosarena-test"
HOST_PORT=8005
VNC_PORT=5929
SSH_USER="pipiwu"
SSH_PASS="1234"

# Image Paths (Extracted for easier modification)
IMG_HDD="TODO"
IMG_BASE="TODO"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== macOS Container Launcher ===${NC}"

# 2. Pre-flight Checks
# ------------------------------------------------------------------------------
# Check for sshpass
if ! command -v sshpass &> /dev/null; then
    echo -e "${RED}Error: sshpass is not installed.${NC}"
    echo "Please install it (e.g., sudo apt install sshpass) and try again."
    exit 1
fi

# Check if source images exist
if [ ! -f "$IMG_HDD" ]; then
    echo -e "${RED}Error: HDD Image not found at: $IMG_HDD${NC}"
    exit 1
fi

if [ ! -f "$IMG_BASE" ]; then
    echo -e "${RED}Error: BaseSystem Image not found at: $IMG_BASE${NC}"
    exit 1
fi

# 3. Cleanup Old Container
# ------------------------------------------------------------------------------
if sudo docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}Found existing container [ $CONTAINER_NAME ]. Removing it...${NC}"
    sudo docker rm -f "$CONTAINER_NAME" > /dev/null
    echo "  -> Old container removed."
fi

# 4. Start Docker Container
# ------------------------------------------------------------------------------
echo -e "${YELLOW}Starting Docker container: $CONTAINER_NAME ...${NC}"

# Note: Using 'sudo' as per original script. Ensure user has permissions.
sudo docker run -itd \
    --name "$CONTAINER_NAME" \
    --device /dev/kvm \
    -p "$HOST_PORT":10022 \
    -p "$VNC_PORT":5901 \
    -e EXTRA="-vnc 0.0.0.0:1,password=off" \
    -e RAM_SIZE="16G" \
    -e CPU_CORES="8" \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -e CPU='Haswell-noTSX' \
    -e CPUID_FLAGS='kvm=on,vendor=GenuineIntel,+invtsc,vmware-cpuid-freq=on' \
    -v "$IMG_HDD:/home/arch/OSX-KVM/mac_hdd_ng_src.img" \
    -v "$IMG_BASE:/home/arch/OSX-KVM/BaseSystem_src.img" \
    -e SHORTNAME=sonoma \
    -e USERNAME="$SSH_USER" \
    -e PASSWORD="$SSH_PASS" \
    "$IMAGE_NAME"

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to start Docker container.${NC}"
    exit 1
fi

echo -e "${GREEN}Container started successfully.${NC}"

# 5. Loop Check for SSH Connection
# ------------------------------------------------------------------------------
echo "---------------------------------------------------"
echo "Waiting for SSH service on localhost:$HOST_PORT..."
echo "User: $SSH_USER"
echo "---------------------------------------------------"

MAX_RETRIES=60  # 60 * 5 seconds = 5 minutes timeout
COUNT=0

while [ $COUNT -lt $MAX_RETRIES ]; do
    # Try to connect
    sshpass -p "$SSH_PASS" ssh \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=2 \
        -o LogLevel=ERROR \
        -p "$HOST_PORT" \
        "$SSH_USER"@localhost "exit" 2>/dev/null
    
    # Check exit status of ssh command
    if [ $? -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✅ SSH Connection Successful! The container is ready.${NC}"
        break
    fi

    echo -n "."
    sleep 5
    ((COUNT++))
done

if [ $COUNT -eq $MAX_RETRIES ]; then
    echo ""
    echo -e "${RED}❌ Timeout: SSH service did not become ready in time.${NC}"
    echo "Please check the container logs: sudo docker logs $CONTAINER_NAME"
    exit 1
fi

# 6. Final Summary
# ------------------------------------------------------------------------------
echo "---------------------------------------------------"
echo -e "${GREEN}Access Information:${NC}"
echo -e "1. ${YELLOW}SSH:${NC}    sshpass -p '$SSH_PASS' ssh -p $HOST_PORT $SSH_USER@localhost"
echo -e "2. ${YELLOW}VNC:${NC}    Connect to localhost:$VNC_PORT (No password)"
echo "---------------------------------------------------"