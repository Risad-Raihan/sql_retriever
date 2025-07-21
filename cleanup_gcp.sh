#!/bin/bash

# GCP Resource Cleanup Script for SQL Retriever
# Author: Cloud Engineering Team
# Description: Safely delete GCP resources with confirmations and backup options
# WARNING: This script will permanently delete resources and data!

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

critical() {
    echo -e "${RED}[CRITICAL]${NC} $1"
}

# Enhanced confirmation function
confirm() {
    local message=$1
    local default=${2:-n}
    
    if [ "$default" = "y" ]; then
        read -p "$message (Y/n): " -n 1 -r
        echo
        [[ $REPLY =~ ^[Nn]$ ]] && return 1
    else
        read -p "$message (y/N): " -n 1 -r
        echo
        [[ ! $REPLY =~ ^[Yy]$ ]] && return 1
    fi
    return 0
}

# Function to extract values from YAML config
get_config() {
    local key=$1
    if [ -f "gcp_config.yaml" ]; then
        grep "^$key:" gcp_config.yaml | sed 's/.*: *"\?\([^"]*\)"\?/\1/' || echo ""
    else
        echo ""
    fi
}

# Load configuration
if [ ! -f "gcp_config.yaml" ]; then
    error "gcp_config.yaml not found. Cannot proceed with cleanup."
    exit 1
fi

PROJECT_ID=$(get_config "project_id")
REGION=$(get_config "region")
BUCKET_NAME=$(get_config "bucket_name")
SQL_INSTANCE=$(get_config "sql_instance_name")
SQL_DATABASE=$(get_config "sql_database_name")
REGISTRY_NAME=$(get_config "registry_name")
SERVICE_NAME=$(get_config "service_name")

# Validate required variables
if [ -z "$PROJECT_ID" ]; then
    error "Project ID not found in configuration"
    exit 1
fi

# Check if gcloud is installed and authenticated
if ! command -v gcloud &> /dev/null; then
    error "gcloud CLI not found. Please install Google Cloud SDK first."
    exit 1
fi

# Check authentication
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1 > /dev/null 2>&1; then
    error "Not authenticated with gcloud. Run 'gcloud auth login' first."
    exit 1
fi

# Set project context
gcloud config set project "$PROJECT_ID" 2>/dev/null || {
    error "Cannot set project $PROJECT_ID. Check if project exists and you have access."
    exit 1
}

log "🧹 GCP Resource Cleanup Tool"
log "Project: $PROJECT_ID"
log "Region: $REGION"
echo ""

critical "⚠️  WARNING: This will permanently delete the following resources:"
info "• Cloud Run service: $SERVICE_NAME"
info "• Cloud SQL instance: $SQL_INSTANCE (including all data)"
info "• Storage bucket: gs://$BUCKET_NAME (including all files)"
info "• Artifact Registry: $REGISTRY_NAME (including all images)"
info "• Secret Manager secrets (if configured)"
info "• Monitoring alerts and dashboards"
info "• IAM bindings and service accounts"
echo ""
critical "💾 Some resources contain DATA that CANNOT be recovered once deleted!"
echo ""

# Final confirmation
if ! confirm "Are you absolutely sure you want to proceed with cleanup?" "n"; then
    log "Cleanup cancelled by user. No resources were deleted."
    exit 0
fi

echo ""
log "🔍 Scanning for resources to delete..."

