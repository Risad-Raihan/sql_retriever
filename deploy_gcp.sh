#!/bin/bash

# GCP Deployment Script for SQL Retriever
# Author: Cloud Engineering Team
# Description: Complete deployment toolkit for SQL Retriever RAG-powered API
# Cost Estimate: $15-50/month (Cloud Run: $5-20, Cloud SQL: $7-15, Storage: $1-5, Registry: $0.50-2)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Progress bar function
show_progress() {
    local duration=$1
    local description=$2
    echo -n "$description"
    for ((i=0; i<duration; i++)); do
        echo -n "."
        sleep 1
    done
    echo " ✅"
}

# Enhanced error handling
handle_error() {
    local exit_code=$?
    local line_number=$1
    echo ""
    error "Deployment failed on line $line_number with exit code $exit_code"
    echo "Check the logs above for details."
    echo "Run './cleanup_gcp.sh' to clean up partial deployment if needed."
}
trap 'handle_error $LINENO' ERR

# Prompt for file paths function
prompt_for_paths() {
    log "🔍 Checking required files and prompting for missing paths..."
    
    # Check for database file
    if [ ! -f "data/test_crm_v1.db" ]; then
        warn "Database file not found at data/test_crm_v1.db"
        read -p "Enter path to your SQLite database file (or press Enter to skip): " DB_PATH
        if [ -n "$DB_PATH" ] && [ -f "$DB_PATH" ]; then
            mkdir -p data
            cp "$DB_PATH" data/test_crm_v1.db
            log "Database file copied to data/test_crm_v1.db"
        fi
    fi
    
    # Check for RAG data
    if [ ! -d "rag_data" ]; then
        warn "RAG data directory not found at rag_data/"
        read -p "Enter path to your RAG data directory (or press Enter to skip): " RAG_PATH
        if [ -n "$RAG_PATH" ] && [ -d "$RAG_PATH" ]; then
            cp -r "$RAG_PATH" rag_data/
            log "RAG data copied to rag_data/"
        fi
    fi
    
    # Check Dockerfile
    if [ ! -f "Dockerfile" ]; then
        error "Dockerfile not found. Please create a Dockerfile for your application."
    fi
    
    # Check requirements.txt
    if [ ! -f "requirements.txt" ]; then
        warn "requirements.txt not found. Docker build may fail without dependencies."
    fi
}

# Check if project exists before creating
check_project_exists() {
    local project_id=$1
    if gcloud projects describe "$project_id" &> /dev/null; then
        return 0  # Project exists
    else
        return 1  # Project doesn't exist
    fi
}

# Load configuration
if [ ! -f "gcp_config.yaml" ]; then
    error "gcp_config.yaml not found. Please create the configuration file first."
fi

# Function to extract values from YAML config
get_config() {
    local key=$1
    grep "^$key:" gcp_config.yaml | sed 's/.*: *"\?\([^"]*\)"\?/\1/'
}

# Load configuration variables
PROJECT_ID=$(get_config "project_id")
REGION=$(get_config "region")
ZONE=$(get_config "zone")
BUCKET_NAME=$(get_config "bucket_name")
SQL_INSTANCE=$(get_config "sql_instance_name")
SQL_DATABASE=$(get_config "sql_database_name")
SQL_USER=$(get_config "sql_user")
SQL_PASSWORD=$(get_config "sql_password")
SQL_TIER=$(get_config "sql_tier")
REGISTRY_NAME=$(get_config "registry_name")
IMAGE_NAME=$(get_config "image_name")
SERVICE_NAME=$(get_config "service_name")
API_KEY=$(get_config "api_key")
SERVICE_MEMORY=$(get_config "service_memory")
SERVICE_CPU=$(get_config "service_cpu")
SERVICE_MIN_INSTANCES=$(get_config "service_min_instances")
SERVICE_MAX_INSTANCES=$(get_config "service_max_instances")
SERVICE_TIMEOUT=$(get_config "service_timeout")
MODEL_ENDPOINT=$(get_config "model_endpoint")
USE_SECRET_MANAGER=$(get_config "use_secret_manager")

