# Technical Context

## Development Environment

### Core Requirements
- Python 3.8+
- ChromaDB instance
- Memgraph instance (optional)
- Neo4j instance (optional)
- Notion API access
- LLM provider (Ollama, Gemini, or Groq)

### Virtual Environment Setup
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

## Dependencies

### Core Python Packages
- `notional-python`: Notion API client
- `chromadb`: Vector database client
- `neo4j`: Neo4j graph database driver
- `langchain`: LLM framework and abstractions
- `langchain-ollama`: Ollama integration
- `tiktoken`: Token counting library
- `pyyaml`: YAML configuration parsing
- `python-dotenv`: Environment variable management

### Database Systems

#### ChromaDB
- Purpose: Vector storage and semantic search
- Requirements:
  - Running ChromaDB instance
  - Authentication token
  - Collection name
- Features:
  - Vector storage and search
  - Document metadata storage
  - Content hash tracking
  - Chunk management

#### Memgraph
- Purpose: High-performance graph database
- Requirements:
  - Memgraph instance
  - Authentication credentials
- Features:
  - Entity relationship storage
  - Graph querying
  - Semantic relationships
  - Chunk summaries

#### Neo4j (Optional)
- Purpose: Alternative graph database
- Requirements:
  - Neo4j instance (Community or Enterprise)
  - Database credentials
  - Bolt protocol access

## Configuration Management

### Environment Variables
```bash
# Core Settings
NOTION_API_TOKEN=your_notion_token
OLLAMA_HOST=your_ollama_host

# ChromaDB Settings
CHROMA_AUTH_TOKEN=your_chroma_token
CHROMA_HOST=your_chroma_host
CHROMA_COLLECTION=notion

# Memgraph Settings
MEMGRAPH_URI=bolt://localhost:7687
MEMGRAPH_USER=your_username
MEMGRAPH_PASSWORD=your_password

# Neo4j Settings (Optional)
NEO4J_URI=your_neo4j_uri
NEO4J_USER=your_neo4j_user
NEO4J_PASSWORD=your_neo4j_password
NEO4J_DATABASE=notion
```

### YAML Configuration
- Location: `src/config/document_stores.yaml`
- Purpose: Store-specific settings and LLM configuration
- Features:
  - Environment variable interpolation
  - Store enablement flags
  - Connection settings
  - LLM provider selection
  - Rate limiting configuration
  - Model settings

### Logging Configuration
- Location: `logging.yaml`
- Features:
  - Granular log levels
  - Component-specific logging
  - Custom formatters
  - Multiple handlers
  - Statistics tracking

## Project Structure

```
project_root/
├── migrations/
│   └── 001_initial_schema.sql
├── prompts/
│   ├── chunking.md
│   └── relationships.md
├── src/
│   ├── api/
│   │   └── notion.py
│   ├── config/
│   │   └── document_stores.yaml
│   ├── llm/
│   │   ├── chunker.py
│   │   ├── extractor.py
│   │   ├── provider.py
│   │   └── rate_limiter.py
│   ├── storage/
│   │   ├── base.py
│   │   ├── chroma.py
│   │   ├── memgraph.py
│   │   ├── neo4j.py
│   │   └── store_manager.py
│   ├── utils/
│   │   ├── logging.py
│   │   ├── stats.py
│   │   └── text.py
│   ├── config.py
│   ├── main.py
│   └── sync.py
├── logging.yaml
├── README.md
├── requirements.txt
└── setup.py
```

## Technical Constraints

### Performance
- Memory usage during chunking (400-1200 tokens per chunk)
- Network latency for API calls
- Database connection management
- LLM rate limiting:
  - Groq: 10 second delay
  - Gemini: 5 second delay
  - Ollama: No delay
- Chunk merging for small final chunks

### Security
- API key management
- Database credentials
- Network security
- Data privacy

### Scalability
- Document size limits
- Rate limiting (Notion API, LLM providers)
- Database connection pooling
- Concurrent processing limits

## Integration Points

### External APIs
1. Notion API
   - Rate limits
   - Authentication
   - Content format
   - Markdown conversion

2. LLM Providers
   - Ollama integration
   - Gemini API
   - Groq API
   - Rate limiting
   - Model selection
   - Embeddings generation

### Databases
1. ChromaDB
   - Collection management
   - Vector operations
   - Document metadata
   - Content hashing

2. Graph Databases
   - Schema constraints
   - Relationship types
   - Query optimization
   - Chunk summaries

## Development Workflow

### Setup Process
1. Install dependencies
2. Configure environment
3. Initialize databases
4. Verify connections

### Testing
1. Unit tests
2. Integration tests
3. Database tests
4. API mocking

### Deployment
1. Environment setup
2. Database initialization
3. Configuration verification
4. Service startup
