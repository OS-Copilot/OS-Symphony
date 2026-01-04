#!/bin/bash

# ==============================================================================
# Script to launch the OSWorld Docker container.
# This script automates cleanup, configuration, and startup.
# ==============================================================================

# 1. Configuration Variables
# ------------------------------------------------------------------------------

# Container and Image Identity
IMAGE_NAME="happysixd/osworld-docker"
CONTAINER_NAME="osworld-test" 

# Resource Allocation
DISK_SIZE="32G"
RAM_SIZE="4G"
CPU_CORES="4"

# Volume Mapping
# !! IMPORTANT: Update this path to the actual location of your .qcow2 file
PATH_TO_VM_QCOW2="TODO"

# Port Mapping (Host:Container)
HOST_VNC_PORT=5923       # Maps to internal 8006 (NoVNC/VNC)
HOST_SERVER_PORT=5099    # Maps to internal 5000 (API Server)
HOST_CHROMIUM_PORT=9289  # Maps to internal 9222 (Chromium Debugging)
HOST_VLC_PORT=8199       # Maps to internal 8080 (VLC)

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== OSWorld Container Launcher ===${NC}"

# 2. Pre-flight Checks
# ------------------------------------------------------------------------------

# Check if Docker is running/installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in PATH.${NC}"
    exit 1
fi

# Check if the VM image exists
if [ ! -f "$PATH_TO_VM_QCOW2" ]; then
    echo -e "${RED}Error: QCOW2 file not found at: $PATH_TO_VM_QCOW2${NC}"
    echo "Please update the 'PATH_TO_VM_QCOW2' variable in the script."
    exit 1
fi

# 3. Cleanup Old Container
# ------------------------------------------------------------------------------
# Check if a container with the same name exists (running or stopped)
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}Found existing container [ $CONTAINER_NAME ]. Removing it...${NC}"
    docker rm -f "$CONTAINER_NAME" > /dev/null
    echo "  -> Old container removed."
fi

# 4. Start Docker Container
# ------------------------------------------------------------------------------
echo -e "${YELLOW}Starting Docker container: $CONTAINER_NAME ...${NC}"

# Note: Removed '--rm' so logs persist if the container crashes.
# Added '--name' to ensure the container gets the specific name defined above.
docker run \
    -d \
    --name "$CONTAINER_NAME" \
    -e "DISK_SIZE=${DISK_SIZE}" \
    -e "RAM_SIZE=${RAM_SIZE}" \
    -e "CPU_CORES=${CPU_CORES}" \
    --cap-add=NET_ADMIN \
    --device=/dev/kvm \
    -v "${PATH_TO_VM_QCOW2}:/System.qcow2:ro" \
    -p "${HOST_VNC_PORT}:8006" \
    -p "${HOST_SERVER_PORT}:5000" \
    -p "${HOST_CHROMIUM_PORT}:9222" \
    -p "${HOST_VLC_PORT}:8080" \
    "$IMAGE_NAME"

# Check exit status of the docker run command
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to start Docker container.${NC}"
    exit 1
fi

# 5. Final Summary
# ------------------------------------------------------------------------------
echo -e "${GREEN}Container started successfully!${NC}"
echo "---------------------------------------------------"
echo -e "${YELLOW}Access Information:${NC}"
echo -e "1. VNC (Web):      http://localhost:$HOST_VNC_PORT"
echo -e "2. Server API:     http://localhost:$HOST_SERVER_PORT"
echo -e "3. Chromium Debug: http://localhost:$HOST_CHROMIUM_PORT"
echo -e "4. VLC Stream:     http://localhost:$HOST_VLC_PORT"
echo "---------------------------------------------------"
echo -e "${YELLOW}Useful Commands:${NC}"
echo -e "View Logs:    docker logs -f $CONTAINER_NAME"
echo -e "Enter Shell:  docker exec -it $CONTAINER_NAME /bin/bash"
echo "---------------------------------------------------"