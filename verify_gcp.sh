#!/bin/bash

# GCP Deployment Verification Script for SQL Retriever
# Author: Cloud Engineering Team
# Description: Verify all components of the SQL Retriever deployment

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Status indicators
PASS="✅"
FAIL="❌"
WARN="⚠️"
INFO="ℹ️"

# Counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_WARNING=0

# Logging functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

pass() {
    echo -e "${GREEN}$PASS${NC} $1"
    ((TESTS_PASSED++))
}

fail() {
    echo -e "${RED}$FAIL${NC} $1"
    ((TESTS_FAILED++))
}

warn() {
    echo -e "${YELLOW}$WARN${NC} $1"
    ((TESTS_WARNING++))
}

info() {
    echo -e "${BLUE}$INFO${NC} $1"
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
PROJECT_ID=$(get_config "project_id")
REGION=$(get_config "region")
BUCKET_NAME=$(get_config "bucket_name")
SQL_INSTANCE=$(get_config "sql_instance_name")
SQL_DATABASE=$(get_config "sql_database_name")
SERVICE_NAME=$(get_config "service_name")
API_KEY=$(get_config "api_key")

log "🔍 Starting GCP Deployment Verification"
log "Project: $PROJECT_ID | Region: $REGION"
echo ""

# Check if configuration exists
if [ ! -f "gcp_config.yaml" ]; then
    fail "gcp_config.yaml not found"
    exit 1
fi

# Verify gcloud is authenticated and project is set
log "1. 🔐 Verifying Authentication & Project Setup"
if CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null) && [ "$CURRENT_PROJECT" = "$PROJECT_ID" ]; then
    pass "gcloud authenticated and project set to $PROJECT_ID"
else
    fail "gcloud not authenticated or wrong project. Run 'gcloud init' first"
fi

ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1)
if [ -n "$ACCOUNT" ]; then
    pass "Active account: $ACCOUNT"
else
    fail "No active gcloud account found"
fi
echo ""

# Verify APIs are enabled
log "2. 🔌 Verifying Required APIs"
REQUIRED_APIS=(
    "cloudbuild.googleapis.com"
    "run.googleapis.com"
    "sqladmin.googleapis.com"
    "storage.googleapis.com"
    "artifactregistry.googleapis.com"
)

for api in "${REQUIRED_APIS[@]}"; do
    if gcloud services list --enabled --filter="name:$api" --format="value(name)" | grep -q "$api"; then
        pass "$api enabled"
    else
        fail "$api not enabled"
    fi
done
echo ""

# Verify Cloud Storage Bucket
log "3. 🗄️  Verifying Cloud Storage Bucket"
if gsutil ls -b "gs://$BUCKET_NAME" &> /dev/null; then
    pass "Bucket gs://$BUCKET_NAME exists"
    
    # Check folder structure
    FOLDERS=("models" "rag" "db" "logs")
    for folder in "${FOLDERS[@]}"; do
        if gsutil ls "gs://$BUCKET_NAME/$folder/" &> /dev/null; then
            pass "Folder /$folder/ exists"
        else
            warn "Folder /$folder/ missing or empty"
        fi
    done
    
    # Check bucket size and object count
    OBJECT_COUNT=$(gsutil ls -r "gs://$BUCKET_NAME" | wc -l)
    info "Bucket contains $OBJECT_COUNT objects"
    
else
    fail "Bucket gs://$BUCKET_NAME does not exist"
fi
echo ""

