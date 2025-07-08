"""VLLM client for Llama-3B model integration."""

import requests
import json
from typing import Optional, Dict, Any
from utils.logger import get_logger

logger = get_logger(__name__)
# Add transformers import for CPU inference
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

class VLLMClient:
    """Client for interacting with VLLM server or direct transformers inference."""
    
    def __init__(self, endpoint: str = "http://localhost:8000", model_name: str = "meta-llama/Llama-3.2-3B-Instruct"):
        self.endpoint = endpoint
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self.use_local = False
        
        # Try VLLM server first, fallback to local transformers
        if not self._test_connection():
            logger.info("VLLM server not available, using local transformers with CPU")
            self._load_local_model()
    
    def _test_connection(self) -> bool:
        """Test if VLLM server is available."""
        try:
            response = requests.get(f"{self.endpoint}/health", timeout=5)
            if response.status_code == 200:
                logger.info("VLLM server is available")
                return True
        except Exception as e:
            logger.info(f"VLLM server not available: {e}")
        return False
    
    def _load_local_model(self):
        """Load model locally using transformers for CPU inference."""
        try:
            logger.info(f"Loading {self.model_name} locally for CPU inference...")
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            
            # Load model for CPU with aggressive memory optimizations
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16,  # Use float16 to save ~50% memory
                low_cpu_mem_usage=True,     # Load weights incrementally
                trust_remote_code=False,
                device_map="auto",          # Automatically distribute across CPU/GPU
                max_memory={0: "2GB", "cpu": "10GB"},  # Limit GPU to 2GB, CPU to 10GB
                offload_folder="./model_offload"  # Offload to disk if needed
            )
            
            self.use_local = True
            logger.info("Local model loaded successfully!")
            
        except Exception as e:
            logger.error(f"Failed to load local model: {e}")
            raise
    
    def generate_sql(self, prompt: str, max_tokens: int = 150) -> str:
        """Generate SQL using either VLLM server or local model."""
        try:
            if self.use_local:
                return self._generate_local(prompt, max_tokens)
            else:
                return self._generate_vllm(prompt, max_tokens)
        except Exception as e:
            logger.error(f"SQL generation error: {e}")
            raise
    
    def _generate_local(self, prompt: str, max_tokens: int = 150) -> str:
        """Generate using local transformers model."""
        try:
            # Tokenize input and move to same device as model
            inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
            
            # Move inputs to the same device as model
            device = next(self.model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            # Generate with better parameters for SQL
            with torch.no_grad():
                outputs = self.model.generate(
                    inputs["input_ids"],
                    attention_mask=inputs["attention_mask"],
                    max_new_tokens=max_tokens,
                    temperature=0.3,  # Slightly higher for more creativity
                    do_sample=True,
                    top_p=0.9,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                    tokenizer=self.tokenizer,  # Pass tokenizer for stop_strings
                    stop_strings=["```", "\n\n", ";"]  # Stop at SQL end markers
                )
            
            # Decode response
            generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Extract only the new generated part
            response = generated_text[len(prompt):].strip()
            
            # Debug: Log the raw response
            logger.info(f"Raw model response: {repr(response)}")
            
            # Clean up the SQL response
            cleaned_response = self._clean_sql_response(response)
            
            logger.info(f"Cleaned SQL response: {repr(cleaned_response)}")
            logger.info("Local SQL generation successful")
            return cleaned_response
            
        except Exception as e:
            logger.error(f"Local generation error: {e}")
            raise
    
    def _clean_sql_response(self, response: str) -> str:
        """Clean up the generated SQL response."""
        try:
            import re
            
            # Remove common prefixes
            response = response.strip()
            prefixes_to_remove = [
                "Here's the SQL query:",
                "SQL:",
                "Query:",
                "The SQL query is:",
                "Answer:",
                "Result:",
            ]
            
            for prefix in prefixes_to_remove:
                if response.lower().startswith(prefix.lower()):
                    response = response[len(prefix):].strip()
            
            # Extract SQL content from code blocks
            sql_blocks = re.findall(r'```(?:sql)?\s*(.*?)\s*```', response, re.DOTALL)
            if sql_blocks:
                # Combine all SQL blocks and clean
                combined_sql = ' '.join(sql_blocks).strip()
                if combined_sql and any(keyword in combined_sql.upper() for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
                    return combined_sql
            
            # If no code blocks, look for SQL patterns
            sql_patterns = [
                r'(SELECT\s+.*?)(?:\s*;|\s*$)',
                r'(INSERT\s+.*?)(?:\s*;|\s*$)',
                r'(UPDATE\s+.*?)(?:\s*;|\s*$)',
                r'(DELETE\s+.*?)(?:\s*;|\s*$)'
            ]
            
            for pattern in sql_patterns:
                match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
                if match:
                    sql = match.group(1).strip()
                    # Clean up the SQL
                    sql = re.sub(r'\s+', ' ', sql)  # Normalize whitespace
                    return sql
            
            # Fallback: if response is empty or doesn't contain SQL, generate a basic query
            if not response.strip() or not any(keyword in response.upper() for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
                logger.warning("Empty or invalid SQL response, generating fallback query")
                return "SELECT name FROM Artist LIMIT 10"
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"SQL cleaning error: {e}")
            # Return a safe fallback query
            return "SELECT name FROM Artist LIMIT 10"
    
    def _generate_vllm(self, prompt: str, max_tokens: int = 150) -> str:
        """Generate using VLLM server."""
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": 0.1,
                "top_p": 0.9,
                "stop": ["\n\n", "```"]
            }
            
            response = requests.post(
                f"{self.endpoint}/v1/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                generated_text = result["choices"][0]["text"].strip()
                logger.info("VLLM SQL generation successful")
                return generated_text
            else:
                raise Exception(f"VLLM request failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"VLLM request error: {e}")
            raise
    
    def generate_response(self, query_result, original_question: str, sql_query: str) -> str:
        """Generate natural language response from query results."""
        try:
            # Simple response generation for now
            if isinstance(query_result, list) and len(query_result) > 0:
                count = len(query_result)
                if count == 1:
                    return f"I found 1 result for your query about {original_question.lower()}."
                else:
                    return f"I found {count} results for your query about {original_question.lower()}."
            else:
                return f"No results found for your query about {original_question.lower()}."
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return "Query completed successfully."
    
    def close(self):
        """Close the client and free resources."""
        try:
            if hasattr(self, 'model') and self.model is not None:
                # Clear model from memory
                del self.model
                del self.tokenizer
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                logger.info("Model resources cleaned up")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")