# Runpod Deployment Summary

## Docker Images Built:
- **LLM Service (GPU)**: `sql-retriever-llm:latest`
  - File: `./docker-images/sql-retriever-llm.tar.gz`
  - For: RTX 3090 GPU pod
  - Port: 8000

- **Embedding Service (CPU)**: `sql-retriever-embedding:latest`
  - File: `./docker-images/sql-retriever-embedding.tar.gz`
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
- GPU Pod: $0.44/hour (RTX 3090)
- CPU Pod: $0.02-0.10/hour (2 vCPU, 4GB)