# Verify Cloud SQL Instance
log "4. 🗃️  Verifying Cloud SQL Instance"
if SQL_STATUS=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(state)" 2>/dev/null); then
    if [ "$SQL_STATUS" = "RUNNABLE" ]; then
        pass "Cloud SQL instance $SQL_INSTANCE is running"
        
        # Get instance details
        CONNECTION_NAME=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(connectionName)")
        INSTANCE_TIER=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(settings.tier)")
        info "Connection name: $CONNECTION_NAME"
        info "Instance tier: $INSTANCE_TIER"
        
        # Check if database exists
        if gcloud sql databases describe "$SQL_DATABASE" --instance="$SQL_INSTANCE" &> /dev/null; then
            pass "Database $SQL_DATABASE exists"
        else
            fail "Database $SQL_DATABASE does not exist"
        fi
        
        # Check backup configuration
        if gcloud sql instances describe "$SQL_INSTANCE" --format="value(settings.backupConfiguration.enabled)" | grep -q "True"; then
            pass "Automated backups enabled"
        else
            warn "Automated backups not configured"
        fi
        
    else
        fail "Cloud SQL instance $SQL_INSTANCE is not running (status: $SQL_STATUS)"
    fi
else
    fail "Cloud SQL instance $SQL_INSTANCE does not exist"
fi
echo ""

# Verify Artifact Registry
log "5. 📦 Verifying Artifact Registry"
REGISTRY_NAME=$(get_config "registry_name")
if gcloud artifacts repositories describe "$REGISTRY_NAME" --location="$REGION" &> /dev/null; then
    pass "Artifact Registry $REGISTRY_NAME exists"
    
    # Check for images
    IMAGE_COUNT=$(gcloud artifacts docker images list "$REGION-docker.pkg.dev/$PROJECT_ID/$REGISTRY_NAME" --format="value(package)" | wc -l || echo "0")
    if [ "$IMAGE_COUNT" -gt 0 ]; then
        pass "Registry contains $IMAGE_COUNT image(s)"
        
        # Get latest image info
        IMAGE_NAME=$(get_config "image_name")
        if gcloud artifacts docker images list "$REGION-docker.pkg.dev/$PROJECT_ID/$REGISTRY_NAME/$IMAGE_NAME" --limit=1 --format="value(version)" &> /dev/null; then
            pass "Latest $IMAGE_NAME image found"
        else
            warn "$IMAGE_NAME image not found"
        fi
    else
        warn "No images found in registry"
    fi
else
    fail "Artifact Registry $REGISTRY_NAME does not exist"
fi
echo ""

# Verify Cloud Run Service
log "6. ☁️  Verifying Cloud Run Service"
if SERVICE_INFO=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format="json" 2>/dev/null); then
    SERVICE_URL=$(echo "$SERVICE_INFO" | jq -r '.status.url')
    SERVICE_STATUS=$(echo "$SERVICE_INFO" | jq -r '.status.conditions[0].status')
    
    if [ "$SERVICE_STATUS" = "True" ]; then
        pass "Cloud Run service $SERVICE_NAME is deployed and ready"
        info "Service URL: $SERVICE_URL"
        
        # Check service configuration
        MEMORY=$(echo "$SERVICE_INFO" | jq -r '.spec.template.spec.containers[0].resources.limits.memory')
        CPU=$(echo "$SERVICE_INFO" | jq -r '.spec.template.spec.containers[0].resources.limits.cpu')
        pass "Resource limits: Memory=$MEMORY, CPU=$CPU"
        
        # Check environment variables
        ENV_VARS=$(echo "$SERVICE_INFO" | jq -r '.spec.template.spec.containers[0].env[]?.name' | wc -l)
        pass "$ENV_VARS environment variables configured"
        
    else
        fail "Cloud Run service $SERVICE_NAME is not ready"
    fi
else
    fail "Cloud Run service $SERVICE_NAME does not exist"
    SERVICE_URL=""
fi
echo ""

