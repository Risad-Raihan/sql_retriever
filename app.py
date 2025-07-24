#!/usr/bin/env python3
"""
FastAPI Production Backend for SQL Retriever
A cloud-ready RAG-powered SQL query generator API for CRM databases.
Updated to use two Runpod pods: GPU for LLM, CPU for embedding service.
Version: 2025-01-23-12:15 - Fixed LLM service integration
"""

import os
import sys
import time
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import requests
import json

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.connection import DatabaseConnection
from database.validator import SQLValidator
from utils.logger import get_logger
from models import (
    QueryRequest, QueryResponse, LearnRequest, LearnResponse,
    HealthResponse, SchemaResponse, StatsResponse, ErrorResponse
)

# Initialize logger
logger = get_logger(__name__)

# Global app state
app_state = {
    "startup_time": None,
    "total_queries": 0,
    "total_processing_time": 0.0
}

# Security
security = HTTPBearer()

# Runpod service URLs (from environment variables)
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://localhost:8000")
LLM_URL = os.getenv("LLM_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY")

def get_api_key() -> str:
    """Get API key from environment variable."""
    if not API_KEY:
        raise ValueError("API_KEY environment variable not set")
    return API_KEY

def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    """Verify API key authentication."""
    try:
        expected_key = get_api_key()
        if credentials.credentials != expected_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
        return True
    except ValueError:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: API key not configured"
        )

