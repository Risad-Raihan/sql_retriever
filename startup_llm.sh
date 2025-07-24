#!/bin/bash
set -e

echo "🚀 Starting GPU Pod - vLLM Server"

# Authenticate with GCP
echo "🔑 Authenticating with Google Cloud..."
gcloud auth activate-service-account --key-file=/app/gcp-key.json
gcloud config set project heroic-overview-466605-p6

# Create model cache directory
mkdir -p /app/models
export HF_HOME=/app/models
export TRANSFORMERS_CACHE=/app/models

echo "📥 Pulling model from GCP bucket..."
# Try to download pre-cached model from GCP bucket
if gsutil -m cp -r gs://${GCP_BUCKET_NAME}/models/${MODEL_NAME}/* /app/models/ 2>/dev/null; then
    echo "✅ Model downloaded from GCP bucket"
else
    echo "⚠️  Model not found in bucket, will download from Hugging Face"
fi

# Set CUDA device
export CUDA_VISIBLE_DEVICES=0

echo "📦 Installing GPU packages..."
# Install GPU-specific packages on actual hardware
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install vllm==0.2.7
pip install transformers==4.36.0

echo "🔥 Starting vLLM server..."
# Start vLLM server with optimized settings for RTX 3090
python3 -m vllm.entrypoints.openai.api_server \
    --model ${MODEL_NAME} \
    --host 0.0.0.0 \
    --port ${PORT} \
    --tensor-parallel-size 1 \
    --gpu-memory-utilization 0.9 \
    --max-model-len 2048 \
    --dtype half \
    --trust-remote-code \
    --disable-log-requests \
    --served-model-name llama-3b-instruct &

VLLM_PID=$!

# Wait for vLLM to start
echo "⏳ Waiting for vLLM server to start..."
for i in {1..60}; do
    if curl -s http://localhost:${PORT}/v1/models > /dev/null 2>&1; then
        echo "✅ vLLM server is ready!"
        break
    fi
    echo "Waiting... ($i/60)"
    sleep 2
done

# Create simple health endpoint
cat > /app/health_server.py << 'EOF'
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
import requests

app = FastAPI()

@app.get("/health")
def health():
    try:
        # Check if vLLM server is responding
        response = requests.get("http://localhost:8000/v1/models", timeout=5)
        if response.status_code == 200:
            return {"status": "healthy", "service": "vllm-llm"}
        else:
            return JSONResponse(content={"status": "unhealthy", "service": "vllm-llm"}, status_code=503)
    except Exception as e:
        return JSONResponse(content={"status": "unhealthy", "error": str(e)}, status_code=503)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
EOF

# Start health server
python3 /app/health_server.py &

# Keep the main process alive
wait $VLLM_PID 