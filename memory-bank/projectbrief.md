# Project Brief: LLM Notion Loader

## Purpose
A specialized synchronization tool that loads Notion pages into a vector database, enabling advanced search and relationship analysis through LLM-powered processing.

## Core Requirements
- Sync Notion pages to Pinecone vector store
- Extract and store relationships as vector metadata
- Support incremental updates and change detection
- Maintain data consistency
- Provide efficient vector search capabilities

## Key Features
- Vector-based synchronization with Pinecone
- Rich semantic search capabilities
- LLM-powered relationship extraction
- Semantic chunking with summaries
- Incremental updates with hash checking
- Skip functionality with #skip tag
- Configurable logging and statistics

## Goals
1. **Primary Goal**: Efficient synchronization of Notion content to vector database
2. **Secondary Goal**: Rich relationship extraction and metadata storage
3. **Tertiary Goal**: Flexible configuration and extensibility

## Scope
### In Scope
- Notion page synchronization
- Content processing and chunking
- Semantic chunk summarization
- Relationship extraction
- Vector embeddings generation
- Pinecone integration
- Configuration management
- Logging and statistics

### Out of Scope
- Real-time synchronization
- Bi-directional sync
- Content modification
- User interface beyond CLI
- Authentication management beyond API keys

## Success Criteria
- Successful sync of Notion pages to Pinecone
- Accurate relationship extraction and storage
- Efficient incremental updates with change detection
- Proper error handling and recovery
- Clear sync statistics and reporting

## Technical Foundation
- Python-based implementation
- LLM integration (Ollama, Gemini, Groq)
- Vector store architecture
- Configuration-driven design
- Robust error handling
