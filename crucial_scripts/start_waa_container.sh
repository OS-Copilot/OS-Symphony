#!/bin/bash

# ==============================================================================
# Script to launch the WinArena (Windows Server) Docker container.
# ==============================================================================

# 1. Configuration Variables
# ------------------------------------------------------------------------------

# Container and Image Identity
IMAGE_NAME="yang695/winarena:latest"
CONTAINER_NAME="winarena-test"

# Host Storage Directory (Maps to /storage inside container)
HOST_STORAGE_DIR="TODO"

# Port Configuration
PORT_BROWSER=5989  # VNC/NoVNC Browser Access (Internal: 8006)
PORT_RDP=3399      # Remote Desktop Protocol (Internal: 3389)
PORT_API=5101      # HTTP API for Client Control (Internal: 5000)

# Environment / Hardware
RAM_SIZE="8G"
CPU_CORES="8"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== WinArena Container Launcher ===${NC}"

# 2. Pre-flight Checks
# ------------------------------------------------------------------------------

# Check if Docker is running
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in PATH.${NC}"
    exit 1
fi

# Check and Create Storage Directory
if [ ! -d "$HOST_STORAGE_DIR" ]; then
    echo -e "${YELLOW}Storage directory not found. Creating: $HOST_STORAGE_DIR${NC}"
    mkdir -p "$HOST_STORAGE_DIR"
else
    echo "Storage directory exists: $HOST_STORAGE_DIR"
fi

# Check KVM (Hardware Acceleration)
KVM_DEVICE_FLAG=""
if [ -e /dev/kvm ]; then
    echo -e "${GREEN}✅ KVM detected. Hardware acceleration enabled.${NC}"
    KVM_DEVICE_FLAG="--device=/dev/kvm"
else
    echo -e "${RED}⚠️  WARNING: KVM not detected (/dev/kvm).${NC}"
    echo "The VM may run very slowly or fail to start."
    # We proceed, but the docker run command might fail if it strictly requires the device
    # If strictly required, uncomment the exit below:
    # exit 1
fi

# 3. Cleanup Old Container
# ------------------------------------------------------------------------------
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}Removing existing container [ $CONTAINER_NAME ]...${NC}"
    docker rm -f "$CONTAINER_NAME" > /dev/null
    echo "  -> Old container removed."
fi

# 4. Start Docker Container
# ------------------------------------------------------------------------------
echo -e "${YELLOW}Starting container...${NC}"

# Logic Explanation:
# 1. --privileged / --cap-add=NET_ADMIN: Required for VM networking and KVM.
# 2. --entrypoint /bin/bash: Overrides default entrypoint to allow custom command.
# 3. -c "./entry_setup.sh & tail -f /dev/null": Runs the setup script in background, keeps container alive.

docker run -d \
    --name "${CONTAINER_NAME}" \
    --privileged \
    --cap-add=NET_ADMIN \
    --stop-timeout 50 \
    --platform linux/amd64 \
    $KVM_DEVICE_FLAG \
    -e KVM=Y \
    --add-host host.docker.internal:host-gateway \
    -p "${PORT_BROWSER}:8006" \
    -p "${PORT_RDP}:3389" \
    -p "${PORT_API}:5000" \
    -v "${HOST_STORAGE_DIR}:/storage" \
    -e RAM_SIZE="${RAM_SIZE}" \
    -e CPU_CORES="${CPU_CORES}" \
    --entrypoint /bin/bash \
    --shm-size "2g" \
    "${IMAGE_NAME}" \
    -c "./entry_setup.sh & tail -f /dev/null"

# Check exit status
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to start Docker container.${NC}"
    exit 1
fi

# 5. Final Summary
# ------------------------------------------------------------------------------
echo -e "${GREEN}Container started successfully!${NC}"
echo "---------------------------------------------------"
echo -e "${YELLOW}Connection Information:${NC}"
echo -e "1. API (Client):   http://127.0.0.1:${PORT_API}"
echo -e "2. Browser VNC:    http://127.0.0.1:${PORT_BROWSER}"
echo -e "3. RDP Access:     127.0.0.1:${PORT_RDP}"
echo "---------------------------------------------------"
echo -e "${YELLOW}Useful Commands:${NC}"
echo -e "View Logs:    docker logs -f ${CONTAINER_NAME}"
echo -e "Enter Shell:  docker exec -it ${CONTAINER_NAME} /bin/bash"
echo "---------------------------------------------------"
echo "Note: It may take a few moments for the internal Windows VM to boot."