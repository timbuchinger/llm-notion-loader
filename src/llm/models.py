"""Models for LLM-related functionality."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TextChunk:
    """Representation of a text chunk with metadata."""

    text: str
    token_count: Optional[int] = None
    chunking_model: Optional[str] = None  # Model used for semantic chunking
    chunking_provider: Optional[str] = None  # Provider used for chunking
    summary: Optional[str] = None  # Generated summary
    summary_model: Optional[str] = None  # Model used for summary
    summary_provider: Optional[str] = None  # Provider used for summary
    embedding: Optional[List[float]] = None  # Vector embedding
    embedding_model: Optional[str] = None  # Model used for embedding
    embedding_provider: Optional[str] = None  # Provider used for embedding

    def format_with_summary(self) -> str:
        """Format the chunk with its summary in the standard format.

        Returns:
            Formatted string with summary and content
        """
        if not self.summary:
            return self.text
        return f"Summary: {self.summary}\n\n{self.text}"
