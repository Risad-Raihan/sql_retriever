#!/usr/bin/env python3
"""
CRM SQL Retriever Bot - Main Application
A RAG-powered SQL query generator for CRM database using LangChain and Llama models.
"""

import os
import sys
import time
import logging
from typing import Dict, Any, Optional

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.connection import DatabaseConnection
from llm.runpod_client import LLMClient
from utils.logger import get_logger
from utils.response_formatter import ResponseFormatter
from config import (
    RAG_ENABLED, ENABLE_SAFETY_CHECKS,
    CRM_BUSINESS_CONTEXT, LOG_LEVEL
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = get_logger(__name__)

class CRMSQLRetriever:
    """Main CRM SQL Retriever application with RAG capabilities."""
    
    def __init__(self):
        """Initialize the CRM SQL Retriever with all components."""
        logger.info("🚀 Initializing CRM SQL Retriever Bot...")
        
        # Initialize components
        self.db = None
        self.llm_client = None
        self.response_formatter = ResponseFormatter()
        
        # Processing stats
        self.query_count = 0
        self.total_processing_time = 0.0
        
        self._initialize_components()
    
    def _initialize_components(self):
        """Initialize all system components."""
        try:
            # Initialize database connection
            logger.info("📊 Connecting to CRM database...")
            self.db = DatabaseConnection()
            self.db.connect()
            logger.info(f"✅ Connected to CRM database")
            
            # Initialize LLM client (Runpod)
            if RAG_ENABLED:
                logger.info("🎯 Initializing Runpod LLM client...")
                self.llm_client = LLMClient()
                logger.info("✅ Runpod LLM client initialized")
            
            # Display system info
            self._display_system_info()
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize components: {e}")
            raise
    
    def _display_system_info(self):
        """Display system initialization information."""
        logger.info("\n" + "="*80)
        logger.info("🎉 CRM SQL Retriever Bot - Successfully Initialized!")
        logger.info("="*80)
        logger.info(f"📊 Database: {self.db.db_type.upper()} connection")
        logger.info(f"🎯 RAG Enabled: {RAG_ENABLED}")
        logger.info(f"🛡️ Safety Checks: {ENABLE_SAFETY_CHECKS}")
        
        # Display database schema info
        try:
            schema_info = self.db.get_schema_description()
            logger.info("\n📋 CRM Database Schema:")
            for line in schema_info.split('\n')[:10]:  # Show first 10 lines
                logger.info(f"   {line}")
            if len(schema_info.split('\n')) > 10:
                logger.info("   ... (truncated)")
                
        except Exception as e:
            logger.warning(f"Could not display schema info: {e}")
        
        logger.info("\n🚀 Ready to process queries!")
        logger.info("="*80)
    
    def process_query(self, question: str) -> Dict[str, Any]:
        """Process a natural language query and return SQL results."""
        start_time = time.time()
        self.query_count += 1
        
        logger.info(f"\n🔍 Processing Query #{self.query_count}: {question}")
        
        try:
            # Get database schema for context
            schema_info = self.db.get_schema_description()
            
            # Generate SQL using RAG if enabled
            sql_result = None
            processing_method = "none"
            
            if RAG_ENABLED and self.llm_client:
                logger.info("🎯 Using Runpod LLM for SQL generation...")
                
                # Build prompt with schema context
                prompt = f"""You are a SQL expert for a CRM database. Generate a SQL query based on this question.

{schema_info}

Question: {question}

Generate only the SQL query, no explanations:"""
                
                sql_query = self.llm_client.generate(prompt, max_tokens=200, temperature=0.1)
                
                if sql_query and sql_query.strip():
                    sql_result = {
                        'sql_query': sql_query.strip(),
                        'method': 'runpod',
                        'confidence': 0.8,  # Default confidence
                        'similar_examples_count': 0,
                        'processing_time': 0.0
                    }
                    processing_method = "🚀 Runpod LLM"
            
            if not sql_result:
                return {
                    'success': False,
                    'error': 'Failed to generate SQL query',
                    'processing_time': time.time() - start_time,
                    'method': 'none'
                }
            
            sql_query = sql_result['sql_query']
            
            # Execute SQL query
            logger.info(f"📊 Executing SQL: {sql_query}")
            query_results = self.db.execute_query(sql_query)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            self.total_processing_time += processing_time
            
            # Format response
            response = {
                'success': True,
                'question': question,
                'sql_query': sql_query,
                'results': query_results,
                'result_count': len(query_results),
                'processing_time': processing_time,
                'method': processing_method,
                'confidence': sql_result.get('confidence', 0.0),
                'query_number': self.query_count
            }
            
            # Add RAG-specific info if available
            if sql_result.get('method') == 'rag':
                response['similar_examples_count'] = sql_result.get('similar_examples_count', 0)
            
            # Log successful interaction for future learning
            if RAG_ENABLED and query_results:
                logger.info(f"📝 Successful query logged: {len(query_results)} results")
            
            logger.info(f"✅ Query completed: {len(query_results)} results in {processing_time:.3f}s")
            return response
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Query processing failed: {e}")
            
            return {
                'success': False,
                'question': question,
                'error': str(e),
                'processing_time': processing_time,
                'method': processing_method,
                'query_number': self.query_count
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get system processing statistics."""
        avg_time = self.total_processing_time / self.query_count if self.query_count > 0 else 0
        
        stats = {
            'total_queries': self.query_count,
            'total_processing_time': self.total_processing_time,
            'average_processing_time': avg_time,
            'database_path': self.db.db_type.upper() + " connection",
            'rag_enabled': RAG_ENABLED,
            'safety_checks_enabled': ENABLE_SAFETY_CHECKS
        }
        
        return stats
    
    def cleanup(self):
        """Clean up resources."""
        try:
            if self.db:
                self.db.disconnect()
            logger.info("🧹 Cleanup completed")
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}") 