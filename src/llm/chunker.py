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

Below is the text to chunk. Replace [Document Title] with the title. Process ONLY the text between the [START] and [END] markers:

Title: {title}

[START]
{text}
[END]
"""

    def chunk_text(self, text: str, title: str = "Untitled") -> List[TextChunk]:
        """Split text into semantic chunks using LLM.

        Args:
            text: Text content to chunk
            title: Document title to include in chunks

        Returns:
            List of TextChunk objects containing chunks and metadata
        """
        chunks = []
        current_summary = None
        current_content = []

        try:
            # Invoke LLM with the templated prompt including title
            response = self.llm.invoke(
                self.template.format(
                    instructions=self.prompt_text, text=text, title=title
                )
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
                        content_lines = "\n".join(current_content)
                        chunks.append(
                            TextChunk(
                                text=content_lines,
                                summary=current_summary,
                                title=title,
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
                content_lines = "\n".join(current_content)
                chunks.append(
                    TextChunk(
                        text=content_lines,
                        summary=current_summary,
                        title=title,
                    )
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
                return self.fallback_chunk_text(text, title=title)

            return chunks

        except Exception as e:
            logger.error(f"LLM chunking failed: {str(e)}")
            return self.fallback_chunk_text(text, title=title)

    @staticmethod
    def merge_adjacent_chunks(chunk1: TextChunk, chunk2: TextChunk) -> TextChunk:
        """Merge two chunks into one.

        Args:
            chunk1: First chunk
            chunk2: Second chunk

        Returns:
            Merged TextChunk
        """
        merged_text = chunk1.text + "\n" + chunk2.text
        merged_summary = f"{chunk1.summary}; {chunk2.summary}"
        return TextChunk(
            text=merged_text,
            summary=merged_summary,
            title=chunk1.title,  # Keep title from first chunk
        )

    @staticmethod
    def merge_small_chunks(chunks: List[TextChunk]) -> List[TextChunk]:
        """Merge small chunks with adjacent chunks where possible.

        Args:
            chunks: List of chunks to process

        Returns:
            List of chunks with small chunks merged where appropriate
        """
        if len(chunks) < 2:
            return chunks

        tokenizer = tiktoken.get_encoding(TOKENIZER_MODEL)
        i = 0
        while i < len(chunks):
            token_count = len(tokenizer.encode(chunks[i].text))

            # Check if current chunk is small
            if token_count < 35:
                merged = False

                # Try merging with next chunk if available
                if i < len(chunks) - 1:
                    next_tokens = len(tokenizer.encode(chunks[i + 1].text))
                    if token_count + next_tokens <= 1200:
                        merged_chunk = ChunkingLLM.merge_adjacent_chunks(
                            chunks[i], chunks[i + 1]
                        )
                        chunks[i] = merged_chunk
                        chunks.pop(i + 1)
                        merged = True
                        logger.debug(
                            f"Merged small chunk (size {token_count}) with next chunk (size {next_tokens})"
                        )
                        continue

                # If we couldn't merge forward and there's a previous chunk, try merging backward
                if not merged and i > 0:
                    prev_tokens = len(tokenizer.encode(chunks[i - 1].text))
                    if token_count + prev_tokens <= 1200:
                        merged_chunk = ChunkingLLM.merge_adjacent_chunks(
                            chunks[i - 1], chunks[i]
                        )
                        chunks[i - 1] = merged_chunk
                        chunks.pop(i)
                        logger.debug(
                            f"Merged small chunk (size {token_count}) with previous chunk (size {prev_tokens})"
                        )
                        continue

            i += 1

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

        tokenizer = tiktoken.get_encoding(TOKENIZER_MODEL)

        # For single chunks, only verify they have a summary
        if len(chunks) == 1:
            has_summary = bool(chunks[0].summary)
            token_count = len(tokenizer.encode(chunks[0].text))
            if not has_summary:
                logger.warning("Single chunk missing summary")
                return False
            if token_count > 1200:
                logger.warning(
                    f"Single chunk size {token_count} tokens exceeds maximum 1200"
                )
                return False
            return True

        # First pass: attempt to merge any small chunks
        i = 0
        while i < len(chunks):
            token_count = len(tokenizer.encode(chunks[i].text))
            logger.debug(f"Chunk {i+1} token count: {token_count}")

            if token_count < 35:
                merged = False
                # Try merging with next chunk
                if i < len(chunks) - 1:
                    next_tokens = len(tokenizer.encode(chunks[i + 1].text))
                    if token_count + next_tokens <= 1200:
                        chunks[i] = ChunkingLLM.merge_adjacent_chunks(
                            chunks[i], chunks[i + 1]
                        )
                        chunks.pop(i + 1)
                        merged = True
                        logger.debug(
                            f"Merged small chunk with next chunk during validation"
                        )
                        continue

                # Try merging with previous chunk
                if not merged and i > 0:
                    prev_tokens = len(tokenizer.encode(chunks[i - 1].text))
                    if token_count + prev_tokens <= 1200:
                        chunks[i - 1] = ChunkingLLM.merge_adjacent_chunks(
                            chunks[i - 1], chunks[i]
                        )
                        chunks.pop(i)
                        i -= 1
                        logger.debug(
                            f"Merged small chunk with previous chunk during validation"
                        )
                        continue

            # Check if chunk is too large
            if token_count > 1200:
                logger.warning(
                    f"Chunk {i+1} size {token_count} tokens exceeds maximum 1200"
                )
                chunks.pop(i)
                continue

            i += 1

        if not chunks:
            logger.warning("All chunks were filtered out during validation")
            return False

        # Verify all remaining chunks have summaries and are properly sized
        for i, chunk in enumerate(chunks, 1):
            if not chunk.summary:
                logger.warning(f"Chunk {i} missing summary")
                return False

            token_count = len(tokenizer.encode(chunk.text))
            if token_count < 35 or token_count > 1200:
                logger.warning(
                    f"Chunk {i} size {token_count} tokens is outside range 35-1200"
                )
                return False

        logger.debug(f"Validation complete - {len(chunks)} valid chunks remaining")
        return True

    def fallback_chunk_text(
        self,
        text: str,
        target_tokens: int = 500,
        overlap_tokens: int = 75,
        min_chunk_tokens: int = 100,
        title: str = "Untitled",
    ) -> List[TextChunk]:
        """Create overlapping chunks when LLM chunking fails.

        Args:
            text: Text to chunk
            target_tokens: Target size for each chunk in tokens
            overlap_tokens: Number of tokens to overlap between chunks
            min_chunk_tokens: Minimum chunk size - smaller chunks will be merged with previous
            title: Document title to include in chunks

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
            chunk = TextChunk(
                text=chunk_text,
                token_count=len(chunk_tokens),
                title=title,  # Include title in fallback chunks too
            )
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

        # Try to generate summaries for each chunk
        for chunk in chunks:
            try:
                # Generate summary using LLM
                summary_prompt = f"Please provide a brief, 1-2 sentence summary of the following text:\n\n{chunk.text}"
                summary_response = self.llm.invoke(summary_prompt)

                # Extract summary from response
                summary = (
                    summary_response.content
                    if hasattr(summary_response, "content")
                    else str(summary_response)
                )

                # Update chunk with summary and metadata
                chunk.summary = summary.strip()
                chunk.summary_model = self.llm.__class__.__name__
                chunk.summary_provider = getattr(self.llm, "provider_name", "unknown")

                logger.debug(f"Generated summary for fallback chunk: {chunk.summary}")
            except Exception as e:
                logger.warning(
                    f"Failed to generate summary for fallback chunk: {str(e)}"
                )
                # Continue without summary rather than failing the whole process
                continue

        return chunks
