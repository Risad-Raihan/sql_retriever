# SQL Retriever Testing Guide & Fix Toolkit

## 📋 Overview

This guide provides comprehensive testing procedures and troubleshooting solutions for the SQL Retriever FastAPI application before Runpod integration.

## 🚀 Quick Start

### Prerequisites

```bash
# Install testing dependencies
pip install pytest pytest-cov pytest-asyncio pytest-mock httpx coverage pytest-html pytest-json-report

# Set environment variables
export API_KEY="test-api-key-12345"
export DATABASE_PATH="./data/test_crm_v1.db"
export RAG_ENABLED="true"
```

### Run All Tests

```bash
# Full test suite with coverage
python test_runner.py

# Quick smoke tests
python test_runner.py --quick

# Manual testing
bash test_manual.sh

# Manual quick test
bash test_manual.sh --quick
```

## 🧪 Testing Components

### 1. Automated Testing Suite (`test_runner.py`)

**Features:**
- ✅ Installs dependencies automatically
- ✅ Runs unit, integration, and load tests
- ✅ Generates coverage reports (HTML, XML, JSON)
- ✅ Creates comprehensive test reports
- ✅ Parallel test execution

**Usage Examples:**
```bash
# Default run (80% coverage threshold)
python test_runner.py

# Custom coverage threshold
python test_runner.py --coverage-threshold 85

# Single-threaded execution
python test_runner.py --parallel false

# Extended timeout
python test_runner.py --timeout 600
```

### 2. Manual Testing Script (`test_manual.sh`)

**Features:**
- ✅ Tests all API endpoints with curl
- ✅ Covers authentication scenarios
- ✅ Tests error handling and edge cases
- ✅ Load testing with concurrent requests
- ✅ Performance measurements

**Usage Examples:**
```bash
# Full manual test suite
bash test_manual.sh

# Test specific URL
bash test_manual.sh --url http://localhost:8080

# Custom API key
bash test_manual.sh --key "my-secret-key"

# Quick smoke tests
bash test_manual.sh --quick
```

### 3. Pytest Test Suite (`tests/test_api.py`)

**Test Classes:**
- `TestHealthEndpoint` - Health check functionality
- `TestQueryEndpoint` - Query processing with various scenarios
- `TestSchemaEndpoint` - Database schema retrieval
- `TestLearnEndpoint` - RAG learning functionality
- `TestStatsEndpoint` - Statistics and metrics
- `TestAsyncIntegration` - Concurrent request handling
- `TestErrorHandling` - Error scenarios and edge cases
- `TestCloudSimulation` - Cloud environment scenarios
- `TestCPUFallback` - Local CPU-only execution

**Direct Execution:**
```bash
# Run specific test class
pytest tests/test_api.py::TestQueryEndpoint -v

# Run with coverage
pytest tests/test_api.py --cov=. --cov-report=html

# Run async tests only
pytest tests/test_api.py -k "async" -v
```

## 🔧 Common Issues & Fix Recipes

### Issue 1: Database Connection Errors

**Symptoms:**
- Health check shows `db_connected: false`
- Query endpoints return 500 errors
- "Database file not found" messages

**Diagnosis:**
```bash
# Check if database exists
ls -la data/test_crm_v1.db

# Test direct connection
python -c "
import sqlite3
conn = sqlite3.connect('data/test_crm_v1.db')
cursor = conn.cursor()
cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\";')
print(cursor.fetchall())
conn.close()
"
```

**Fixes:**
1. **Missing Database File:**
   ```bash
   # Create test database
   python -c "
   import sqlite3
   conn = sqlite3.connect('data/test_crm_v1.db')
   cursor = conn.cursor()
   cursor.execute('CREATE TABLE customers (customerNumber INTEGER, customerName TEXT)')
   cursor.execute('INSERT INTO customers VALUES (1, \"Test Customer\")')
   conn.commit()
   conn.close()
   print('Test database created')
   "
   ```

