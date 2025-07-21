"""
RAG (Retrieval-Augmented Generation) Client for CRM Database
Provides semantic search and SQL generation with example retrieval.
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

import numpy as np
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import faiss
from sklearn.metrics.pairwise import cosine_similarity

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

from config import (
    RAG_VECTOR_STORE_PATH, RAG_SIMILARITY_THRESHOLD, RAG_RELAXED_THRESHOLD, RAG_MAX_EXAMPLES,
    MODEL_NAME, MODEL_TEMPERATURE, MAX_TOKENS, CRM_BUSINESS_CONTEXT
)

logger = logging.getLogger(__name__)

@dataclass
class SQLExample:
    """Structured SQL example for CRM database."""
    question: str
    sql_query: str
    explanation: str
    category: str
    difficulty: str = "medium"
    tables_used: Optional[List[str]] = None
    created_at: Optional[str] = None
    usage_count: int = 0
    success_rate: float = 1.0
    
    def __post_init__(self):
        if self.tables_used is None:
            self.tables_used = []
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

class RAGVectorStore:
    """Vector store for SQL examples using ChromaDB and FAISS."""
    
    def __init__(self, persist_directory: str = RAG_VECTOR_STORE_PATH):
        self.persist_directory = persist_directory
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.chroma_client = None
        self.collection = None
        self.faiss_index = None
        self.examples: List[SQLExample] = []
        
        self._initialize_vector_store()
        self._load_default_examples()
    
    def _initialize_vector_store(self):
        """Initialize ChromaDB and FAISS index."""
        try:
            os.makedirs(self.persist_directory, exist_ok=True)
            
            # Initialize ChromaDB
            self.chroma_client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Get or create collection
            try:
                self.collection = self.chroma_client.get_collection("crm_sql_examples")
                logger.info("Loaded existing ChromaDB collection")
            except:
                self.collection = self.chroma_client.create_collection(
                    name="crm_sql_examples",
                    metadata={"description": "CRM SQL examples for RAG"}
                )
                logger.info("Created new ChromaDB collection")
            
            # Initialize FAISS index (384 dimensions for all-MiniLM-L6-v2)
            self.faiss_index = faiss.IndexFlatIP(384)
            
            logger.info("Vector store initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            raise
    
    def _load_default_examples(self):
        """Load default CRM SQL examples."""
        default_examples = [
            # Basic SELECT operations
            SQLExample(
                question="Show me all customers",
                sql_query="SELECT customerNumber, customerName, city, country FROM customers ORDER BY customerName;",
                explanation="Retrieves all customers with basic information",
                category="basic_select",
                difficulty="easy",
                tables_used=["customers"]
            ),
            SQLExample(
                question="Find customers from USA",
                sql_query="SELECT customerNumber, customerName, city, state FROM customers WHERE country = 'USA' ORDER BY state, city;",
                explanation="Filters customers by country",
                category="filtering",
                difficulty="easy",
                tables_used=["customers"]
            ),
            SQLExample(
                question="List all products with their prices",
                sql_query="SELECT productCode, productName, buyPrice, MSRP, quantityInStock FROM products ORDER BY productName;",
                explanation="Shows product catalog with pricing information",
                category="basic_select",
                difficulty="easy",
                tables_used=["products"]
            ),
            
            # COUNTING operations
            SQLExample(
                question="Count number of customers",
                sql_query="SELECT COUNT(*) as total_customers FROM customers;",
                explanation="Counts total number of customers",
                category="counting",
                difficulty="easy",
                tables_used=["customers"]
            ),
            SQLExample(
                question="How many products are there",
                sql_query="SELECT COUNT(*) as total_products FROM products;",
                explanation="Counts total number of products",
                category="counting",
                difficulty="easy",
                tables_used=["products"]
            ),
            SQLExample(
                question="Count orders per customer",
                sql_query="SELECT c.customerName, COUNT(o.orderNumber) as order_count FROM customers c LEFT JOIN orders o ON c.customerNumber = o.customerNumber GROUP BY c.customerNumber, c.customerName ORDER BY order_count DESC;",
                explanation="Counts orders for each customer",
                category="counting_grouped",
                difficulty="medium",
                tables_used=["customers", "orders"]
            ),
            SQLExample(
                question="How many unique countries are there in customers",
                sql_query="SELECT COUNT(DISTINCT country) as unique_countries FROM customers;",
                explanation="Counts distinct countries",
                category="counting",
                difficulty="easy",
                tables_used=["customers"]
            ),
            
            # SUM operations
            SQLExample(
                question="Total value of all payments",
                sql_query="SELECT SUM(amount) as total_payments FROM payments;",
                explanation="Sums all payment amounts",
                category="sum",
                difficulty="easy",
                tables_used=["payments"]
            ),
            SQLExample(
                question="Sum of payments by customer",
                sql_query="SELECT c.customerName, COALESCE(SUM(p.amount), 0) as total_payments FROM customers c LEFT JOIN payments p ON c.customerNumber = p.customerNumber GROUP BY c.customerNumber, c.customerName ORDER BY total_payments DESC;",
                explanation="Sums payments for each customer",
                category="sum_grouped",
                difficulty="medium",
                tables_used=["customers", "payments"]
            ),
            SQLExample(
                question="Total order value",
                sql_query="SELECT SUM(od.quantityOrdered * od.priceEach) as total_order_value FROM orderdetails od;",
                explanation="Calculates total value of all orders",
                category="sum",
                difficulty="medium",
                tables_used=["orderdetails"]
            ),
            
            # AVERAGE operations
            SQLExample(
                question="Average product price",
                sql_query="SELECT AVG(MSRP) as average_price FROM products;",
                explanation="Calculates average product price",
                category="average",
                difficulty="easy",
                tables_used=["products"]
            ),
            SQLExample(
                question="Average payment amount",
                sql_query="SELECT AVG(amount) as average_payment FROM payments;",
                explanation="Calculates average payment amount",
                category="average",
                difficulty="easy",
                tables_used=["payments"]
            ),
            SQLExample(
                question="Average order value per customer",
                sql_query="SELECT c.customerName, AVG(od.quantityOrdered * od.priceEach) as avg_order_value FROM customers c JOIN orders o ON c.customerNumber = o.customerNumber JOIN orderdetails od ON o.orderNumber = od.orderNumber GROUP BY c.customerNumber, c.customerName ORDER BY avg_order_value DESC;",
                explanation="Calculates average order value for each customer",
                category="average_grouped",
                difficulty="hard",
                tables_used=["customers", "orders", "orderdetails"]
            ),
            
            # MIN/MAX operations (highest/lowest)
            SQLExample(
                question="Find the most expensive product",
                sql_query="SELECT productCode, productName, MSRP FROM products WHERE MSRP = (SELECT MAX(MSRP) FROM products);",
                explanation="Finds product with highest price",
                category="max",
                difficulty="medium",
                tables_used=["products"]
            ),
            SQLExample(
                question="Find the cheapest product",
                sql_query="SELECT productCode, productName, MSRP FROM products WHERE MSRP = (SELECT MIN(MSRP) FROM products);",
                explanation="Finds product with lowest price",
                category="min",
                difficulty="medium",
                tables_used=["products"]
            ),
            SQLExample(
                question="Highest payment amount",
                sql_query="SELECT MAX(amount) as highest_payment FROM payments;",
                explanation="Finds the highest payment amount",
                category="max",
                difficulty="easy",
                tables_used=["payments"]
            ),
            SQLExample(
                question="Lowest payment amount",
                sql_query="SELECT MIN(amount) as lowest_payment FROM payments;",
                explanation="Finds the lowest payment amount",
                category="min",
                difficulty="easy",
                tables_used=["payments"]
            ),
            SQLExample(
                question="Customer with highest total payments",
                sql_query="SELECT c.customerName, SUM(p.amount) as total_payments FROM customers c JOIN payments p ON c.customerNumber = p.customerNumber GROUP BY c.customerNumber, c.customerName ORDER BY total_payments DESC LIMIT 1;",
                explanation="Finds customer with highest total payments",
                category="max_grouped",
                difficulty="medium",
                tables_used=["customers", "payments"]
            ),
            
            # MEDIAN operations (using percentile functions)
            SQLExample(
                question="Median product price",
                sql_query="SELECT AVG(MSRP) as median_price FROM (SELECT MSRP FROM products ORDER BY MSRP LIMIT 2 - (SELECT COUNT(*) FROM products) % 2 OFFSET (SELECT (COUNT(*) - 1) / 2 FROM products));",
                explanation="Calculates median product price",
                category="median",
                difficulty="hard",
                tables_used=["products"]
            ),
            
            # JOIN operations
            SQLExample(
                question="Show employees and their managers",
                sql_query="SELECT e.employeeNumber, e.firstName, e.lastName, e.jobTitle, m.firstName as managerFirstName, m.lastName as managerLastName FROM employees e LEFT JOIN employees m ON e.reportsTo = m.employeeNumber ORDER BY e.lastName;",
                explanation="Self-join to show employee hierarchy",
                category="joins",
                difficulty="medium",
                tables_used=["employees"]
            ),
            SQLExample(
                question="Show customers with their total payments",
                sql_query="SELECT c.customerNumber, c.customerName, COALESCE(SUM(p.amount), 0) as totalPayments FROM customers c LEFT JOIN payments p ON c.customerNumber = p.customerNumber GROUP BY c.customerNumber, c.customerName ORDER BY totalPayments DESC;",
                explanation="Aggregates payment data by customer",
                category="aggregation_joins",
                difficulty="medium",
                tables_used=["customers", "payments"]
            ),
            
            # Complex aggregations
            SQLExample(
                question="Find top 5 customers by total order value",
                sql_query="SELECT c.customerNumber, c.customerName, SUM(od.quantityOrdered * od.priceEach) as totalOrderValue FROM customers c JOIN orders o ON c.customerNumber = o.customerNumber JOIN orderdetails od ON o.orderNumber = od.orderNumber GROUP BY c.customerNumber, c.customerName ORDER BY totalOrderValue DESC LIMIT 5;",
                explanation="Complex join with aggregation to find top customers",
                category="complex_aggregation",
                difficulty="hard",
                tables_used=["customers", "orders", "orderdetails"]
            ),
            SQLExample(
                question="Show product lines with product counts",
                sql_query="SELECT pl.productLine, pl.textDescription, COUNT(p.productCode) as productCount FROM productlines pl LEFT JOIN products p ON pl.productLine = p.productLine GROUP BY pl.productLine, pl.textDescription ORDER BY productCount DESC;",
                explanation="Groups products by product line",
                category="aggregation_joins",
                difficulty="medium",
                tables_used=["productlines", "products"]
            ),
            
            # Date and filtering operations
            SQLExample(
                question="List orders from last month",
                sql_query="SELECT orderNumber, orderDate, status, customerNumber FROM orders WHERE orderDate >= date('now', '-1 month') ORDER BY orderDate DESC;",
                explanation="Filters orders by date range",
                category="date_filtering",
                difficulty="medium",
                tables_used=["orders"]
            ),
            SQLExample(
                question="Find customers who have never placed an order",
                sql_query="SELECT c.customerNumber, c.customerName, c.city, c.country FROM customers c LEFT JOIN orders o ON c.customerNumber = o.customerNumber WHERE o.customerNumber IS NULL ORDER BY c.customerName;",
                explanation="Uses LEFT JOIN to find customers without orders",
                category="joins",
                difficulty="medium",
                tables_used=["customers", "orders"]
            ),
            SQLExample(
                question="Show office locations with employee counts",
                sql_query="SELECT o.officeCode, o.city, o.country, COUNT(e.employeeNumber) as employeeCount FROM offices o LEFT JOIN employees e ON o.officeCode = e.officeCode GROUP BY o.officeCode, o.city, o.country ORDER BY employeeCount DESC;",
                explanation="Aggregates employee data by office",
                category="aggregation_joins",
                difficulty="medium",
                tables_used=["offices", "employees"]
            ),
            SQLExample(
                question="Find products with low stock",
                sql_query="SELECT productCode, productName, quantityInStock, productLine FROM products WHERE quantityInStock < 100 ORDER BY quantityInStock ASC;",
                explanation="Filters products by stock level",
                category="filtering",
                difficulty="easy",
                tables_used=["products"]
            ),
            
            # SQLite-specific DATE operations with STRFTIME
            SQLExample(
                question="What's the total revenue generated this year",
                sql_query="SELECT SUM(od.quantityOrdered * od.priceEach) as total_revenue FROM orders o JOIN orderdetails od ON o.orderNumber = od.orderNumber WHERE STRFTIME('%Y', o.orderDate) = STRFTIME('%Y', 'now');",
                explanation="Calculates total revenue for current year using SQLite STRFTIME",
                category="revenue_analysis",
                difficulty="medium",
                tables_used=["orders", "orderdetails"]
            ),
            SQLExample(
                question="Monthly revenue trends",
                sql_query="SELECT STRFTIME('%Y-%m', o.orderDate) as month, SUM(od.quantityOrdered * od.priceEach) as monthly_revenue FROM orders o JOIN orderdetails od ON o.orderNumber = od.orderNumber GROUP BY STRFTIME('%Y-%m', o.orderDate) ORDER BY month;",
                explanation="Shows monthly revenue trends using SQLite date functions",
                category="time_series",
                difficulty="medium",
                tables_used=["orders", "orderdetails"]
            ),
            SQLExample(
                question="Which customer has the highest lifetime value",
                sql_query="SELECT c.customerName, SUM(od.quantityOrdered * od.priceEach) as lifetime_value FROM customers c JOIN orders o ON c.customerNumber = o.customerNumber JOIN orderdetails od ON o.orderNumber = od.orderNumber GROUP BY c.customerNumber, c.customerName ORDER BY lifetime_value DESC LIMIT 1;",
                explanation="Finds customer with highest total order value",
                category="customer_analytics",
                difficulty="hard",
                tables_used=["customers", "orders", "orderdetails"]
            ),
            SQLExample(
                question="Top 3 product lines by revenue",
                sql_query="SELECT pl.productLine, SUM(od.quantityOrdered * od.priceEach) as total_revenue FROM productlines pl JOIN products p ON pl.productLine = p.productLine JOIN orderdetails od ON p.productCode = od.productCode GROUP BY pl.productLine ORDER BY total_revenue DESC LIMIT 3;",
                explanation="Shows top product lines by total revenue",
                category="product_analytics",
                difficulty="hard", 
                tables_used=["productlines", "products", "orderdetails"]
            ),
            SQLExample(
                question="Which sales rep has the most customers",
                sql_query="SELECT e.firstName, e.lastName, COUNT(c.customerNumber) as customer_count FROM employees e JOIN customers c ON e.employeeNumber = c.salesRepEmployeeNumber GROUP BY e.employeeNumber, e.firstName, e.lastName ORDER BY customer_count DESC LIMIT 1;",
                explanation="Finds sales representative with most customers",
                category="employee_analytics",
                difficulty="medium",
                tables_used=["employees", "customers"]
            ),
            SQLExample(
                question="Product profitability analysis",
                sql_query="SELECT p.productName, SUM(od.quantityOrdered * (od.priceEach - p.buyPrice)) as total_profit FROM products p JOIN orderdetails od ON p.productCode = od.productCode GROUP BY p.productCode, p.productName ORDER BY total_profit DESC LIMIT 10;",
                explanation="Calculates profit for each product (revenue minus cost)",
                category="profitability",
                difficulty="hard",
                tables_used=["products", "orderdetails"]
            ),
            
            # Customer distribution analysis
            SQLExample(
                question="Customer distribution by country with counts",
                sql_query="SELECT c.country, COUNT(c.customerNumber) as customer_count FROM customers c GROUP BY c.country ORDER BY customer_count DESC;",
                explanation="Shows customer distribution across countries with proper GROUP BY",
                category="customer_analytics",
                difficulty="medium",
                tables_used=["customers"]
            ),
            SQLExample(
                question="Show customer distribution by country",
                sql_query="SELECT c.country, COUNT(*) as customer_count FROM customers c GROUP BY c.country ORDER BY customer_count DESC;",
                explanation="Customer distribution across all countries",
                category="customer_analytics", 
                difficulty="medium",
                tables_used=["customers"]
            )
        ]
        
        # Add examples to vector store if collection is empty
        if self.collection.count() == 0:
            for example in default_examples:
                self.add_example(example)
            logger.info(f"Added {len(default_examples)} default CRM examples")
        else:
            # Load existing examples
            self._load_existing_examples()
            logger.info(f"Loaded {len(self.examples)} existing examples")
    
    def _load_existing_examples(self):
        """Load existing examples from ChromaDB."""
        try:
            results = self.collection.get(include=['metadatas', 'documents'])
            
            for i, metadata in enumerate(results['metadatas']):
                # Convert string back to list for tables_used
                tables_used = metadata.get('tables_used', [])
                if isinstance(tables_used, str):
                    tables_used = tables_used.split(',') if tables_used else []
                
                example = SQLExample(
                    question=metadata['question'],
                    sql_query=metadata['sql_query'],
                    explanation=metadata['explanation'],
                    category=metadata['category'],
                    difficulty=metadata.get('difficulty', 'medium'),
                    tables_used=tables_used,
                    created_at=metadata.get('created_at'),
                    usage_count=metadata.get('usage_count', 0),
                    success_rate=metadata.get('success_rate', 1.0)
                )
                self.examples.append(example)
                
        except Exception as e:
            logger.error(f"Failed to load existing examples: {e}")
    
    def add_example(self, example: SQLExample) -> bool:
        """Add a new SQL example to the vector store."""
        try:
            # Generate embedding
            embedding = self.embedding_model.encode([example.question])[0]
            
            # Add to ChromaDB
            example_id = f"example_{len(self.examples)}_{int(time.time())}"
            
            # Convert lists to strings for ChromaDB metadata
            metadata = asdict(example)
            if metadata.get('tables_used') and isinstance(metadata['tables_used'], list):
                metadata['tables_used'] = ','.join(metadata['tables_used'])
            else:
                metadata['tables_used'] = ""
            
            self.collection.add(
                ids=[example_id],
                embeddings=[embedding.tolist()],
                documents=[example.question],
                metadatas=[metadata]
            )
            
            # Add to FAISS index
            self.faiss_index.add(np.array([embedding], dtype=np.float32))
            
            # Add to local examples list
            self.examples.append(example)
            
            logger.info(f"Added example: {example.question}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add example: {e}")
            return False
    
    def search_similar_examples(self, question: str, k: int = RAG_MAX_EXAMPLES, 
                               use_relaxed_threshold: bool = False) -> List[Tuple[SQLExample, float]]:
        """Search for similar examples using semantic similarity."""
        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode([question])[0]
            
            # Search using ChromaDB - get more results for relaxed matching
            search_k = k * 3 if use_relaxed_threshold else k
            n_results = max(1, min(search_k, len(self.examples))) if self.examples else 0
            if n_results == 0:
                return []
                
            results = self.collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=n_results,
                include=['metadatas', 'distances']
            )
            
            # Choose threshold based on mode
            threshold = RAG_RELAXED_THRESHOLD if use_relaxed_threshold else RAG_SIMILARITY_THRESHOLD
            
            similar_examples = []
            for i, metadata in enumerate(results['metadatas'][0]):
                # Convert distance to similarity (ChromaDB uses cosine distance)
                distance = results['distances'][0][i]
                similarity = 1 - distance
                
                if similarity >= threshold:
                    # Convert string back to list for tables_used
                    tables_used = metadata.get('tables_used', [])
                    if isinstance(tables_used, str):
                        tables_used = tables_used.split(',') if tables_used else []
                    
                    example = SQLExample(
                        question=metadata['question'],
                        sql_query=metadata['sql_query'],
                        explanation=metadata['explanation'],
                        category=metadata['category'],
                        difficulty=metadata.get('difficulty', 'medium'),
                        tables_used=tables_used,
                        created_at=metadata.get('created_at'),
                        usage_count=metadata.get('usage_count', 0),
                        success_rate=metadata.get('success_rate', 1.0)
                    )
                    similar_examples.append((example, similarity))
            
            # Sort by similarity and limit results
            similar_examples.sort(key=lambda x: x[1], reverse=True)
            similar_examples = similar_examples[:k]
            
            logger.info(f"Found {len(similar_examples)} similar examples for: {question} (threshold: {threshold})")
            return similar_examples
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def update_example_stats(self, example: SQLExample, success: bool):
        """Update usage statistics for an example."""
        try:
            # Find and update the example
            for i, stored_example in enumerate(self.examples):
                if stored_example.question == example.question:
                    stored_example.usage_count += 1
                    if success:
                        stored_example.success_rate = (
                            (stored_example.success_rate * (stored_example.usage_count - 1) + 1.0) 
                            / stored_example.usage_count
                        )
                    else:
                        stored_example.success_rate = (
                            (stored_example.success_rate * (stored_example.usage_count - 1) + 0.0) 
                            / stored_example.usage_count
                        )
                    
                    # Update in ChromaDB (this is simplified - in production you'd want to update by ID)
                    logger.info(f"Updated stats for example: {example.question}")
                    break
                    
        except Exception as e:
            logger.error(f"Failed to update example stats: {e}")

class RAGSQLClient:
    """Main RAG client for SQL generation with CRM context."""
    
    def __init__(self):
        self.vector_store = RAGVectorStore()
        self.model = None
        self.tokenizer = None
        self.torch = torch if TORCH_AVAILABLE else None
        
        if TORCH_AVAILABLE:
            self._initialize_llm()
        else:
            logger.warning("PyTorch not available, falling back to example retrieval only")
    
    def _initialize_llm(self):
        """Initialize the Llama model for SQL generation."""
        try:
            logger.info(f"Loading model: {MODEL_NAME}")
            
            self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
            self.model = AutoModelForCausalLM.from_pretrained(
                MODEL_NAME,
                torch_dtype=self.torch.float16 if self.torch.cuda.is_available() else self.torch.float32,
                device_map="auto" if self.torch.cuda.is_available() else None,
                trust_remote_code=True
            )
            
            # Set pad token if not present
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            logger.info("LLM initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            self.model = None
            self.tokenizer = None
    
    def _generate_sql_with_llm(self, question: str, similar_examples: List[Tuple[SQLExample, float]], 
                              schema_info: str) -> Optional[str]:
        """Generate SQL using the LLM with RAG context."""
        if not self.model or not self.tokenizer:
            return None
        
        try:
            # Build prompt with examples
            examples_text = ""
            if similar_examples:
                examples_text = "\n\nSimilar examples:\n"
                for example, similarity in similar_examples:
                    examples_text += f"Q: {example.question}\nSQL: {example.sql_query}\n\n"
            
            prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are an expert SQLite query generator for a CRM database. Generate ONLY valid SQLite SQL queries.

🔧 CRITICAL SQLite Syntax Rules (MUST FOLLOW):
- Use STRFTIME('%Y', date_column) for year extraction, NOT EXTRACT()
- Use STRFTIME('%m', date_column) for month extraction, NOT EXTRACT()
- Use STRFTIME('%Y-%m', date_column) for year-month grouping
- Revenue calculation: orderdetails.quantityOrdered * orderdetails.priceEach

⚠️ Key Column Locations (CRITICAL):
- orderDate: In ORDERS table (not orderdetails)
- priceEach: In ORDERDETAILS table (not products)
- salesRepEmployeeNumber: In CUSTOMERS table (not orders)

📊 Common Join Patterns:
- Employee performance: employees -> customers -> orders -> orderdetails
- Revenue analysis: orders -> orderdetails
- Product analysis: products -> orderdetails

{CRM_BUSINESS_CONTEXT}

Database Schema:
{schema_info}
{examples_text}
<|eot_id|><|start_header_id|>user<|end_header_id|>

Question: {question}

Generate ONLY a valid SQLite query using proper table relationships and SQLite syntax. 
REMEMBER: Use STRFTIME() not EXTRACT(), and check column locations carefully.

<|eot_id|><|start_header_id|>assistant<|end_header_id|>

SELECT"""
            
            # Tokenize and generate
            inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048)
            
            if self.torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
            
            with self.torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=MAX_TOKENS,
                    temperature=MODEL_TEMPERATURE,
                    do_sample=True,
                    pad_token_id=self.tokenizer.eos_token_id
                )
            
            # Decode response
            response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Extract SQL from response
            sql_query = self._extract_sql_from_response(response)
            
            # Apply validation and auto-correction
            if sql_query:
                sql_query = self._validate_and_fix_sql(sql_query)
            
            return sql_query
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return None
    
    def _extract_sql_from_response(self, response: str) -> str:
        """Extract SQL query from LLM response."""
        try:
            # Find the last occurrence of SELECT (the generated part)
            select_pos = response.rfind("SELECT")
            if select_pos == -1:
                return None
            
            sql_part = "SELECT" + response[select_pos + 6:]
            
            # Clean up the SQL
            sql_lines = []
            for line in sql_part.split('\n'):
                line = line.strip()
                if line and not line.startswith('<|') and not line.startswith('Q:'):
                    sql_lines.append(line)
                elif line.startswith('<|') or line.startswith('Q:'):
                    break
            
            sql_query = ' '.join(sql_lines).strip()
            
            # Remove any trailing punctuation that's not semicolon
            sql_query = sql_query.rstrip('.,!?')
            
            # Fix common syntax errors
            # Remove extra closing parentheses
            while sql_query.count(')') > sql_query.count('('):
                sql_query = sql_query.rstrip(');').rstrip(')')
            
            # Ensure it ends with semicolon
            if sql_query and not sql_query.endswith(';'):
                sql_query += ';'
            
            return sql_query if sql_query else None
            
        except Exception as e:
            logger.error(f"Failed to extract SQL: {e}")
            return None
    
    def _validate_and_fix_sql(self, sql_query: str) -> str:
        """Validate and fix common SQLite syntax issues."""
        if not sql_query:
            return sql_query
            
        # Fix common syntax issues
        fixes = [
            # PostgreSQL/MySQL to SQLite date functions
            ("EXTRACT(MONTH FROM", "STRFTIME('%m',"),
            ("EXTRACT(YEAR FROM", "STRFTIME('%Y',"),
            ("EXTRACT(DAY FROM", "STRFTIME('%d',"),
            
            # Common column location errors
            ("orderdetails.orderDate", "orders.orderDate"),
            ("products.priceEach", "orderdetails.priceEach"),
            ("orders.salesRepEmployeeNumber", "customers.salesRepEmployeeNumber"),
            
            # Table alias corrections
            ("PS.priceEach", "od.priceEach"),
            ("T2.orderDate", "o.orderDate"),
            ("O.salesRepEmployeeNumber", "c.salesRepEmployeeNumber"),
            
            # Fix common JOIN issues
            ("JOIN Orders O ON E.employeeNumber = O.salesRepEmployeeNumber", 
             "JOIN customers c ON E.employeeNumber = c.salesRepEmployeeNumber JOIN orders o ON c.customerNumber = o.customerNumber"),
        ]
        
        for old, new in fixes:
            sql_query = sql_query.replace(old, new)
        
        # Ensure proper capitalization for SQLite
        sql_query = sql_query.replace("FROM PRODUCTS", "FROM products")
        sql_query = sql_query.replace("FROM ORDERDETAILS", "FROM orderdetails")
        sql_query = sql_query.replace("FROM ORDERS", "FROM orders")
        sql_query = sql_query.replace("FROM CUSTOMERS", "FROM customers")
        sql_query = sql_query.replace("FROM EMPLOYEES", "FROM employees")
        
        # Fix missing GROUP BY clauses
        sql_query = self._fix_missing_group_by(sql_query)
        
        logger.info(f"SQL validation applied: {sql_query}")
        return sql_query
    
    def _fix_missing_group_by(self, sql_query: str) -> str:
        """Detect and fix missing GROUP BY clauses."""
        try:
            # Convert to uppercase for analysis
            sql_upper = sql_query.upper()
            
            # Check if query has aggregate functions
            aggregate_functions = ['COUNT(', 'SUM(', 'AVG(', 'MIN(', 'MAX(']
            has_aggregates = any(func in sql_upper for func in aggregate_functions)
            
            # Check if query already has GROUP BY
            has_group_by = 'GROUP BY' in sql_upper
            
            if has_aggregates and not has_group_by:
                # Detect non-aggregate columns in SELECT clause
                # Look for patterns like "c.country" or "country" that aren't in aggregate functions
                import re
                
                # Extract SELECT clause
                select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql_query, re.IGNORECASE | re.DOTALL)
                if select_match:
                    select_clause = select_match.group(1)
                    
                    # Find non-aggregate columns
                    # Remove aggregate function calls
                    temp_select = select_clause
                    for func in aggregate_functions:
                        # Remove aggregate function calls
                        temp_select = re.sub(func.replace('(', r'\(') + r'[^)]+\)', '', temp_select, flags=re.IGNORECASE)
                    
                    # Find remaining column references
                    column_patterns = [
                        r'(\w+\.\w+)',  # table.column
                        r'(\w+)(?=\s*,|\s*$)',  # standalone column names
                    ]
                    
                    group_by_columns = []
                    for pattern in column_patterns:
                        matches = re.findall(pattern, temp_select)
                        for match in matches:
                            if match.strip() and match.upper() not in ['AS', 'FROM'] and not match.isdigit():
                                group_by_columns.append(match.strip())
                    
                    # Add GROUP BY if we found non-aggregate columns
                    if group_by_columns:
                        # Remove semicolon temporarily
                        sql_clean = sql_query.rstrip(';')
                        
                        # Add GROUP BY clause
                        group_by_clause = f" GROUP BY {', '.join(group_by_columns)}"
                        sql_query = sql_clean + group_by_clause + ";"
                        
                        logger.info(f"Added GROUP BY clause: {group_by_clause}")
            
            return sql_query
            
        except Exception as e:
            logger.error(f"Failed to fix GROUP BY: {e}")
            return sql_query
    
    def generate_sql(self, question: str, schema_info: str) -> Dict[str, Any]:
        """Generate SQL query using 3-tier RAG approach for maximum analytical capability."""
        start_time = time.time()
        
        try:
            # Tier 1: Search for high-confidence similar examples (threshold 0.6)
            similar_examples = self.vector_store.search_similar_examples(question)
            
            sql_query = None
            method_used = "none"
            confidence = 0.0
            
            # Tier 1: Try LLM generation with high-confidence examples
            if self.model and similar_examples:
                sql_query = self._generate_sql_with_llm(question, similar_examples, schema_info)
                if sql_query:
                    method_used = "llm_with_rag"
                    confidence = similar_examples[0][1]
                    logger.info(f"Tier 1 Success: Generated SQL with high-confidence examples")
            
            # Tier 2: Try LLM generation with relaxed similarity examples (threshold 0.3)
            if not sql_query and self.model:
                relaxed_examples = self.vector_store.search_similar_examples(question, use_relaxed_threshold=True)
                if relaxed_examples:
                    sql_query = self._generate_sql_with_llm(question, relaxed_examples, schema_info)
                    if sql_query:
                        method_used = "llm_with_relaxed_rag"
                        confidence = relaxed_examples[0][1]
                        logger.info(f"Tier 2 Success: Generated SQL with relaxed examples")
            
            # Tier 3: Pure LLM generation (NO examples needed - for analytical queries)
            if not sql_query and self.model:
                sql_query = self._generate_sql_with_llm(question, [], schema_info)  # Empty examples
                if sql_query:
                    method_used = "pure_llm"
                    confidence = 0.5  # Medium confidence for pure generation
                    logger.info(f"Tier 3 Success: Pure LLM generation for analytical query")
            
            # Tier 4: Fallback to best example if everything fails
            if not sql_query and similar_examples:
                best_example, similarity = similar_examples[0]
                sql_query = best_example.sql_query
                method_used = "example_retrieval"
                confidence = similarity
                
                # Update example usage stats
                self.vector_store.update_example_stats(best_example, True)
                logger.info(f"Tier 4 Fallback: Using best example")
            
            # Final check - if still no SQL, return error
            if not sql_query:
                return {
                    'sql_query': None,
                    'confidence': 0.0,
                    'similar_examples_count': 0,
                    'method_used': 'failed',
                    'processing_time': time.time() - start_time,
                    'error': 'Failed to generate SQL query with all methods'
                }
            
            return {
                'sql_query': sql_query,
                'confidence': confidence,
                'similar_examples_count': len(similar_examples),
                'method_used': method_used,
                'processing_time': time.time() - start_time,
                'similar_examples': [
                    {
                        'question': ex.question,
                        'similarity': sim,
                        'category': ex.category
                    }
                    for ex, sim in similar_examples[:3]  # Show top 3
                ]
            }
            
        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            return {
                'sql_query': None,
                'confidence': 0.0,
                'similar_examples_count': 0,
                'method_used': 'error',
                'processing_time': time.time() - start_time,
                'error': str(e)
            }
    
    def learn_from_interaction(self, question: str, sql_query: str, success: bool, 
                             explanation: str = "", category: str = "learned"):
        """Learn from successful interactions by adding new examples."""
        try:
            if success and sql_query:
                # Create new example
                new_example = SQLExample(
                    question=question,
                    sql_query=sql_query,
                    explanation=explanation or f"Learned from user interaction",
                    category=category,
                    difficulty="medium",
                    tables_used=[]  # Initialize with empty list
                )
                
                # Add to vector store
                self.vector_store.add_example(new_example)
                logger.info(f"Learned new example from interaction: {question}")
                
        except Exception as e:
            logger.error(f"Failed to learn from interaction: {e}") 