#!/bin/bash

# ==============================================================================
# Script to stop and remove running Docker containers based on a specific image.
# Target Image: happysixd/osworld-docker
# Includes a safety check and a confirmation prompt.
# Now supports --exclude parameter to skip specific container IDs.
# ==============================================================================

# --- Configuration ---
TARGET_IMAGE="happysixd/osworld-docker"
EXCLUDE_IDS=()

# Set colors for clearer output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- Function Definitions ---
usage() {
    echo "Usage: $0 [--exclude ID1,ID2,...]"
    echo "Example: $0 --exclude abc123,def456"
    echo "         $0 (no arguments, process all containers)"
    exit 1
}

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --exclude)
            if [[ -n "$2" ]]; then
                IFS=',' read -ra EXCLUDE_IDS <<< "$2"
                shift 2
            else
                echo -e "${RED}Error: --exclude argument requires container IDs${NC}"
                usage
            fi
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Unknown argument: $1${NC}"
            usage
            ;;
    esac
done

echo -e "${YELLOW}Finding containers based on image: ${TARGET_IMAGE}...${NC}"

# 1. Get all container IDs based on the specified image
CONTAINER_IDS=$(docker ps -a --filter "ancestor=${TARGET_IMAGE}" -q)

# 2. Check if there are matching containers
if [ -z "$CONTAINER_IDS" ]; then
  echo -e "${GREEN}No containers found for image '${TARGET_IMAGE}'. Nothing to do.${NC}"
  exit 0
fi

# 3. Filter out container IDs to be excluded
FILTERED_IDS=()
for container_id in $CONTAINER_IDS; do
    should_exclude=false
    for exclude_id in "${EXCLUDE_IDS[@]}"; do
        # Support full ID or partial ID matching
        if [[ "$container_id" == *"$exclude_id"* ]]; then
            echo -e "${YELLOW}Excluding container: $container_id (Matched exclude ID: $exclude_id)${NC}"
            should_exclude=true
            break
        fi
    done
    if [ "$should_exclude" = false ]; then
        FILTERED_IDS+=("$container_id")
    fi
done

# 4. Check if there are still containers to process after filtering
if [ ${#FILTERED_IDS[@]} -eq 0 ]; then
    echo -e "${GREEN}All matching containers have been excluded. No action needed.${NC}"
    exit 0
fi

# 5. List containers to be processed for user confirmation
echo -e "${YELLOW}The following containers based on image '${TARGET_IMAGE}' will be stopped and removed:${NC}"
for container_id in "${FILTERED_IDS[@]}"; do
    docker ps -a --filter "id=$container_id" --format "table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}"
done

echo "" # Print an empty line

# 6. Confirm operation
read -p "Are you sure you want to continue? (y/N): " confirm
if [[ ! $confirm =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Operation cancelled.${NC}"
    exit 0
fi

# 7. Execute stop and remove operations
echo -e "${YELLOW}Stopping containers...${NC}"
for container_id in "${FILTERED_IDS[@]}"; do
    echo "Stopping container: $container_id"
    docker stop "$container_id"
done

echo -e "${YELLOW}Removing containers...${NC}"
for container_id in "${FILTERED_IDS[@]}"; do
    echo "Removing container: $container_id"
    docker rm "$container_id"
done

echo -e "${GREEN}Operation completed!${NC}"
exit 0