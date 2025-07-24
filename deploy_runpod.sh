#!/bin/bash
set -e

echo "🚀 Runpod Deployment Script for SQL Retriever"

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

if ! command -v gcloud &> /dev/null; then
    print_error "Google Cloud SDK is not installed. Please install it first."
    exit 1
fi

# Authenticate with GCP
print_step "Authenticating with Google Cloud..."
gcloud auth login
gcloud config set project $GCP_PROJECT

# Create GCP service account key if it doesn't exist
if [ ! -f "gcp-key.json" ]; then
    print_step "Creating GCP service account key..."
    
    SERVICE_ACCOUNT_NAME="runpod-service-account"
    SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${GCP_PROJECT}.iam.gserviceaccount.com"
    
    # Create service account
    gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
        --display-name="Runpod Service Account" \
        --description="Service account for Runpod access to GCP resources" || true
    
    # Grant necessary permissions
    gcloud projects add-iam-policy-binding $GCP_PROJECT \
        --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --role="roles/storage.objectViewer"
    
    # Create and download key
    gcloud iam service-accounts keys create gcp-key.json \
        --iam-account=$SERVICE_ACCOUNT_EMAIL
    
    print_success "Service account key created"
else
    print_success "GCP service account key already exists"
fi

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

# Upload models to GCP bucket (optional - for faster pod startup)
print_step "Setting up GCP bucket for model caching..."

# Create bucket if it doesn't exist
gsutil mb gs://${GCP_BUCKET} 2>/dev/null || print_warning "Bucket may already exist"

# Set up bucket permissions
gsutil iam ch serviceAccount:${SERVICE_ACCOUNT_EMAIL}:roles/storage.objectViewer gs://${GCP_BUCKET}

# Pre-download and cache models (optional optimization)
read -p "Do you want to pre-cache models in GCP bucket for faster startup? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_step "Pre-caching models in GCP bucket..."
    
    # Create temporary directory for model caching
    mkdir -p ./temp-models
    
    # Download and cache Llama model
    python3 << 'EOF'
import os
from transformers import AutoTokenizer, AutoModelForCausalLM

model_name = "unsloth/Llama-3.2-3B-Instruct"
cache_dir = "./temp-models"

print("Downloading Llama model...")
tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir)
model = AutoModelForCausalLM.from_pretrained(model_name, cache_dir=cache_dir, torch_dtype="auto")
print("Model downloaded successfully")
EOF
    
    # Download and cache sentence transformer
    python3 << 'EOF'
from sentence_transformers import SentenceTransformer
import os

cache_dir = "./temp-models"
os.makedirs(cache_dir, exist_ok=True)

print("Downloading sentence transformer...")
model = SentenceTransformer('all-MiniLM-L6-v2', cache_folder=cache_dir)
print("Sentence transformer downloaded successfully")
EOF
    
    # Upload to GCP bucket
    print_step "Uploading cached models to GCP bucket..."
    gsutil -m cp -r ./temp-models/* gs://${GCP_BUCKET}/models/
    
    # Clean up
    rm -rf ./temp-models
    
    print_success "Models cached in GCP bucket"
fi

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

## Next Steps:
1. Upload images to Runpod (see GUIDE.md)
2. Create GPU pod with RTX 3090
3. Create CPU pod with 2 vCPU, 4GB RAM
4. Get pod URLs and update GCP Cloud Run environment variables
5. Run integration tests

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
echo "  - ./gcp-key.json (service account key)"
echo "  - ./deployment-summary.md (deployment guide)"
echo
print_step "Next: Follow GUIDE.md to deploy on Runpod"

# Display estimated costs
echo
print_warning "💰 Estimated Costs:"
echo "  - GPU Pod (RTX 3090): ~\$0.44/hour"
echo "  - CPU Pod (2 vCPU): ~\$0.02-0.10/hour"
echo "  - Total: ~\$0.46-0.54/hour"
echo
print_step "Remember to stop pods when not in use to save costs!" 