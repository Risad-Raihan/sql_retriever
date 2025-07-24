#!/bin/bash
set -e

echo "🚀 Runpod Deployment Script for SQL Retriever (Simplified)"

# Configuration
PROJECT_NAME="sql-retriever"
GCP_PROJECT="heroic-overview-466605-p6"
GCP_BUCKET="sql-retriever-models"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check prerequisites
print_step "Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

print_success "Docker is installed"

# Set GCP project
print_step "Setting GCP project..."
gcloud config set project $GCP_PROJECT

# Create dummy GCP key for Docker build (will be replaced with real one)
print_step "Creating placeholder service account key..."
cat > gcp-key.json << EOF
{
  "type": "service_account",
  "project_id": "$GCP_PROJECT",
  "private_key_id": "placeholder",
  "private_key": "-----BEGIN PRIVATE KEY-----\nPLACEHOLDER\n-----END PRIVATE KEY-----\n",
  "client_email": "runpod-service-account@$GCP_PROJECT.iam.gserviceaccount.com",
  "client_id": "placeholder",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
}
EOF

print_warning "⚠️  IMPORTANT: Replace gcp-key.json with real service account key before deployment!"

# Build Docker images
print_step "Building Docker images..."

# Build LLM GPU image
print_step "Building GPU LLM image..."
docker build -f Dockerfile_llm -t ${PROJECT_NAME}-llm:latest .
if [ $? -eq 0 ]; then
    print_success "GPU LLM image built successfully"
else
    print_error "Failed to build GPU LLM image"
    exit 1
fi

# Build Embedding CPU image
print_step "Building CPU Embedding image..."
docker build -f Dockerfile_embedding -t ${PROJECT_NAME}-embedding:latest .
if [ $? -eq 0 ]; then
    print_success "CPU Embedding image built successfully"
else
    print_error "Failed to build CPU Embedding image"
    exit 1
fi

# Save Docker images for Runpod upload
print_step "Saving Docker images for Runpod upload..."

mkdir -p ./docker-images

print_step "Saving LLM image (this may take several minutes)..."
docker save ${PROJECT_NAME}-llm:latest | gzip > ./docker-images/${PROJECT_NAME}-llm.tar.gz

print_step "Saving Embedding image..."
docker save ${PROJECT_NAME}-embedding:latest | gzip > ./docker-images/${PROJECT_NAME}-embedding.tar.gz

print_success "Docker images saved to ./docker-images/"

# Create deployment summary
cat > deployment-summary.md << EOF
# Runpod Deployment Summary

## Docker Images Built:
- **LLM Service (GPU)**: \`${PROJECT_NAME}-llm:latest\`
  - File: \`./docker-images/${PROJECT_NAME}-llm.tar.gz\`
  - For: RTX 3090 GPU pod
  - Port: 8000

- **Embedding Service (CPU)**: \`${PROJECT_NAME}-embedding:latest\`
  - File: \`./docker-images/${PROJECT_NAME}-embedding.tar.gz\`
  - For: CPU pod (2 vCPU, 4GB RAM)
  - Port: 8000

## IMPORTANT: Before Deployment
1. Create service account in GCP Console:
   - Go to IAM & Admin > Service Accounts
   - Create "runpod-service-account" 
   - Grant "Storage Object Viewer" role
   - Download JSON key as gcp-key.json
2. Replace the placeholder gcp-key.json with real one
3. Upload images to Runpod (see GUIDE.md)

## Next Steps:
1. Get real service account key from GCP Console
2. Upload images to Runpod
3. Create GPU pod with RTX 3090
4. Create CPU pod with 2 vCPU, 4GB RAM
5. Get pod URLs and update GCP Cloud Run environment variables
6. Run integration tests

## Environment Variables Needed:
- EMBEDDING_URL: CPU pod public URL
- LLM_URL: GPU pod public URL  
- API_KEY: Your secure API key

## Costs (Estimated):
- GPU Pod: \$0.44/hour (RTX 3090)
- CPU Pod: \$0.02-0.10/hour (2 vCPU, 4GB)
EOF

print_success "Deployment preparation complete!"
echo
echo "📄 Files created:"
echo "  - ./docker-images/${PROJECT_NAME}-llm.tar.gz (GPU image)"
echo "  - ./docker-images/${PROJECT_NAME}-embedding.tar.gz (CPU image)"
echo "  - ./gcp-key.json (PLACEHOLDER - needs replacement)"
echo "  - ./deployment-summary.md (deployment guide)"
echo
print_warning "🔑 NEXT STEPS:"
echo "1. Create service account in GCP Console (see deployment-summary.md)"
echo "2. Replace gcp-key.json with real service account key"
echo "3. Follow GUIDE.md to deploy on Runpod"

# Display estimated costs
echo
print_warning "💰 Estimated Costs:"
echo "  - GPU Pod (RTX 3090): ~\$0.44/hour"
echo "  - CPU Pod (2 vCPU): ~\$0.02-0.10/hour"
echo "  - Total: ~\$0.46-0.54/hour"
echo
print_step "Remember to stop pods when not in use to save costs!" 