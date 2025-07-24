# 🚀 Runpod Two-Pod Architecture Deployment Guide

Complete guide to deploy SQL Retriever with GPU LLM pod and CPU embedding service on Runpod.

## 📋 Overview

This architecture splits the SQL Retriever into two specialized pods:
- **GPU Pod**: Runs vLLM server with Llama-3.2-3B model for SQL generation
- **CPU Pod**: Runs embedding service for semantic search and example retrieval

## 💰 Cost Structure

- **GPU Pod (RTX 3090)**: ~$0.44/hour
- **CPU Pod (2 vCPU, 4GB)**: ~$0.02-0.10/hour  
- **Total**: ~$0.46-0.54/hour
- **Daily**: ~$11-13 (if running 24/7)

⚠️ **Cost Tip**: Stop pods when not in use to save money!

## 🛠 Prerequisites

- Runpod account with credits
- Docker installed locally
- Google Cloud SDK installed
- SQL Retriever codebase

## 📦 Step 1: Prepare Docker Images

Run the deployment script to build images:

```bash
chmod +x deploy_runpod.sh
./deploy_runpod.sh
```

This creates:
- `docker-images/sql-retriever-llm.tar.gz` (GPU image)
- `docker-images/sql-retriever-embedding.tar.gz` (CPU image)
- `gcp-key.json` (service account key)

## 🌐 Step 2: Runpod Account Setup

