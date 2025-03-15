# Technical Context

## Development Environment

### Core Requirements
- Python 3.8+
- Pinecone account with API access
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
- `pinecone`: Pinecone client
- `langchain`: LLM framework and abstractions
- `langchain-ollama`: Ollama integration
- `nomic-embed-text`: Vector embeddings generation
- `tiktoken`: Token counting library
- `pyyaml`: YAML configuration parsing
- `python-dotenv`: Environment variable management

### Storage System

#### Pinecone
- Purpose: Vector storage and semantic search
- Requirements:
  - Pinecone API key
  - Pinecone environment
  - Index name
  - Optional namespace
- Features:
  - Vector storage and search
  - Document metadata storage
  - Content hash tracking
  - Chunk management
  - Relationship storage
  - Query capabilities

## Configuration Management

### Environment Variables
```bash
# Core Settings
NOTION_API_TOKEN=your_notion_token
OLLAMA_HOST=your_ollama_host

# Pinecone Settings
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_ENVIRONMENT=your_pinecone_environment
PINECONE_INDEX=your_pinecone_index
PINECONE_NAMESPACE=optional_namespace

# Optional Configuration Paths
LOG_CONFIG_PATH=logging.yaml
CONFIG_PATH=src/config/document_stores.yaml

# LLM Model Provider
MODEL_PROVIDER=ollama  # Options: ollama, gemini, groq

# Provider Specific Settings
# Rate Limiting
GROQ_RATE_LIMIT=10  # seconds delay
GEMINI_RATE_LIMIT=5  # seconds delay
OLLAMA_RATE_LIMIT=0  # no delay
GOOGLE_API_KEY=your_google_api_key  # For Gemini
GROQ_API_KEY=your_groq_api_key  # For Groq
```

### YAML Configuration
- Location: `src/config/document_stores.yaml`
- Purpose: Store settings and LLM configuration
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
│   │   ├── pinecone.py
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
- Pinecone request limits
- LLM rate limiting:
  - Groq: 10 second delay
  - Gemini: 5 second delay
  - Ollama: No delay
- Chunk merging for small final chunks

### Security
- API key management
- Network security
- Data privacy

### Scalability
- Document size limits
- Rate limiting (Notion API, LLM providers)
- Pinecone request quotas
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

3. Pinecone API
   - Vector operations
   - Index management
   - Metadata handling
   - Query optimization
   - Namespace management

## Development Workflow

### Setup Process
1. Install dependencies
2. Configure environment
3. Initialize Pinecone index
4. Verify connections

### Testing
1. Unit tests
2. Integration tests
3. Vector store tests
4. API mocking

### Deployment
1. Environment setup
2. Pinecone index creation
3. Configuration verification
4. Service startup
