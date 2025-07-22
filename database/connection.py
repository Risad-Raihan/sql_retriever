"""Database connection management for SQL retriever bot."""

import os
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
from sqlalchemy import create_engine, text, MetaData, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine
from config import DATABASE_PATH, DATABASE_TYPE, DATABASE_URL, CRM_TABLES, CRM_BUSINESS_CONTEXT

logger = logging.getLogger(__name__)

class DatabaseConnection:
    """Database connection handler supporting both SQLite and PostgreSQL."""
    
    def __init__(self, db_path_or_url: Optional[str] = None):
        self.db_type = DATABASE_TYPE.lower()
        
        if db_path_or_url:
            self.connection_string = db_path_or_url
        elif DATABASE_URL:
            # Use PostgreSQL connection URL from environment
            if "cloudsql" in DATABASE_URL:
                # Fix Cloud SQL connection format
                # Convert from postgresql://user:pass@//cloudsql/project:region:instance/db
                # To postgresql://user:pass@/db?host=/cloudsql/project:region:instance
                import re
                match = re.match(r'postgresql://([^@]+)@//cloudsql/([^/]+)/(.+)', DATABASE_URL)
                if match:
                    user_pass, instance_connection, db_name = match.groups()
                    self.connection_string = f"postgresql://{user_pass}@/{db_name}?host=/cloudsql/{instance_connection}"
                else:
                    self.connection_string = DATABASE_URL
            else:
                self.connection_string = DATABASE_URL
            self.db_type = "postgresql"
        else:
            # Use SQLite file path
            self.connection_string = f"sqlite:///{DATABASE_PATH}"
            self.db_type = "sqlite"
            
        self.engine: Optional[Engine] = None
        self.session_maker = None
        self._validate_database()
        
    def _validate_database(self):
        """Validate database connection based on type."""
        try:
            if self.db_type == "sqlite":
                # For SQLite, check if file exists
                db_file = self.connection_string.replace("sqlite:///", "")
                if not os.path.exists(db_file):
                    raise FileNotFoundError(f"SQLite database file not found: {db_file}")
        
            # Test connection for both SQLite and PostgreSQL
            engine = create_engine(self.connection_string)
            with engine.connect() as conn:
                if self.db_type == "sqlite":
                    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
                    tables = [row[0] for row in result.fetchall()]
                else:  # PostgreSQL
                    result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public';"))
                    tables = [row[0] for row in result.fetchall()]
                
                # Validate expected CRM tables exist
                expected_tables = set(CRM_TABLES.keys())
                actual_tables = set(tables)
                
                if not expected_tables.issubset(actual_tables):
                    missing = expected_tables - actual_tables
                    logger.warning(f"Missing expected tables: {missing}")
                
                logger.info(f"Connected to {self.db_type.upper()} database with tables: {tables}")
                
        except Exception as e:
            logger.error(f"Database validation failed: {e}")
            raise ConnectionError(f"Failed to connect to {self.db_type} database: {e}")
    
    def connect(self):
        """Establish database connection."""
        try:
            self.engine = create_engine(
                self.connection_string,
                pool_pre_ping=True,
                pool_recycle=300 if self.db_type == "postgresql" else -1
            )
            self.session_maker = sessionmaker(bind=self.engine)
            logger.info(f"{self.db_type.upper()} database connection established")
            return self.engine
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def disconnect(self):
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
            self.engine = None
            self.session_maker = None
            logger.info("Database connection closed")
    
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a SQL query and return results."""
        if not self.engine:
            self.connect()
        
        try:
            with self.engine.connect() as conn:
                if params:
                    result = conn.execute(text(query), params)
                else:
                    result = conn.execute(text(query))
                
                # Convert results to list of dictionaries
                results = []
                if result.returns_rows:
                    columns = result.keys()
                    rows = result.fetchall()
                    results = [dict(zip(columns, row)) for row in rows]
            
            logger.info(f"Query executed successfully, returned {len(results)} rows")
            return results
            
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query}")
            raise
    
    def get_table_info(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        """Get information about tables and their schemas."""
        if not self.engine:
            self.connect()
        
        try:
            inspector = inspect(self.engine)
            
            if table_name:
                # Get specific table info
                columns = inspector.get_columns(table_name)
                
                # Get sample data
                with self.engine.connect() as conn:
                    result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT 3"))
                    sample_rows = [dict(row._mapping) for row in result.fetchall()]
                
                return {
                    'table_name': table_name,
                    'columns': [
                        {
                            'name': col['name'], 
                            'type': str(col['type']), 
                            'nullable': col['nullable']
                        } for col in columns
                    ],
                    'sample_rows': sample_rows
                }
            else:
                # Get all tables info
                tables_info = {}
                for table in CRM_TABLES.keys():
                    try:
                        tables_info[table] = self.get_table_info(table)
                    except Exception as e:
                        logger.warning(f"Could not get info for table {table}: {e}")
                
                return tables_info
                
        except Exception as e:
            logger.error(f"Failed to get table info: {e}")
            raise
    
    def get_schema_description(self) -> str:
        """Get a comprehensive schema description for the CRM database."""
        syntax_rules = {
            "sqlite": [
                "- Use STRFTIME('%Y', date_column) for year extraction, NOT EXTRACT()",
                "- Use STRFTIME('%m', date_column) for month extraction, NOT EXTRACT()",
                "- Use STRFTIME('%Y-%m', date_column) for year-month grouping"
            ],
            "postgresql": [
                "- Use EXTRACT(YEAR FROM date_column) for year extraction",
                "- Use EXTRACT(MONTH FROM date_column) for month extraction", 
                "- Use DATE_TRUNC('month', date_column) for year-month grouping",
                "- Use TO_CHAR(date_column, 'YYYY-MM') for formatted year-month"
            ]
        }
        
        schema_parts = [
            CRM_BUSINESS_CONTEXT,
            f"\n🗄️ Database Schema ({self.db_type.upper()}):",
            f"\n🔧 CRITICAL {self.db_type.upper()} Syntax Rules:"
        ]
        
        # Add database-specific syntax rules
        schema_parts.extend(syntax_rules.get(self.db_type, syntax_rules["sqlite"]))
        
        schema_parts.extend([
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
            "- paymentDate: In PAYMENTS table"
        ])
        
        # Add database-specific analytical patterns
        if self.db_type == "sqlite":
            schema_parts.extend([
                "\n📈 Common Analytical Patterns (SQLite):",
                "- Total revenue: SUM(od.quantityOrdered * od.priceEach) FROM orderdetails od",
                "- Monthly trends: GROUP BY STRFTIME('%Y-%m', o.orderDate)",
                "- Top customers: ORDER BY SUM(revenue) DESC LIMIT N",
                "- Employee performance: JOIN customers c ON e.employeeNumber = c.salesRepEmployeeNumber"
            ])
        else:  # PostgreSQL
            schema_parts.extend([
                "\n📈 Common Analytical Patterns (PostgreSQL):",
                "- Total revenue: SUM(od.quantityOrdered * od.priceEach) FROM orderdetails od", 
                "- Monthly trends: GROUP BY DATE_TRUNC('month', o.orderDate)",
                "- Top customers: ORDER BY SUM(revenue) DESC LIMIT N",
                "- Employee performance: JOIN customers c ON e.employeeNumber = c.salesRepEmployeeNumber"
            ])
        
        try:
            if not self.engine:
                self.connect()
            
            inspector = inspect(self.engine)
            
            for table_name, expected_columns in CRM_TABLES.items():
                try:
                    # Get table schema
                    columns_info = inspector.get_columns(table_name)
                
                    # Get row count
                    with self.engine.connect() as conn:
                        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                        row_count = result.scalar()
                
                    schema_parts.append(f"\n📋 {table_name.upper()} ({row_count} rows):")
                    for col_info in columns_info:
                        col_name = col_info['name']
                        col_type = str(col_info['type'])
                        nullable = "NULL" if col_info['nullable'] else "NOT NULL"
                        schema_parts.append(f"  - {col_name}: {col_type} {nullable}")
                    
                    # Add specific guidance for key tables
                    if table_name == "orderdetails":
                        schema_parts.append("  💡 Key for revenue: quantityOrdered * priceEach")
                    elif table_name == "orders":
                        if self.db_type == "sqlite":
                            schema_parts.append("  💡 Date operations: STRFTIME('%Y', orderDate) for year")
                        else:
                            schema_parts.append("  💡 Date operations: EXTRACT(YEAR FROM orderDate) for year")
                    elif table_name == "products":
                        schema_parts.append("  💡 Pricing: MSRP (retail), buyPrice (cost)")
                    elif table_name == "customers":
                        schema_parts.append("  💡 Links to employees via salesRepEmployeeNumber")
                    elif table_name == "employees":
                        schema_parts.append("  💡 Performance via customer relationships")
                        
                except Exception as e:
                    logger.warning(f"Could not get schema for table {table_name}: {e}")
                    schema_parts.append(f"\n📋 {table_name.upper()} (schema unavailable)")
            
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