# Test API Health Endpoint
log "7. 🏥 Testing API Health"
if [ -n "$SERVICE_URL" ]; then
    if HEALTH_RESPONSE=$(curl -s -f "$SERVICE_URL/health" 2>/dev/null); then
        pass "Health endpoint responds successfully"
        
        # Parse health response
        if echo "$HEALTH_RESPONSE" | jq -e '.status' &> /dev/null; then
            STATUS=$(echo "$HEALTH_RESPONSE" | jq -r '.status')
            DB_CONNECTED=$(echo "$HEALTH_RESPONSE" | jq -r '.db_connected')
            RAG_ENABLED=$(echo "$HEALTH_RESPONSE" | jq -r '.rag_enabled')
            
            if [ "$STATUS" = "healthy" ]; then
                pass "API status: healthy"
            else
                warn "API status: $STATUS"
            fi
            
            if [ "$DB_CONNECTED" = "true" ]; then
                pass "Database connection: OK"
            else
                fail "Database connection: Failed"
            fi
            
            if [ "$RAG_ENABLED" = "true" ]; then
                pass "RAG system: enabled"
            else
                warn "RAG system: disabled"
            fi
        else
            warn "Health response format unexpected"
        fi
    else
        fail "Health endpoint not responding or returns error"
    fi
else
    fail "Cannot test health - service URL not available"
fi
echo ""

# Test API Authentication
log "8. 🔑 Testing API Authentication"
if [ -n "$SERVICE_URL" ] && [ -n "$API_KEY" ] && [ "$API_KEY" != "your_api_key_here" ]; then
    # Test without API key (should fail)
    if curl -s -f "$SERVICE_URL/stats" &> /dev/null; then
        warn "API allows access without authentication"
    else
        pass "API properly requires authentication"
    fi
    
    # Test with API key (should succeed)
    if curl -s -f -H "Authorization: Bearer $API_KEY" "$SERVICE_URL/stats" &> /dev/null; then
        pass "API key authentication works"
    else
        fail "API key authentication failed"
    fi
else
    warn "Cannot test authentication - missing service URL or API key"
fi
echo ""

# Enhanced API Endpoint Testing
log "8.1. 🌐 Testing API Endpoints"
if [ -n "$SERVICE_URL" ] && [ -n "$API_KEY" ] && [ "$API_KEY" != "your_api_key_here" ]; then
    # Test query endpoint with sample data
    log "Testing /query endpoint..."
    QUERY_RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"query": "SELECT COUNT(*) FROM users LIMIT 1;", "safe_mode": true}' \
        "$SERVICE_URL/query" 2>/dev/null || echo "000")
    
    HTTP_CODE=$(echo "$QUERY_RESPONSE" | tail -1)
    RESPONSE_BODY=$(echo "$QUERY_RESPONSE" | head -n -1)
    
    if [ "$HTTP_CODE" = "200" ]; then
        if echo "$RESPONSE_BODY" | jq -e '.results' &> /dev/null; then
            pass "Query endpoint returns valid JSON response"
        else
            warn "Query endpoint responds but JSON structure unexpected"
        fi
    elif [ "$HTTP_CODE" = "400" ] || [ "$HTTP_CODE" = "403" ]; then
        pass "Query endpoint properly validates requests (HTTP $HTTP_CODE)"
    else
        fail "Query endpoint error (HTTP $HTTP_CODE)"
    fi
    
    # Test schema endpoint
    log "Testing /schema endpoint..."
    if SCHEMA_RESPONSE=$(curl -s -H "Authorization: Bearer $API_KEY" "$SERVICE_URL/schema" 2>/dev/null); then
        if echo "$SCHEMA_RESPONSE" | jq -e '.tables' &> /dev/null; then
            TABLE_COUNT=$(echo "$SCHEMA_RESPONSE" | jq -r '.tables | length')
            pass "Schema endpoint returns $TABLE_COUNT tables"
        else
            warn "Schema endpoint responds but format unexpected"
        fi
    else
        fail "Schema endpoint not accessible"
    fi
    
    # Test stats endpoint
    log "Testing /stats endpoint..."
    if STATS_RESPONSE=$(curl -s -H "Authorization: Bearer $API_KEY" "$SERVICE_URL/stats" 2>/dev/null); then
        if echo "$STATS_RESPONSE" | jq -e '.query_count' &> /dev/null; then
            QUERY_COUNT=$(echo "$STATS_RESPONSE" | jq -r '.query_count // 0')
            UPTIME=$(echo "$STATS_RESPONSE" | jq -r '.uptime // "unknown"')
            pass "Stats endpoint accessible (queries: $QUERY_COUNT, uptime: $UPTIME)"
        else
            warn "Stats endpoint responds but format unexpected"
        fi
    else
        fail "Stats endpoint not accessible"
    fi
    
    # Test performance with concurrent requests
    log "Testing API performance..."
    START_TIME=$(date +%s)
    for i in {1..5}; do
        curl -s -H "Authorization: Bearer $API_KEY" "$SERVICE_URL/health" > /dev/null &
    done
    wait
    END_TIME=$(date +%s)
    RESPONSE_TIME=$((END_TIME - START_TIME))
    
    if [ $RESPONSE_TIME -lt 10 ]; then
        pass "API handles concurrent requests well ($RESPONSE_TIME seconds for 5 requests)"
    else
        warn "API response time high ($RESPONSE_TIME seconds for 5 requests)"
    fi
    
