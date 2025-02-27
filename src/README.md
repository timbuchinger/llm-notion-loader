
# Usage

From the loader/memgraph directory:

```bash
# Run with default settings
python -m src.main  

# Run with debug logging
python -m src.main --log-level DEBUG

# Clear databases before sync
python -m src.main --clear-database
```

# Statistics

The sync process now tracks and reports detailed statistics about the operation:

- Document Processing
  - Total documents found
  - Documents processed
  - Documents skipped

- Database Operations
  - Chroma: insertions, updates, and deletions
  - Neo4j: nodes created, relationships created, deletions

- Text Chunking
  - Documents using LLM-based chunking vs token-based
  - Number of chunks created by each method
  - Rate limit hits during LLM chunking operations

- Timing
  - Total process duration
  - Start timestamp
  - Total time spent in rate-limiting

The statistics are displayed automatically at the end of the sync process. For more detailed logging during the process, use the `--log-level DEBUG` flag.