2. **Permission Issues:**
   ```bash
   # Fix permissions
   chmod 644 data/test_crm_v1.db
   chown $USER:$USER data/test_crm_v1.db
   ```

3. **Path Configuration:**
   ```python
   # In config.py, ensure absolute path
   DATABASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "test_crm_v1.db"))
   ```

4. **Add Retry Logic:**
   ```python
   # In database/connection.py
   import time
   
   def connect_with_retry(self, max_retries=3, delay=1):
       for attempt in range(max_retries):
           try:
               self.connection = sqlite3.connect(self.db_path, timeout=30.0)
               return self.connection
           except Exception as e:
               if attempt == max_retries - 1:
                   raise
               time.sleep(delay * (attempt + 1))
   ```

### Issue 2: Slow LLM Response Times

**Symptoms:**
- Query timeouts after 30+ seconds
- High memory usage (>8GB)
- CPU at 100% during processing

**Diagnosis:**
```bash
# Monitor resource usage during tests
top -p $(pgrep -f "uvicorn\|python")

# Check model loading
python -c "
from llm.rag_client import RAGSQLClient
import time
start = time.time()
client = RAGSQLClient()
print(f'Model loaded in {time.time() - start:.2f}s')
"
```

**Fixes:**
1. **Enable CPU Fallback:**
   ```python
   # In llm/vllm_client.py
   def __init__(self):
       try:
           self.model = AutoModelForCausalLM.from_pretrained(
               self.model_name,
               torch_dtype=torch.float16,
               low_cpu_mem_usage=True,
               device_map="cpu",  # Force CPU
               max_memory={"cpu": "6GB"}  # Limit memory
           )
       except Exception as e:
           logger.warning(f"Model loading failed: {e}")
           self.model = None
   ```

2. **Add Timeout Handling:**
   ```python
   # In app.py
   import signal
   from contextlib import contextmanager
   
   @contextmanager
   def timeout(duration):
       def timeout_handler(signum, frame):
           raise TimeoutError(f"Operation timed out after {duration}s")
       
       signal.signal(signal.SIGALRM, timeout_handler)
       signal.alarm(duration)
       try:
           yield
       finally:
           signal.alarm(0)
   
   # Use in query processing
   try:
       with timeout(30):
           result = retriever.process_query(request.question)
   except TimeoutError:
       return QueryResponse(
           success=False,
           error="Query processing timed out",
           processing_time=30.0
       )
   ```

3. **Optimize Model Parameters:**
   ```python
   # Reduce token limits
   MAX_TOKENS = 100  # Instead of 200
   MODEL_TEMPERATURE = 0.1  # More deterministic
   
   # Use lighter model
   MODEL_NAME = "microsoft/DialoGPT-small"  # Instead of Llama-3B
   ```

### Issue 3: Authentication Failures

**Symptoms:**
- All authenticated endpoints return 401
- "Invalid API key" errors
- Missing Authorization header errors

**Diagnosis:**
```bash
# Check environment variable
echo $API_KEY

# Test with curl
curl -v -H "Authorization: Bearer test-api-key-12345" http://localhost:8000/stats
```

**Fixes:**
1. **Environment Variable Missing:**
   ```bash
   # Set in shell
   export API_KEY="test-api-key-12345"
   
   # Or in .env file
   echo "API_KEY=test-api-key-12345" >> .env
   ```

2. **Debug Middleware:**
   ```python
   # Add debug middleware in app.py
   @app.middleware("http")
   async def debug_auth_middleware(request: Request, call_next):
       auth_header = request.headers.get("Authorization")
       logger.info(f"Auth header: {auth_header}")
       
       response = await call_next(request)
       logger.info(f"Response status: {response.status_code}")
       return response
   ```

3. **Handle Missing API Key:**
   ```python
   # In app.py, update get_api_key function
   def get_api_key() -> str:
       api_key = os.getenv("API_KEY")
       if not api_key:
           logger.warning("API_KEY not set, using default for testing")
           return "test-api-key-12345"  # Fallback for testing
       return api_key
   ```

