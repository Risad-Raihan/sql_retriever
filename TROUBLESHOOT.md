# SQL Retriever GCP Deployment Troubleshooting Guide

## Common Issues and Solutions

### 1. 🔐 Authentication Issues

#### Problem: `gcloud` not authenticated
```bash
ERROR: (gcloud.auth.list) Your current active account does not have any valid credentials
```

**Solution:**
```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

#### Problem: Insufficient permissions
```bash
ERROR: The caller does not have permission
```

**Solutions:**
1. Ensure you have the necessary IAM roles:
   - `Editor` or `Owner` role for full deployment
   - `Cloud SQL Admin`, `Storage Admin`, `Cloud Run Admin` for specific services

2. Check if APIs are enabled:
   ```bash
   gcloud services enable cloudbuild.googleapis.com run.googleapis.com sqladmin.googleapis.com
   ```

3. Verify current permissions:
   ```bash
   gcloud auth list
   gcloud projects get-iam-policy YOUR_PROJECT_ID
   ```

---

### 2. 💳 Billing and Project Issues

#### Problem: Project creation fails
```bash
ERROR: The project ID you specified is already in use
```

**Solution:**
Change the `project_id` in `gcp_config.yaml` to a globally unique name:
```yaml
project_id: "sql-retriever-YOUR_NAME-TIMESTAMP"
```

#### Problem: Billing account not linked
```bash
ERROR: Cloud billing budget requires billing to be enabled
```

**Solutions:**
1. Link a billing account:
   - Visit [Google Cloud Console Billing](https://console.cloud.google.com/billing)
   - Select your project and link a billing account
   
2. Verify billing is enabled:
   ```bash
   gcloud beta billing projects describe YOUR_PROJECT_ID
   ```

---

### 3. 🗄️ Cloud Storage Issues

#### Problem: Bucket name already exists
```bash
ERROR: The bucket you tried to create already exists
```

**Solution:**
Bucket names must be globally unique. Update `gcp_config.yaml`:
```yaml
bucket_name: "sql-retriever-storage-YOUR_NAME-RANDOM_STRING"
```

#### Problem: Permission denied when uploading to bucket
```bash
AccessDenied: Caller does not have storage.objects.create access
```

**Solutions:**
1. Check bucket permissions:
   ```bash
   gsutil iam get gs://YOUR_BUCKET_NAME
   ```

2. Grant necessary permissions:
   ```bash
   gsutil iam ch user:YOUR_EMAIL:objectAdmin gs://YOUR_BUCKET_NAME
   ```

---

### 4. 🗃️ Cloud SQL Issues

#### Problem: Instance creation timeout
```bash
ERROR: Operation timed out
```

**Solutions:**
1. Cloud SQL creation can take 10-15 minutes. Wait longer and check status:
   ```bash
   gcloud sql instances describe YOUR_INSTANCE_NAME
   ```

2. If still failing, try a different region:
   ```yaml
   region: "us-east1"  # or "europe-west1"
   ```

#### Problem: Database import fails
```bash
ERROR: Invalid file format or corrupted file
```

**Solutions:**
1. Verify the database dump format:
   ```bash
   file db_dump.sql
   head -20 db_dump.sql
   ```

2. Manually create a PostgreSQL-compatible dump:
   ```bash
   # If you have a PostgreSQL version of your data
   pg_dump your_database > db_dump.sql
   gsutil cp db_dump.sql gs://YOUR_BUCKET/db/
   ```

3. Import manually:
   ```bash
   gcloud sql import sql YOUR_INSTANCE_NAME gs://YOUR_BUCKET/db/db_dump.sql \
     --database=YOUR_DATABASE_NAME
   ```

#### Problem: SQL import timeout/slow import
```bash
ERROR: Operation timed out or Taking longer than expected
```

**Solutions:**
1. Check import operation status:
   ```bash
   gcloud sql operations list --instance=YOUR_INSTANCE_NAME --limit=5
   gcloud sql operations describe OPERATION_ID
   ```

2. For large databases, split the import:
   ```bash
   # Split large SQL file
   split -l 10000 db_dump.sql db_chunk_
   # Import chunks separately
   for file in db_chunk_*; do
     gsutil cp $file gs://YOUR_BUCKET/db/
     gcloud sql import sql YOUR_INSTANCE_NAME gs://YOUR_BUCKET/db/$file --database=YOUR_DATABASE
   done
   ```

3. Optimize SQL dump format:
   ```bash
   # Create optimized PostgreSQL dump
   pg_dump --verbose --no-acl --no-owner -h localhost -U postgres YOUR_DB > optimized_dump.sql
   ```

4. Use parallel import for large datasets:
   ```bash
   # Enable parallel import (for supported formats)
   gcloud sql import sql YOUR_INSTANCE_NAME gs://YOUR_BUCKET/db/db_dump.sql \
     --database=YOUR_DATABASE --parallel
   ```

5. Monitor import progress:
   ```bash
   # Check operation logs
   gcloud sql operations describe OPERATION_ID --format="value(error,status)"
   
   # Monitor instance CPU/memory during import
   gcloud sql instances describe YOUR_INSTANCE_NAME --format="value(state,settings.dataDiskSizeGb)"
   ```

6. Increase instance tier temporarily for faster import:
   ```bash
   # Upgrade before import
   gcloud sql instances patch YOUR_INSTANCE_NAME --tier=db-n1-standard-2
   # Downgrade after import
   gcloud sql instances patch YOUR_INSTANCE_NAME --tier=db-f1-micro
   ```

#### Problem: Connection string issues
```bash
ERROR: failed to connect to database
```

**Solutions:**
1. Verify connection string format:
   ```bash
   # Should be: postgresql://user:password@//cloudsql/PROJECT:REGION:INSTANCE/database
   gcloud sql instances describe YOUR_INSTANCE --format="value(connectionName)"
   ```

2. Test connection locally (if Cloud SQL Proxy installed):
   ```bash
   cloud_sql_proxy -instances=YOUR_CONNECTION_NAME=tcp:5432
   psql -h 127.0.0.1 -p 5432 -U YOUR_USER -d YOUR_DATABASE
   ```

---

### 5. 🐳 Docker and Artifact Registry Issues

#### Problem: Docker build fails
```bash
ERROR: failed to solve: failed to compute cache key
```

**Solutions:**
1. Clean Docker cache:
   ```bash
   docker system prune -a
   ```

2. Build without cache:
   ```bash
   docker build --no-cache -t YOUR_IMAGE_NAME .
   ```

3. Check Dockerfile syntax and dependencies in `requirements.txt`

#### Problem: Docker push fails - Permission denied
```bash
ERROR: denied: Permission "artifactregistry.repositories.uploadArtifacts" denied
```

**Solutions:**
1. Configure Docker authentication:
   ```bash
   gcloud auth configure-docker us-central1-docker.pkg.dev
   ```

2. Verify registry exists:
   ```bash
   gcloud artifacts repositories list --location=us-central1
   ```

3. Check IAM permissions:
   ```bash
   gcloud projects get-iam-policy YOUR_PROJECT_ID --flatten="bindings[].members" --filter="bindings.members:user:YOUR_EMAIL"
   ```

#### Problem: Docker push fails - Network timeout
```bash
ERROR: failed to push: EOF
```

**Solutions:**
1. Increase Docker timeout:
   ```bash
   export DOCKER_CLIENT_TIMEOUT=300
   export COMPOSE_HTTP_TIMEOUT=300
   ```

2. Use parallel upload:
   ```bash
   docker push --parallel YOUR_IMAGE_NAME
   ```

3. Check image size and optimize:
   ```bash
   docker images | grep YOUR_IMAGE_NAME
   # If too large (>2GB), optimize Dockerfile
   ```

#### Problem: Docker push fails - Quota exceeded
```bash
ERROR: RESOURCE_EXHAUSTED: Quota exceeded for quota metric 'artifact_registry_storage'
```

**Solutions:**
1. Clean old images:
   ```bash
   gcloud artifacts docker images list LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY
   gcloud artifacts docker images delete IMAGE_URL --delete-tags
   ```

2. Check storage quota:
   ```bash
   gcloud compute project-info describe --format="value(quotas[].usage,quotas[].limit)"
   ```

3. Request quota increase in GCP Console

#### Problem: Docker push fails - Authentication error
```bash
ERROR: unauthorized: authentication required
```

**Solutions:**
1. Re-authenticate Docker:
   ```bash
   gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
   ```

2. Use service account key (for CI/CD):
   ```bash
   gcloud auth activate-service-account --key-file=SERVICE_ACCOUNT_KEY.json
   gcloud auth configure-docker us-central1-docker.pkg.dev
   ```

3. Check token expiry:
   ```bash
   gcloud auth print-access-token
   ```

---

### 6. ☁️ Cloud Run Issues

#### Problem: Service deployment fails
```bash
ERROR: Cloud Run error: Container failed to start
```

**Solutions:**
1. Check Cloud Run logs:
   ```bash
   gcloud run services logs tail YOUR_SERVICE_NAME --region=us-central1
   ```

2. Common fixes:
   - Ensure `PORT` environment variable is properly handled in your app
   - Verify all required environment variables are set
   - Check that the container listens on `0.0.0.0`, not `127.0.0.1`

#### Problem: Cold start issues
```bash
ERROR: The request was aborted because it didn't finish within the timeout
```

**Solutions:**
1. Increase timeout:
   ```bash
   gcloud run services update YOUR_SERVICE_NAME \
     --region=us-central1 \
     --timeout=900s
   ```

2. Set minimum instances to prevent cold starts:
   ```bash
   gcloud run services update YOUR_SERVICE_NAME \
     --region=us-central1 \
     --min-instances=1
   ```

#### Problem: Memory or CPU limits exceeded
```bash
ERROR: Memory limit exceeded
```

**Solutions:**
1. Increase memory allocation:
   ```bash
   gcloud run services update YOUR_SERVICE_NAME \
     --region=us-central1 \
     --memory=4Gi \
     --cpu=2000m
   ```

2. Monitor resource usage:
   ```bash
   gcloud run services logs tail YOUR_SERVICE_NAME --region=us-central1 | grep -i memory
   ```

---

### 7. 🔑 API and Environment Variable Issues

#### Problem: API returns 401 Unauthorized
```bash
{"error": "Invalid API key"}
```

**Solutions:**
1. Verify API key is set correctly:
   ```bash
   gcloud run services describe YOUR_SERVICE_NAME \
     --region=us-central1 \
     --format="value(spec.template.spec.containers[0].env[?(@.name=='API_KEY')].value)"
   ```

2. Test with correct header format:
   ```bash
   curl -H "Authorization: Bearer YOUR_API_KEY" https://YOUR_SERVICE_URL/health
   ```

#### Problem: Database connection fails in Cloud Run
```bash
{"error": "Database connection failed"}
```

**Solutions:**
1. Verify Cloud SQL connection is added:
   ```bash
   gcloud run services describe YOUR_SERVICE_NAME \
     --region=us-central1 \
     --format="value(spec.template.metadata.annotations)"
   ```

2. Check environment variables:
   ```bash
   gcloud run services describe YOUR_SERVICE_NAME \
     --region=us-central1 \
     --format="value(spec.template.spec.containers[0].env[].name,spec.template.spec.containers[0].env[].value)"
   ```

---

### 8. 📊 Monitoring and Logging Issues

#### Problem: No logs appearing
```bash
ERROR: Listed 0 items
```

**Solutions:**
1. Verify the service name and region:
   ```bash
   gcloud run services list
   ```

2. Check log filters:
   ```bash
   gcloud logging read "resource.type=\"cloud_run_revision\"" --limit=50
   ```

3. Enable debug logging in your application

---

### 9. 💰 Cost Management Issues

#### Problem: Unexpected high costs/cost overage
**Solutions:**
1. Check current billing and usage:
   ```bash
   # Get billing account
   BILLING_ACCOUNT=$(gcloud beta billing projects describe YOUR_PROJECT_ID --format="value(billingAccountName)" | sed 's/.*\///')
   
   # Check current month costs
   gcloud beta billing projects describe YOUR_PROJECT_ID
   
   # List all active resources and their costs
   gcloud beta billing projects get-billing-info YOUR_PROJECT_ID
   ```

2. Identify cost drivers:
   ```bash
   # Check Cloud Run usage and costs
   gcloud run services list --format="table(metadata.name,status.url,status.traffic.percent)"
   gcloud logging read "resource.type=cloud_run_revision" --limit=100 | grep "request"
   
   # Check Cloud SQL usage
   gcloud sql instances describe YOUR_INSTANCE_NAME --format="value(settings.tier,settings.dataDiskSizeGb)"
   
   # Check storage usage and costs
   gsutil du -sh gs://YOUR_BUCKET_NAME
   gsutil ls -L -b gs://YOUR_BUCKET_NAME | grep "Storage class\|Location"
   ```

3. Immediate cost reduction actions:
   ```bash
   # Reduce Cloud Run instances
   gcloud run services update YOUR_SERVICE_NAME --max-instances=2 --region=us-central1
   
   # Scale down Cloud SQL (if not in use)
   gcloud sql instances patch YOUR_INSTANCE_NAME --tier=db-f1-micro
   
   # Delete unnecessary storage
   gsutil -m rm -r gs://YOUR_BUCKET_NAME/logs/old_logs/**
   
   # Set storage lifecycle policy
   gsutil lifecycle set lifecycle.json gs://YOUR_BUCKET_NAME
   ```

4. Set up immediate budget alerts:
   ```bash
   gcloud beta billing budgets create \
     --billing-account=$BILLING_ACCOUNT \
     --display-name="Emergency Budget Alert" \
     --budget-amount=20USD \
     --threshold-rules-percent=50,75,90,100 \
     --threshold-rules-spend-basis=CURRENT_SPEND \
     --notification-channels=NOTIFICATION_CHANNEL_ID
   ```

5. Enable cost monitoring and optimization:
   ```bash
   # Check for idle resources
   gcloud compute instances list --filter="status:STOPPED"
   gcloud run services list --filter="status.traffic.percent=0"
   
   # Review committed use discounts
   gcloud compute commitments list
   
   # Check for unused IP addresses
   gcloud compute addresses list --filter="status:RESERVED"
   ```

6. Monitor resources in real-time:
   ```bash
   # Set up cost alerts for specific services
   gcloud alpha monitoring policies create --policy-from-file=cost-policy.json
   
   # Monitor billing with custom dashboard
   gcloud monitoring dashboards create --config-from-file=billing-dashboard.yaml
   ```

#### Problem: Budget alerts not working
**Solutions:**
1. Verify notification channels:
   ```bash
   gcloud alpha monitoring channels list
   gcloud alpha monitoring channels create --channel-labels=email_address=YOUR_EMAIL --type=email
   ```

2. Test budget configuration:
   ```bash
   gcloud beta billing budgets describe BUDGET_ID --billing-account=BILLING_ACCOUNT
   ```

3. Check IAM permissions for billing:
   ```bash
   gcloud projects get-iam-policy YOUR_PROJECT_ID --flatten="bindings[].members" --filter="bindings.role:roles/billing.*"
   ```

#### Problem: Services consuming unexpected resources
**Solutions:**
1. Monitor Cloud Run memory/CPU:
   ```bash
   # Check service limits and usage
   gcloud run services describe YOUR_SERVICE_NAME --region=us-central1 --format="value(spec.template.spec.containers[].resources)"
   
   # View memory usage logs
   gcloud logging read "resource.type=cloud_run_revision AND textPayload:memory" --limit=50
   ```

2. Optimize resource allocation:
   ```bash
   # Right-size Cloud Run
   gcloud run services update YOUR_SERVICE_NAME \
     --region=us-central1 \
     --memory=1Gi \
     --cpu=500m \
     --max-instances=5
   
   # Optimize Cloud SQL
   gcloud sql instances patch YOUR_INSTANCE_NAME --tier=db-g1-small
   ```

3. Set up automatic scaling policies:
   ```bash
   # Create auto-scaling based on metrics
   gcloud run services update YOUR_SERVICE_NAME \
     --region=us-central1 \
     --concurrency=80 \
     --min-instances=0 \
     --max-instances=3
   ```

---

### 10. 🔧 General Debugging Commands

#### Check deployment status:
```bash
# Overall project status
gcloud projects describe YOUR_PROJECT_ID