class RunpodSQLRetriever:
    """SQL Retriever using two Runpod services."""
    
    def __init__(self):
        self.db = None
        self.embedding_url = EMBEDDING_URL
        self.llm_url = LLM_URL
        
        # Initialize database connection
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize database connection."""
        try:
            db_url = os.getenv("DATABASE_URL")
            if db_url:
                self.db = DatabaseConnection(db_url)
            else:
                # Fallback to local SQLite
                db_path = os.getenv("DATABASE_PATH", "data/test_crm_v1.db")
                self.db = DatabaseConnection(f"sqlite:///{db_path}")
            
            self.db.connect()
            logger.info("✅ Database connection initialized")
            
            # Initialize SQL validator
            self.sql_validator = SQLValidator(self.db.engine)
            logger.info("✅ SQL validator initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            raise
    
    def _call_embedding_service(self, endpoint: str, data: dict, timeout: int = 30) -> dict:
        """Call the embedding service pod."""
        try:
            url = f"{self.embedding_url.rstrip('/')}/{endpoint.lstrip('/')}"
            response = requests.post(
                url, 
                json=data, 
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Embedding service error: {response.status_code} - {response.text}")
                
        except requests.exceptions.Timeout:
            raise Exception("Embedding service timeout")
        except Exception as e:
            logger.error(f"Embedding service call failed: {e}")
            raise
    
    def _call_llm_service(self, prompt: str, max_tokens: int = 200, timeout: int = 60) -> str:
        """Call the LLM service pod using OpenAI-compatible chat completions API."""
        try:
            url = f"{self.llm_url.rstrip('/')}/v1/chat/completions"
            
            # Convert prompt to chat format
            # Extract system and user content from the formatted prompt
            if "<|start_header_id|>system<|end_header_id|>" in prompt:
                # Parse the existing chat format
                system_start = prompt.find("<|start_header_id|>system<|end_header_id|>") + len("<|start_header_id|>system<|end_header_id|>")
                system_end = prompt.find("<|eot_id|><|start_header_id|>user<|end_header_id|>")
                system_content = prompt[system_start:system_end].strip()
                
                user_start = prompt.find("<|start_header_id|>user<|end_header_id|>") + len("<|start_header_id|>user<|end_header_id|>")
                user_end = prompt.find("<|eot_id|><|start_header_id|>assistant<|end_header_id|>")
                user_content = prompt[user_start:user_end].strip()
            else:
                # Fallback: treat entire prompt as user message
                system_content = "You are an expert SQL generator. Generate ONLY valid SQL queries using proper SQLite syntax."
                user_content = prompt
            
            payload = {
                "model": "meta-llama/Llama-3.2-3B-Instruct",
                "messages": [
                    {
                        "role": "system",
                        "content": system_content
                    },
                    {
                        "role": "user", 
                        "content": user_content
                    }
                ],
                "max_tokens": max_tokens,
                "temperature": 0.1,
                "top_p": 0.9
            }
            
            response = requests.post(
                url,
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                generated_text = result["choices"][0]["message"]["content"].strip()
                return self._clean_sql_response(generated_text)
            else:
                raise Exception(f"LLM service error: {response.status_code} - {response.text}")
                
        except requests.exceptions.Timeout:
            raise Exception("LLM service timeout")
        except Exception as e:
            logger.error(f"LLM service call failed: {e}")
            raise
    
    def _clean_sql_response(self, response: str) -> str:
        """Clean up the generated SQL response."""
        try:
            import re
            
            # Remove common prefixes
            response = response.strip()
            prefixes_to_remove = [
                "Here's the SQL query:",
                "SQL:",
                "Query:",
                "The SQL query is:",
                "Answer:",
                "Result:",
            ]
            
            for prefix in prefixes_to_remove:
                if response.lower().startswith(prefix.lower()):
                    response = response[len(prefix):].strip()
            
            # Extract SQL content from code blocks
            sql_blocks = re.findall(r'```(?:sql)?\s*(.*?)\s*```', response, re.DOTALL)
            if sql_blocks:
                combined_sql = ' '.join(sql_blocks).strip()
                if combined_sql and any(keyword in combined_sql.upper() for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
                    return combined_sql
            
            # Look for SQL patterns
            sql_patterns = [
                r'(SELECT\s+.*?)(?:\s*;|\s*$)',
                r'(INSERT\s+.*?)(?:\s*;|\s*$)',
                r'(UPDATE\s+.*?)(?:\s*;|\s*$)',
                r'(DELETE\s+.*?)(?:\s*;|\s*$)'
            ]
            
            for pattern in sql_patterns:
                match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
                if match:
                    sql = match.group(1).strip()
                    sql = re.sub(r'\s+', ' ', sql)  # Normalize whitespace
                    if not sql.endswith(';'):
                        sql += ';'
                    return sql
            
            # If no valid SQL found, check if it looks like SQL without SELECT
            if "FROM" in response.upper() and not response.upper().strip().startswith('SELECT'):
                response = "SELECT " + response.strip()
            
            # If no valid SQL found, return response as-is
            if not response.endswith(';'):
                response += ';'
            return response.strip()
            
        except Exception as e:
            logger.error(f"SQL cleaning error: {e}")
            return response.strip()
    
    def _generate_llm_prompt(self, question: str, similar_examples: list, schema_info: str) -> str:
        """Generate prompt for LLM service."""
        examples_text = ""
        if similar_examples:
            examples_text = "\n\nSimilar examples:\n"
            for example in similar_examples:
                examples_text += f"Q: {example['question']}\nSQL: {example['sql_query']}\n\n"
        
        prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are an expert SQLite query generator for a CRM database. Generate ONLY valid SQLite SQL queries.

🔧 CRITICAL SQLite Syntax Rules (MUST FOLLOW):
- Use STRFTIME('%Y', date_column) for year extraction, NOT EXTRACT()
- Use STRFTIME('%m', date_column) for month extraction, NOT EXTRACT()
- Use STRFTIME('%Y-%m', date_column) for year-month grouping
- Revenue calculation: orderdetails.quantityOrdered * orderdetails.priceEach

⚠️ Key Column Locations (CRITICAL):
- orderDate: In ORDERS table (not orderdetails)
- priceEach: In ORDERDETAILS table (not products)
- salesRepEmployeeNumber: In CUSTOMERS table (not orders)

Database Schema:
{schema_info}
{examples_text}
<|eot_id|><|start_header_id|>user<|end_header_id|>

Question: {question}

Generate ONLY a valid SQLite query using proper table relationships and SQLite syntax.

<|eot_id|><|start_header_id|>assistant<|end_header_id|>

SELECT"""
        
        return prompt
    
    def process_query(self, question: str) -> Dict[str, Any]:
        """Process query using two-pod architecture."""
        start_time = time.time()
        
        try:
            # Step 1: Get schema information
            if not self.db:
                raise Exception("Database not initialized")
            
            schema_info = self.db.get_schema_description()
            
            # Step 2: Search for similar examples using embedding service
            search_request = {
                "question": question,
                "k": 3,
                "use_relaxed_threshold": False
            }
            
            similar_examples = []
            method_used = "pure_llm"
            
            try:
                search_result = self._call_embedding_service("search", search_request)
                similar_examples = search_result.get("examples", [])
                
                if not similar_examples:
                    # Try relaxed search
                    search_request["use_relaxed_threshold"] = True
                    search_result = self._call_embedding_service("search", search_request)
                    similar_examples = search_result.get("examples", [])
                    method_used = "llm_with_relaxed_rag" if similar_examples else "pure_llm"
                else:
                    method_used = "llm_with_rag"
                    
                logger.info(f"Found {len(similar_examples)} similar examples")
                
            except Exception as e:
                logger.warning(f"Embedding service failed, using pure LLM: {e}")
                similar_examples = []
                method_used = "pure_llm"
            
            # Step 3: Generate SQL using LLM service
            prompt = self._generate_llm_prompt(question, similar_examples, schema_info)
            
            try:
                sql_query = self._call_llm_service(prompt)
                logger.info(f"Generated SQL: {sql_query}")
            except Exception as e:
                logger.error(f"LLM service failed: {e}")
                # Fallback to best example if available
                if similar_examples:
                    sql_query = similar_examples[0]['sql_query']
                    method_used = "example_retrieval"
                    logger.info("Used fallback to best example")
                else:
                    raise Exception(f"Both LLM service and example retrieval failed: {e}")
            
            # Step 4: Validate and fix SQL query
            is_valid, corrected_sql, validation_warnings = self.sql_validator.validate_and_fix_sql(sql_query)
            
            if validation_warnings:
                logger.info(f"SQL validation warnings: {validation_warnings}")
            
            if corrected_sql != sql_query:
                logger.info(f"SQL auto-corrected from: {sql_query}")
                logger.info(f"SQL auto-corrected to: {corrected_sql}")
                sql_query = corrected_sql
            
            # Step 5: Execute SQL query
            try:
                results = self.db.execute_query(sql_query)
                success = True
                error = None
            except Exception as e:
                logger.error(f"SQL execution failed: {e}")
                results = {}
                success = False
                error = str(e)
            
            # Update statistics
            processing_time = time.time() - start_time
            app_state["total_queries"] += 1
            app_state["total_processing_time"] += processing_time
            
            return {
                "success": success,
                "sql_query": sql_query,
                "results": results,
                "processing_time": processing_time,
                "method_used": method_used,
                "similar_examples_count": len(similar_examples),
                "error": error
            }
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Query processing failed: {e}")
            return {
                "success": False,
                "sql_query": None,
                "results": {},
                "processing_time": processing_time,
                "method_used": "error",
                "similar_examples_count": 0,
                "error": str(e)
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get system statistics."""
        avg_processing_time = 0.0
        if app_state["total_queries"] > 0:
            avg_processing_time = app_state["total_processing_time"] / app_state["total_queries"]
        
        return {
            "total_queries": app_state["total_queries"],
            "total_processing_time": app_state["total_processing_time"],
            "average_processing_time": avg_processing_time,
            "database_path": str(self.db.connection_string) if self.db else "unknown",
            "rag_enabled": True,  # Always true with Runpod services
            "safety_checks_enabled": True,
            "embedding_service": self.embedding_url,
            "llm_service": self.llm_url
        }
    
    def _format_column_descriptions(self, columns):
        """Format column descriptions for frontend display."""
        descriptions = []
        for col in columns:
            col_name = col[0]
            # Try to get description from schema or create a friendly one
            if col_name.lower().endswith('_id'):
                desc = f"ID for {col_name[:-3].replace('_', ' ').title()}"
            elif col_name.lower() in ['name', 'title']:
                desc = f"Name or title"
            elif col_name.lower() in ['email']:
                desc = "Email address"
            elif col_name.lower() in ['phone']:
                desc = "Phone number"
            elif col_name.lower() in ['created_at', 'updated_at']:
                desc = f"Timestamp when record was {col_name.split('_')[0]}"
            elif col_name.lower() in ['status']:
                desc = "Current status"
            elif col_name.lower() in ['amount', 'price', 'cost']:
                desc = "Monetary value"
            elif col_name.lower() in ['date']:
                desc = "Date value"
            else:
                desc = col_name.replace('_', ' ').title()
            
            descriptions.append({
                "column": col_name,
                "description": desc
            })
        return descriptions
    
    def _format_query_insights(self, sql_query, row_count):
        """Generate insights about the query for frontend display."""
        insights = []
        
        # Analyze query type
        query_lower = sql_query.lower().strip()
        if query_lower.startswith('select'):
            if 'join' in query_lower:
                insights.append("This query combines data from multiple tables")
            if 'where' in query_lower:
                insights.append("This query filters results based on specific conditions")
            if 'group by' in query_lower:
                insights.append("This query groups and aggregates data")
            if 'order by' in query_lower:
                insights.append("Results are sorted in a specific order")
        
        # Add row count insight
        if row_count == 0:
            insights.append("No records match your criteria")
        elif row_count == 1:
            insights.append("Found exactly one matching record")
        elif row_count < 10:
            insights.append(f"Found {row_count} matching records")
        elif row_count < 100:
            insights.append(f"Found {row_count} records - consider refining your search")
        else:
            insights.append(f"Found {row_count} records - showing sample results")
        
        return insights
    
    def _format_performance_metrics(self, execution_time, total_time):
        """Format performance metrics for frontend display."""
        return {
            "query_execution_time": f"{execution_time:.3f}s",
            "total_processing_time": f"{total_time:.3f}s",
            "embedding_time": f"{total_time - execution_time:.3f}s",
            "performance_rating": "Excellent" if total_time < 1.0 else "Good" if total_time < 3.0 else "Slow"
        }
    
    def _create_enhanced_response(self, query_result, natural_query, sql_query, execution_time, total_time):
        """Create an enhanced response with rich metadata for frontend."""
        try:
            # Handle different query_result formats
            if isinstance(query_result, dict):
                # Expected format: {"columns": [...], "data": [...]}
                columns = query_result.get('columns', [])
                data = query_result.get('data', [])
            elif isinstance(query_result, list):
                # Raw database results: [{"col1": "val1", "col2": "val2"}, ...]
                data = query_result
                columns = list(data[0].keys()) if data else []
            else:
                # Fallback
                data = []
                columns = []
            
            row_count = len(data)
            
            # Create enhanced response
            enhanced_response = {
                "success": True,
                "natural_query": natural_query,
                "sql_query": sql_query,
                "results": {
                    "columns": columns,
                    "data": data,
                    "row_count": row_count,
                    "column_descriptions": self._format_column_descriptions(columns),
                },
                "insights": self._format_query_insights(sql_query, row_count),
                "performance": self._format_performance_metrics(execution_time, total_time),
                "metadata": {
                    "query_id": f"query_{int(time.time())}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "database": "CRM Database",
                    "query_complexity": "Simple" if len(sql_query.split()) < 10 else "Complex"
                }
            }
            
            return enhanced_response
            
        except Exception as e:
            logger.error(f"Error creating enhanced response: {str(e)}")
            # Fallback to basic response
            return {
                "success": True,
                "natural_query": natural_query,
                "sql_query": sql_query,
                "results": query_result,
                "error": f"Enhanced formatting failed: {str(e)}"
            }
    
    def cleanup(self):
        """Clean up resources."""
        if self.db:
            self.db.disconnect()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    # Startup
    logger.info("🚀 Starting SQL Retriever API with Runpod services...")
    app_state["startup_time"] = time.time()
    
    try:
        # Initialize SQL Retriever with Runpod services
        retriever = RunpodSQLRetriever()
        app_state["retriever"] = retriever
        logger.info("✅ Runpod SQL Retriever initialized successfully")
        
        # Test database connection
        if retriever.db:
            test_result = retriever.db.execute_query("SELECT 1 as test")
            logger.info(f"✅ Database connection verified: {len(test_result)} rows")
        
        # Test Runpod services
        try:
            # Test embedding service
            embed_health = requests.get(f"{EMBEDDING_URL}/health", timeout=10)
            if embed_health.status_code == 200:
                logger.info("✅ Embedding service connected")
            else:
                logger.warning("⚠️  Embedding service not responding")
        except Exception as e:
            logger.warning(f"⚠️  Embedding service connection failed: {e}")
        
        try:
            # Test LLM service
            llm_health = requests.get(f"{LLM_URL}/v1/models", timeout=10)
            if llm_health.status_code == 200:
                logger.info("✅ LLM service connected")
            else:
                logger.warning("⚠️  LLM service not responding")
        except Exception as e:
            logger.warning(f"⚠️  LLM service connection failed: {e}")
        
        logger.info("🎉 SQL Retriever API ready with Runpod services!")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize application: {e}")
        raise e
    
    yield
    
    # Shutdown
    logger.info("🧹 Shutting down SQL Retriever API...")
    if app_state.get("retriever"):
        app_state["retriever"].cleanup()
    logger.info("👋 SQL Retriever API shut down complete")

# Initialize FastAPI app
app = FastAPI(
    title="SQL Retriever API (Runpod)",
    description="RAG-powered SQL query generator using Runpod GPU and CPU services",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent error format."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            detail=f"Request: {request.method} {request.url.path}"
        ).model_dump()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail="An unexpected error occurred"
        ).model_dump()
    )

# Health check endpoint (no auth required)
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Check API health status including Runpod services."""
    try:
        retriever = app_state.get("retriever")
        if not retriever:
            return HealthResponse(
                status="unhealthy",
                db_connected=False,
                rag_enabled=False,
                details={"error": "Retriever not initialized"}
            )
        
        # Test database connection
        db_connected = False
        try:
            if retriever.db:
                retriever.db.execute_query("SELECT 1")
                db_connected = True
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
        
        # Test Runpod services
        embedding_healthy = False
        llm_healthy = False
        
        try:
            response = requests.get(f"{EMBEDDING_URL}/health", timeout=5)
            embedding_healthy = response.status_code == 200
        except:
            pass
            
        try:
            response = requests.get(f"{LLM_URL}/v1/models", timeout=5)
            llm_healthy = response.status_code == 200
        except:
            pass
        
        # Get system statistics
        stats = retriever.get_statistics()
        
        status = "healthy" if (db_connected and embedding_healthy and llm_healthy) else "unhealthy"
        
        return HealthResponse(
            status=status,
            db_connected=db_connected,
            rag_enabled=True,
            details={
                "uptime_seconds": time.time() - app_state.get("startup_time", 0),
                "total_queries": stats.get("total_queries", 0),
                "database_path": stats.get("database_path", "unknown"),
                "embedding_service": f"{'✅' if embedding_healthy else '❌'} {EMBEDDING_URL}",
                "llm_service": f"{'✅' if llm_healthy else '❌'} {LLM_URL}"
            }
        )
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthResponse(
            status="unhealthy",
            db_connected=False,
            rag_enabled=False,
            details={"error": str(e)}
        )

@app.post("/query", response_model=QueryResponse, tags=["Query"])
async def process_query(
    request: QueryRequest,
    _: bool = Depends(verify_api_key)
):
    """Process natural language query using Runpod services."""
    retriever = app_state.get("retriever")
    if not retriever:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        # Handle optional database URI override
        original_db = None
        if request.db_uri:
            logger.info(f"Using database URI override: {request.db_uri}")
            original_db = retriever.db
            retriever.db = DatabaseConnection(request.db_uri)
            retriever.db.connect()
        
        # Process the query
        result = retriever.process_query(request.question)
        
        # Restore original database if overridden
        if original_db:
            if retriever.db:
                retriever.db.disconnect()
            retriever.db = original_db
        
        # Create enhanced response if successful
        if result.get("success", False):
            enhanced_result = retriever._create_enhanced_response(
                query_result=result.get("results", {}),
                natural_query=request.question,
                sql_query=result.get("sql_query", ""),
                execution_time=result.get("processing_time", 0.0),
                total_time=result.get("processing_time", 0.0)
            )
            
            return QueryResponse(
                success=enhanced_result.get("success", False),
                sql_query=enhanced_result.get("sql_query"),
                results=enhanced_result.get("results", {}),
                processing_time=enhanced_result.get("performance", {}).get("total_processing_time", "0.000s"),
                error=enhanced_result.get("error"),
                insights=enhanced_result.get("insights", []),
                performance=enhanced_result.get("performance", {}),
                metadata=enhanced_result.get("metadata", {})
            )
        else:
            # Return basic response for failed queries
        return QueryResponse(
            success=result.get("success", False),
            sql_query=result.get("sql_query"),
                results=result.get("results", {}),
            processing_time=result.get("processing_time", 0.0),
            error=result.get("error")
        )
        
    except Exception as e:
        logger.error(f"Query processing error: {e}")
        
        # Restore original database if overridden
        if 'original_db' in locals() and original_db:
            if retriever.db:
                retriever.db.disconnect()
            retriever.db = original_db
        
        raise HTTPException(
            status_code=500,
            detail=f"Query processing failed: {str(e)}"
        )

@app.get("/schema", response_model=SchemaResponse, tags=["Database"])
async def get_schema(
    db_uri: Optional[str] = Query(None, description="Optional database URI override"),
    _: bool = Depends(verify_api_key)
):
    """Get database schema information."""
    retriever = app_state.get("retriever")
    if not retriever:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        # Handle optional database URI override
        original_db = None
        db_connection = retriever.db
        
        if db_uri:
            logger.info(f"Using database URI override for schema: {db_uri}")
            original_db = retriever.db
            db_connection = DatabaseConnection(db_uri)
            db_connection.connect()
        
        # Get schema description
        schema_description = db_connection.get_schema_description()
        
        # Get table names
        table_info = db_connection.get_table_info()
        if isinstance(table_info, dict):
            tables = list(table_info.keys())
        else:
            # Fallback: get tables from database
            tables_result = db_connection.execute_query(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row["name"] for row in tables_result]
        
        # Restore original database if overridden
        if original_db:
            db_connection.disconnect()
        
        return SchemaResponse(
            schema=schema_description,
            tables=tables
        )
        
    except Exception as e:
        logger.error(f"Schema retrieval error: {e}")
        
        # Restore original database if overridden
        if 'original_db' in locals() and original_db and 'db_connection' in locals():
            try:
                db_connection.disconnect()
            except:
                pass
        
        raise HTTPException(
            status_code=500,
            detail=f"Schema retrieval failed: {str(e)}"
        )

@app.post("/learn", response_model=LearnResponse, tags=["Learning"])
async def learn_from_feedback(
    request: LearnRequest,
    _: bool = Depends(verify_api_key)
):
    """Learn from user feedback (placeholder - would need embedding service extension)."""
            return LearnResponse(
                success=False,
        message="Learning feature requires embedding service extension"
        )

@app.get("/stats", response_model=StatsResponse, tags=["Statistics"])
async def get_statistics(_: bool = Depends(verify_api_key)):
    """Get system statistics."""
    retriever = app_state.get("retriever")
    if not retriever:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        stats = retriever.get_statistics()
        
        return StatsResponse(
            total_queries=stats.get("total_queries", 0),
            total_processing_time=stats.get("total_processing_time", 0.0),
            average_processing_time=stats.get("average_processing_time", 0.0),
            database_path=stats.get("database_path", "unknown"),
            rag_enabled=stats.get("rag_enabled", True),
            safety_checks_enabled=stats.get("safety_checks_enabled", True)
        )
        
    except Exception as e:
        logger.error(f"Statistics error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Statistics retrieval failed: {str(e)}"
        )

# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """API root endpoint."""
    return {
        "message": "SQL Retriever API (Runpod Architecture)",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "services": {
            "embedding": EMBEDDING_URL,
            "llm": LLM_URL
        }
    }

# Debug endpoint
@app.get("/debug", tags=["Debug"])
async def debug_info():
    """Debug endpoint to check environment and service connections."""
    debug_data = {
        "environment_vars": {
            "DATABASE_URL": "***" if os.getenv("DATABASE_URL") else None,
            "DATABASE_TYPE": os.getenv("DATABASE_TYPE"),
            "API_KEY": "***" if os.getenv("API_KEY") else None,
            "EMBEDDING_URL": EMBEDDING_URL,
            "LLM_URL": LLM_URL,
            "PORT": os.getenv("PORT")
        },
        "retriever_status": "initialized" if app_state.get("retriever") else "not_initialized"
    }
    
    retriever = app_state.get("retriever")
    if retriever and retriever.db:
        try:
            # Test basic database connection
            result = retriever.db.execute_query("SELECT 1 as test")
            debug_data["database_test"] = "success"
            debug_data["database_type"] = retriever.db.db_type
        except Exception as e:
            debug_data["database_test"] = f"failed: {str(e)}"
            debug_data["database_error"] = str(e)
    
    # Test Runpod services
    try:
        response = requests.get(f"{EMBEDDING_URL}/health", timeout=5)
        debug_data["embedding_service"] = f"status: {response.status_code}"
    except Exception as e:
        debug_data["embedding_service"] = f"error: {str(e)}"
    
    try:
        response = requests.get(f"{LLM_URL}/v1/models", timeout=5)
        debug_data["llm_service"] = f"status: {response.status_code}"
    except Exception as e:
        debug_data["llm_service"] = f"error: {str(e)}"
    
    return debug_data

if __name__ == "__main__":
    # Development server
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=os.getenv("ENVIRONMENT") == "development",
        log_level="info"
    ) 