"""
Runpod client for external LLM and embedding services.
This will connect to your Runpod containers once they're set up.
"""

import os
import requests
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class RunpodLLMClient:
    """Client for Runpod LLM service (vLLM with OpenAI API compatibility)."""
    
    def __init__(self):
        self.endpoint = os.getenv('LLM_ENDPOINT')
        self.api_key = os.getenv('RUNPOD_LLM_KEY', 'not-needed')
        self.model_name = os.getenv('MODEL_NAME', 'llama-3.2-3b-instruct')
        
    def generate_sql(self, prompt: str, max_tokens: int = 200, temperature: float = 0.1) -> str:
        """Generate SQL query from natural language prompt."""
        
        # For now, return mock response until Runpod is set up
        if not self.endpoint or self.endpoint == "your_runpod_endpoint_here":
            logger.info("Using mock response - Runpod endpoint not configured yet")
            return self._mock_sql_response(prompt)
        
        try:
            # This will be the real API call to your Runpod vLLM service
            response = requests.post(
                f"{self.endpoint}/v1/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stop": ["```", "\n\n"]
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["text"].strip()
            else:
                logger.error(f"Runpod LLM API error: {response.status_code} - {response.text}")
                return self._mock_sql_response(prompt)
                
        except Exception as e:
            logger.error(f"Failed to call Runpod LLM service: {e}")
            return self._mock_sql_response(prompt)
    
    def _mock_sql_response(self, prompt: str) -> str:
        """Return mock SQL responses based on common queries."""
        prompt_lower = prompt.lower()
        
        if "customer" in prompt_lower and "total" in prompt_lower:
            return "SELECT c.customerName, SUM(od.quantityOrdered * od.priceEach) as total_revenue FROM customers c JOIN orders o ON c.customerNumber = o.customerNumber JOIN orderdetails od ON o.orderNumber = od.orderNumber GROUP BY c.customerNumber, c.customerName ORDER BY total_revenue DESC;"
        
        elif "product" in prompt_lower and ("popular" in prompt_lower or "selling" in prompt_lower):
            return "SELECT p.productName, SUM(od.quantityOrdered) as total_sold FROM products p JOIN orderdetails od ON p.productCode = od.productCode GROUP BY p.productCode, p.productName ORDER BY total_sold DESC LIMIT 10;"
        
        elif "employee" in prompt_lower and ("performance" in prompt_lower or "sales" in prompt_lower):
            return "SELECT e.firstName, e.lastName, COUNT(DISTINCT o.orderNumber) as orders_managed FROM employees e JOIN customers c ON e.employeeNumber = c.salesRepEmployeeNumber JOIN orders o ON c.customerNumber = o.customerNumber GROUP BY e.employeeNumber, e.firstName, e.lastName ORDER BY orders_managed DESC;"
        
        elif "order" in prompt_lower and "month" in prompt_lower:
            return "SELECT EXTRACT(YEAR FROM orderDate) as year, EXTRACT(MONTH FROM orderDate) as month, COUNT(*) as order_count FROM orders GROUP BY EXTRACT(YEAR FROM orderDate), EXTRACT(MONTH FROM orderDate) ORDER BY year DESC, month DESC;"
        
        elif "revenue" in prompt_lower:
            return "SELECT SUM(od.quantityOrdered * od.priceEach) as total_revenue FROM orderdetails od JOIN orders o ON od.orderNumber = o.orderNumber WHERE o.orderDate >= '2023-01-01';"
        
        else:
            return "SELECT * FROM customers LIMIT 10;"


class RunpodEmbeddingClient:
    """Client for Runpod embedding service."""
    
    def __init__(self):
        self.endpoint = os.getenv('EMBEDDING_ENDPOINT')
        self.api_key = os.getenv('RUNPOD_EMBEDDING_KEY', 'not-needed')
        
    def search_similar_examples(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Search for similar SQL examples using embeddings."""
        
        # For now, return mock examples until Runpod embedding service is set up
        if not self.endpoint or self.endpoint == "your_runpod_embedding_endpoint_here":
            logger.info("Using mock examples - Runpod embedding endpoint not configured yet")
            return self._mock_rag_examples(query)
        
        try:
            response = requests.post(
                f"{self.endpoint}/search",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "query": query,
                    "top_k": top_k,
                    "threshold": 0.6
                },
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()["results"]
            else:
                logger.error(f"Runpod embedding API error: {response.status_code}")
                return self._mock_rag_examples(query)
                
        except Exception as e:
            logger.error(f"Failed to call Runpod embedding service: {e}")
            return self._mock_rag_examples(query)
    
    def _mock_rag_examples(self, query: str) -> List[Dict[str, Any]]:
        """Return mock RAG examples."""
        return [
            {
                "query": "Show me top customers by revenue",
                "sql": "SELECT c.customerName, SUM(od.quantityOrdered * od.priceEach) as revenue FROM customers c JOIN orders o ON c.customerNumber = o.customerNumber JOIN orderdetails od ON o.orderNumber = od.orderNumber GROUP BY c.customerNumber ORDER BY revenue DESC LIMIT 10;",
                "similarity": 0.85
            },
            {
                "query": "List products with their sales",
                "sql": "SELECT p.productName, SUM(od.quantityOrdered) as units_sold FROM products p JOIN orderdetails od ON p.productCode = od.productCode GROUP BY p.productCode ORDER BY units_sold DESC;",
                "similarity": 0.72
            },
            {
                "query": "Monthly order trends",
                "sql": "SELECT EXTRACT(YEAR FROM orderDate) as year, EXTRACT(MONTH FROM orderDate) as month, COUNT(*) as orders FROM orders GROUP BY year, month ORDER BY year, month;",
                "similarity": 0.68
            }
        ]


# Compatibility with existing code
class LLMClient:
    """Wrapper to maintain compatibility with existing code."""
    
    def __init__(self):
        self.llm_client = RunpodLLMClient()
        self.embedding_client = RunpodEmbeddingClient()
    
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Runpod LLM service."""
        return self.llm_client.generate_sql(prompt, **kwargs)
    
    def search_examples(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Search for similar examples using Runpod embedding service."""
        return self.embedding_client.search_similar_examples(query, top_k) 