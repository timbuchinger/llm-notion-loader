#!/usr/bin/env python3
import argparse
import os
import sys
from typing import Dict, List

# Add parent directory to path so we can import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.storage.store_manager import StoreManager


def format_document(doc: Dict, chunks: List[Dict]) -> str:
    """Format a document and its chunks according to the template.

    Args:
        doc: Document metadata including title and content
        chunks: List of chunk dictionaries

    Returns:
        Formatted string representation
    """
    output = []

    # Document header
    output.append(f"Title: {doc['title']}")
    output.append(f"Chunk count: {len(chunks)}")
    # TODO: Add token count when available
    output.append(f"Content: {doc['content']}")

    # Chunk details
    for i, chunk in enumerate(chunks, 1):
        output.append("=" * 16)
        output.append(f"Chunk #{i} summary: {chunk.get('summary', 'N/A')}")
        output.append(f"Chunk #{i} token count: {chunk.get('token_count', 'N/A')}")
        output.append(f"Chunk #{i}: {chunk['content']}")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="Export contents of a document store to a text file"
    )
    parser.add_argument(
        "--store",
        choices=["chroma", "neo4j", "age", "memgraph"],
        required=True,
        help="Document store to export from",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output file path",
    )
    parser.add_argument(
        "--notion-id",
        type=str,
        help="Optional: Export only the specified Notion document ID",
    )

    args = parser.parse_args()

    # Load config and initialize store
    config = load_config()
    store_manager = StoreManager(config)
    store = store_manager.get_store(args.store)

    if not store:
        print(f"Error: {args.store} store is not enabled in configuration")
        sys.exit(1)

    try:
        # TODO: Add methods to store base class for retrieving documents
        documents = store.get_documents(notion_id=args.notion_id)

        with open(args.output, "w") as f:
            for doc in documents:
                chunks = store.get_chunks(doc["notion_id"])
                formatted = format_document(doc, chunks)
                f.write(formatted)
                f.write("\n\n" + "=" * 80 + "\n\n")  # Document separator

        print(f"Successfully exported to {args.output}")

    except Exception as e:
        print(f"Error during export: {e}")
        sys.exit(1)
    finally:
        store.close()


if __name__ == "__main__":
    main()
