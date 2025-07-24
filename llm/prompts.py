"""Prompt management for SQL generation and response generation."""

import json
from typing import Dict, Any, List, Optional


class PromptManager:
    """Manages prompts for SQL generation and response generation."""
    
    def __init__(self):
        """Initialize prompt manager."""
        self.sql_generation_template = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are an expert SQL query generator for a CRM database. Your task is to generate PERFECT, EXECUTABLE SQL queries.

🚨 CRITICAL RULES - FOLLOW EXACTLY:
1. ALWAYS use table aliases (customers AS c, orders AS o, etc.)
2. ALWAYS specify which table each column belongs to (c.customername, NOT customername)
3. CHECK column locations carefully - many columns are NOT where you think they are!
4. Use LIMIT to control result size
5. Generate ONLY valid SQL - no explanations, no markdown, no extra text

🔍 COLUMN LOCATION WARNINGS:
- orderDate is in ORDERS table (NOT orderdetails)
- country can be in CUSTOMERS or OFFICES (NOT employees for location)
- priceEach is in ORDERDETAILS (NOT products)
- salesRepEmployeeNumber is in CUSTOMERS (links to employees.employeeNumber)
- quantityOrdered is in ORDERDETAILS (NOT orders)

🗓️ DATE HANDLING RULES (POSTGRESQL):
- For recent orders: WHERE o.orderDate >= '2022-01-01'
- For date comparisons: Use simple date strings like '2024-01-01'
- NEVER use STRFTIME or DATE_TRUNC with constant dates
- For current year: WHERE EXTRACT(YEAR FROM o.orderDate) = EXTRACT(YEAR FROM CURRENT_DATE)
- Keep date logic SIMPLE and avoid complex date functions

🏗️ COMMON JOIN PATTERNS:
- Customer info with orders: customers c JOIN orders o ON c.customerNumber = o.customerNumber
- Customer with employee: customers c JOIN employees e ON c.salesRepEmployeeNumber = e.employeeNumber  
- Order details: orders o JOIN orderdetails od ON o.orderNumber = od.orderNumber
- Product info: orderdetails od JOIN products p ON od.productCode = p.productCode

<|eot_id|><|start_header_id|>user<|end_header_id|>

{schema}

Question: {question}

🎯 GENERATE ONLY THE SQL QUERY. Start with SELECT, end with semicolon.
🔍 Double-check column locations and table joins before responding.
🗓️ Use SIMPLE date comparisons - avoid complex date functions!

<|eot_id|><|start_header_id|>assistant<|end_header_id|>

SELECT"""
        
        self.response_generation_template = """
You are a helpful assistant that converts SQL query results into natural language responses.

Original Question: {question}
SQL Query: {sql_query}
Query Results: {results}

Provide a clear, concise response in natural language that answers the user's question.
If the results are empty, provide a helpful message.
Format data appropriately (tables, lists, or summaries as needed).
"""
    
    def build_sql_generation_prompt(self, natural_language: str, schema: Dict[str, Any]) -> str:
        """Build prompt for SQL generation.
        
        Args:
            natural_language: User's natural language query
            schema: Database schema information
            
        Returns:
            Formatted prompt string
        """
        # Format schema information
        schema_text = self._format_schema_for_prompt(schema)
        
        # Build the prompt
        prompt = self.sql_generation_template.format(
            schema=schema_text,
            question=natural_language
        )
        
        return prompt
    
    def build_response_generation_prompt(
        self, 
        original_question: str, 
        sql_query: str, 
        query_result: Any
    ) -> str:
        """Build prompt for response generation.
        
        Args:
            original_question: User's original question
            sql_query: SQL query that was executed
            query_result: Results from query execution
            
        Returns:
            Formatted prompt string
        """
        # Format query results
        results_text = self._format_results_for_prompt(query_result)
        
        # Build the prompt
        prompt = self.response_generation_template.format(
            question=original_question,
            sql_query=sql_query,
            results=results_text
        )
        
        return prompt
    
    def _format_schema_for_prompt(self, schema: Dict[str, Any]) -> str:
        """Format database schema for inclusion in prompts.
        
        Args:
            schema: Database schema information
            
        Returns:
            Formatted schema string
        """
        if not schema:
            return "No schema information available."
        
        schema_lines = []
        
        # Add database type
        db_type = schema.get('database_type', 'Unknown')
        schema_lines.append(f"Database Type: {db_type}")
        schema_lines.append("")
        
        # Add tables
        tables = schema.get('tables', {})
        if tables:
            schema_lines.append("Tables:")
            for table_name, table_info in tables.items():
                schema_lines.append(f"\n{table_name}:")
                
                # Add columns
                columns = table_info.get('columns', [])
                if columns:
                    for col in columns:
                        col_line = f"  - {col['name']} ({col['type']})"
                        if not col.get('nullable', True):
                            col_line += " NOT NULL"
                        if col.get('primary_key'):
                            col_line += " PRIMARY KEY"
                        schema_lines.append(col_line)
                
                # Add foreign keys
                foreign_keys = table_info.get('foreign_keys', [])
                if foreign_keys:
                    schema_lines.append("  Foreign Keys:")
                    for fk in foreign_keys:
                        fk_line = f"    - {fk.get('constrained_columns', [])} -> {fk.get('referred_table', '')}.{fk.get('referred_columns', [])}"
                        schema_lines.append(fk_line)
        
        # Add views
        views = schema.get('views', [])
        if views:
            schema_lines.append("\nViews:")
            for view in views:
                schema_lines.append(f"  - {view}")
        
        return "\n".join(schema_lines)
    
    def _format_results_for_prompt(self, query_result: Any) -> str:
        """Format query results for inclusion in prompts.
        
        Args:
            query_result: Results from query execution
            
        Returns:
            Formatted results string
        """
        if not query_result:
            return "No results returned."
        
        try:
            # Handle different result types
            if isinstance(query_result, list):
                if len(query_result) == 0:
                    return "No results returned."
                elif len(query_result) == 1:
                    return f"1 result: {json.dumps(query_result[0], default=str, indent=2)}"
                else:
                    # Show first few results
                    sample_size = min(5, len(query_result))
                    sample_results = query_result[:sample_size]
                    results_text = f"{len(query_result)} results (showing first {sample_size}):\n"
                    for i, result in enumerate(sample_results, 1):
                        results_text += f"{i}. {json.dumps(result, default=str)}\n"
                    return results_text
            elif isinstance(query_result, dict):
                return f"Result: {json.dumps(query_result, default=str, indent=2)}"
            elif isinstance(query_result, (int, float)):
                return f"Result: {query_result}"
            else:
                return str(query_result)
                
        except Exception as e:
            return f"Error formatting results: {str(e)}"
    
    def build_schema_explanation_prompt(self, schema: Dict[str, Any]) -> str:
        """Build prompt for explaining database schema.
        
        Args:
            schema: Database schema information
            
        Returns:
            Formatted prompt string
        """
        schema_text = self._format_schema_for_prompt(schema)
        
        prompt = f"""
