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

# Add missing configurations
LOGGING_CONFIG = {
    'level': LOG_LEVEL,
    'log_file': LOG_FILE,
    'format': '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
}

# CRM Business Context
CRM_BUSINESS_CONTEXT = {
    "description": "Customer Relationship Management system for tracking customers, orders, employees, products, offices, and payments.",
    "tables": {
        "customers": "Customer information and contact details",
        "orders": "Customer purchase orders",
        "employees": "Company staff and sales representatives", 
        "products": "Product catalog and inventory",
        "offices": "Company office locations",
        "payments": "Customer payment records"
    }
}

# CRM Tables configuration
CRM_TABLES = [
    "customers", "orders", "orderdetails", "products", "productlines", 
    "employees", "offices", "payments"
] 