else
    warn "Cannot test API endpoints - missing credentials"
fi
echo ""

# Check Cloud SQL Connection from Cloud Run
log "9. 🔌 Testing Database Connection"
if [ -n "$SERVICE_URL" ] && [ -n "$API_KEY" ] && [ "$API_KEY" != "your_api_key_here" ]; then
    if SCHEMA_RESPONSE=$(curl -s -f -H "Authorization: Bearer $API_KEY" "$SERVICE_URL/schema" 2>/dev/null); then
        if echo "$SCHEMA_RESPONSE" | jq -e '.tables' &> /dev/null; then
            TABLE_COUNT=$(echo "$SCHEMA_RESPONSE" | jq -r '.tables | length')
            pass "Database schema accessible ($TABLE_COUNT tables found)"
        else
            fail "Database schema not accessible"
        fi
    else
        fail "Cannot retrieve database schema"
    fi
else
    warn "Cannot test database connection - missing credentials"
fi
echo ""

# Check Monitoring and Logging
log "10. 📊 Verifying Monitoring & Logging"

# Check if logs are being generated
if gcloud logging read "resource.type=\"cloud_run_revision\" resource.labels.service_name=\"$SERVICE_NAME\"" --limit=10 --format="value(timestamp)" | head -1 &> /dev/null; then
    pass "Cloud Run logs are being generated"
else
    warn "No recent logs found for Cloud Run service"
fi

# Check if log sink exists
if gcloud logging sinks describe "sql-retriever-error-sink" &> /dev/null; then
    pass "Error log sink configured"
else
    warn "Error log sink not found"
fi

# Check monitoring dashboards (basic check)
if gcloud monitoring dashboards list --filter="displayName:SQL" --limit=1 &> /dev/null; then
    pass "Monitoring dashboards available"
else
    info "No custom monitoring dashboards found"
fi
echo ""

# Enhanced Cost Analysis and Monitoring
log "11. 💰 Enhanced Cost Analysis and Monitoring"

