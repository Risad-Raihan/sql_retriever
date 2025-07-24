#!/usr/bin/env python3
"""
Comprehensive Test Suite for SQL Retriever FastAPI Application
Tests all endpoints with various scenarios including edge cases and error conditions.
"""

import pytest
import asyncio
import os
import tempfile
import sqlite3
import json
import time
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List
import httpx
from fastapi.testclient import TestClient
from contextlib import asynccontextmanager

# Import the FastAPI app and related modules
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from database.connection import DatabaseConnection
from llm.runpod_client import LLMClient
from models import QueryRequest, QueryResponse, HealthResponse

# Test configuration
TEST_API_KEY = "test-api-key-12345"
INVALID_API_KEY = "invalid-key"


class TestDatabaseSetup:
    """Setup test database for integration tests."""
    
    @staticmethod
    def create_test_database(db_path: str):
        """Create minimal test database with CRM structure."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                customerNumber INTEGER PRIMARY KEY,
                customerName TEXT NOT NULL,
                country TEXT
            )
        ''')
        cursor.execute("INSERT OR IGNORE INTO customers (customerNumber, customerName, country) VALUES (1, 'Test Customer', 'USA')")
        
        conn.commit()
        conn.close()


@pytest.fixture(scope="session")
def test_db():
    """Create test database for the session."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        TestDatabaseSetup.create_test_database(temp_db.name)
        yield temp_db.name
        try:
            os.unlink(temp_db.name)
        except:
            pass


@pytest.fixture
def mock_api_key():
    """Mock API key environment variable."""
    with patch.dict(os.environ, {"API_KEY": TEST_API_KEY}):
        yield TEST_API_KEY


@pytest.fixture
def client(mock_api_key):
    """Create test client with mocked dependencies."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Authentication headers for API requests."""
    return {"Authorization": f"Bearer {TEST_API_KEY}"}


@pytest.fixture
def invalid_auth_headers():
    """Invalid authentication headers."""
    return {"Authorization": f"Bearer {INVALID_API_KEY}"}


@pytest.fixture
def mock_retriever():
    """Mock CRMSQLRetriever for testing."""
    retriever = Mock(spec=CRMSQLRetriever)
    retriever.db = Mock(spec=DatabaseConnection)
    retriever.rag_client = Mock(spec=LLMClient)
    retriever.cleanup = Mock()
    
    # Mock successful query response
    retriever.process_query.return_value = {
        "success": True,
        "sql_query": "SELECT COUNT(*) FROM customers;",
        "results": [{"count": 5}],
        "processing_time": 1.2,
        "method": "rag"
    }
    
    # Mock statistics
    retriever.get_statistics.return_value = {
        "total_queries": 10,
        "total_processing_time": 25.5,
        "average_processing_time": 2.55,
        "database_path": "/test/db/path",
        "rag_enabled": True,
        "safety_checks_enabled": True
    }
    
    # Mock database connection test
    retriever.db.execute_query.return_value = [{"test": 1}]
    retriever.db.get_schema_description.return_value = "Test Schema"
    retriever.db.get_table_info.return_value = {"customers": [], "products": []}
    
    return retriever


class TestHealthEndpoint:
    """Test cases for /health endpoint."""
    
    def test_health_check_success(self, client, mock_retriever):
        """Test successful health check."""
        with patch('app.app_state', {'retriever': mock_retriever, 'startup_time': time.time()}):
            response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["db_connected"] is True
        assert "uptime_seconds" in data["details"]
    
    def test_health_check_no_retriever(self, client):
        """Test health check when retriever is not initialized."""
        with patch('app.app_state', {'retriever': None, 'startup_time': time.time()}):
            response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["db_connected"] is False
    
    def test_health_check_db_failure(self, client, mock_retriever):
        """Test health check when database connection fails."""
        mock_retriever.db.execute_query.side_effect = Exception("DB connection error")
        
        with patch('app.app_state', {'retriever': mock_retriever, 'startup_time': time.time()}):
            response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"