### 2.1 Create Account
1. Go to [runpod.io](https://runpod.io)
2. Sign up and verify email
3. Add credits (minimum $10 recommended)

### 2.2 Navigate to Pods
1. Click **"My Pods"** in sidebar
2. Click **"+ GPU Pod"** or **"+ CPU Pod"**

## 🔥 Step 3: Deploy GPU Pod (LLM Service)

### 3.1 Create GPU Pod
1. **Template**: Select "Custom" or "PyTorch"
2. **GPU**: RTX 3090 (24GB VRAM) - $0.44/hr
3. **CPU**: 6 vCPU
4. **RAM**: 12GB
5. **Storage**: 50GB (for model cache)

### 3.2 Configure GPU Pod
**Container Image**: 
- Click "Deploy Custom Container"
- Upload `docker-images/sql-retriever-llm.tar.gz`

**Ports**:
- HTTP Port: `8000`
- Expose HTTP Ports: ✅ Enabled

**Environment Variables**:
```
MODEL_NAME=unsloth/Llama-3.2-3B-Instruct
GCP_BUCKET_NAME=sql-retriever-models
PORT=8000
CUDA_VISIBLE_DEVICES=0
```

**Volume Mounts** (optional for model caching):
```
/runpod-volume -> /app/models
```

### 3.3 Deploy GPU Pod
1. Click **"Deploy"**
2. Wait for status: **"Running"** (takes 5-10 minutes)
3. Note the **Public IP** or **Connect URL**

**Expected URL format**: `https://xxxxx-8000.proxy.runpod.net`

### 3.4 Verify GPU Pod
Test the vLLM server:

```bash
# Health check
curl https://your-gpu-pod-url/v1/models

# Should return JSON with model info
```

## 💻 Step 4: Deploy CPU Pod (Embedding Service)  

### 4.1 Create CPU Pod
1. **Template**: Select "Custom" or "Python"
2. **CPU**: 2 vCPU
3. **RAM**: 4GB  
4. **Storage**: 20GB
5. **GPU**: None (CPU only) - $0.02-0.10/hr

### 4.2 Configure CPU Pod
**Container Image**:
- Upload `docker-images/sql-retriever-embedding.tar.gz`

**Ports**:
- HTTP Port: `8000`
- Expose HTTP Ports: ✅ Enabled

**Environment Variables**:
```
GCP_BUCKET_NAME=sql-retriever-models
RAG_DATA_PATH=/app/rag_data
PORT=8000
```

**Volume Mounts** (optional for data persistence):
```
/runpod-volume -> /app/rag_data
```

### 4.3 Deploy CPU Pod
1. Click **"Deploy"**
2. Wait for status: **"Running"** (takes 2-5 minutes)
3. Note the **Public IP** or **Connect URL**

**Expected URL format**: `https://yyyyy-8000.proxy.runpod.net`

### 4.4 Verify CPU Pod
Test the embedding service:

```bash
# Health check
curl https://your-cpu-pod-url/health

# Test embedding
curl -X POST https://your-cpu-pod-url/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "test query"}'

# Test search
curl -X POST https://your-cpu-pod-url/search \
  -H "Content-Type: application/json" \
  -d '{"question": "show customers", "k": 3}'
```

## 📡 Step 5: Connect to GCP Cloud Run

### 5.1 Update Environment Variables
Update your GCP Cloud Run service with the pod URLs:

```bash
# Set environment variables
gcloud run services update sql-retriever-api \
  --set-env-vars="EMBEDDING_URL=https://yyyyy-8000.proxy.runpod.net" \
  --set-env-vars="LLM_URL=https://xxxxx-8000.proxy.runpod.net" \
  --region=us-central1
```

### 5.2 Redeploy Cloud Run
```bash
gcloud run deploy sql-retriever-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```

## 🧪 Step 6: Integration Testing

### 6.1 Test Individual Services
```bash
# Test both pods
export EMBEDDING_URL="https://yyyyy-8000.proxy.runpod.net"
export LLM_URL="https://xxxxx-8000.proxy.runpod.net" 
export API_ENDPOINT="https://your-cloud-run-url"
export API_KEY="your-api-key"

./integration_test.sh
```

### 6.2 Test Full Workflow
```bash
# Test complete query flow
curl -X POST https://your-cloud-run-url/query \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"question": "show me top 5 customers by revenue"}'
```

Expected response:
```json
{
  "success": true,
  "sql_query": "SELECT c.customerName, SUM(od.quantityOrdered * od.priceEach) as revenue FROM customers c JOIN orders o ON c.customerNumber = o.customerNumber JOIN orderdetails od ON o.orderNumber = od.orderNumber GROUP BY c.customerNumber, c.customerName ORDER BY revenue DESC LIMIT 5;",
  "results": [...],
  "processing_time": 2.34
}
```

## 🎯 Step 7: Production Setup

### 7.1 Security
- [ ] Change default API keys
- [ ] Implement pod-to-pod authentication
- [ ] Use HTTPS everywhere
- [ ] Restrict pod access to specific IPs

### 7.2 Monitoring
- [ ] Set up pod monitoring
- [ ] Configure alerts for downtime
- [ ] Monitor costs daily
- [ ] Track query performance

### 7.3 Optimization
- [ ] Cache models in persistent volumes
- [ ] Implement pod auto-scaling
- [ ] Use spot instances for cost savings
- [ ] Optimize model parameters

## 🚨 Troubleshooting

### Common Issues

#### GPU Pod Won't Start
```bash
# Check logs
runpod logs gpu-pod-id

# Common fixes:
1. Increase storage (models are large)
2. Check CUDA drivers
3. Verify GPU availability
```

#### CPU Pod Memory Issues
```bash
# Reduce model size or increase RAM
# Check embedding model cache
```

#### Network Connectivity
```bash
# Test pod connectivity
curl -v https://pod-url/health

# Check firewall rules
# Verify port exposure
```

#### High Costs
```bash
# Stop unused pods
runpod stop pod-id

# Use spot pricing
# Monitor usage dashboard
```

### Performance Issues

#### Slow Response Times
1. **Model Loading**: First query takes longer (model loading)
2. **Cold Start**: Pods go to sleep, restart takes time
3. **Network Latency**: Use same region for all services

#### Memory Errors
1. **GPU OOM**: Reduce `max_model_len` in vLLM config
2. **CPU OOM**: Increase pod RAM or reduce batch sizes

## 📊 Monitoring Dashboard

Create a simple monitoring script:

```bash
#!/bin/bash
# monitor_pods.sh

echo "🔍 Pod Status Check"
echo "===================="

# Check GPU Pod
if curl -s https://your-gpu-pod-url/v1/models > /dev/null; then
    echo "✅ GPU Pod: Online"
else
    echo "❌ GPU Pod: Offline"
fi

# Check CPU Pod  
if curl -s https://your-cpu-pod-url/health > /dev/null; then
    echo "✅ CPU Pod: Online"
else
    echo "❌ CPU Pod: Offline"
fi

# Check costs (estimated)
echo "💰 Estimated hourly cost: $0.46-0.54"
echo "💰 Daily cost (if always on): $11-13"
```

## 🎉 Project Completion Checklist

- [ ] Both pods deployed and running
- [ ] GCP Cloud Run updated with pod URLs
- [ ] Integration tests passing
- [ ] Cost monitoring set up
- [ ] Security measures implemented
- [ ] Documentation updated
- [ ] Team trained on operations

## 📚 Additional Resources

- [Runpod Documentation](https://docs.runpod.io/)
- [vLLM Documentation](https://docs.vllm.ai/)
- [Llama Model Details](https://huggingface.co/unsloth/Llama-3.2-3B-Instruct)

## 🆘 Support

If you encounter issues:

1. Check the troubleshooting section
2. Review pod logs in Runpod dashboard  
3. Test individual services separately
4. Verify environment variables
5. Check network connectivity

## 🏁 Success Metrics

Your deployment is successful when:
- [ ] Both pods respond to health checks
- [ ] End-to-end query completes in <10 seconds
- [ ] Integration tests pass 100%
- [ ] Costs are within expected range
- [ ] No errors in logs

**Congratulations! Your two-pod Runpod architecture is now live!** 🎉

---

*Remember to stop pods when not in use to control costs. Happy querying!* 💾 