# Validate required variables
if [ -z "$PROJECT_ID" ] || [ -z "$BUCKET_NAME" ] || [ -z "$SQL_PASSWORD" ] || [ -z "$API_KEY" ]; then
    error "Please update gcp_config.yaml with your project settings"
fi

# Validate region is us-central1
if [ "$REGION" != "us-central1" ]; then
    warn "Region is set to '$REGION'. For cost optimization, consider using 'us-central1'"
    read -p "Continue with $REGION? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        error "Please update region to 'us-central1' in gcp_config.yaml"
    fi
fi

log "🚀 Starting GCP Deployment for SQL Retriever"
log "Project ID: $PROJECT_ID"
log "Region: $REGION"
log "Bucket: $BUCKET_NAME"
log "Estimated monthly cost: \$15-50 (varies by usage)"

# Step 0: Prompt for required files
prompt_for_paths

# Step 1: Authentication and Project Setup
log "🔐 Setting up authentication and project..."

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    error "gcloud CLI not found. Please install Google Cloud SDK first."
fi

# Initialize gcloud if needed
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1 > /dev/null 2>&1; then
    log "Initializing gcloud authentication..."
    gcloud init
fi

# Enhanced project creation with existence check
log "📋 Checking/creating project: $PROJECT_ID"
if check_project_exists "$PROJECT_ID"; then
    log "✅ Project $PROJECT_ID already exists"
else
    log "Creating new project: $PROJECT_ID"
    gcloud projects create "$PROJECT_ID" --name="SQL Retriever Production"
    
    # Link billing account (user will need to do this manually if no default)
    warn "Please ensure billing is enabled for project $PROJECT_ID"
    warn "Visit: https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID"
    read -p "Press Enter once billing is enabled..."
    
    # Wait for project to be ready
    show_progress 5 "Waiting for project initialization"
fi

# Set the project
gcloud config set project "$PROJECT_ID"
gcloud config set compute/region "$REGION"
gcloud config set compute/zone "$ZONE"

# Step 2: Enable required APIs with progress tracking
log "🔌 Enabling required GCP APIs..."
REQUIRED_APIS=(
    "cloudbuild.googleapis.com"
    "run.googleapis.com"
    "sqladmin.googleapis.com"
    "storage.googleapis.com"
    "artifactregistry.googleapis.com"
    "cloudresourcemanager.googleapis.com"
    "iam.googleapis.com"
    "logging.googleapis.com"
    "monitoring.googleapis.com"
    "secretmanager.googleapis.com"
)

for api in "${REQUIRED_APIS[@]}"; do
    if gcloud services list --enabled --filter="name:$api" --format="value(name)" | grep -q "$api"; then
        log "✅ API $api already enabled"
    else
        log "Enabling API: $api"
        gcloud services enable "$api"
    fi
done

show_progress 10 "Waiting for APIs to be fully enabled"

# Step 3: Secret Manager setup (if enabled)
if [ "$USE_SECRET_MANAGER" = "true" ]; then
    log "🔐 Setting up Secret Manager..."
    
    # Create secrets
    if ! gcloud secrets describe "sql-password" &> /dev/null; then
        echo -n "$SQL_PASSWORD" | gcloud secrets create "sql-password" --data-file=-
        log "✅ SQL password stored in Secret Manager"
    fi
    
    if ! gcloud secrets describe "api-key" &> /dev/null; then
        echo -n "$API_KEY" | gcloud secrets create "api-key" --data-file=-
        log "✅ API key stored in Secret Manager"
    fi
    
    # Update variables to use secret references
    SQL_PASSWORD_REF="projects/$PROJECT_ID/secrets/sql-password/versions/latest"
    API_KEY_REF="projects/$PROJECT_ID/secrets/api-key/versions/latest"
fi

