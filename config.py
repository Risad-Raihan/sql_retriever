import os
from pathlib import Path
from typing import Dict, List, Any

# Database Configuration
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "data", "test_crm_v1.db")
DATABASE_TYPE = "sqlite"

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

# LangChain Configuration
LANGCHAIN_CONFIG = {
    'agent_type': 'zero-shot-react-description',
    'verbose': True,
    'max_iterations': 5,
    'early_stopping_method': 'generate',
    'handle_parsing_errors': True,
    
    # SQL Database Chain Configuration
    'sql_chain': {
        'use_query_checker': True,
        'query_checker_llm_chain': True,
        'return_intermediate_steps': True,
        'return_direct': False,
        'top_k': 5,  # Number of examples to include in few-shot prompting
        'custom_table_info': None,
        'sample_rows_in_table_info': 3
    },
    
    # Memory Configuration
    'memory': {
        'type': 'conversation_buffer_window',  # conversation_buffer, conversation_buffer_window, conversation_summary
        'k': 10,  # For window memory - number of interactions to remember
        'max_token_limit': 2000,  # For summary memory
        'return_messages': True,
        'ai_prefix': "SQL Assistant",
        'human_prefix': "User"
    },
    
    # Agent Configuration
    'agent': {
        'agent_type': 'structured-chat-zero-shot-react-description',
        'max_iterations': 5,
        'max_execution_time': None,
        'early_stopping_method': 'generate',
        'handle_parsing_errors': True,
        'verbose': True
    },
    
    # Output Parser Configuration
    'output_parsers': {
        'sql_parser': {
            'fix_malformed': True,
            'return_fixing_parser': True
        },
        'pydantic_parser': {
            'pydantic_object': None  # Will be set dynamically
        }
    },
    
    # Prompt Template Configuration
    'prompts': {
        'sql_generation': {
            'template_format': 'f-string',
            'input_variables': ['input', 'table_info', 'dialect', 'top_k'],
            'partial_variables': {}
        },
        'query_checker': {
            'template_format': 'f-string',
            'input_variables': ['query', 'dialect'],
            'partial_variables': {}
        }
    },
    
    # Tool Configuration
    'tools': {
        'sql_database_toolkit': {
            'include_tables': None,  # None means all tables
            'sample_rows_in_table_info': 3,
            'max_string_length': 300,
            'custom_table_info': None
        },
        'custom_tools': {
            'schema_inspector': True,
            'query_explainer': True,
            'query_optimizer': True,
            'safety_checker': True
        }
    },
    
    # Callback Configuration
    'callbacks': {
        'langsmith_tracing': False,
        'verbose_callbacks': True,
        'custom_callback_manager': None
    },
    
    # Chain Configuration
    'chains': {
        'sql_db_chain': {
            'use_query_checker': True,
            'query_checker_llm_chain': True,
            'return_intermediate_steps': True,
            'return_direct': False,
            'top_k': 5
        },
        'sequential_chain': {
            'return_all': False,
            'input_key': 'input',
            'output_key': 'output'
        }
    },
    
    # Retry Configuration
    'retry': {
        'max_retries': 3,
        'retry_delay': 1,
        'exponential_backoff': True,
        'retry_on_exceptions': ['openai.error.RateLimitError', 'requests.exceptions.Timeout']
    }
}

# Logging Configuration
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}',
    'rotation': '1 week',
    'retention': '1 month',
    'log_file': 'sql_retriever_bot.log'
}

# Response Configuration
RESPONSE_CONFIG = {
    'max_table_rows': 50,
    'table_format': 'grid',
    'include_query_time': True,
    'include_row_count': True,
    'truncate_long_text': True,
    'max_text_length': 100
}

# User Roles and Permissions
USER_ROLES = {
    'viewer': {
        'allowed_operations': ['SELECT'],
        'max_results': 100,
        'requires_confirmation': []
    },
    'user': {
        'allowed_operations': ['SELECT', 'INSERT', 'UPDATE'],
        'max_results': 1000,
        'requires_confirmation': ['INSERT', 'UPDATE']
    },
    'admin': {
        'allowed_operations': ['SELECT', 'INSERT', 'UPDATE', 'DELETE'],
        'max_results': 10000,
        'requires_confirmation': ['DELETE']
    }
}

# Default prompts (Legacy - will be replaced by LangChain templates)
SQL_GENERATION_PROMPT = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are an expert SQL query generator for a music database. Generate ONLY the SQL query, nothing else.

<|eot_id|><|start_header_id|>user<|end_header_id|>

Database Schema:
{schema}

Question: {question}

Generate only a valid SQL query that answers the question. Do not include any explanations, just the SQL.

<|eot_id|><|start_header_id|>assistant<|end_header_id|>

SELECT"""

RESPONSE_GENERATION_PROMPT = """
You are a helpful assistant that converts SQL query results into natural language responses.

Original Question: {question}
SQL Query: {sql_query}
Query Results: {results}

Provide a clear, concise response in natural language that answers the user's question.
If the results are empty, provide a helpful message.
Format data appropriately (tables, lists, or summaries as needed).
"""

# Environment variables
def get_env_var(var_name: str, default: Any = None) -> Any:
    """Get environment variable with optional default."""
    return os.getenv(var_name, default)

# Update configurations from environment variables
MODEL_NAME = get_env_var('MODEL_NAME', MODEL_NAME)
DATABASE_PATH = get_env_var('DATABASE_PATH', DATABASE_PATH)
LOG_LEVEL = get_env_var('LOG_LEVEL', LOG_LEVEL) 