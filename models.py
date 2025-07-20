from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


# Request Models
class QueryRequest(BaseModel):
    """Request model for /query endpoint."""
    question: str = Field(..., description="Natural language question", min_length=1, max_length=500)
    db_uri: Optional[str] = Field(None, description="Optional database URI override")


class LearnRequest(BaseModel):
    """Request model for /learn endpoint."""
    question: str = Field(..., description="Original question", min_length=1)
    sql_query: str = Field(..., description="SQL query that was executed", min_length=1)
    success: bool = Field(..., description="Whether the query was successful")
    feedback: str = Field(..., description="User feedback or explanation", max_length=1000)


# Response Models
class QueryResponse(BaseModel):
    """Response model for /query endpoint."""
    success: bool = Field(..., description="Whether the query was successful")
    sql_query: Optional[str] = Field(None, description="Generated SQL query")
    results: List[Dict[str, Any]] = Field(default_factory=list, description="Query results")
    processing_time: float = Field(..., description="Processing time in seconds")
    error: Optional[str] = Field(None, description="Error message if failed")


class HealthResponse(BaseModel):
    """Response model for /health endpoint."""
    status: str = Field(..., description="Health status: healthy or unhealthy")
    db_connected: bool = Field(..., description="Database connection status")
    rag_enabled: bool = Field(..., description="RAG functionality status")
    details: Dict[str, Any] = Field(..., description="Additional health details")


class SchemaResponse(BaseModel):
    """Response model for /schema endpoint."""
    schema: str = Field(..., description="Database schema description")
    tables: List[str] = Field(..., description="List of table names")


class LearnResponse(BaseModel):
    """Response model for /learn endpoint."""
    success: bool = Field(..., description="Whether learning was successful")
    message: str = Field(..., description="Response message")


class StatsResponse(BaseModel):
    """Response model for /stats endpoint."""
    total_queries: int = Field(..., description="Total number of queries processed")
    total_processing_time: float = Field(..., description="Total processing time")
    average_processing_time: float = Field(..., description="Average processing time per query")
    database_path: str = Field(..., description="Current database path")
    rag_enabled: bool = Field(..., description="RAG functionality status")
    safety_checks_enabled: bool = Field(..., description="Safety checks status")


class ErrorResponse(BaseModel):
    """Generic error response model."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.now, description="Error timestamp") 