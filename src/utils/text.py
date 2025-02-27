"""Text processing utilities."""

import logging
import re
from typing import List, Optional, Union

import tiktoken
from langchain_ollama import OllamaEmbeddings

from ..config import Config
from ..llm.models import TextChunk
from .stats import SyncStats, get_stats

logger = logging.getLogger(__name__)


def get_embeddings() -> OllamaEmbeddings:
    """Get embeddings model instance."""
    return OllamaEmbeddings(
        base_url=f"https://{Config.REQUIRED_ENV_VARS['OLLAMA_HOST']}",
        model="nomic-embed-text",
    )


def split_text(
    text: str,
    use_semantic: bool = True,
    max_tokens: int = 300,
    overlap: int = 50,
    stats: Optional[SyncStats] = None,
) -> Union[List[str], List[TextChunk]]:
    """Split text into chunks using either semantic or token-based approach.

    Args:
        text: Text to split
        use_semantic: Whether to use semantic chunking (LLM-based)
        max_tokens: Maximum number of tokens per chunk (for token-based)
        overlap: Number of tokens to overlap between chunks (for token-based)
        stats: Optional stats tracker instance

    Returns:
        List of either text chunks (token-based) or TextChunk objects (semantic)
    """
    # Initialize embeddings model and stats
    embeddings_model = get_embeddings()
    stats = stats or get_stats()

    if use_semantic:
        try:
            # Import ChunkingLLM here to avoid circular import
            from ..llm.chunker import ChunkingLLM

            chunker = ChunkingLLM()
            chunks = chunker.chunk_text(text)

            if chunker.validate_chunks(chunks):
                logger.debug("Successfully created semantic chunks")

                # Generate embeddings for each chunk
                for chunk in chunks:
                    try:
                        # Include both summary and content in embedding
                        embed_text = chunk.format_with_summary()
                        chunk.embedding = embeddings_model.embed_query(embed_text)
                        chunk.embedding_model = "nomic-embed-text"
                        chunk.embedding_provider = "ollama"
                        logger.debug(
                            f"Generated embedding of size {len(chunk.embedding)}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to generate embedding: {str(e)}")
                        chunk.embedding = None

                stats.increment_counter("llm_chunked_docs")
                stats.increment_counter("llm_chunks_created", len(chunks))
                return chunks

            logger.warning(
                "Semantic chunks failed validation, falling back to token-based"
            )
        except Exception as e:
            logger.warning(
                f"Semantic chunking failed: {str(e)}, falling back to token-based"
            )
            stats.increment_counter("rate_limit_hits")

    # Token-based fallback
    tokenizer = tiktoken.get_encoding("cl100k_base")
    tokens = tokenizer.encode(text)
    chunks = []

    for i in range(0, len(tokens), max_tokens - overlap):
        chunk = tokens[i : i + max_tokens]
        chunk_text = tokenizer.decode(chunk)

        if use_semantic:
            # Create TextChunk with embedding for semantic mode
            try:
                chunk_obj = TextChunk(text=chunk_text)
                chunk_obj.embedding = embeddings_model.embed_query(chunk_text)
                chunk_obj.embedding_model = "nomic-embed-text"
                chunk_obj.embedding_provider = "ollama"
                chunks.append(chunk_obj)
                logger.debug(f"Generated embedding of size {len(chunk_obj.embedding)}")
            except Exception as e:
                logger.error(f"Failed to generate embedding: {str(e)}")
                chunks.append(TextChunk(text=chunk_text))
        else:
            chunks.append(chunk_text)

    if use_semantic:
        stats.increment_counter("token_chunked_docs")
        stats.increment_counter("token_chunks_created", len(chunks))
    return chunks


def clean_markdown(text: str) -> str:
    """Clean and normalize markdown text.

    Args:
        text: Markdown text to clean

    Returns:
        Cleaned markdown text
    """
    # Strip text
    text = text.strip()

    # Replace multiple newlines with double newline
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text


def should_skip_document(text: str) -> bool:
    """Check if document should be skipped based on content.

    Args:
        text: Document content

    Returns:
        True if document should be skipped, False otherwise
    """
    return "#skip" in text