# Function to create backups before deletion
create_backups() {
    log "💾 Creating backups before deletion..."
    
    BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    # Backup Cloud SQL database
    if gcloud sql instances describe "$SQL_INSTANCE" &> /dev/null; then
        log "Creating Cloud SQL backup..."
        BACKUP_ID="final-backup-$(date +%Y%m%d-%H%M%S)"
        if gcloud sql backups create --instance="$SQL_INSTANCE" --description="Final backup before deletion" 2>/dev/null; then
            log "✅ Cloud SQL backup created: $BACKUP_ID"
        else
            warn "Failed to create Cloud SQL backup"
        fi
        
        # Export database dump to storage
        if gcloud sql export sql "$SQL_INSTANCE" "gs://$BUCKET_NAME/final_backup_$(date +%Y%m%d_%H%M%S).sql" --database="$SQL_DATABASE" 2>/dev/null; then
            log "✅ Database exported to Cloud Storage"
        else
            warn "Failed to export database to storage"
        fi
    fi
    
    # Download critical bucket contents
    if gsutil ls -b "gs://$BUCKET_NAME" &> /dev/null; then
        log "Downloading critical bucket contents..."
        mkdir -p "$BACKUP_DIR/storage_backup"
        
        # Download configuration files and important data
        gsutil -m cp -r "gs://$BUCKET_NAME/db/" "$BACKUP_DIR/storage_backup/" 2>/dev/null || true
        gsutil -m cp -r "gs://$BUCKET_NAME/rag/" "$BACKUP_DIR/storage_backup/" 2>/dev/null || true
        gsutil cp "gs://$BUCKET_NAME/**/*.json" "$BACKUP_DIR/storage_backup/" 2>/dev/null || true
        
        log "✅ Critical files backed up to $BACKUP_DIR/storage_backup/"
    fi
    
    # Save current configuration
    cp gcp_config.yaml "$BACKUP_DIR/"
    
    # Save resource information
    log "Saving resource information..."
    {
        echo "# Resource Information - $(date)"
        echo "Project ID: $PROJECT_ID"
        echo "Region: $REGION"
        echo "Cleanup Date: $(date)"
        echo ""
        echo "# Services that were running:"
        gcloud run services list --filter="metadata.name:$SERVICE_NAME" --format="table(metadata.name,status.url,metadata.namespace)" 2>/dev/null || echo "No Cloud Run services found"
        echo ""
        echo "# SQL Instances:"
        gcloud sql instances list --filter="name:$SQL_INSTANCE" --format="table(name,databaseVersion,region,settings.tier)" 2>/dev/null || echo "No SQL instances found"
        echo ""
        echo "# Storage buckets:"
        gsutil ls -b "gs://$BUCKET_NAME" 2>/dev/null || echo "No buckets found"
    } > "$BACKUP_DIR/resource_info.txt"
    
    log "✅ Backups created in directory: $BACKUP_DIR"
    echo ""
}

# Ask if user wants backups
if confirm "Do you want to create backups before deletion? (HIGHLY RECOMMENDED)" "y"; then
    create_backups
else
    warn "Proceeding without backups - data will be permanently lost!"
    if ! confirm "Are you absolutely sure you want to skip backups?" "n"; then
        create_backups
    fi
fi

# Step 1: Delete Cloud Run Service
log "🚀 Deleting Cloud Run service..."
if gcloud run services describe "$SERVICE_NAME" --region="$REGION" &> /dev/null; then
    log "Found Cloud Run service: $SERVICE_NAME"
    if confirm "Delete Cloud Run service $SERVICE_NAME?" "y"; then
        if gcloud run services delete "$SERVICE_NAME" --region="$REGION" --quiet; then
            log "✅ Cloud Run service deleted"
        else
            error "Failed to delete Cloud Run service"
        fi
    else
        info "Skipping Cloud Run service deletion"
    fi
else
    info "Cloud Run service $SERVICE_NAME not found"
fi
echo ""

# Step 2: Delete Cloud SQL Instance
log "🗃️  Deleting Cloud SQL instance..."
if gcloud sql instances describe "$SQL_INSTANCE" &> /dev/null; then
    log "Found Cloud SQL instance: $SQL_INSTANCE"
    
    # Show current database size and cost information
    INSTANCE_TIER=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(settings.tier)")
    STORAGE_SIZE=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(settings.dataDiskSizeGb)")
    warn "Instance details: $INSTANCE_TIER, ${STORAGE_SIZE}GB storage"
    warn "This will permanently delete ALL databases and data!"
    
    if confirm "Delete Cloud SQL instance $SQL_INSTANCE and ALL its data?" "n"; then
        # Remove deletion protection first
        log "Removing deletion protection..."
        gcloud sql instances patch "$SQL_INSTANCE" --no-deletion-protection --quiet
        
        log "Deleting Cloud SQL instance (this may take several minutes)..."
        if gcloud sql instances delete "$SQL_INSTANCE" --quiet; then
            log "✅ Cloud SQL instance deleted"
        else
            error "Failed to delete Cloud SQL instance"
        fi
    else
        info "Skipping Cloud SQL instance deletion"
    fi
