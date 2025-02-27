# System Patterns

## Architecture Overview

```mermaid
graph TD
    NotionAPI[Notion API Client] --> Sync[Sync Manager]
    
    Sync --> LLM[LLM Processing]
    LLM --> Chunker[Semantic Chunker]
    LLM --> Extractor[Relationship Extractor]
    
    Sync --> StoreManager[Store Manager]
    
    StoreManager --> ChromaDB[ChromaDB Store]
    StoreManager --> Memgraph[Memgraph Store]
    StoreManager --> Neo4j[Neo4j Store]
    
    Config[Configuration] --> Sync
    Config --> StoreManager
    Config --> LLM
```

## Core Components

### 1. Sync Manager (`NotionSync`)
- Central orchestrator for the sync process
- Manages document processing pipeline
- Handles content updates and hash checking
- Coordinates store updates
- Tracks sync statistics

### 2. Document Stores
```mermaid
classDiagram
    class DocumentStore {
        <<abstract>>
        +clean_document()
        +create_note()
        +create_chunks()
        +create_relationships()
        +get_documents()
        +get_chunks()
        +close()
    }
    
    class ChromaStore {
        +get_document_hash()
        +update_document()
        +get_document_metadata()
        +clear_collection()
    }
    
    class MemgraphStore {
        +create_chunk_summary()
        +_initialize_constraints()
    }
    
    class Neo4jStore {
        +initialize_indexes()
    }
    
    DocumentStore <|-- ChromaStore
    DocumentStore <|-- MemgraphStore
    DocumentStore <|-- Neo4jStore
```

### 3. LLM Integration
```mermaid
graph TD
    Provider[LLM Provider] --> RateLimiter[Rate Limiter]
    RateLimiter --> Operations[LLM Operations]
    
    Operations --> Chunking[Semantic Chunking]
    Operations --> Relationships[Relationship Extraction]
    Operations --> Embeddings[Vector Embeddings]
    
    Chunking --> Summary[Chunk Summaries]
    Relationships --> Entities[Entity Relations]
```

## Design Patterns

### 1. Strategy Pattern
- Document store implementations
- LLM provider selection
- Rate limiter configuration

### 2. Factory Pattern
- Store creation via StoreManager
- LLM provider initialization
- Configuration loading

### 3. Observer Pattern
- Sync statistics tracking
- Progress monitoring
- Error logging

### 4. Template Method Pattern
- Base document store operations
- Chunking pipeline
- Relationship extraction

## Data Flow

```mermaid
sequenceDiagram
    participant Sync as Sync Manager
    participant Notion as Notion API
    participant LLM as LLM Processor
    participant Store as Store Manager
    
    Sync->>Notion: Get Pages
    Notion-->>Sync: Page Data
    
    loop Each Page
        Sync->>LLM: Generate Chunks
        LLM-->>Sync: Semantic Chunks + Summaries
        
        Sync->>LLM: Extract Relationships
        LLM-->>Sync: Entity Relationships
        
        Sync->>Store: Clean Old Data
        Store-->>Sync: Cleanup Status
        
        Sync->>Store: Update Stores
        Store-->>Sync: Update Status
    end
```

## Key Technical Decisions

### 1. Storage Implementation
- ChromaDB for vector search and metadata
- Memgraph for graph relationships
- Neo4j as optional graph store
- Modular store selection

### 2. LLM Integration
- Multiple provider support:
  - Ollama
  - Gemini
  - Groq
- Provider-specific rate limiting:
  - Groq: 10 second delay
  - Gemini: 5 second delay
  - Ollama: No delay
- Semantic chunking:
  - Target size: 400-500 tokens
  - Valid range: 35-1200 tokens
  - Small chunk merging (<100 tokens)
  - Chunk summaries
- Relationship extraction with validation
- Vector embeddings via nomic-embed-text

### 3. Configuration Management
- YAML-based configuration
- Environment variable interpolation
- Store enablement flags
- Rate limit configuration
- Model selection

### 4. Error Handling
- Graceful degradation
- Fallback chunking
- Validation checks
- Statistics tracking
- Clean error recovery

## System Boundaries

### Internal Components
- Notion API client
- LLM processors
- Document stores
- Configuration management

### External Dependencies
- Notion API
- LLM providers
- Vector embeddings
- Database systems

## Performance Considerations

### Optimization Points
1. Incremental updates via hash checking
2. Smart chunking with fallbacks
3. Rate limit management
4. Connection handling
5. Resource cleanup

### Scalability Factors
1. Document size/count
2. Relationship complexity
3. Database performance
4. Network latency
5. Memory usage

### Critical Paths
1. Document Processing
   - Chunk generation
   - Summary creation
   - Relationship extraction
   - Vector embeddings

2. Storage Operations
   - Data cleanup
   - Content updates
   - Relationship creation
   - Metadata management

3. Error Recovery
   - Validation checks
   - Fallback strategies
   - Resource cleanup
   - State management
