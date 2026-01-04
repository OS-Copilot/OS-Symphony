#!/bin/bash

# Define the list of target images to clean up
TARGET_IMAGES=(
    "numbmelon/docker-osx-evalkit-auto:latest"
)

echo "=========================================="
echo "Starting cleanup of containers for specified images..."
echo "=========================================="

for img in "${TARGET_IMAGES[@]}"; do
    echo "Checking for containers based on image [ $img ]..."
    
    # Find container IDs using the ancestor filter (-q for IDs only, -a includes stopped ones)
    CONTAINER_IDS=$(docker ps -a -q --filter "ancestor=$img")
    
    if [ -n "$CONTAINER_IDS" ]; then
        echo "  -> Found Container IDs: $(echo $CONTAINER_IDS | tr '\n' ' ')"
        
        # Stop containers
        echo "  -> Stopping containers..."
        docker stop $CONTAINER_IDS 2>/dev/null
        
        # Remove containers
        echo "  -> Removing containers..."
        docker rm $CONTAINER_IDS
        
        echo "  -> [Success] Cleanup completed"
    else
        echo "  -> [Skipped] No related containers found"
    fi
    echo "------------------------------------------"
done

echo "All tasks finished."