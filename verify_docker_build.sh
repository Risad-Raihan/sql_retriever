#!/bin/bash
# Docker Image Verification Script for SQL Retriever API
# Tests the built Docker image locally

set -e  # Exit on any error

echo "🐳 Docker Image Verification Script for SQL Retriever API"
echo "=========================================================="

# Configuration
IMAGE_NAME="sql-retriever-api:latest"
CONTAINER_NAME="sql-retriever-verify"
API_KEY="testkey123"
PORT="8000"
HEALTH_ENDPOINT="http://localhost:${PORT}/health"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Cleanup function
cleanup() {
    echo -e "${YELLOW}🧹 Cleaning up...${NC}"
    docker rm -f $CONTAINER_NAME 2>/dev/null || true
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Step 1: Check if Docker image exists
echo -e "${YELLOW}📦 Checking if Docker image exists...${NC}"
if ! docker image inspect $IMAGE_NAME > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker image '$IMAGE_NAME' not found!${NC}"
    echo "Please build the image first with: docker build -t $IMAGE_NAME ."
    exit 1
fi
echo -e "${GREEN}✅ Docker image found${NC}"

# Step 2: Remove any existing container with the same name
echo -e "${YELLOW}🗑️  Removing existing container if any...${NC}"
docker rm -f $CONTAINER_NAME 2>/dev/null || true

# Step 3: Start the container
echo -e "${YELLOW}🚀 Starting Docker container...${NC}"
CONTAINER_ID=$(docker run -d \
    --name $CONTAINER_NAME \
    -p $PORT:$PORT \
    -e API_KEY=$API_KEY \
    $IMAGE_NAME)

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to start container${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Container started with ID: ${CONTAINER_ID:0:12}${NC}"

# Step 4: Wait for container to be ready
echo -e "${YELLOW}⏳ Waiting for container to be ready (may take 30-60s for model downloads)...${NC}"
WAIT_TIME=0
MAX_WAIT=180  # 3 minutes max wait

while [ $WAIT_TIME -lt $MAX_WAIT ]; do
    if docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Status}}" | grep -q "Up"; then
        # Container is running, try health check
        if curl -s -f $HEALTH_ENDPOINT > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Container is ready and healthy${NC}"
            break
        fi
    else
        echo -e "${RED}❌ Container has stopped running${NC}"
        echo "Container logs:"
        docker logs $CONTAINER_NAME
        exit 1
    fi
    
    echo -n "."
    sleep 3
    WAIT_TIME=$((WAIT_TIME + 3))
done

if [ $WAIT_TIME -ge $MAX_WAIT ]; then
    echo -e "${RED}❌ Container did not become ready within ${MAX_WAIT}s${NC}"
    echo "This is likely due to network issues downloading ML models."
    echo "Container logs:"
    docker logs --tail 20 $CONTAINER_NAME
    echo -e "${YELLOW}ℹ️  The container may still work once models are downloaded.${NC}"
    exit 1
fi

# Step 5: Test health endpoint
echo -e "${YELLOW}🏥 Testing health endpoint...${NC}"
HEALTH_RESPONSE=$(curl -s $HEALTH_ENDPOINT)
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Health endpoint responded successfully${NC}"
    echo "Response: $HEALTH_RESPONSE"
else
    echo -e "${RED}❌ Health endpoint failed${NC}"
    echo "Container may still be initializing. Logs:"
    docker logs --tail 10 $CONTAINER_NAME
fi

# Step 6: Test API with authentication
echo -e "${YELLOW}🔐 Testing API authentication...${NC}"
AUTH_TEST=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $API_KEY" http://localhost:$PORT/stats)
if [ "$AUTH_TEST" = "200" ]; then
    echo -e "${GREEN}✅ API authentication working${NC}"
else
    echo -e "${YELLOW}⚠️  API authentication returned HTTP $AUTH_TEST${NC}"
fi

# Step 7: Show container info
echo -e "${YELLOW}📊 Container Information:${NC}"
echo "Container Name: $CONTAINER_NAME"
echo "Image: $IMAGE_NAME"
echo "Port: $PORT"
echo "API Key: $API_KEY"
echo "Health URL: $HEALTH_ENDPOINT"

# Step 8: Show next steps
echo ""
echo -e "${GREEN}🎉 Docker Image Verification Complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Access API docs at: http://localhost:$PORT/docs"
echo "2. Test queries with: curl -H 'Authorization: Bearer $API_KEY' -X POST http://localhost:$PORT/query -d '{\"question\":\"count customers\"}'"
echo "3. Stop container with: docker rm -f $CONTAINER_NAME"
echo ""
echo "Container will remain running for further testing." 