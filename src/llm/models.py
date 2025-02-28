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
    title: Optional[str] = None  # Document title
    summary: Optional[str] = None  # Generated summary
    summary_model: Optional[str] = None  # Model used for summary
    summary_provider: Optional[str] = None  # Provider used for summary
    embedding: Optional[List[float]] = None  # Vector embedding
    embedding_model: Optional[str] = None  # Model used for embedding
    embedding_provider: Optional[str] = None  # Provider used for embedding

    def format_with_summary(self) -> str:
        """Format the chunk with summary and title in the standard format.

        Returns:
            Formatted string with summary, title, and content
        """
        result = []
        if self.summary:
            result.append(self.summary)
            result.append("")  # Blank line after summary

        if self.title:
            result.append(f"# {self.title}")
            result.append("")  # Blank line after title

        result.append(self.text)
        return "\n".join(result)
