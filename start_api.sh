#!/bin/bash

# SQL Retriever API Startup Script
echo "🚀 Starting SQL Retriever FastAPI Backend..."

# Check if API_KEY is set
if [ -z "$API_KEY" ]; then
    echo "⚠️  Warning: API_KEY environment variable not set!"
    echo "💡 Set it with: export API_KEY='your-secure-api-key-here'"
    echo "📝 Using default for development (INSECURE)"
    export API_KEY="dev-key-change-in-production"
fi

# Set default environment variables if not set
export DATABASE_PATH="${DATABASE_PATH:-./data/test_crm_v1.db}"
export RAG_ENABLED="${RAG_ENABLED:-true}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export PORT="${PORT:-8000}"

# Print configuration
echo "📊 Configuration:"
echo "   - API Key: ${API_KEY:0:8}..."
echo "   - Database: $DATABASE_PATH"
echo "   - RAG Enabled: $RAG_ENABLED"
echo "   - Log Level: $LOG_LEVEL"
echo "   - Port: $PORT"

# Check if database exists
if [[ "$DATABASE_PATH" == ./* ]] && [ ! -f "$DATABASE_PATH" ]; then
    echo "❌ Database file not found: $DATABASE_PATH"
    echo "💡 Make sure the database file exists or set DATABASE_PATH to a valid URI"
    exit 1
fi

# Start the API
echo "🎉 Starting FastAPI server on http://0.0.0.0:$PORT"
echo "📖 API Documentation: http://localhost:$PORT/docs"
echo "🏥 Health Check: http://localhost:$PORT/health"
echo ""

# Run with uvicorn
uvicorn app:app \
    --host 0.0.0.0 \
    --port $PORT \
    --log-level info \
    --access-log 