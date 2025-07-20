# SQL Retriever FastAPI Backend

A production-ready FastAPI backend for RAG-powered SQL query generation from natural language questions.

## Features

- 🚀 **FastAPI** with async routes and automatic OpenAPI documentation
- 🔐 **API Key Authentication** via `X-API-Key` header
- 🎯 **RAG-powered SQL Generation** with semantic search and LLM integration
- 📊 **Dynamic Database Connections** with optional URI overrides
- 🛡️ **Error Handling** with consistent JSON responses
- 📈 **Health Checks** and system statistics
- 🐳 **Docker Ready** for cloud deployment
- 🔄 **Learning System** for continuous improvement

## Quick Start

### Local Development

1. **Set up environment:**
```bash
# Set required API key
export API_KEY="your-secure-api-key-here"

# Optional: Override default database
export DATABASE_PATH="/path/to/your/database.db"
```

2. **Run with Docker Compose:**
```bash
docker-compose up --build
```

3. **Or run directly:**
```bash
pip install -r requirements.txt
python app.py
```

4. **Access the API:**
- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- ReDoc: http://localhost:8000/redoc

### Cloud Deployment (GCP Cloud Run)

1. **Build and push Docker image:**
```bash
docker build -t gcr.io/your-project/sql-retriever .
docker push gcr.io/your-project/sql-retriever
```

2. **Deploy to Cloud Run:**
```bash
gcloud run deploy sql-retriever \
  --image gcr.io/your-project/sql-retriever \
  --port 8000 \
  --set-env-vars API_KEY=your-secure-key,DATABASE_PATH=your-cloud-sql-uri \
  --allow-unauthenticated
```

## API Endpoints

### Authentication
All endpoints except `/health` require authentication via `Authorization: Bearer YOUR_API_KEY` header.

### 1. POST `/query` - Process Natural Language Query

**Request:**
```json
{
  "question": "What's the total revenue this year?",
  "db_uri": "optional-database-override"
}
```

**Response:**
```json
{
  "success": true,
  "sql_query": "SELECT SUM(od.quantityOrdered * od.priceEach) as total_revenue FROM orders o JOIN orderdetails od ON o.orderNumber = od.orderNumber WHERE STRFTIME('%Y', o.orderDate) = STRFTIME('%Y', 'now');",
  "results": [{"total_revenue": 2345678.90}],
  "processing_time": 1.23,
  "error": null
}
```

### 2. GET `/health` - Health Check

**Response:**
```json
{
  "status": "healthy",
  "db_connected": true,
  "rag_enabled": true,
  "details": {
    "uptime_seconds": 3600,
    "total_queries": 42,
    "database_path": "/app/data/test_crm_v1.db"
  }
}
```

### 3. GET `/schema` - Get Database Schema

**Query Parameters:**
- `db_uri` (optional): Database URI override

**Response:**
```json
{
  "schema": "Detailed schema description...",
  "tables": ["customers", "orders", "products", "employees"]
}
```

### 4. POST `/learn` - Learn from Feedback

**Request:**
```json
{
  "question": "Find top customers",
  "sql_query": "SELECT customerName FROM customers ORDER BY creditLimit DESC LIMIT 5;",
  "success": true,
  "feedback": "Query worked perfectly for finding top customers by credit limit"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully learned from feedback"
}
```

### 5. GET `/stats` - System Statistics

**Response:**
```json
{
  "total_queries": 156,
  "total_processing_time": 234.56,
  "average_processing_time": 1.50,
  "database_path": "/app/data/test_crm_v1.db",
  "rag_enabled": true,
  "safety_checks_enabled": true
}
```

## Usage Examples

### Python Client
```python
import requests

# Configuration
API_URL = "http://localhost:8000"
API_KEY = "your-api-key"
headers = {"Authorization": f"Bearer {API_KEY}"}

# Query the database
response = requests.post(
    f"{API_URL}/query",
    json={"question": "Show me top 5 customers by total orders"},
    headers=headers
)
print(response.json())

# Get health status
health = requests.get(f"{API_URL}/health")
print(health.json())
```

