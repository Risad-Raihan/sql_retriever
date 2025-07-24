"""
Embedding Service for Runpod CPU Pod
Extracted from rag_client.py - handles embedding and semantic search only.
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

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
RAG_VECTOR_STORE_PATH = os.getenv("RAG_DATA_PATH", "/app/rag_data")
RAG_SIMILARITY_THRESHOLD = 0.6
RAG_RELAXED_THRESHOLD = 0.3
RAG_MAX_EXAMPLES = 3

# Request/Response models
class EmbedRequest(BaseModel):
    text: str

class EmbedResponse(BaseModel):
    embedding: List[float]
    processing_time: float

class SearchRequest(BaseModel):
    question: str
    k: int = 3
    use_relaxed_threshold: bool = False

class SQLExample(BaseModel):
    question: str
    sql_query: str
    explanation: str
    category: str
    difficulty: str = "medium"
    tables_used: List[str] = []
    similarity: float = 0.0

class SearchResponse(BaseModel):
    examples: List[SQLExample]
    processing_time: float
    method_used: str

@dataclass
class SQLExampleInternal:
    """Internal SQL example structure matching original rag_client.py"""
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

class EmbeddingVectorStore:
    """Embedding and search functionality extracted from RAGVectorStore"""
    
    def __init__(self, persist_directory: str = RAG_VECTOR_STORE_PATH):
        self.persist_directory = persist_directory
        self.embedding_model = None
        self.chroma_client = None
        self.collection = None
        self.faiss_index = None
        self.examples: List[SQLExampleInternal] = []
        
        self._initialize_vector_store()
        self._load_default_examples()
    
    def _initialize_vector_store(self):
        """Initialize ChromaDB, FAISS, and embedding model."""
        try:
            # Initialize embedding model
            logger.info("Loading sentence transformer model...")
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("✅ Sentence transformer loaded")
            
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
                logger.info("✅ Loaded existing ChromaDB collection")
            except:
                self.collection = self.chroma_client.create_collection(
                    name="crm_sql_examples",
                    metadata={"description": "CRM SQL examples for RAG"}
                )
                logger.info("✅ Created new ChromaDB collection")
            
            # Initialize FAISS index (384 dimensions for all-MiniLM-L6-v2)
            self.faiss_index = faiss.IndexFlatIP(384)
            
            logger.info("✅ Vector store initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize vector store: {e}")
            raise
    
    def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for given text."""
        if not self.embedding_model:
            raise Exception("Embedding model not initialized")
        
        return self.embedding_model.encode([text])[0]
    
    def search_similar_examples(self, question: str, k: int = RAG_MAX_EXAMPLES, 
                               use_relaxed_threshold: bool = False) -> List[Tuple[SQLExampleInternal, float]]:
        """Search for similar examples using semantic similarity."""
        try:
            # Generate query embedding
            query_embedding = self.generate_embedding(question)
            
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
                    
                    example = SQLExampleInternal(
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
    
    def _load_default_examples(self):
        """Load default CRM SQL examples if collection is empty."""
        if self.collection.count() == 0:
            # Load default examples (abbreviated list for space)
            default_examples = [
                SQLExampleInternal(
                    question="Show me all customers",
                    sql_query="SELECT customerNumber, customerName, city, country FROM customers ORDER BY customerName;",
                    explanation="Retrieves all customers with basic information",
                    category="basic_select",
                    difficulty="easy",
                    tables_used=["customers"]
                ),
                SQLExampleInternal(
                    question="Find customers from USA",
                    sql_query="SELECT customerNumber, customerName, city, state FROM customers WHERE country = 'USA' ORDER BY state, city;",
                    explanation="Filters customers by country",
                    category="filtering",
                    difficulty="easy",
                    tables_used=["customers"]
                ),
                SQLExampleInternal(
                    question="Count number of customers",
                    sql_query="SELECT COUNT(*) as total_customers FROM customers;",
                    explanation="Counts total number of customers",
                    category="counting",
                    difficulty="easy",
                    tables_used=["customers"]
                ),
                SQLExampleInternal(
                    question="Total value of all payments",
                    sql_query="SELECT SUM(amount) as total_payments FROM payments;",
                    explanation="Sums all payment amounts",
                    category="sum",
                    difficulty="easy",
                    tables_used=["payments"]
                ),
                SQLExampleInternal(
                    question="Top 5 customers by total order value",
                    sql_query="SELECT c.customerNumber, c.customerName, SUM(od.quantityOrdered * od.priceEach) as totalOrderValue FROM customers c JOIN orders o ON c.customerNumber = o.customerNumber JOIN orderdetails od ON o.orderNumber = od.orderNumber GROUP BY c.customerNumber, c.customerName ORDER BY totalOrderValue DESC LIMIT 5;",
                    explanation="Complex join with aggregation to find top customers",
                    category="complex_aggregation",
                    difficulty="hard",
                    tables_used=["customers", "orders", "orderdetails"]
                )
            ]
            
            # Add examples to vector store
            for example in default_examples:
                self._add_example_to_store(example)
            
            logger.info(f"✅ Added {len(default_examples)} default CRM examples")
        else:
            # Load existing examples
            self._load_existing_examples()
            logger.info(f"✅ Loaded {len(self.examples)} existing examples")
    
    def _add_example_to_store(self, example: SQLExampleInternal):
        """Add example to ChromaDB and local storage."""
        try:
            # Generate embedding
            embedding = self.generate_embedding(example.question)
            
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
            
            # Add to local examples list
            self.examples.append(example)
            
        except Exception as e:
            logger.error(f"Failed to add example: {e}")
    
    def _load_existing_examples(self):
        """Load existing examples from ChromaDB."""
        try:
            results = self.collection.get(include=['metadatas', 'documents'])
            
            for i, metadata in enumerate(results['metadatas']):
                # Convert string back to list for tables_used
                tables_used = metadata.get('tables_used', [])
                if isinstance(tables_used, str):
                    tables_used = tables_used.split(',') if tables_used else []
                
                example = SQLExampleInternal(
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

# Initialize FastAPI app
app = FastAPI(
    title="SQL Retriever Embedding Service",
    description="Embedding and semantic search service for SQL retrieval",
    version="1.0.0"
)

# Global vector store
vector_store = None

@app.on_event("startup")
async def startup_event():
    """Initialize the embedding service on startup."""
    global vector_store
    try:
        logger.info("🚀 Starting Embedding Service...")
        vector_store = EmbeddingVectorStore()
        logger.info("✅ Embedding Service ready!")
    except Exception as e:
        logger.error(f"❌ Failed to initialize embedding service: {e}")
        raise

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        if vector_store and vector_store.embedding_model:
            return {"status": "healthy", "service": "embedding", "examples_count": len(vector_store.examples)}
        else:
            return {"status": "unhealthy", "service": "embedding", "error": "Service not initialized"}
    except Exception as e:
        return {"status": "unhealthy", "service": "embedding", "error": str(e)}

@app.post("/embed", response_model=EmbedResponse)
async def generate_embedding(request: EmbedRequest):
    """Generate embedding for given text."""
    if not vector_store:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    start_time = time.time()
    
    try:
        embedding = vector_store.generate_embedding(request.text)
        
        return EmbedResponse(
            embedding=embedding.tolist(),
            processing_time=time.time() - start_time
        )
        
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Embedding failed: {str(e)}")

@app.post("/search", response_model=SearchResponse)
async def search_examples(request: SearchRequest):
    """Search for similar SQL examples."""
    if not vector_store:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    start_time = time.time()
    
    try:
        # Search for similar examples
        similar_examples = vector_store.search_similar_examples(
            request.question, 
            k=request.k, 
            use_relaxed_threshold=request.use_relaxed_threshold
        )
        
        # Convert to response format
        examples = []
        method_used = "standard_search" if not request.use_relaxed_threshold else "relaxed_search"
        
        for example_internal, similarity in similar_examples:
            example = SQLExample(
                question=example_internal.question,
                sql_query=example_internal.sql_query,
                explanation=example_internal.explanation,
                category=example_internal.category,
                difficulty=example_internal.difficulty,
                tables_used=example_internal.tables_used,
                similarity=similarity
            )
            examples.append(example)
        
        return SearchResponse(
            examples=examples,
            processing_time=time.time() - start_time,
            method_used=method_used
        )
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "SQL Retriever Embedding Service",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "embed": "/embed",
            "search": "/search"
        }
    }

if __name__ == "__main__":
    uvicorn.run(
        "embedding_service:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    ) 