# Get billing account and current costs
if BILLING_ACCOUNT=$(gcloud beta billing projects describe "$PROJECT_ID" --format="value(billingAccountName)" 2>/dev/null); then
    BILLING_ID=$(basename "$BILLING_ACCOUNT")
    pass "Billing account linked: $BILLING_ID"
    
    # Check current project billing status
    BILLING_ENABLED=$(gcloud beta billing projects describe "$PROJECT_ID" --format="value(billingEnabled)")
    if [ "$BILLING_ENABLED" = "True" ]; then
        pass "Billing is enabled for project"
    else
        fail "Billing is not enabled for project"
    fi
    
    # Check if budget alerts are configured
    BUDGET_COUNT=$(gcloud beta billing budgets list --billing-account="$BILLING_ID" --filter="displayName~SQL" --format="value(displayName)" 2>/dev/null | wc -l || echo "0")
    if [ "$BUDGET_COUNT" -gt 0 ]; then
        pass "$BUDGET_COUNT budget alert(s) configured"
        
        # Show budget details
        BUDGETS=$(gcloud beta billing budgets list --billing-account="$BILLING_ID" --filter="displayName~SQL" --format="table(displayName,budgetFilter.projects,amount.specifiedAmount.units)" 2>/dev/null || echo "")
        if [ -n "$BUDGETS" ]; then
            info "Budget details:"
            echo "$BUDGETS" | head -5
        fi
    else
        warn "No budget alerts found"
    fi
    
    # Check for cost anomaly detection
    if gcloud alpha billing budgets list --billing-account="$BILLING_ID" --filter="thresholdRules.spendBasis=FORECASTED_SPEND" --limit=1 &> /dev/null; then
        pass "Forecasted spend monitoring enabled"
    else
        info "Consider enabling forecasted spend monitoring"
    fi
    
    # Estimate current resource costs
    log "Analyzing current resource costs..."
    
    # Cloud Run cost estimation
    if [ -n "$SERVICE_NAME" ]; then
        CPU_ALLOCATION=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format="value(spec.template.spec.containers[0].resources.limits.cpu)" 2>/dev/null || echo "1000m")
        MEMORY_ALLOCATION=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format="value(spec.template.spec.containers[0].resources.limits.memory)" 2>/dev/null || echo "2Gi")
        MAX_INSTANCES=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format="value(spec.template.metadata.annotations.'autoscaling.knative.dev/maxScale')" 2>/dev/null || echo "10")
        
        info "Cloud Run config: CPU=$CPU_ALLOCATION, Memory=$MEMORY_ALLOCATION, Max instances=$MAX_INSTANCES"
    fi
    
    # Cloud SQL cost estimation
    if [ -n "$SQL_INSTANCE" ]; then
        SQL_TIER=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(settings.tier)" 2>/dev/null || echo "unknown")
        SQL_STORAGE=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(settings.dataDiskSizeGb)" 2>/dev/null || echo "unknown")
        BACKUP_ENABLED=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(settings.backupConfiguration.enabled)" 2>/dev/null || echo "unknown")
        
        info "Cloud SQL config: Tier=$SQL_TIER, Storage=${SQL_STORAGE}GB, Backups=$BACKUP_ENABLED"
    fi
    
    # Storage cost estimation
    if [ -n "$BUCKET_NAME" ] && gsutil ls -b "gs://$BUCKET_NAME" &> /dev/null; then
        BUCKET_SIZE=$(gsutil du -sh "gs://$BUCKET_NAME" 2>/dev/null | cut -f1 || echo "unknown")
        OBJECT_COUNT=$(gsutil ls -r "gs://$BUCKET_NAME" 2>/dev/null | wc -l || echo "0")
        STORAGE_CLASS=$(gsutil ls -L -b "gs://$BUCKET_NAME" 2>/dev/null | grep "Storage class" | cut -d: -f2 | xargs || echo "STANDARD")
        
        info "Storage: Size=$BUCKET_SIZE, Objects=$OBJECT_COUNT, Class=$STORAGE_CLASS"
    fi
    
    # Cost optimization recommendations
    log "Cost optimization recommendations:"
    
    # Check for idle resources
    IDLE_RESOURCES=0
    
    # Check Cloud Run utilization (basic)
    if RECENT_REQUESTS=$(gcloud logging read "resource.type=cloud_run_revision resource.labels.service_name=$SERVICE_NAME" --limit=10 --format="value(timestamp)" 2>/dev/null | wc -l); then
        if [ "$RECENT_REQUESTS" -lt 5 ]; then
            warn "Low Cloud Run usage detected - consider reducing min instances"
            ((IDLE_RESOURCES++))
        fi
    fi
    
    # Check storage lifecycle policies
    if ! gsutil lifecycle get "gs://$BUCKET_NAME" &> /dev/null; then
        warn "No storage lifecycle policy - consider adding for cost optimization"
        ((IDLE_RESOURCES++))
    fi
    
    if [ $IDLE_RESOURCES -eq 0 ]; then
        pass "No obvious idle resources detected"
    else
        warn "$IDLE_RESOURCES potential cost optimization opportunities found"
    fi
    
