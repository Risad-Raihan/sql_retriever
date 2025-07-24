#!/bin/bash

# Quick Fix Script for SQL Retriever Deployment Issues
# This script addresses common deployment problems

echo "🔧 SQL Retriever Quick Fix Script"
echo "=================================="

# Function to check if gcloud is configured
check_gcloud() {
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
        echo "❌ No active gcloud authentication found"
        echo "Please run: gcloud auth login"
        exit 1
    fi
    echo "✅ gcloud authentication verified"
}

# Function to set environment variables
set_env_vars() {
    echo "🌍 Setting environment variables..."
    
    # Read from gcp_config.yaml if it exists
    if [ -f "gcp_config.yaml" ]; then
        PROJECT_ID=$(grep "project_id:" gcp_config.yaml | awk '{print $2}' | tr -d '"')
        SERVICE_NAME=$(grep "service_name:" gcp_config.yaml | awk '{print $2}' | tr -d '"')
        REGION=$(grep "region:" gcp_config.yaml | awk '{print $2}' | tr -d '"')
        
        export PROJECT_ID="$PROJECT_ID"
        export SERVICE_NAME="$SERVICE_NAME"
        export REGION="$REGION"
        
        echo "✅ Environment variables set from gcp_config.yaml"
        echo "   PROJECT_ID: $PROJECT_ID"
        echo "   SERVICE_NAME: $SERVICE_NAME"
        echo "   REGION: $REGION"
    else
        echo "❌ gcp_config.yaml not found"
        exit 1
    fi
}

# Function to fix database connection
fix_database() {
    echo "🗄️ Fixing database connection issues..."
    
    # Check if database/connection.py has import-time connection
    if grep -q "^db = DatabaseConnection" database/connection.py; then
        echo "⚠️ Found import-time database connection, commenting it out..."
        sed -i 's/^db = DatabaseConnection/#db = DatabaseConnection/' database/connection.py
        echo "✅ Fixed import-time database connection"
    else
        echo "✅ Database connection looks good"
    fi
}

# Function to clean and deploy
deploy_service() {
    echo "🚀 Deploying to Cloud Run..."
    
    # Make deploy script executable
    chmod +x deploy_gcp.sh
    
    # Run deployment
    ./deploy_gcp.sh
    
    if [ $? -eq 0 ]; then
        echo "✅ Deployment successful!"
        
        # Get service URL
        SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")
        echo "🌐 Service URL: $SERVICE_URL"
        echo "📖 API Docs: $SERVICE_URL/docs"
    else
        echo "❌ Deployment failed"
        echo "💡 Check logs with: gcloud logs read --service=$SERVICE_NAME --limit=50"
        exit 1
    fi
}

# Function to check service health
check_health() {
    echo "🏥 Checking service health..."
    
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)" 2>/dev/null)
    
    if [ -n "$SERVICE_URL" ]; then
        echo "📊 Testing health endpoint..."
        curl -s "$SERVICE_URL/health" | jq . || echo "Service is running but health check may have failed"
    else
        echo "❌ Service not found or not deployed"
    fi
}

# Function to show logs
show_logs() {
    echo "📋 Recent logs:"
    gcloud logs read --service=$SERVICE_NAME --limit=20 --format="table(timestamp,severity,textPayload)"
}

# Main execution
main() {
    case "${1:-all}" in
        "auth")
            check_gcloud
            ;;
        "env")
            set_env_vars
            ;;
        "db")
            fix_database
            ;;
        "deploy")
            check_gcloud
            set_env_vars
            fix_database
            deploy_service
            ;;
        "health")
            set_env_vars
            check_health
            ;;
        "logs")
            set_env_vars
            show_logs
            ;;
        "all"|*)
            check_gcloud
            set_env_vars
            fix_database
            deploy_service
            check_health
            ;;
    esac
}

# Help text
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  all     - Run full fix and deployment (default)"
    echo "  auth    - Check gcloud authentication"
    echo "  env     - Set environment variables"
    echo "  db      - Fix database connection issues"
    echo "  deploy  - Deploy to Cloud Run"
    echo "  health  - Check service health"
    echo "  logs    - Show recent logs"
    echo "  -h      - Show this help"
    exit 0
fi

# Run main function
main "$1"