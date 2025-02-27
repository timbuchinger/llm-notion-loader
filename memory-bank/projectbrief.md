# Project Brief: LLM Notion Loader

## Purpose
A specialized synchronization tool that loads Notion pages into vector and graph databases, enabling advanced search and relationship analysis through LLM-powered processing.

## Core Requirements
- Sync Notion pages to configured document stores
- Extract and represent relationships between documents
- Support incremental updates and change detection
- Maintain data consistency across stores
- Provide configurable store selection

## Key Features
- Multi-store synchronization (ChromaDB, Memgraph)
- Vector search capabilities via ChromaDB
- Graph relationship representation via Memgraph
- LLM-powered relationship extraction
- Semantic chunking with summaries
- Incremental updates with hash checking
- Skip functionality with #skip tag
- Configurable logging and statistics

## Goals
1. **Primary Goal**: Efficient synchronization of Notion content to specialized databases
2. **Secondary Goal**: Rich relationship extraction and representation
3. **Tertiary Goal**: Flexible configuration and extensibility

## Scope
### In Scope
- Notion page synchronization
- Content processing and chunking
- Semantic chunk summarization
- Relationship extraction
- Vector embeddings generation
- Multiple database support (ChromaDB, Memgraph)
- Configuration management
- Logging and statistics

### Out of Scope
- Real-time synchronization
- Bi-directional sync
- Content modification
- User interface beyond CLI
- Authentication management beyond API keys

## Success Criteria
- Successful sync of Notion pages to enabled stores
- Accurate relationship extraction and storage
- Efficient incremental updates with change detection
- Proper error handling and recovery
- Consistent data across active stores
- Clear sync statistics and reporting

## Technical Foundation
- Python-based implementation
- LLM integration (Ollama, Gemini, Groq)
- Modular store architecture
- Configuration-driven design
- Extensible store support