class TestQueryEndpoint:
    """Test cases for /query endpoint."""
    
    def test_query_success(self, client, auth_headers, mock_retriever):
        """Test successful query processing."""
        with patch('app.app_state', {'retriever': mock_retriever, 'startup_time': time.time()}):
            response = client.post(
                "/query",
                headers=auth_headers,
                json={"question": "How many customers are there?"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["sql_query"] == "SELECT COUNT(*) FROM customers;"
        assert len(data["results"]) == 1
    
    def test_query_without_auth(self, client):
        """Test query without authentication."""
        response = client.post(
            "/query",
            json={"question": "How many customers are there?"}
        )
        assert response.status_code == 403
    
    def test_query_invalid_auth(self, client, invalid_auth_headers):
        """Test query with invalid authentication."""
        response = client.post(
            "/query",
            headers=invalid_auth_headers,
            json={"question": "How many customers are there?"}
        )
        assert response.status_code == 401
    
    def test_query_empty_question(self, client, auth_headers):
        """Test query with empty question."""
        response = client.post(
            "/query",
            headers=auth_headers,
            json={"question": ""}
        )
        assert response.status_code == 422
    
    def test_query_too_long(self, client, auth_headers):
        """Test query with question that's too long."""
        long_question = "x" * 600
        response = client.post(
            "/query",
            headers=auth_headers,
            json={"question": long_question}
        )
        assert response.status_code == 422
    
    def test_query_missing_field(self, client, auth_headers):
        """Test query without question field."""
        response = client.post(
            "/query",
            headers=auth_headers,
            json={}
        )
        assert response.status_code == 422
    
    def test_query_processing_error(self, client, auth_headers, mock_retriever):
        """Test query processing error."""
        mock_retriever.process_query.side_effect = Exception("Processing error")
        
        with patch('app.app_state', {'retriever': mock_retriever, 'startup_time': time.time()}):
            response = client.post(
                "/query",
                headers=auth_headers,
                json={"question": "How many customers are there?"}
            )
        
        assert response.status_code == 500
    
    def test_query_service_not_initialized(self, client, auth_headers):
        """Test query when service is not initialized."""
        with patch('app.app_state', {'retriever': None, 'startup_time': time.time()}):
            response = client.post(
                "/query",
                headers=auth_headers,
                json={"question": "How many customers are there?"}
            )
        
        assert response.status_code == 503
    
    def test_query_with_db_override(self, client, auth_headers, mock_retriever, test_db):
        """Test query with database URI override."""
        with patch('app.app_state', {'retriever': mock_retriever, 'startup_time': time.time()}):
            response = client.post(
                "/query",
                headers=auth_headers,
                json={
                    "question": "How many customers are there?",
                    "db_uri": f"sqlite:///{test_db}"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
    
    def test_query_failed_result(self, client, auth_headers, mock_retriever):
        """Test query that fails during processing."""
        mock_retriever.process_query.return_value = {
            "success": False,
            "error": "SQL generation failed",
            "processing_time": 0.5
        }
        
        with patch('app.app_state', {'retriever': mock_retriever, 'startup_time': time.time()}):
            response = client.post(
                "/query",
                headers=auth_headers,
                json={"question": "Invalid query"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False


class TestSchemaEndpoint:
    """Test cases for /schema endpoint."""
    
    def test_schema_success(self, client, auth_headers, mock_retriever):
        """Test successful schema retrieval."""
        with patch('app.app_state', {'retriever': mock_retriever, 'startup_time': time.time()}):
            response = client.get("/schema", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "schema" in data
        assert "tables" in data
    
    def test_schema_without_auth(self, client):
        """Test schema retrieval without authentication."""
        response = client.get("/schema")
        assert response.status_code == 403
    
    def test_schema_invalid_auth(self, client, invalid_auth_headers):
        """Test schema retrieval with invalid authentication."""
        response = client.get("/schema", headers=invalid_auth_headers)
        assert response.status_code == 401
    
    def test_schema_service_not_initialized(self, client, auth_headers):
        """Test schema retrieval when service is not initialized."""
        with patch('app.app_state', {'retriever': None, 'startup_time': time.time()}):
            response = client.get("/schema", headers=auth_headers)
        
        assert response.status_code == 503


class TestLearnEndpoint:
    """Test cases for /learn endpoint."""
    
    def test_learn_success(self, client, auth_headers, mock_retriever):
        """Test successful learning from feedback."""
        mock_retriever.rag_client.learn_from_interaction = Mock()
        
        with patch('app.app_state', {'retriever': mock_retriever, 'startup_time': time.time()}):
            with patch('app.RAG_ENABLED', True):
                response = client.post(
                    "/learn",
                    headers=auth_headers,
                    json={
                        "question": "How many customers?",
                        "sql_query": "SELECT COUNT(*) FROM customers;",
                        "success": True,
                        "feedback": "Query worked well"
                    }
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
    
    def test_learn_rag_disabled(self, client, auth_headers, mock_retriever):
        """Test learning when RAG is disabled."""
        mock_retriever.rag_client = None
        
        with patch('app.app_state', {'retriever': mock_retriever, 'startup_time': time.time()}):
            with patch('app.RAG_ENABLED', False):
                response = client.post(
                    "/learn",
                    headers=auth_headers,
                    json={
                        "question": "How many customers?",
                        "sql_query": "SELECT COUNT(*) FROM customers;",
                        "success": True,
                        "feedback": "Query worked well"
                    }
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
    
    def test_learn_without_auth(self, client):
        """Test learning without authentication."""
        response = client.post(
            "/learn",
            json={
                "question": "How many customers?",
                "sql_query": "SELECT COUNT(*) FROM customers;",
                "success": True,
                "feedback": "Query worked well"
            }
        )
        assert response.status_code == 403
    
    def test_learn_invalid_input(self, client, auth_headers):
        """Test learning with invalid input."""
        response = client.post(
            "/learn",
            headers=auth_headers,
            json={
                "question": "",
                "sql_query": "SELECT COUNT(*) FROM customers;",
                "success": True,
                "feedback": "Query worked well"
            }
        )
        assert response.status_code == 422


class TestStatsEndpoint:
    """Test cases for /stats endpoint."""
    
    def test_stats_success(self, client, auth_headers, mock_retriever):
        """Test successful statistics retrieval."""
        with patch('app.app_state', {'retriever': mock_retriever, 'startup_time': time.time()}):
            response = client.get("/stats", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "total_queries" in data
        assert data["total_queries"] == 10
    
    def test_stats_without_auth(self, client):
        """Test statistics without authentication."""
        response = client.get("/stats")
        assert response.status_code == 403
    
    def test_stats_service_not_initialized(self, client, auth_headers):
        """Test statistics when service is not initialized."""
        with patch('app.app_state', {'retriever': None, 'startup_time': time.time()}):
            response = client.get("/stats", headers=auth_headers)
        
        assert response.status_code == 503


class TestRootEndpoint:
    """Test cases for root endpoint."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"]) 