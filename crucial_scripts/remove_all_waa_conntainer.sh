#!/bin/bash

# ==============================================================================
# Script to stop and remove running Docker containers for a list of images.
# ==============================================================================

# Define the list of target images to clean up
TARGET_IMAGES=(
    "yang695/winarena:latest"
)

# Alternative image example
# TARGET_IMAGES=(
#     "windowsarena/winarena:latest"
# )

# Set colors for clearer output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Starting cleanup of containers for specified images..."
echo "=========================================="

for img in "${TARGET_IMAGES[@]}"; do
    echo -e "${YELLOW}Checking for containers based on image [ $img ]...${NC}"
    
    # Use ancestor filter to find container IDs (-q for ID only, -a for all statuses)
    CONTAINER_IDS=$(docker ps -a -q --filter "ancestor=$img")
    
    if [ -n "$CONTAINER_IDS" ]; then
        # Format IDs for display (replace newlines with spaces)
        DISPLAY_IDS=$(echo "$CONTAINER_IDS" | tr '\n' ' ')
        echo "  -> Found Container IDs: $DISPLAY_IDS"
        
        # Stop containers
        echo "  -> Stopping containers..."
        # We use unquoted $CONTAINER_IDS here to pass multiple IDs as separate arguments
        docker stop $CONTAINER_IDS 2>/dev/null
        
        # Remove containers
        echo "  -> Removing containers..."
        docker rm $CONTAINER_IDS
        
        echo -e "  -> ${GREEN}[Success] Cleanup complete${NC}"
    else
        echo -e "  -> ${GREEN}[Skip] No related containers found${NC}"
    fi
    echo "------------------------------------------"
done

echo -e "${GREEN}All tasks completed.${NC}"