You are a database expert. Please explain the following database schema in a clear, user-friendly way.

Database Schema:
{schema_text}

Provide a summary that includes:
1. What type of database this is
2. What tables are available and their purpose
3. Key relationships between tables
4. Any important constraints or features

Keep the explanation accessible to non-technical users.
"""
        
        return prompt
    
    def build_query_explanation_prompt(self, sql_query: str, schema: Dict[str, Any]) -> str:
        """Build prompt for explaining SQL queries.
        
        Args:
            sql_query: SQL query to explain
            schema: Database schema information
            
        Returns:
            Formatted prompt string
        """
        schema_text = self._format_schema_for_prompt(schema)
        
        prompt = f"""
You are a database expert. Please explain the following SQL query in plain English.

Database Schema:
{schema_text}

SQL Query:
{sql_query}

Provide a clear explanation that includes:
1. What the query is trying to accomplish
2. Which tables it's accessing
3. What conditions or filters it's applying
4. What the expected output would be

Keep the explanation accessible to non-technical users.
"""
        
        return prompt
    
    def build_query_optimization_prompt(self, sql_query: str, schema: Dict[str, Any]) -> str:
        """Build prompt for SQL query optimization suggestions.
        
        Args:
            sql_query: SQL query to optimize
            schema: Database schema information
            
        Returns:
            Formatted prompt string
        """
        schema_text = self._format_schema_for_prompt(schema)
        
        prompt = f"""
You are a database performance expert. Please analyze the following SQL query and suggest optimizations.

Database Schema:
{schema_text}

SQL Query:
{sql_query}

Provide optimization suggestions including:
1. Index recommendations
2. Query structure improvements
3. Potential performance issues
4. Alternative approaches if applicable

Focus on practical, actionable suggestions.
"""
        
        return prompt
    
    def build_error_explanation_prompt(self, error_message: str, sql_query: str) -> str:
        """Build prompt for explaining SQL errors.
        
        Args:
            error_message: Error message from database
            sql_query: SQL query that caused the error
            
        Returns:
            Formatted prompt string
        """
        prompt = f"""
You are a database expert. Please explain the following SQL error in plain English and suggest how to fix it.

SQL Query:
{sql_query}

Error Message:
{error_message}

Provide:
1. What the error means in simple terms
2. What likely caused the error
3. How to fix the query
4. General tips to avoid similar errors

Keep the explanation accessible to non-technical users.
"""
        
        return prompt
    
    def get_few_shot_examples(self, query_type: str = "general") -> List[Dict[str, str]]:
        """Get few-shot examples for different query types.
        
        Args:
            query_type: Type of query examples to retrieve
            
        Returns:
            List of example dictionaries with 'input' and 'output' keys
        """
        examples = {
            "general": [
                {
                    "input": "Show me all customers",
                    "output": "SELECT * FROM customers;"
                },
                {
                    "input": "Find customers in New York",
                    "output": "SELECT * FROM customers WHERE city = 'New York';"
                },
                {
                    "input": "How many orders do we have?",
                    "output": "SELECT COUNT(*) FROM orders;"
                }
            ],
            "aggregation": [
                {
                    "input": "What's the average order value?",
                    "output": "SELECT AVG(total_amount) FROM orders;"
                },
                {
                    "input": "Show me sales by month",
                    "output": "SELECT DATE_TRUNC('month', order_date) as month, SUM(total_amount) FROM orders GROUP BY month ORDER BY month;"
                }
            ],
            "joins": [
                {
                    "input": "Show customers and their orders",
                    "output": "SELECT c.name, o.order_date, o.total_amount FROM customers c JOIN orders o ON c.id = o.customer_id;"
                },
                {
                    "input": "Find customers who haven't placed any orders",
                    "output": "SELECT c.* FROM customers c LEFT JOIN orders o ON c.id = o.customer_id WHERE o.customer_id IS NULL;"
                }
            ]
        }
        
        return examples.get(query_type, examples["general"]) 