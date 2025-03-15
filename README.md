# Notion Document Store Sync

A tool for synchronizing Notion pages to Pinecone vector database, with optional relationship extraction using LLMs.

## Features

- Syncs Notion pages to Pinecone vector database
- Vector search capabilities with semantic embeddings
- Optional relationship extraction using LLMs
- Supports incremental updates
- Skip functionality with #skip tag
- Configurable logging levels
- Detailed statistics tracking
- Multiple LLM provider options (Ollama, Gemini, Groq)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd llm-notion-loader
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the package in development mode:
```bash
pip install -e .
```

## Configuration

### 1. Document Store Configuration

The tool uses a YAML configuration file to manage settings. By default, it looks for `src/config/document_stores.yaml`:

```yaml
relationship_extraction:
  enabled: false  # Global flag for relationship extraction

model:
  provider: "groq"  # Options: "ollama", "gemini", "groq"
  rate_limits:
    ollama: 0  # seconds
    gemini: 5  # seconds
    groq: 5    # seconds
  models:
    ollama: "mistral:7b"
    gemini: "gemini-2.0-flash"
    groq: "qwen-2.5-32b"

document_stores:
  pinecone:
    enabled: true
    supports_relationships: false
    settings:
      api_key: ${PINECONE_API_KEY}
      environment: ${PINECONE_ENVIRONMENT}
      index_name: ${PINECONE_INDEX}
      namespace: ${PINECONE_NAMESPACE}  # Optional
```

Key configuration points:
- Enable/disable relationship extraction globally
- Choose and configure LLM provider
- Configure rate limits for each provider
- Pinecone settings with environment variable interpolation

### 2. Environment Variables

1. Copy the example environment file:
```bash
cp .env_example .env
```

2. Edit .env and fill in your configuration:
```
# Core Settings
NOTION_API_TOKEN=your_notion_token
OLLAMA_HOST=your_ollama_host

# Pinecone Settings
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_ENVIRONMENT=your_pinecone_environment
PINECONE_INDEX=your_index_name
PINECONE_NAMESPACE=your_namespace  # Optional

# LLM Provider Settings (based on chosen provider)
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Logging Configuration

The tool supports granular logging control through a YAML configuration file (`logging.yaml`):

```yaml
version: 1
disable_existing_loggers: false

defaults:
  level: INFO

loggers:
  src.storage.pinecone:
    level: INFO
  src.llm.chunker:
    level: DEBUG
  src.llm.extractor:
    level: INFO
  src.api.notion:
    level: INFO

handlers:
  console:
    class: logging.StreamHandler
    formatter: standard
    stream: ext://sys.stdout

formatters:
  standard:
    format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## Usage

Run the sync tool using the module directly:

```bash
# Run with default settings
python -m src.main

# Run with debug logging
python -m src.main --log-level DEBUG

# Clear database before sync
python -m src.main --clear-database
```

### Statistics Tracking

The sync process tracks and reports detailed statistics:

- Document Processing
  - Total documents found
  - Documents processed
  - Documents skipped
  - Documents with errors

- Database Operations
  - Vector insertions and deletions
  - Relationship creation (if enabled)

- Text Chunking
  - Documents using LLM-based chunking vs token-based
  - Number of chunks created by each method
  - Rate limit hits during LLM operations

- Timing
  - Total process duration
  - Start timestamp
  - Time spent in rate-limiting

Statistics are displayed automatically at the end of the sync process. For more detailed logging during the process, use the `--log-level DEBUG` flag.

## Utility Scripts

### Export Store Data
Export documents and chunks from Pinecone to a text file:

```bash
# Export all documents
./scripts/export_store.py --store pinecone --output pinecone.txt

# Export a specific document by Notion ID
./scripts/export_store.py --store pinecone --output document.txt --notion-id your-notion-id
```

The export format includes:
- Document title and content
- Total chunk count
- Detailed chunk information:
  - Chunk content
  - Chunk summary (if available)
  - Token count (if available)

### Delete Pinecone Namespace
Delete documents from a Pinecone namespace:

```bash
# Delete all documents in namespace
./scripts/delete_pinecone_namespace.py

# Delete specific document by Notion ID
./scripts/delete_pinecone_namespace.py --notion-id your-notion-id

# Delete from specific namespace
./scripts/delete_pinecone_namespace.py --namespace your-namespace

# Skip confirmation prompt
./scripts/delete_pinecone_namespace.py --force
```

## Requirements

- Python 3.8+
- Notion API access
- Pinecone account and API key
- LLM provider access (one of):
  - Ollama with local models
  - Google Gemini API key
  - Groq API key