# Step 3: Create Cloud Storage Bucket with enhanced error handling
log "🗄️  Creating Cloud Storage bucket: $BUCKET_NAME"
if gsutil ls -b "gs://$BUCKET_NAME" &> /dev/null; then
    log "✅ Bucket $BUCKET_NAME already exists"
else
    # Check if bucket name is globally unique
    if gsutil ls -b "gs://$BUCKET_NAME" 2>&1 | grep -q "BucketNotFound"; then
        gsutil mb -l "$REGION" "gs://$BUCKET_NAME"
        log "✅ Created bucket gs://$BUCKET_NAME"
    else
        error "Bucket name '$BUCKET_NAME' is already taken. Please choose a unique name in gcp_config.yaml"
    fi
    
    # Set up folder structure
    log "📁 Setting up bucket folder structure..."
    echo "This is the models directory" | gsutil cp - "gs://$BUCKET_NAME/models/.keep"
    echo "This is the RAG data directory" | gsutil cp - "gs://$BUCKET_NAME/rag/.keep"
    echo "This is the database dumps directory" | gsutil cp - "gs://$BUCKET_NAME/db/.keep"
    echo "This is the logs directory" | gsutil cp - "gs://$BUCKET_NAME/logs/.keep"
    
    # Set bucket permissions
    gsutil iam ch serviceAccount:$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")-compute@developer.gserviceaccount.com:objectViewer "gs://$BUCKET_NAME"
fi

# Step 4: Upload application data to bucket with progress
log "📤 Uploading application data to bucket..."