### JavaScript/Node.js Client
```javascript
const API_URL = 'http://localhost:8000';
const API_KEY = 'your-api-key';

const headers = {
  'Authorization': `Bearer ${API_KEY}`,
  'Content-Type': 'application/json'
};

// Query the database
const queryResponse = await fetch(`${API_URL}/query`, {
  method: 'POST',
  headers,
  body: JSON.stringify({
    question: 'What are our monthly sales trends?'
  })
});

const result = await queryResponse.json();
console.log(result);
```

### cURL Examples
```bash
# Health check (no auth required)
curl http://localhost:8000/health

# Query with authentication
curl -X POST http://localhost:8000/query \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"question": "Find customers in USA"}'

# Get database schema
curl -H "Authorization: Bearer your-api-key" \
  "http://localhost:8000/schema"
```

## Environment Variables

### Required
- `API_KEY`: Secret key for API authentication

### Optional
- `DATABASE_PATH`: Database file path or URI (default: data/test_crm_v1.db)
- `RAG_ENABLED`: Enable RAG functionality (default: true)
- `LOG_LEVEL`: Logging level (default: INFO)
- `PORT`: Server port (default: 8000)
- `ENVIRONMENT`: Environment mode (development/production)

### Cloud-Specific
- `MODEL_NAME`: LLM model name for Runpod integration
- `DATABASE_PATH`: Cloud SQL connection string for GCP

## Error Handling

All errors return consistent JSON format:
```json
{
  "error": "Error message",
  "detail": "Additional details",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

Common error codes:
- `401`: Invalid or missing API key
- `400`: Invalid request format
- `404`: Endpoint not found
- `500`: Internal server error
- `503`: Service not initialized

## Performance & Scaling

- **Single Worker**: Optimized for Cloud Run (stateful RAG client)
- **Memory Usage**: ~2GB for full LLM inference
- **Response Time**: 0.5-3s depending on query complexity
- **Concurrency**: FastAPI handles multiple concurrent requests
- **Caching**: ChromaDB provides semantic search caching

## Security

- ✅ API key authentication
- ✅ SQL injection protection via parameterized queries
- ✅ Input validation with Pydantic models
- ✅ Non-root Docker container
- ✅ CORS middleware configuration
- ✅ Error message sanitization

## Monitoring

The API provides built-in monitoring endpoints:
- `/health`: Service health and database connectivity
- `/stats`: Processing statistics and performance metrics

Integrate with your monitoring stack:
- **Prometheus**: Scrape `/stats` endpoint
- **Grafana**: Visualize query performance and success rates
- **Cloud Monitoring**: Use health checks for uptime monitoring

## Development

### Project Structure
```
.
├── app.py              # FastAPI application
├── models.py           # Pydantic request/response models
├── main.py             # Original CRMSQLRetriever class
├── config.py           # Configuration management
├── database/           # Database connection logic
├── llm/                # RAG and LLM integration
├── utils/              # Logging and utilities
├── Dockerfile          # Production Docker image
└── docker-compose.yml  # Local development setup
```

### Adding New Endpoints
1. Define Pydantic models in `models.py`
2. Add endpoint function to `app.py`
3. Update API documentation
4. Add tests if needed

## Troubleshooting

### Common Issues

**1. Authentication Errors**
```bash
# Check if API_KEY is set
echo $API_KEY

# Test with curl
curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/stats
```

**2. Database Connection Issues**
```bash
# Check database file exists
ls -la data/test_crm_v1.db

# Test database connectivity
curl http://localhost:8000/health
```

**3. Memory Issues with LLM**
```bash
# Monitor memory usage
docker stats

# Disable RAG if needed
export RAG_ENABLED=false
```

**4. Docker Build Issues**
```bash
# Clear Docker cache
docker system prune -a

# Rebuild without cache
docker-compose build --no-cache
```

## License

This project is part of the SQL Retriever system for CRM database analysis. 