# Service status
gcloud run services list --region=us-central1
gcloud sql instances list
gcloud artifacts repositories list --location=us-central1
gsutil ls

# Health checks
curl https://YOUR_SERVICE_URL/health
```

#### Clean up for fresh deployment:
```bash
# WARNING: This will delete all resources
gcloud run services delete YOUR_SERVICE_NAME --region=us-central1 --quiet
gcloud sql instances delete YOUR_INSTANCE_NAME --quiet
gcloud artifacts repositories delete YOUR_REGISTRY_NAME --location=us-central1 --quiet
gsutil -m rm -r gs://YOUR_BUCKET_NAME
```

#### View comprehensive logs:
```bash
# Cloud Run logs
gcloud run services logs tail YOUR_SERVICE_NAME --region=us-central1

# Cloud SQL logs
gcloud sql operations list --instance=YOUR_INSTANCE_NAME

# Build logs
gcloud builds list --limit=10
```

---

## 🆘 Getting Help

If you're still experiencing issues:

1. **Check the official documentation:**
   - [Cloud Run Troubleshooting](https://cloud.google.com/run/docs/troubleshooting)
   - [Cloud SQL Troubleshooting](https://cloud.google.com/sql/docs/troubleshooting)

2. **Community resources:**
   - [Stack Overflow GCP tag](https://stackoverflow.com/questions/tagged/google-cloud-platform)
   - [Google Cloud Community](https://cloud.google.com/community)

3. **Contact support:**
   - Basic support is included with billing
   - Visit [Google Cloud Support](https://cloud.google.com/support)

4. **Create an issue:**
   - If this is a deployment script issue, create an issue in your project repository
   - Include logs and configuration details

---

## 📝 Common Configuration Mistakes

### `gcp_config.yaml` issues:
- Project ID must be globally unique
- Bucket name must be globally unique  
- Passwords should be strong and not default values
- API keys should be secure random strings

### Environment-specific issues:
- Ensure you're using the correct region consistently
- Check that all services are in the same region for lower latency
- Verify that your local Docker daemon is running

### Security considerations:
- Never commit real API keys or passwords to git
- Use Google Secret Manager for production secrets
- Regularly rotate credentials
- Monitor access logs for suspicious activity 