### Issue 4: RAG Vector Store Issues

**Symptoms:**
- "ChromaDB not found" errors
- Empty search results from RAG
- Vector store initialization failures

**Diagnosis:**
```bash
# Check ChromaDB files
ls -la rag_data/
file rag_data/chroma.sqlite3

# Test vector store directly
python -c "
from llm.rag_client import RAGVectorStore
store = RAGVectorStore()
print(f'Examples loaded: {len(store.examples)}')
"
```

**Fixes:**
1. **Mock ChromaDB for Testing:**
   ```python
   # In tests/test_api.py
   @pytest.fixture
   def mock_chroma():
       with patch('chromadb.PersistentClient') as mock_client:
           mock_collection = Mock()
           mock_collection.count.return_value = 10
           mock_collection.query.return_value = {
               'metadatas': [[]],
               'distances': [[]]
           }
           mock_client.return_value.get_collection.return_value = mock_collection
           yield mock_client
   ```

2. **Fallback to In-Memory Store:**
   ```python
   # In llm/rag_client.py
   def _initialize_vector_store(self):
       try:
           self.chroma_client = chromadb.PersistentClient(path=self.persist_directory)
       except Exception as e:
           logger.warning(f"ChromaDB failed, using in-memory: {e}")
           self.chroma_client = chromadb.Client()  # In-memory fallback
   ```

3. **Reset Vector Store:**
   ```bash
   # Clear corrupted vector store
   rm -rf rag_data/
   mkdir rag_data
   
   # Reinitialize
   python -c "
   from llm.rag_client import RAGSQLClient
   client = RAGSQLClient()
   print('Vector store reinitialized')
   "
   ```

### Issue 5: High Load Testing Failures

**Symptoms:**
- Concurrent request failures
- Memory leaks during load tests
- Connection pool exhaustion

**Diagnosis:**
```bash
# Monitor during load test
watch -n 1 'ps aux | grep python; netstat -an | grep :8000 | wc -l'

# Run controlled load test
for i in {1..10}; do
  curl -s http://localhost:8000/health &
done; wait
```

**Fixes:**
1. **Add Connection Pooling:**
   ```python
   # In app.py
   from fastapi import FastAPI
   from asyncio import Semaphore
   
   # Limit concurrent requests
   semaphore = Semaphore(10)
   
   @app.middleware("http")
   async def limit_concurrency(request: Request, call_next):
       async with semaphore:
           return await call_next(request)
   ```

2. **Resource Cleanup:**
   ```python
   # In main.py
   def cleanup(self):
       try:
           if self.db:
               self.db.disconnect()
           if hasattr(self, 'model') and self.model:
               del self.model
           import gc
           gc.collect()
       except Exception as e:
           logger.error(f"Cleanup error: {e}")
   ```

3. **Configure Uvicorn Properly:**
   ```bash
   # For production testing
   uvicorn app:app --host 0.0.0.0 --port 8000 --workers 2 --limit-concurrency 50
   ```

## 📊 Test Metrics & Benchmarks

### Expected Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Health Check Response | < 100ms | Average response time |
| Simple Query (COUNT) | < 5s | End-to-end processing |
| Complex Query (JOINs) | < 30s | End-to-end processing |
| Memory Usage | < 8GB | Peak during processing |
| Concurrent Requests | 10+ | Without failures |
| Test Coverage | 80%+ | Code coverage percentage |

### Monitoring Commands

```bash
# Resource monitoring during tests
htop -p $(pgrep -f "uvicorn\|python")

# Network connections
netstat -tulnp | grep :8000

# Memory usage
ps -p $(pgrep -f "uvicorn") -o pid,ppid,cmd,pmem,pcpu,rss

# Disk usage
du -sh rag_data/ test_reports/ *.log
```

## 🔍 Debugging Tools

### Log Analysis

```bash
# Real-time log monitoring
tail -f sql_retriever_bot.log

# Filter for errors
grep -i "error\|exception\|failed" sql_retriever_bot.log

# Query performance analysis
grep -i "processing_time" sql_retriever_bot.log | tail -20
```