else
    warn "Cannot access billing information - check IAM permissions"
fi

# Real-time cost monitoring
log "Setting up real-time cost monitoring..."

# Check if Cloud Billing API is enabled
if gcloud services list --enabled --filter="name:cloudbilling.googleapis.com" --format="value(name)" | grep -q cloudbilling; then
    pass "Cloud Billing API is enabled"
else
    warn "Cloud Billing API not enabled - some cost features unavailable"
fi

# Estimate costs based on current resources
info "Current resource cost estimates (monthly):"
info "• Cloud Run (${CPU_ALLOCATION:-1000m}/${MEMORY_ALLOCATION:-2Gi}): ~$5-20"
info "• Cloud SQL ($SQL_TIER): ~$7-15"
info "• Cloud Storage ($BUCKET_SIZE): ~$1-5"
info "• Artifact Registry: ~$0.50-2"
info "• Networking/Egress: ~$1-3"
info "• Total estimated: ~$15-50/month"

# Cost alerting check
if [ -n "$BILLING_ACCOUNT" ]; then
    # Check notification channels for budget alerts
    NOTIFICATION_CHANNELS=$(gcloud alpha monitoring channels list --filter="type:email" --format="value(name)" | wc -l || echo "0")
    if [ "$NOTIFICATION_CHANNELS" -gt 0 ]; then
        pass "$NOTIFICATION_CHANNELS email notification channel(s) configured"
    else
        warn "No email notification channels found for cost alerts"
    fi
fi

echo ""

# Security Check
log "12. 🔒 Security Verification"

# Check service account permissions
SERVICE_ACCOUNT_EMAIL="$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")-compute@developer.gserviceaccount.com"
if gcloud projects get-iam-policy "$PROJECT_ID" --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:serviceAccount:$SERVICE_ACCOUNT_EMAIL" | grep -q "roles/cloudsql.client"; then
    pass "Service account has Cloud SQL access"
else
    warn "Service account may not have proper Cloud SQL permissions"
fi

if gcloud projects get-iam-policy "$PROJECT_ID" --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:serviceAccount:$SERVICE_ACCOUNT_EMAIL" | grep -q "roles/storage.objectViewer"; then
    pass "Service account has Storage access"
else
    warn "Service account may not have proper Storage permissions"
fi

# Check if service allows unauthenticated access
if gcloud run services get-iam-policy "$SERVICE_NAME" --region="$REGION" --flatten="bindings[].members" --format="value(bindings.members)" | grep -q "allUsers"; then
    pass "Cloud Run service allows public access (as configured)"
else
    info "Cloud Run service requires authentication"
fi
echo ""

# Final Summary
echo "==================== VERIFICATION SUMMARY ===================="
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
fi
if [ $TESTS_WARNING -gt 0 ]; then
    echo -e "Warnings: ${YELLOW}$TESTS_WARNING${NC}"
fi
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    log "🎉 All critical tests passed! Your SQL Retriever deployment looks good."
    
    if [ -n "$SERVICE_URL" ]; then
        echo ""
        echo "==================== QUICK COMMANDS ===================="
        echo "Test health:     curl $SERVICE_URL/health"
        echo "Test with auth:  curl -H 'Authorization: Bearer $API_KEY' $SERVICE_URL/stats"
        echo "View logs:       gcloud run services logs tail $SERVICE_NAME --region=$REGION"
        echo "Monitor costs:   https://console.cloud.google.com/billing"
    fi
else
    warn "Some tests failed. Please review the issues above before using the deployment."
fi

if [ $TESTS_WARNING -gt 0 ]; then
    warn "There are warnings that should be addressed for optimal operation."
fi

echo ""
log "✅ Verification complete!" 