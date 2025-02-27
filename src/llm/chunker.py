"""Text chunking using LLM for semantic chunking."""

import logging
from pathlib import Path
from typing import List, Optional

import tiktoken
from langchain.prompts import PromptTemplate
from langchain.schema.language_model import BaseLanguageModel

from ..config import Config
from .models import TextChunk
from .provider import get_llm

logger = logging.getLogger(__name__)

# Use consistent tokenizer model across the system
TOKENIZER_MODEL = "cl100k_base"  # OpenAI's recommended model


class ChunkingLLM:
    """LLM-based text chunking."""

    def __init__(self, llm: Optional[BaseLanguageModel] = None):
        """Initialize the chunking LLM.

        Args:
            llm: Optional language model instance. If not provided,
                 uses the default provider from config.
        """
        self.llm = llm or get_llm()

        # Load chunking prompt
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "chunking.md"
        with open(prompt_path) as f:
            self.prompt_text = f.read()

        # Template to wrap text with markers
        self.template = """
{instructions}

Below is the text to chunk. Process ONLY the text between the [START] and [END] markers:

[START]
{text}
[END]
"""

    def chunk_text(self, text: str) -> List[TextChunk]:
        """Split text into semantic chunks using LLM.

        Args:
            text: Text content to chunk

        Returns:
            List of TextChunk objects containing chunks and metadata
        """
        chunks = []
        current_summary = None
        current_content = []

        try:
            # Invoke LLM with the templated prompt
            response = self.llm.invoke(
                self.template.format(instructions=self.prompt_text, text=text)
            )
            # Extract content from AIMessage or string response
            content = (
                response.content if hasattr(response, "content") else str(response)
            )

            # Parse response and extract chunks with summaries
            for line in content.split("\n"):
                line = line.strip()

                if not line:
                    continue

                if line.startswith("CHUNK") and "SUMMARY:" in line:
                    # If we have an existing chunk, save it
                    if current_content and current_summary:
                        chunks.append(
                            TextChunk(
                                text="\n".join(current_content), summary=current_summary
                            )
                        )
                        current_content = []
                    current_summary = None
                elif line.startswith("CHUNK") and "CONTENT:" in line:
                    continue
                elif current_summary is None:
                    current_summary = line
                else:
                    current_content.append(line)

            # Add the last chunk
            if current_content and current_summary:
                chunks.append(
                    TextChunk(text="\n".join(current_content), summary=current_summary)
                )

            # Log chunks at debug level
            if chunks:
                logger.debug(f"Created {len(chunks)} chunks:")
                for i, chunk in enumerate(chunks, 1):
                    logger.debug(f"Chunk {i}:")
                    logger.debug(f"Summary: {chunk.summary}")
                    logger.debug(f"Content: {chunk.text}\n")

                # Merge small final chunks if needed
                chunks = self.merge_small_chunks(chunks)

            if not chunks:
                logger.warning("No chunks created, falling back to chunking algorithm")
                return self.fallback_chunk_text(text)

            return chunks

        except Exception as e:
            logger.error(f"LLM chunking failed: {str(e)}")
            return self.fallback_chunk_text(text)

    @staticmethod
    def merge_small_chunks(chunks: List[TextChunk]) -> List[TextChunk]:
        """Merge small final chunks with their predecessor if possible.

        Args:
            chunks: List of chunks to process

        Returns:
            List of chunks with small final chunks merged if appropriate
        """
        if len(chunks) < 2:
            return chunks

        # Check if final chunk is small
        tokenizer = tiktoken.get_encoding(TOKENIZER_MODEL)
        final_tokens = len(tokenizer.encode(chunks[-1].text))

        if final_tokens < 100:
            # Check if merging with previous chunk would be reasonable
            prev_tokens = len(tokenizer.encode(chunks[-2].text))
            if prev_tokens + final_tokens <= 1200:
                # Merge the chunks
                merged_text = chunks[-2].text + "\n" + chunks[-1].text
                merged_summary = f"{chunks[-2].summary}; {chunks[-1].summary}"
                merged_chunk = TextChunk(text=merged_text, summary=merged_summary)
                return chunks[:-2] + [merged_chunk]

        return chunks

    @staticmethod
    def validate_chunks(chunks: List[TextChunk]) -> bool:
        """Validate chunks meet requirements.

        Args:
            chunks: List of chunks to validate

        Returns:
            True if chunks are valid, False otherwise
        """
        if not chunks:
            return False

        # Check chunk sizes are reasonable
        tokenizer = tiktoken.get_encoding(TOKENIZER_MODEL)

        # For single chunks, only verify they have a summary
        if len(chunks) == 1:
            return bool(chunks[0].summary)

        # For multiple chunks, validate size ranges
        for i, chunk in enumerate(chunks, 1):
            token_count = len(tokenizer.encode(chunk.text))
            logger.debug(f"Chunk {i} token count: {token_count}")
            if token_count < 35 or token_count > 1200:
                logger.warning(
                    f"Chunk size {token_count} tokens is outside ideal range"
                )
                return False

        # Verify all chunks have summaries
        return all(chunk.summary for chunk in chunks)

    def fallback_chunk_text(
        self,
        text: str,
        target_tokens: int = 500,
        overlap_tokens: int = 75,
        min_chunk_tokens: int = 100,
    ) -> List[TextChunk]:
        """Create overlapping chunks when LLM chunking fails.

        Args:
            text: Text to chunk
            target_tokens: Target size for each chunk in tokens
            overlap_tokens: Number of tokens to overlap between chunks
            min_chunk_tokens: Minimum chunk size - smaller chunks will be merged with previous

        Returns:
            List of TextChunk objects
        """
        tokenizer = tiktoken.get_encoding(TOKENIZER_MODEL)
        tokens = tokenizer.encode(text)
        chunks = []

        pos = 0
        while pos < len(tokens):
            # Get chunk contents including overlap
            chunk_tokens = tokens[max(0, pos - overlap_tokens) : pos + target_tokens]
            chunk_text = tokenizer.decode(chunk_tokens)

            # Create chunk
            chunk = TextChunk(text=chunk_text, token_count=len(chunk_tokens))
            chunks.append(chunk)

            # Advance position by target size (overlap will be added on next iteration)
            pos += target_tokens

            # Handle final chunk if it would be too small
            remaining_tokens = len(tokens) - pos
            if 0 < remaining_tokens <= min_chunk_tokens:
                final_tokens = tokens[pos - overlap_tokens :]
                final_text = tokenizer.decode(final_tokens)
                chunks[-1].text = final_text
                chunks[-1].token_count = len(final_tokens)
                break

        return chunks
