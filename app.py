#!/usr/bin/env python3
"""
FastAPI Production Backend for SQL Retriever
A cloud-ready RAG-powered SQL query generator API for CRM databases.
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

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import CRMSQLRetriever
from database.connection import DatabaseConnection
from utils.logger import get_logger
from models import (
    QueryRequest, QueryResponse, LearnRequest, LearnResponse,
    HealthResponse, SchemaResponse, StatsResponse, ErrorResponse
)
from config import RAG_ENABLED

# Initialize logger
logger = get_logger(__name__)

# Global app state
app_state = {
    "retriever": None,
    "startup_time": None
}

# Security
security = HTTPBearer()

def get_api_key() -> str:
    """Get API key from environment variable."""
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise ValueError("API_KEY environment variable not set")
    return api_key

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    # Startup
    logger.info("🚀 Starting SQL Retriever API...")
    app_state["startup_time"] = time.time()
    
    try:
        # Initialize CRM SQL Retriever
        retriever = CRMSQLRetriever()
        app_state["retriever"] = retriever
        logger.info("✅ CRM SQL Retriever initialized successfully")
        
        # Test database connection
        if retriever.db:
            test_result = retriever.db.execute_query("SELECT 1 as test")
            logger.info(f"✅ Database connection verified: {len(test_result)} rows")
        
        logger.info("🎉 SQL Retriever API ready!")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize application: {e}")
        raise e
    
    yield
    
    # Shutdown
    logger.info("🧹 Shutting down SQL Retriever API...")
    if app_state["retriever"]:
        app_state["retriever"].cleanup()
    logger.info("👋 SQL Retriever API shut down complete")

# Initialize FastAPI app
app = FastAPI(
    title="SQL Retriever API",
    description="RAG-powered SQL query generator for CRM databases",
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
        ).dict()
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
        ).dict()
    )

# Health check endpoint (no auth required)
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Check API health status."""
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
        
        # Get system statistics
        stats = retriever.get_statistics()
        
        status = "healthy" if db_connected else "unhealthy"
        
        return HealthResponse(
            status=status,
            db_connected=db_connected,
            rag_enabled=RAG_ENABLED and hasattr(retriever, 'llm_client') and retriever.llm_client is not None,
            details={
                "uptime_seconds": time.time() - app_state.get("startup_time", 0),
                "total_queries": stats.get("total_queries", 0),
                "database_path": stats.get("database_path", "unknown")
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
    """Process natural language query and return SQL results."""
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
        
        return QueryResponse(
            success=result.get("success", False),
            sql_query=result.get("sql_query"),
            results=result.get("results", []),
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
    """Learn from user feedback to improve query generation."""
    retriever = app_state.get("retriever")
    if not retriever:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        if not RAG_ENABLED or not retriever.rag_client:
            return LearnResponse(
                success=False,
                message="RAG learning is not enabled"
            )
        
        # Learn from the interaction
        retriever.rag_client.learn_from_interaction(
            question=request.question,
            sql_query=request.sql_query,
            success=request.success,
            explanation=request.feedback
        )
        
        return LearnResponse(
            success=True,
            message="Successfully learned from feedback"
        )
        
    except Exception as e:
        logger.error(f"Learning error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Learning failed: {str(e)}"
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
            rag_enabled=stats.get("rag_enabled", False),
            safety_checks_enabled=stats.get("safety_checks_enabled", False)
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
        "message": "SQL Retriever API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

# Debug endpoint (temporary) 
@app.get("/debug", tags=["Debug"])
async def debug_info():
    """Debug endpoint to check environment and database connection."""
    debug_data = {
        "environment_vars": {
            "DATABASE_URL": "***" if os.getenv("DATABASE_URL") else None,
            "DATABASE_TYPE": os.getenv("DATABASE_TYPE"),
            "API_KEY": "***" if os.getenv("API_KEY") else None,
            "RAG_ENABLED": os.getenv("RAG_ENABLED"),
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