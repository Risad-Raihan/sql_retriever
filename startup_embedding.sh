#!/bin/bash
set -e

echo "🚀 Starting CPU Pod - Embedding Service"

# Authenticate with GCP
echo "🔑 Authenticating with Google Cloud..."
gcloud auth activate-service-account --key-file=/app/gcp-key.json
gcloud config set project heroic-overview-466605-p6

# Create directories
mkdir -p /app/rag_data /app/models

echo "📥 Pulling RAG data from GCP bucket..."
# Download RAG data from GCP bucket
if gsutil -m cp -r gs://${GCP_BUCKET_NAME}/rag_data/* /app/rag_data/ 2>/dev/null; then
    echo "✅ RAG data downloaded from GCP bucket"
else
    echo "⚠️  RAG data not found in bucket, will create new vector store"
fi

echo "📥 Setting up model cache..."
# Set up model cache directory for sentence transformers
export SENTENCE_TRANSFORMERS_HOME=/app/models
export TRANSFORMERS_CACHE=/app/models

# Try to download pre-cached embedding model
if gsutil -m cp -r gs://${GCP_BUCKET_NAME}/models/sentence-transformers/* /app/models/ 2>/dev/null; then
    echo "✅ Embedding model downloaded from GCP bucket"
else
    echo "⚠️  Embedding model not found in bucket, will download from Hugging Face"
fi

echo "📦 Installing ML packages..."
# Install heavy ML packages at runtime on actual hardware
pip install \
    sentence-transformers==2.2.2 \
    chromadb==0.4.15 \
    faiss-cpu==1.7.4 \
    numpy==1.24.3 \
    scikit-learn==1.3.0

echo "🔥 Starting Embedding Service..."
# Start the FastAPI embedding service
python3 /app/embedding_service.py 