import os
from pathlib import Path
from typing import Dict, List, Any

# Database Configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "data", "test_crm_v1.db"))
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite")
DATABASE_URL = os.getenv("DATABASE_URL")  # For PostgreSQL connections

# LLM Configuration
MODEL_NAME = "unsloth/Llama-3.2-3B-Instruct"
MODEL_TEMPERATURE = 0.1
MAX_TOKENS = 200

# RAG Configuration
RAG_ENABLED = True
RAG_VECTOR_STORE_PATH = os.path.join(os.path.dirname(__file__), "rag_data")
RAG_SIMILARITY_THRESHOLD = 0.6
RAG_RELAXED_THRESHOLD = 0.3  # For loose similarity matching to provide context
RAG_MAX_EXAMPLES = 3

# Safety Configuration
ENABLE_SAFETY_CHECKS = True
ALLOWED_OPERATIONS = ["SELECT"]
BLOCKED_KEYWORDS = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE"]

# Logging Configuration
LOG_LEVEL = "INFO"
LOG_FILE = "sql_retriever_bot.log"

# CRM Database Schema Information
CRM_TABLES = {
    "productlines": ["productLine", "textDescription", "htmlDescription", "image"],
    "products": ["productCode", "productName", "productLine", "productScale", "productVendor", 
                "productDescription", "quantityInStock", "buyPrice", "MSRP"],
    "offices": ["officeCode", "city", "phone", "addressLine1", "addressLine2", "state", 
               "country", "postalCode", "territory"],
    "employees": ["employeeNumber", "lastName", "firstName", "extension", "email", 
                 "officeCode", "reportsTo", "jobTitle"],
    "customers": ["customerNumber", "customerName", "contactLastName", "contactFirstName", 
                 "phone", "addressLine1", "addressLine2", "city", "state", "postalCode", 
                 "country", "salesRepEmployeeNumber", "creditLimit"],
    "payments": ["customerNumber", "checkNumber", "paymentDate", "amount"],
    "orders": ["orderNumber", "orderDate", "requiredDate", "shippedDate", "status", 
              "comments", "customerNumber"],
    "orderdetails": ["orderNumber", "productCode", "quantityOrdered", "priceEach", 
                    "orderLineNumber"]
}

# CRM Business Context
CRM_BUSINESS_CONTEXT = """
This is a CRM (Customer Relationship Management) database for a company that sells products.
Key business entities:
- Customers: Companies/individuals who buy products
- Products: Items sold by the company, organized into product lines
- Orders: Purchase orders from customers
- Employees: Company staff who manage sales and operations
- Offices: Company locations where employees work
- Payments: Customer payments for orders
"""

# Logging Configuration
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}',
    'rotation': '1 week',
    'retention': '1 month',
    'log_file': 'sql_retriever_bot.log'
}

# Environment variable overrides
MODEL_NAME = os.getenv('MODEL_NAME', MODEL_NAME)
DATABASE_PATH = os.getenv('DATABASE_PATH', DATABASE_PATH)
LOG_LEVEL = os.getenv('LOG_LEVEL', LOG_LEVEL) 