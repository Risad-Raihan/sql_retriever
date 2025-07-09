# 🚀 MongoDB Retriever System - Cloud Deployment Report

**Simple Cost Analysis & Architecture Overview**

---

## 📋 System Overview

This is an **AI-powered document retrieval system** with:

- **🎯 3-Tier RAG (Retrieval-Augmented Generation)**
- **🤖 Llama 3.2-3B-Instruct Language Model** 
- **📊 MongoDB Database**
- **⚡ ChromaDB + FAISS Vector Search**

---

## 🏗️ System Architecture

```mermaid
graph TB
    subgraph "Input Processing"
        Q[Natural Language Question]
        EMB[Embedding Model<br/>all-MiniLM-L6-v2<br/>Text → 384D Vector]
    end
    
    subgraph "3-Tier RAG System"
        T1[Tier 1: High Confidence RAG<br/>Similarity > 0.6<br/>Use Best Examples]
        T2[Tier 2: Relaxed RAG<br/>Similarity > 0.3<br/>Use Context]
        T3[Tier 3: Pure LLM<br/>No Examples<br/>Pure Generation]
        FALLBACK[Fallback<br/>Best Available Example]
    end
    
    subgraph "Vector Database Operations"
        CHROMA[ChromaDB<br/>Vector Storage<br/>Persistent Collection]
        FAISS[FAISS Index<br/>Fast Similarity Search<br/>IndexFlatIP]
        SEARCH[Vector Search<br/>Cosine Similarity<br/>Top-K Retrieval]
    end
    
    subgraph "Knowledge Base"
        EXAMPLES[SQL Examples<br/>Question + Query + Context<br/>32+ Examples]
        EMBEDDINGS[Stored Embeddings<br/>384-dimensional Vectors<br/>Semantic Representations]
    end
    
    subgraph "LLM Processing"
        LLM[Llama 3.2-3B-Instruct<br/>GPU Accelerated<br/>Context + Examples → SQL]
        PROMPT[Prompt Engineering<br/>CRM Schema + Examples<br/>SQLite Syntax Rules]
        VALIDATION[SQL Validation<br/>Auto-correction<br/>Syntax Fixing]
    end
    
    subgraph "Data Storage"
        MONGO[(MongoDB<br/>Document Storage<br/>Conversations & Results)]
        LEARNING[Continuous Learning<br/>Successful Interactions<br/>Knowledge Base Growth]
    end
    
    %% Processing Flow
    Q --> EMB
    EMB --> SEARCH
    SEARCH --> CHROMA
    CHROMA --> FAISS
    FAISS --> EMBEDDINGS
    
    %% RAG Decision Flow
    SEARCH --> T1
    SEARCH --> T2
    SEARCH --> T3
    T1 --> FALLBACK
    T2 --> FALLBACK
    T3 --> FALLBACK
    
    %% Knowledge Retrieval
    EXAMPLES --> EMBEDDINGS
    EMBEDDINGS --> T1
    EMBEDDINGS --> T2
    
    %% LLM Generation
    T1 --> PROMPT
    T2 --> PROMPT
    T3 --> PROMPT
    PROMPT --> LLM
    LLM --> VALIDATION
    
    %% Storage & Learning
    VALIDATION --> MONGO
    MONGO --> LEARNING
    LEARNING --> EXAMPLES
    
    %% Styling
    style LLM fill:#f3e5f5
    style T1 fill:#e8f5e8
    style T2 fill:#fff3e0
    style T3 fill:#fce4ec
    style CHROMA fill:#e1f5fe
    style FAISS fill:#f0f4f8
    style MONGO fill:#e1f5fe
```

---

## 🔄 How It Works

### **Step 1: Question Processing**
```
User Question → Embedding Model → Vector Representation
```

### **Step 2: 3-Tier RAG System**
```
Tier 1: High Confidence Match (>60% similarity)
    └── Use existing examples + LLM

Tier 2: Medium Confidence (>30% similarity)  
    └── Use context + LLM

Tier 3: Pure LLM Generation
    └── No examples needed
```

### **Step 3: Response Generation**
```
Vector Search → Similar Examples → LLM Processing → Final Answer
```

### **Data Flow:**
1. **User asks question** in natural language
2. **System converts** question to vector embedding
3. **ChromaDB searches** for similar previous questions
4. **FAISS provides** fast similarity matching
5. **Llama model generates** response using retrieved context
6. **MongoDB stores** conversation history and results

---

## 💰 AWS Hosting Costs (Cheapest Options)

### **Monthly Costs Breakdown**

| Component | AWS Service | Instance Type | Monthly Cost |
|-----------|-------------|---------------|--------------|
| **API Server** | EC2 | t3.small | $15 |
| **LLM Processing** | EC2 GPU | g4dn.large | $85 |



---

## 🚀 Simple Deployment

### **What You Need:**
- 1x EC2 instance for API (t3.small)
- 1x EC2 GPU instance for LLM (g4dn.large) 
- 1x DocumentDB cluster (t3.medium)
- S3 bucket for vector storage



---

## 📊 Resource Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| **RAM** | 8GB | 16GB |
| **GPU** | 16GB VRAM | 24GB VRAM |
| **Storage** | 50GB | 100GB |
| **CPU** | 2 cores | 4 cores |

---



*Simple Report - No Migration Required*  
*Ready to Deploy on AWS* 