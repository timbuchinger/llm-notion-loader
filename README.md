# Notion Document Store Sync

A tool for synchronizing Notion pages to multiple document stores (ChromaDB, Apache AGE, Neo4j, and Memgraph), with relationship extraction using LLMs.

## Features

- Syncs Notion pages to multiple destination stores
- Configurable document store selection (use one, two, or all three)
- Vector search capabilities with ChromaDB
- Graph representations in Apache AGE and Neo4j
- Relationship extraction using LLMs
- Supports incremental updates
- Skip functionality with #skip tag
- Configurable logging levels

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd loader/age
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the package in development mode:
```bash
pip install -e .
```

## Configuration

### 1. Document Store Configuration

The tool uses a YAML configuration file to manage document store settings. By default, it looks for `src/config/document_stores.yaml`:

```yaml
document_stores:
  chroma:
    enabled: true
    settings:
      host: ${CHROMA_HOST}
      auth_token: ${CHROMA_AUTH_TOKEN}
      collection: ${CHROMA_COLLECTION}
      port: "443"
      ssl: true

  neo4j:
    enabled: false  # disabled by default
    settings:
      uri: ${NEO4J_URI}
      user: ${NEO4J_USER}
      password: ${NEO4J_PASSWORD}
      database: ${NEO4J_DATABASE}

  age:
    enabled: true
    settings:
      host: ${AGE_HOST}
      port: ${AGE_PORT}
      database: ${AGE_DATABASE}
      user: ${AGE_USER}
      password: ${AGE_PASSWORD}
```

Key configuration points:
- Each store can be independently enabled/disabled
- Environment variables are automatically interpolated
- Store-specific settings can be customized
- Settings fallback to environment variables if not specified

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

# ChromaDB Settings
CHROMA_AUTH_TOKEN=your_chroma_token
CHROMA_HOST=your_chroma_host
CHROMA_COLLECTION=notion

# Apache AGE Settings
AGE_HOST=localhost
AGE_PORT=5432
AGE_DATABASE=notion
AGE_USER=postgres
AGE_PASSWORD=your_password

# Neo4j Settings (optional)
NEO4J_URI=your_neo4j_uri
NEO4J_USER=your_neo4j_user
NEO4J_PASSWORD=your_neo4j_password
NEO4J_DATABASE=notion
```

### 3. Logging Configuration

The tool supports granular logging control through a YAML configuration file (`logging.yaml`):

```yaml
version: 1
disable_existing_loggers: false

defaults:
  level: INFO

loggers:
  src.storage.age:
    level: WARNING
  src.storage.neo4j:
    level: WARNING
  src.llm.chunker:
    level: DEBUG
  src.llm.extractor:
    level: INFO
  src.storage.chroma:
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

The recommended way to run the sync tool is using the module directly:

```bash
# From the loader/age directory
python -m src.main

# With debug logging
python -m src.main --log-level DEBUG

# Clear databases
python -m src.main --clear-database
```

## Database Setup

### Apache AGE Setup
1. Install and configure PostgreSQL with Apache AGE:
   - Follow the [Apache AGE installation guide](https://github.com/apache/age)
   - Ensure PostgreSQL has the vector extension installed: `CREATE EXTENSION vector;`

2. Initialize the database schema:
```bash
psql -f migrations/001_initial_schema.sql -d your_database_name
```

### Neo4j Setup (Optional)
If you plan to use Neo4j:
1. Install Neo4j Community or Enterprise Edition
2. Create a new database (default: notion)
3. Set up the required credentials in .env
4. The system will automatically create necessary constraints

### Memgraph Setup (Optional)
If you plan to use Memgraph:
1. Ensure access to a Memgraph instance
2. Configure the connection settings in .env:
   ```bash
   MEMGRAPH_URI=bolt://memgraph.buchinger.ca:7687
   MEMGRAPH_USER=your_username
   MEMGRAPH_PASSWORD=your_password
   ```
3. Enable Memgraph in document_stores.yaml:
   ```yaml
   memgraph:
     enabled: true
     settings:
       uri: ${MEMGRAPH_URI}
       user: ${MEMGRAPH_USER}
       password: ${MEMGRAPH_PASSWORD}
   ```
   4. The system will automatically:
   - Set up required constraints

### ChromaDB Setup
1. Set up a ChromaDB instance (local or hosted)
2. Configure the connection details in .env
3. Collections are automatically created as needed

## Architecture

The package is organized into several modules:

- `api/`: Notion API integration
- `llm/`: Language model integration and relationship extraction
- `storage/`: Document store implementations (ChromaDB, AGE, Neo4j)
- `utils/`: Common utilities and helpers
- `sync.py`: Main synchronization logic
- `config.py`: Configuration management
- `config/`: YAML configuration files

## Utility Scripts

The project includes utility scripts in the `scripts/` directory:

### Query Memgraph Knowledge Base
Query the Memgraph knowledge base using semantic search and graph relationships:

```bash
# Basic usage
./scripts/query_memgraph.py "What are the key features?"

# Advanced options
./scripts/query_memgraph.py --top-n 10 --threshold 0.6 "What are the architectural patterns?"
```

The query script combines:
- Vector similarity search for relevant chunks
- Graph relationship analysis
- Result ranking and formatting

Options:
- `--top-n`: Number of results to return (default: 5)
- `--threshold`: Minimum similarity score threshold (default: 0.5)

Output includes:
- Chunk content with summaries
- Source note titles
- Related entities from the knowledge graph
- Similarity scores

### Export Store Data
Export documents and chunks from any enabled store to a text file:

```bash
# Export all documents from ChromaDB
./scripts/export_store.py --store chroma --output chroma.txt

# Export a specific document by Notion ID
./scripts/export_store.py --store chroma --output document.txt --notion-id your-notion-id
```

The export format includes:
- Document title and content
- Total chunk count
- Detailed chunk information:
  - Chunk content
  - Chunk summary (if available)
  - Token count (if available)

### Export Entities and Relationships
Export all entities and their relationships from the graph store to CSV files:

```bash
./scripts/export_relationships.py
```

This generates two CSV files:
1. `entities.csv`: Contains entity names and the notes they are mentioned in
2. `relationships.csv`: Contains relationships between entities with source note context

You can specify a custom output directory:
```bash
./scripts/export_relationships.py --output-dir path/to/directory
```

## Requirements

- Python 3.8+
- PostgreSQL with Apache AGE extension
- ChromaDB instance
- Neo4j (optional)
- Notion API access
- LLM provider (Ollama, Gemini, or Groq)

## Note on Document Store Selection

You can enable or disable any combination of document stores in the YAML config file. This allows you to:
- Use just one store (e.g., only ChromaDB for vector search)
- Use any combination of stores (e.g., ChromaDB + AGE)
- Use all available stores simultaneously

Changes to the enabled/disabled status take effect without any code changes - simply update the YAML file.
