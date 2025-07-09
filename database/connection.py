"""Database connection management for SQL retriever bot."""

import sqlite3
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
from config import DATABASE_PATH, CRM_TABLES, CRM_BUSINESS_CONTEXT

logger = logging.getLogger(__name__)

class DatabaseConnection:
    """Database connection handler for CRM SQLite database."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DATABASE_PATH
        self.connection: Optional[sqlite3.Connection] = None
        self._validate_database()
        
    def _validate_database(self):
        """Validate that the database file exists and is accessible."""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database file not found: {self.db_path}")
        
        # Test connection
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall()]
                
                # Validate expected CRM tables exist
                expected_tables = set(CRM_TABLES.keys())
                actual_tables = set(tables)
                
                if not expected_tables.issubset(actual_tables):
                    missing = expected_tables - actual_tables
                    logger.warning(f"Missing expected tables: {missing}")
                
                logger.info(f"Connected to CRM database with tables: {tables}")
                
        except Exception as e:
            raise ConnectionError(f"Failed to connect to database: {e}")
    
    def connect(self):
        """Establish database connection."""
        try:
            self.connection = sqlite3.connect(self.db_path, timeout=30.0)
            self.connection.row_factory = sqlite3.Row  # Enable column access by name
            logger.info("Database connection established")
            return self.connection
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Database connection closed")
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Execute a SQL query and return results."""
        if not self.connection:
            self.connect()
        
        try:
            cursor = self.connection.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            # Fetch results and convert to list of dictionaries
            columns = [description[0] for description in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append(dict(zip(columns, row)))
            
            logger.info(f"Query executed successfully, returned {len(results)} rows")
            return results
            
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query}")
            raise
    
    def get_table_info(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        """Get information about tables and their schemas."""
        if not self.connection:
            self.connect()
        
        try:
            cursor = self.connection.cursor()
            
            if table_name:
                # Get specific table info
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                # Get sample data
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
                sample_rows = cursor.fetchall()
                
                return {
                    'table_name': table_name,
                    'columns': [{'name': col[1], 'type': col[2], 'nullable': not col[3]} for col in columns],
                    'sample_rows': sample_rows
                }
            else:
                # Get all tables info
                tables_info = {}
                for table in CRM_TABLES.keys():
                    tables_info[table] = self.get_table_info(table)
                
                return tables_info
                
        except Exception as e:
            logger.error(f"Failed to get table info: {e}")
            raise
    
    def get_schema_description(self) -> str:
        """Get a comprehensive schema description for the CRM database with SQLite syntax guidance."""
        schema_parts = [
            CRM_BUSINESS_CONTEXT,
            "\n🗄️ Database Schema (SQLite):",
            "\n🔧 CRITICAL SQLite Syntax Rules:",
            "- Use STRFTIME('%Y', date_column) for year extraction, NOT EXTRACT()",
            "- Use STRFTIME('%m', date_column) for month extraction, NOT EXTRACT()",
            "- Use STRFTIME('%Y-%m', date_column) for year-month grouping",
            "\n📊 Table Relationships (Foreign Keys):",
            "- customers.salesRepEmployeeNumber -> employees.employeeNumber",
            "- orders.customerNumber -> customers.customerNumber", 
            "- orderdetails.orderNumber -> orders.orderNumber",
            "- orderdetails.productCode -> products.productCode",
            "- products.productLine -> productlines.productLine",
            "- employees.officeCode -> offices.officeCode",
            "- payments.customerNumber -> customers.customerNumber",
            "\n💰 Revenue & Financial Calculations:",
            "- Revenue = orderdetails.quantityOrdered * orderdetails.priceEach",
            "- Product cost = products.buyPrice",
            "- Product retail price = products.MSRP",
            "- Payment amounts = payments.amount",
            "\n⚠️ Key Column Locations (IMPORTANT!):",
            "- orderDate: In ORDERS table (not orderdetails)",
            "- priceEach: In ORDERDETAILS table (not products)", 
            "- salesRepEmployeeNumber: In CUSTOMERS table (not orders)",
            "- quantityOrdered: In ORDERDETAILS table",
            "- paymentDate: In PAYMENTS table",
            "\n📈 Common Analytical Patterns:",
            "- Total revenue: SUM(od.quantityOrdered * od.priceEach) FROM orderdetails od",
            "- Monthly trends: GROUP BY STRFTIME('%Y-%m', o.orderDate)",
            "- Top customers: ORDER BY SUM(revenue) DESC LIMIT N",
            "- Employee performance: JOIN customers c ON e.employeeNumber = c.salesRepEmployeeNumber"
        ]
        
        try:
            if not self.connection:
                self.connect()
            
            cursor = self.connection.cursor()
            
            for table_name, expected_columns in CRM_TABLES.items():
                # Get table schema
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns_info = cursor.fetchall()
                
                # Get row count
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = cursor.fetchone()[0]
                
                schema_parts.append(f"\n📋 {table_name.upper()} ({row_count} rows):")
                for col_info in columns_info:
                    col_name, col_type, nullable = col_info[1], col_info[2], "NULL" if not col_info[3] else "NOT NULL"
                    schema_parts.append(f"  - {col_name}: {col_type} {nullable}")
                    
                # Add specific guidance for key tables
                if table_name == "orderdetails":
                    schema_parts.append("  💡 Key for revenue: quantityOrdered * priceEach")
                elif table_name == "orders":
                    schema_parts.append("  💡 Date operations: STRFTIME('%Y', orderDate) for year")
                elif table_name == "products":
                    schema_parts.append("  💡 Pricing: MSRP (retail), buyPrice (cost)")
                elif table_name == "customers":
                    schema_parts.append("  💡 Links to employees via salesRepEmployeeNumber")
                elif table_name == "employees":
                    schema_parts.append("  💡 Performance via customer relationships")
            
            return "\n".join(schema_parts)
            
        except Exception as e:
            logger.error(f"Failed to generate schema description: {e}")
            return f"Error generating schema: {e}"
    
    def get_business_context(self) -> str:
        """Get business context for the CRM system."""
        return CRM_BUSINESS_CONTEXT
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

# Global database instance
db = DatabaseConnection() 