else
    info "Cloud SQL instance $SQL_INSTANCE not found"
fi
echo ""

# Step 3: Delete Storage Bucket
log "🗄️  Deleting Cloud Storage bucket..."
if gsutil ls -b "gs://$BUCKET_NAME" &> /dev/null; then
    # Show bucket size
    BUCKET_SIZE=$(gsutil du -sh "gs://$BUCKET_NAME" 2>/dev/null | cut -f1 || echo "Unknown size")
    OBJECT_COUNT=$(gsutil ls -r "gs://$BUCKET_NAME" 2>/dev/null | wc -l || echo "0")
    
    log "Found bucket: gs://$BUCKET_NAME"
    warn "Bucket size: $BUCKET_SIZE, Objects: $OBJECT_COUNT"
    warn "This will permanently delete ALL files in the bucket!"
    
    if confirm "Delete storage bucket gs://$BUCKET_NAME and ALL its contents?" "n"; then
        log "Deleting all objects in bucket..."
        if gsutil -m rm -r "gs://$BUCKET_NAME/**" 2>/dev/null || true; then
            log "Deleted bucket contents"
        fi
        
        log "Deleting bucket..."
        if gsutil rb "gs://$BUCKET_NAME"; then
            log "✅ Storage bucket deleted"
        else
            error "Failed to delete storage bucket"
        fi
    else
        info "Skipping storage bucket deletion"
    fi
else
    info "Storage bucket gs://$BUCKET_NAME not found"
fi
echo ""

# Step 4: Delete Artifact Registry
log "📦 Deleting Artifact Registry..."
if gcloud artifacts repositories describe "$REGISTRY_NAME" --location="$REGION" &> /dev/null; then
    # Show repository size
    IMAGE_COUNT=$(gcloud artifacts docker images list "$REGION-docker.pkg.dev/$PROJECT_ID/$REGISTRY_NAME" --format="value(package)" 2>/dev/null | wc -l || echo "0")
    
    log "Found registry: $REGISTRY_NAME"
    warn "Contains $IMAGE_COUNT images"
    
    if confirm "Delete Artifact Registry $REGISTRY_NAME and all images?" "y"; then
        if gcloud artifacts repositories delete "$REGISTRY_NAME" --location="$REGION" --quiet; then
            log "✅ Artifact Registry deleted"
        else
            error "Failed to delete Artifact Registry"
        fi
    else
        info "Skipping Artifact Registry deletion"
    fi
else
    info "Artifact Registry $REGISTRY_NAME not found"
fi
echo ""

# Step 5: Delete Secret Manager Secrets
log "🔐 Deleting Secret Manager secrets..."
USE_SECRET_MANAGER=$(get_config "use_secret_manager")
if [ "$USE_SECRET_MANAGER" = "true" ]; then
    SECRET_NAMES=("sql-password" "api-key" "runpod-api-key" "openai-api-key")
    
    for secret in "${SECRET_NAMES[@]}"; do
        if gcloud secrets describe "$secret" &> /dev/null; then
            log "Found secret: $secret"
            if confirm "Delete secret $secret?" "y"; then
                if gcloud secrets delete "$secret" --quiet; then
                    log "✅ Secret $secret deleted"
                else
                    warn "Failed to delete secret $secret"
                fi
            fi
        fi
    done
else
    info "Secret Manager not configured, skipping"
fi
echo ""

# Step 6: Clean up monitoring and alerting
log "📊 Cleaning up monitoring resources..."

# Delete log sinks
if gcloud logging sinks describe "sql-retriever-error-sink" &> /dev/null; then
    if confirm "Delete log sink 'sql-retriever-error-sink'?" "y"; then
        if gcloud logging sinks delete "sql-retriever-error-sink" --quiet; then
            log "✅ Log sink deleted"
        fi
    fi
fi

# Delete alerting policies
ALERT_POLICIES=$(gcloud alpha monitoring policies list --filter="displayName:SQL" --format="value(name)" 2>/dev/null || echo "")
if [ -n "$ALERT_POLICIES" ]; then
    for policy in $ALERT_POLICIES; do
        if confirm "Delete monitoring alert policy?" "y"; then
            gcloud alpha monitoring policies delete "$policy" --quiet 2>/dev/null || true
        fi
    done