### Health Check Script

```bash
#!/bin/bash
# health_check.sh - Quick system health verification

echo "🏥 SQL Retriever Health Check"
echo "================================"

# Check server status
if curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo "✅ Server is healthy"
else
    echo "❌ Server health check failed"
fi

# Check database
if [ -f "data/test_crm_v1.db" ]; then
    echo "✅ Database file exists"
    db_size=$(stat -c%s "data/test_crm_v1.db")
    echo "   Size: ${db_size} bytes"
else
    echo "❌ Database file missing"
fi

# Check memory usage
memory_usage=$(ps -o rss= -p $(pgrep -f "uvicorn") 2>/dev/null | awk '{sum+=$1} END {print sum/1024}')
if [ ! -z "$memory_usage" ]; then
    echo "📊 Memory usage: ${memory_usage}MB"
else
    echo "❌ Server process not found"
fi

# Check port availability
if netstat -tulnp 2>/dev/null | grep -q ":8000.*LISTEN"; then
    echo "✅ Port 8000 is listening"
else
    echo "❌ Port 8000 not available"
fi

echo "================================"
```

## 📝 Test Report Templates

### CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Test SQL Retriever

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.8'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests
      run: python test_runner.py
      env:
        API_KEY: test-key
        RAG_ENABLED: true
    
    - name: Upload coverage
      uses: codecov/codecov-action@v1
      with:
        file: ./test_reports/coverage/coverage.xml
```

### Manual Test Checklist

- [ ] Server starts without errors
- [ ] Health endpoint returns 200
- [ ] All authenticated endpoints reject requests without API key
- [ ] Query endpoint processes simple questions
- [ ] Complex queries complete within timeout
- [ ] Schema endpoint returns valid database structure
- [ ] Learn endpoint accepts feedback
- [ ] Stats endpoint shows metrics
- [ ] Concurrent requests don't crash server
- [ ] Memory usage stays below 8GB
- [ ] Error responses are properly formatted
- [ ] Database URI override works
- [ ] RAG functionality loads examples
- [ ] CPU fallback activates when needed

## 🚀 Pre-Deployment Validation

### Final Check Command

```bash
#!/bin/bash
# final_validation.sh - Complete pre-deployment check

echo "🚀 Final Deployment Validation"
echo "==============================="

# Run full test suite
echo "Running comprehensive tests..."
python test_runner.py --coverage-threshold 80

# Manual endpoint verification
echo "Running manual endpoint tests..."
bash test_manual.sh --quick

# Performance check
echo "Performance validation..."
python -c "
import time
import requests

start = time.time()
response = requests.post('http://localhost:8000/query', 
    headers={'Authorization': 'Bearer test-api-key-12345'},
    json={'question': 'Count customers'})
duration = time.time() - start

print(f'Query response time: {duration:.2f}s')
if duration < 30:
    print('✅ Performance acceptable')
else:
    print('❌ Performance too slow')
"

echo "==============================="
echo "✅ Validation complete!"
```

## 📞 Support & Troubleshooting

### Common Questions

**Q: Tests are failing with "Service not initialized" error**
A: Ensure the FastAPI lifespan handler is properly initializing the CRMSQLRetriever. Check that all environment variables are set.

**Q: ChromaDB errors during testing**
A: Use the mock fixtures provided in the test suite, or clear the rag_data directory and reinitialize.

**Q: Memory usage is too high**
A: Enable CPU fallback mode and reduce model parameters. Consider using a smaller model for testing.

**Q: Timeout errors on complex queries**
A: Increase timeout settings in test configuration and add proper timeout handling in the application.

### Debug Mode Activation

```bash
# Enable debug logging
export LOG_LEVEL="DEBUG"

# Run with detailed output
python test_runner.py --verbose

# Manual testing with verbose output
bash test_manual.sh -v
```

---

**Last Updated:** 2024-01-20  
**Version:** 1.0  
**Maintainer:** SQL Retriever Team 