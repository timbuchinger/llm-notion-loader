#!/usr/bin/env python3

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

from langchain_ollama import OllamaEmbeddings
from neo4j import GraphDatabase

# Add src to Python path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.config import Config
from src.storage.memgraph import MemgraphStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_embeddings() -> OllamaEmbeddings:
    """Get the embeddings model using the same settings as the main project."""
    return OllamaEmbeddings(
        base_url=f"https://{Config.REQUIRED_ENV_VARS.get('OLLAMA_HOST')}",
        model="nomic-embed-text",
    )


def embed_text(text: str) -> List[float]:
    """Generate embeddings using Ollama for consistency with main project."""
    embeddings = get_embeddings()
    return embeddings.embed_query(text)


def diagnose_embeddings(session) -> None:
    """Check the state of embeddings in the database."""
    # Check Note embeddings
    note_results = session.run(
        """
        MATCH (n:Note)
        WITH n LIMIT 1
        RETURN n.id as id,
               n.title as title,
               CASE WHEN n.embedding IS NOT NULL THEN size(n.embedding) ELSE 0 END as embedding_size,
               keys(n) as properties
        """
    ).single()

    if note_results:
        logger.info("\nNote embedding info:")
        logger.info(f"ID: {note_results['id']}")
        logger.info(f"Title: {note_results['title']}")
        logger.info(f"Properties: {note_results['properties']}")
        logger.info(f"Embedding size: {note_results['embedding_size']}")

    # Check chunk embeddings and related properties
    chunk_results = session.run(
        """
        MATCH (c:NoteChunk)
        WITH c LIMIT 1
        RETURN c.id as id,
               c.embedding_model as model,
               c.embedding_provider as provider,
               CASE WHEN c.embedding IS NOT NULL THEN size(c.embedding) ELSE 0 END as embedding_size,
               keys(c) as properties
        """
    ).single()

    if chunk_results:
        logger.info("\nChunk embedding info:")
        logger.info(f"ID: {chunk_results['id']}")
        logger.info(f"Model: {chunk_results['model']}")
        logger.info(f"Provider: {chunk_results['provider']}")
        logger.info(f"Properties: {chunk_results['properties']}")
        logger.info(f"Embedding size: {chunk_results['embedding_size']}")

    # Get embedding statistics
    stats = session.run(
        """
        MATCH (c:NoteChunk)
        RETURN count(c) as total_chunks,
               count(c.embedding) as chunks_with_embeddings,
               count(c.vector) as chunks_with_vector,
               count(c.embeddings) as chunks_with_embeddings_plural
        """
    ).single()

    logger.info("\nEmbedding statistics:")
    logger.info(f"Total chunks: {stats['total_chunks']}")
    logger.info(f"Chunks with embedding: {stats['chunks_with_embeddings']}")
    logger.info(f"Chunks with vector: {stats['chunks_with_vector']}")
    logger.info(f"Chunks with embeddings: {stats['chunks_with_embeddings_plural']}")


def query_memgraph(question: str, top_n: int = 5, threshold: float = 0.5) -> List[Dict]:
    """Query Memgraph for relevant chunks using vector similarity."""
    question_embedding = embed_text(question)
    logger.info(f"Generated embedding of length: {len(question_embedding)}")

    store = MemgraphStore()
    results = []

    with store.driver.session() as session:
        # First diagnose the embeddings state
        diagnose_embeddings(session)

        # Create vector index if it doesn't exist
        try:
            session.run(
                """
                CREATE INDEX chunk_index ON :NoteChunk(embedding) TYPE VECTOR DIMENSION 768;
                """
            )
            logger.info("Created vector index for embeddings")
        except Exception as e:
            logger.debug(f"Vector index might already exist: {str(e)}")

        # Create query node
        session.run(
            "CREATE (:QueryNode {embedding: $embedding})", embedding=question_embedding
        )

        try:
            similar_chunks = session.run(
                """
                MATCH (q:QueryNode)
                WITH q, q.embedding as query_embedding
                MATCH (chunk:NoteChunk)
                WHERE chunk.embedding IS NOT NULL
                WITH q, chunk,
                     reduce(dot = 0.0, i IN range(0, size(chunk.embedding)-1) |
                        dot + chunk.embedding[i] * q.embedding[i]
                     ) / (
                        sqrt(reduce(norm1 = 0.0, i IN range(0, size(chunk.embedding)-1) |
                            norm1 + chunk.embedding[i] * chunk.embedding[i]
                        )) *
                        sqrt(reduce(norm2 = 0.0, i IN range(0, size(q.embedding)-1) |
                            norm2 + q.embedding[i] * q.embedding[i]
                        ))
                     ) AS similarity
                WITH chunk, similarity, q
                WHERE similarity > $threshold
                MATCH (note:Note)-[:HAS_CHUNK]->(chunk)
                OPTIONAL MATCH (chunk)-[:HAS_SOURCE]->(sr:SourceReference)-[:HAS_SOURCE]->(e:Entity)
                WITH chunk, note, similarity, COLLECT(DISTINCT e.name) as related_entities
                RETURN
                    chunk.content as content,
                    chunk.summary as summary,
                    note.title as note_title,
                    related_entities,
                    similarity
                ORDER BY similarity DESC
                LIMIT $top_n
                """,
                threshold=threshold,
                top_n=top_n,
            )

            for record in similar_chunks:
                logger.info(
                    f"\nFound match with similarity: {record['similarity']:.3f}"
                )
                logger.debug(f"Note title: {record['note_title']}")
                results.append(
                    {
                        "content": record["content"],
                        "summary": record["summary"],
                        "note_title": record["note_title"],
                        "related_entities": record["related_entities"],
                        "similarity": record["similarity"],
                    }
                )

        finally:
            session.run("MATCH (q:QueryNode) DETACH DELETE q")

    logger.info(f"\nFound {len(results)} results")
    return results


def format_results(results: List[Dict]) -> str:
    """Format query results for display."""
    if not results:
        return "No relevant results found."

    output = []
    for i, result in enumerate(results, 1):
        output.append(f"\n=== Result {i} (Similarity: {result['similarity']:.3f}) ===")
        output.append(f"From: {result['note_title']}")

        if result["summary"]:
            output.append(f"\nSummary: {result['summary']}")

        output.append(f"\nContent: {result['content']}")

        if result["related_entities"]:
            output.append(
                f"\nRelated Entities: {', '.join(result['related_entities'])}"
            )

        output.append("\n")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="Query Memgraph for relevant note chunks"
    )
    parser.add_argument("question", help="Question to search for")
    parser.add_argument(
        "--top-n", type=int, default=5, help="Number of results to return (default: 5)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.3,
        help="Minimum similarity score threshold (default: 0.3)",
    )

    args = parser.parse_args()

    try:
        results = query_memgraph(
            question=args.question, top_n=args.top_n, threshold=args.threshold
        )
        print(format_results(results))

    except Exception as e:
        logger.error(f"Error querying Memgraph: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