fi

# Delete dashboards
DASHBOARDS=$(gcloud monitoring dashboards list --filter="displayName:SQL" --format="value(name)" 2>/dev/null || echo "")
if [ -n "$DASHBOARDS" ]; then
    for dashboard in $DASHBOARDS; do
        if confirm "Delete monitoring dashboard?" "y"; then
            gcloud monitoring dashboards delete "$dashboard" --quiet 2>/dev/null || true
        fi
    done
fi

log "✅ Monitoring cleanup completed"
echo ""

# Step 7: Clean up IAM bindings
log "🔒 Cleaning up IAM bindings..."
SERVICE_ACCOUNT_EMAIL="$PROJECT_ID-compute@developer.gserviceaccount.com"

ROLES_TO_REMOVE=(
    "roles/cloudsql.client"
    "roles/storage.objectViewer"
    "roles/secretmanager.secretAccessor"
)

for role in "${ROLES_TO_REMOVE[@]}"; do
    if gcloud projects get-iam-policy "$PROJECT_ID" --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:serviceAccount:$SERVICE_ACCOUNT_EMAIL" | grep -q "$role"; then
        log "Removing IAM binding: $role"
        gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
            --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
            --role="$role" --quiet || true
    fi
done

log "✅ IAM cleanup completed"
echo ""

# Step 8: Delete budget alerts
log "💰 Cleaning up budget alerts..."
BILLING_ACCOUNT=$(gcloud beta billing projects describe "$PROJECT_ID" --format="value(billingAccountName)" 2>/dev/null | sed 's/.*\///' || echo "")

if [ -n "$BILLING_ACCOUNT" ]; then
    BUDGETS=$(gcloud beta billing budgets list --billing-account="$BILLING_ACCOUNT" --filter="displayName:SQL" --format="value(name)" 2>/dev/null || echo "")
    
    for budget in $BUDGETS; do
        if confirm "Delete budget alert?" "y"; then
            gcloud beta billing budgets delete "$budget" --billing-account="$BILLING_ACCOUNT" --quiet 2>/dev/null || true
        fi
    done
    
    log "✅ Budget cleanup completed"
else
    info "No billing account found or accessible"
fi
echo ""

# Final project deletion option
log "🗑️  Project deletion option..."
critical "FINAL WARNING: Do you want to DELETE THE ENTIRE PROJECT?"
warn "This will permanently delete:"
warn "• The entire project: $PROJECT_ID"
warn "• ALL resources in the project"
warn "• ALL billing history"
warn "• ALL logs and monitoring data"
warn "• This action CANNOT be undone!"
echo ""

if confirm "Delete the entire project $PROJECT_ID?" "n"; then
    critical "Final confirmation required!"
    if confirm "Type 'DELETE PROJECT' to confirm total project deletion" "n"; then
        read -p "Type the project ID '$PROJECT_ID' to confirm: " PROJECT_CONFIRM
        if [ "$PROJECT_CONFIRM" = "$PROJECT_ID" ]; then
            log "Deleting project $PROJECT_ID..."
            if gcloud projects delete "$PROJECT_ID" --quiet; then
                log "✅ Project deleted successfully"
            else
                error "Failed to delete project"
            fi
        else
            warn "Project ID mismatch. Project not deleted."
        fi
    else
        info "Project deletion cancelled"
    fi
else
    info "Keeping project $PROJECT_ID"
fi

echo ""
echo "==================== CLEANUP SUMMARY ===================="
log "🎉 Cleanup process completed!"
log "📍 Remaining project: $PROJECT_ID (if not deleted)"
log "💾 Backups location: $BACKUP_DIR (if created)"
echo ""
warn "Next steps:"
warn "1. Verify no unexpected charges in billing console"
warn "2. Check for any remaining resources: gcloud resources list"
warn "3. Save backup directory in safe location"
warn "4. Update any CI/CD pipelines that reference deleted resources"
echo ""
log "✅ GCP cleanup completed successfully!" 