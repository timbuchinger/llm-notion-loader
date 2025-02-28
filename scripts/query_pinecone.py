#!/usr/bin/env python3

import argparse
import logging
import os
import sys
from typing import Any, List

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from langchain_ollama import OllamaEmbeddings

from src.config import Config
from src.storage.pinecone import PineconeStore


def get_embedding(text: str) -> List[float]:
    """Get embedding for text using Ollama's API.

    Args:
        text: Text to get embedding for

    Returns:
        List of floats representing the embedding
    """
    embeddings = OllamaEmbeddings(
        base_url=f"https://{Config.REQUIRED_ENV_VARS['OLLAMA_HOST']}",
        model="nomic-embed-text",
    )

    return embeddings.embed_query(text)


def format_result(match) -> str:
    """Format a search result for display.

    Args:
        match: Pinecone match object

    Returns:
        Formatted string representation
    """
    metadata = match.metadata
    score = round(match.score * 100, 2)

    result = []
    result.append(f"\nScore: {score}%")
    result.append(f"Namespace: {metadata.get('namespace', 'Unknown')}")

    # Display all metadata fields except 'text' and 'namespace' (shown separately)
    result.append("\nMetadata:")
    for key, value in sorted(metadata.items()):
        if key not in ["text", "namespace"]:  # Skip fields we show separately
            result.append(f"  {key}: {value}")

    # Show the actual content last
    result.append(f"\nContent: {metadata.get('text', 'No content available')}")

    return "\n".join(result)


def get_all_namespaces(store: PineconeStore) -> List[str]:
    """Get all namespaces in the index.

    Args:
        store: PineconeStore instance

    Returns:
        List of namespace names
    """
    logger.info("Getting list of namespaces...")
    stats = store.index.describe_index_stats()
    namespaces = list(stats.namespaces.keys())
    logger.debug(f"Found namespaces: {namespaces}")
    return namespaces


def check_index_data(store: PineconeStore) -> bool:
    """Check if there's any data in the index.

    Args:
        store: PineconeStore instance

    Returns:
        True if data exists, False otherwise
    """
    logger.info("Checking for data in index...")
    stats = store.index.describe_index_stats()
    total_vectors = sum(ns.vector_count for ns in stats.namespaces.values())
    logger.debug(f"Total vectors in index: {total_vectors}")
    return total_vectors > 0


def search_all_namespaces(
    store: PineconeStore, query_embedding: List[float]
) -> List[Any]:
    """Search across all namespaces and return top results.

    Args:
        store: PineconeStore instance
        query_embedding: Query vector

    Returns:
        Combined and sorted list of top matches
    """
    all_results = []
    namespaces = get_all_namespaces(store)

    for namespace in namespaces:
        logger.debug(f"Searching namespace: {namespace}")
        results = store.index.query(
            vector=query_embedding,
            top_k=5,  # Get top 5 from each namespace
            include_metadata=True,
            namespace=namespace,
        )
        if results.matches:
            for match in results.matches:
                # Add namespace to metadata for reference
                match.metadata["namespace"] = namespace
            all_results.extend(results.matches)
            logger.debug(f"Found {len(results.matches)} results in {namespace}")

    # Sort by score and get top 5 overall
    all_results.sort(key=lambda x: x.score, reverse=True)
    return all_results[:5]


def main():
    parser = argparse.ArgumentParser(
        description="Search Pinecone index using semantic search"
    )
    parser.add_argument("query", help="The search query to execute")
    args = parser.parse_args()

    # Initialize Pinecone store
    store = PineconeStore()

    try:
        # First check if index has any data
        if not check_index_data(store):
            logger.error("No data found in the index!")
            return

        # Get embedding for query
        logger.info("\nGenerating embedding for query...")
        query_embedding = get_embedding(args.query)
        logger.debug(f"Generated embedding (first 5 values): {query_embedding[:5]}")

        logger.info("Searching across all namespaces...")
        matches = search_all_namespaces(store, query_embedding)

        if not matches:
            logger.info("\nNo results found.")
            return

        print(f"\nFound {len(matches)} results across all namespaces:")
        for match in matches:
            print("\n" + "=" * 50)
            print(format_result(match))

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        if hasattr(e, "response"):
            logger.error(
                f"Response content: {e.response.content if hasattr(e.response, 'content') else 'No content'}"
            )
            logger.error(
                f"Response status: {e.response.status_code if hasattr(e.response, 'status_code') else 'No status'}"
            )
    finally:
        store.close()


if __name__ == "__main__":
    main()