# Upload RAG data if it exists
if [ -d "rag_data" ]; then
    log "Uploading RAG data..."
    gsutil -o GSUtil:parallel_process_count=4 -m cp -r rag_data/* "gs://$BUCKET_NAME/rag/"
    log "✅ RAG data uploaded"
else
    warn "rag_data directory not found. Creating empty directory in bucket."
fi

# Create and upload database dump
log "💾 Creating and uploading database dump..."
if [ -f "data/test_crm_v1.db" ]; then
    # Convert SQLite to SQL dump for PostgreSQL import
    sqlite3 data/test_crm_v1.db .dump > db_dump.sql
    
    # Upload database dump
    gsutil cp db_dump.sql "gs://$BUCKET_NAME/db/"
    rm db_dump.sql
    log "✅ Database dump uploaded"
else
    warn "Database file not found. You'll need to upload it manually later."
fi

# Step 5: Create Cloud SQL Instance with enhanced error handling
log "🗃️  Creating Cloud SQL instance: $SQL_INSTANCE"
if gcloud sql instances describe "$SQL_INSTANCE" &> /dev/null; then
    log "✅ Cloud SQL instance $SQL_INSTANCE already exists"
    CONNECTION_STRING=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(connectionName)")
else
    log "Creating PostgreSQL instance (this may take 10-15 minutes)..."
    log "Estimated cost: \$7-15/month for $SQL_TIER"
    
    if ! gcloud sql instances create "$SQL_INSTANCE" \
        --database-version=POSTGRES_15 \
        --tier="$SQL_TIER" \
        --region="$REGION" \
        --storage-type=SSD \
        --storage-size=20GB \
        --backup-start-time=03:00 \
        --enable-bin-log \
        --retained-backups-count=7 \
        --deletion-protection; then
        error "Failed to create Cloud SQL instance. Check quota limits and billing."
    fi
    
    # Wait for instance to be ready
    show_progress 30 "Waiting for Cloud SQL instance to be ready"
    
    # Create database
    log "Creating database: $SQL_DATABASE"
    gcloud sql databases create "$SQL_DATABASE" --instance="$SQL_INSTANCE"
    
    # Create user
    log "Creating database user: $SQL_USER"
    gcloud sql users create "$SQL_USER" \
        --instance="$SQL_INSTANCE" \
        --password="$SQL_PASSWORD"
    
    # Get connection string
    CONNECTION_STRING=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(connectionName)")
    log "✅ Cloud SQL instance created. Connection: $CONNECTION_STRING"
    
    # Import database if dump exists
    if gsutil ls "gs://$BUCKET_NAME/db/db_dump.sql" &> /dev/null; then
        log "📥 Importing database dump (this may take several minutes)..."
        if ! gcloud sql import sql "$SQL_INSTANCE" "gs://$BUCKET_NAME/db/db_dump.sql" \
            --database="$SQL_DATABASE"; then
            warn "Database import failed. You may need to import manually."
        else
            log "✅ Database imported successfully"
        fi
    fi
fi

# Auto-fetch Cloud SQL IP for environment variables
SQL_PUBLIC_IP=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(ipAddresses[0].ipAddress)")
SQL_PRIVATE_IP=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(ipAddresses[?type=PRIVATE].ipAddress)" 2>/dev/null || echo "")

log "📊 Cloud SQL Instance Details:"
log "  Connection Name: $CONNECTION_STRING"
log "  Public IP: $SQL_PUBLIC_IP"
if [ -n "$SQL_PRIVATE_IP" ]; then
    log "  Private IP: $SQL_PRIVATE_IP"
fi

# Step 6: Create Artifact Registry with error handling
log "📦 Creating Artifact Registry: $REGISTRY_NAME"
if gcloud artifacts repositories describe "$REGISTRY_NAME" --location="$REGION" &> /dev/null; then
    log "✅ Artifact Registry $REGISTRY_NAME already exists"
else
    gcloud artifacts repositories create "$REGISTRY_NAME" \
        --repository-format=docker \
        --location="$REGION" \
        --description="Docker registry for SQL Retriever"
    
    # Configure Docker authentication
    gcloud auth configure-docker "$REGION-docker.pkg.dev"
    log "✅ Artifact Registry created and configured"
fi

# Step 7: Build and Push Docker Image with progress tracking
log "🐳 Building and pushing Docker image..."
IMAGE_URL="$REGION-docker.pkg.dev/$PROJECT_ID/$REGISTRY_NAME/$IMAGE_NAME:latest"

# Build the image with progress
log "Building Docker image: $IMAGE_NAME"
if ! docker build -t "$IMAGE_URL" .; then
    error "Docker build failed. Check Dockerfile and dependencies."
fi

# Push the image with progress tracking
log "Pushing Docker image to registry..."
log "Image URL: $IMAGE_URL"
log "Estimated registry cost: \$0.50-2/month"

# Enhanced Docker push with retry logic
PUSH_ATTEMPTS=0
MAX_PUSH_ATTEMPTS=3
while [ $PUSH_ATTEMPTS -lt $MAX_PUSH_ATTEMPTS ]; do
    if docker push "$IMAGE_URL"; then
        log "✅ Docker image pushed successfully"
        break
    else
        ((PUSH_ATTEMPTS++))
        if [ $PUSH_ATTEMPTS -lt $MAX_PUSH_ATTEMPTS ]; then
            warn "Push attempt $PUSH_ATTEMPTS failed, retrying in 10 seconds..."
            sleep 10
        else
            error "Docker push failed after $MAX_PUSH_ATTEMPTS attempts. Check network and registry permissions."
        fi
    fi
done

# Step 8: Deploy to Cloud Run with enhanced environment setup
log "☁️  Deploying to Cloud Run: $SERVICE_NAME"
log "Estimated cost: \$5-20/month (varies by usage)"

# Create environment variables
if [ "$USE_SECRET_MANAGER" = "true" ]; then
    DATABASE_URL="postgresql://$SQL_USER:\$SQL_PASSWORD_SECRET@//cloudsql/$CONNECTION_STRING/$SQL_DATABASE"
    ENV_VARS="DATABASE_PATH=$DATABASE_URL,RAG_VECTOR_STORE_PATH=gs://$BUCKET_NAME/rag,MODEL_NAME=$(get_config 'model_name'),LOG_LEVEL=$(get_config 'log_level'),ENVIRONMENT=$(get_config 'environment'),RAG_ENABLED=true,ENABLE_SAFETY_CHECKS=true,SQL_PUBLIC_IP=$SQL_PUBLIC_IP"
    
    if [ -n "$MODEL_ENDPOINT" ] && [ "$MODEL_ENDPOINT" != "your_runpod_endpoint_here" ]; then
        ENV_VARS="$ENV_VARS,MODEL_ENDPOINT=$MODEL_ENDPOINT"
    fi
    
    # Deploy with secrets
    gcloud run deploy "$SERVICE_NAME" \
        --image="$IMAGE_URL" \
        --platform=managed \
        --region="$REGION" \
        --allow-unauthenticated \
        --memory="$SERVICE_MEMORY" \
        --cpu="$SERVICE_CPU" \
        --min-instances="$SERVICE_MIN_INSTANCES" \
        --max-instances="$SERVICE_MAX_INSTANCES" \
        --timeout="$SERVICE_TIMEOUT" \
        --set-env-vars="$ENV_VARS" \
        --set-secrets="API_KEY=$API_KEY_REF:latest,SQL_PASSWORD_SECRET=$SQL_PASSWORD_REF:latest" \
        --add-cloudsql-instances="$CONNECTION_STRING"
else
    DATABASE_URL="postgresql://$SQL_USER:$SQL_PASSWORD@//cloudsql/$CONNECTION_STRING/$SQL_DATABASE"
    ENV_VARS="DATABASE_PATH=$DATABASE_URL,RAG_VECTOR_STORE_PATH=gs://$BUCKET_NAME/rag,API_KEY=$API_KEY,MODEL_NAME=$(get_config 'model_name'),LOG_LEVEL=$(get_config 'log_level'),ENVIRONMENT=$(get_config 'environment'),RAG_ENABLED=true,ENABLE_SAFETY_CHECKS=true,SQL_PUBLIC_IP=$SQL_PUBLIC_IP"
    
    if [ -n "$MODEL_ENDPOINT" ] && [ "$MODEL_ENDPOINT" != "your_runpod_endpoint_here" ]; then
        ENV_VARS="$ENV_VARS,MODEL_ENDPOINT=$MODEL_ENDPOINT"
    fi
    
    gcloud run deploy "$SERVICE_NAME" \
        --image="$IMAGE_URL" \
        --platform=managed \
        --region="$REGION" \
        --allow-unauthenticated \
        --memory="$SERVICE_MEMORY" \
        --cpu="$SERVICE_CPU" \
        --min-instances="$SERVICE_MIN_INSTANCES" \
        --max-instances="$SERVICE_MAX_INSTANCES" \
        --timeout="$SERVICE_TIMEOUT" \
        --set-env-vars="$ENV_VARS" \
        --add-cloudsql-instances="$CONNECTION_STRING"
fi

# Get the service URL
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format="value(status.url)")

log "✅ Cloud Run service deployed successfully!"
log "🌐 Service URL: $SERVICE_URL"

# Step 9: Enhanced monitoring and logging
log "📊 Setting up monitoring and logging..."

# Create log sink for errors
gcloud logging sinks create sql-retriever-error-sink \
    "storage.googleapis.com/$BUCKET_NAME/logs" \
    --log-filter='resource.type="cloud_run_revision" AND severity>=ERROR' \
    --project="$PROJECT_ID" || true

# Create alerting policy for high error rate
cat > alerting-policy.json << EOF
{
  "displayName": "SQL Retriever High Error Rate",
  "conditions": [
    {
      "displayName": "Error rate above 5%",
      "conditionThreshold": {
        "filter": "resource.type=\"cloud_run_revision\" resource.label.service_name=\"$SERVICE_NAME\"",
        "comparison": "COMPARISON_GREATER_THAN",
        "thresholdValue": 0.05
      }
    }
  ]
}
EOF

gcloud alpha monitoring policies create --policy-from-file=alerting-policy.json || warn "Could not create alerting policy"
rm -f alerting-policy.json

log "✅ Monitoring and logging configured"

# Step 10: Enhanced security configuration
log "🔒 Configuring security settings..."

# Set up IAM bindings for the service account
SERVICE_ACCOUNT_EMAIL=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format="value(spec.template.spec.serviceAccountName)")
if [ -z "$SERVICE_ACCOUNT_EMAIL" ]; then
    SERVICE_ACCOUNT_EMAIL="$PROJECT_ID-compute@developer.gserviceaccount.com"
fi

# Grant necessary permissions
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
    --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
    --role="roles/storage.objectViewer"

if [ "$USE_SECRET_MANAGER" = "true" ]; then
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
        --role="roles/secretmanager.secretAccessor"
fi

log "✅ Security settings configured"

# Step 11: Enhanced cost monitoring setup
log "💰 Setting up cost monitoring..."

# Get billing account
BILLING_ACCOUNT=$(gcloud beta billing projects describe $PROJECT_ID --format="value(billingAccountName)" | sed 's/.*\///' 2>/dev/null || echo "")

if [ -n "$BILLING_ACCOUNT" ]; then
    # Create budget alert
    gcloud beta billing budgets create \
        --billing-account="$BILLING_ACCOUNT" \
        --display-name="SQL Retriever Budget Alert" \
        --budget-amount=$(get_config 'daily_spend_limit')USD \
        --threshold-rules-percent=50,90,100 \
        --threshold-rules-spend-basis=CURRENT_SPEND \
        --all-projects || warn "Could not create budget alert. Please set up manually in console."
    
    log "✅ Budget alert created for \$$(get_config 'daily_spend_limit')/day"
else
    warn "Could not access billing account. Please set up budget alerts manually."
fi

# Basic health check
log "🏥 Performing initial health check..."
sleep 10  # Wait for service to fully start

if curl -s -f "$SERVICE_URL/health" > /dev/null 2>&1; then
    log "✅ Health check passed"
else
    warn "Health check failed - service may still be starting up"
fi

# Final Summary
log "🎉 Deployment Complete!"
echo ""
echo "==================== DEPLOYMENT SUMMARY ===================="
echo "Project ID:      $PROJECT_ID"
echo "Region:          $REGION"
echo "Service URL:     $SERVICE_URL"
echo "Database:        $SQL_INSTANCE ($SQL_DATABASE)"
echo "Database IP:     $SQL_PUBLIC_IP"
echo "Storage Bucket:  gs://$BUCKET_NAME"
echo "Docker Image:    $IMAGE_URL"
echo "Secret Manager:  $([ "$USE_SECRET_MANAGER" = "true" ] && echo "Enabled" || echo "Disabled")"
echo ""
echo "==================== COST ESTIMATES ===================="
echo "Cloud Run:       \$5-20/month (varies by usage)"
echo "Cloud SQL:       \$7-15/month ($SQL_TIER)"
echo "Cloud Storage:   \$1-5/month (varies by data size)"
echo "Artifact Registry: \$0.50-2/month"
echo "Total Estimated: \$15-50/month"
echo ""
echo "==================== NEXT STEPS ===================="
echo "1. Test the deployment: curl $SERVICE_URL/health"
echo "2. Test with API key: curl -H 'Authorization: Bearer YOUR_API_KEY' $SERVICE_URL/stats"
echo "3. View logs: gcloud run services logs tail $SERVICE_NAME --region=$REGION"
echo "4. Monitor costs: https://console.cloud.google.com/billing"
echo "5. Run verification: ./verify_gcp.sh"
echo ""
echo "==================== IMPORTANT NOTES ===================="
if [ "$USE_SECRET_MANAGER" = "true" ]; then
    warn "Secrets stored in Secret Manager (recommended for production)"
else
    warn "API Key: $API_KEY (Keep this secure!)"
    warn "Database Password: $SQL_PASSWORD (Keep this secure!)"
    warn "Consider enabling Secret Manager for production deployments"
fi
warn "Make sure to update these in your CI/CD pipeline securely"
echo ""
log "✅ All done! Your SQL Retriever API is now live on GCP." 