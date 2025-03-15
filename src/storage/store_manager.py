import logging
import os
from pathlib import Path
from string import Template
from typing import Dict, List, Optional

import yaml

from .base import DocumentStore

logger = logging.getLogger(__name__)


class StoreManager:
    """Manages Pinecone document store."""

    def __init__(self, config_input: Optional[str | Dict] = None):
        """Initialize store manager.

        Args:
            config_input: Path to YAML config file or config dictionary. If None, uses default path.
        """
        self.store: Optional[DocumentStore] = None
        self.config = (
            config_input
            if isinstance(config_input, dict)
            else self._load_config(config_input)
        )
        self._initialize_store()

    def _load_config(self, config_path: Optional[str]) -> dict:
        """Load configuration from YAML file.

        Args:
            config_path: Path to config file or None for default

        Returns:
            Loaded and processed configuration dictionary
        """
        if not config_path:
            config_path = (
                Path(__file__).parent.parent / "config" / "document_stores.yaml"
            )

        try:
            with open(config_path) as f:
                # Load YAML content
                config_content = f.read()

                # Replace environment variables
                config_template = Template(config_content)
                config_with_env = config_template.safe_substitute(os.environ)

                # Parse YAML
                return yaml.safe_load(config_with_env)
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {str(e)}")
            raise

    def _initialize_store(self) -> None:
        """Initialize Pinecone store."""
        store_configs = self.config.get("document_stores", {})

        if store_configs.get("pinecone", {}).get("enabled", False):
            try:
                from .pinecone import PineconeStore

                self.store = PineconeStore(config=self.config)
                logger.info("Initialized Pinecone store")
            except Exception as e:
                logger.error(f"Failed to initialize Pinecone store: {str(e)}")
                raise

    def clean_document(self, notion_id: str) -> None:
        """Remove document from store.

        Args:
            notion_id: Notion page ID
        """
        if self.store:
            try:
                self.store.clean_document(notion_id)
                logger.info(f"Cleaned document {notion_id} from Pinecone")
            except Exception as e:
                logger.error(f"Failed to clean document from Pinecone: {str(e)}")
                raise

    def create_chunks(self, notion_id: str, chunks: List[Dict]) -> None:
        """Create chunks in store.

        Args:
            notion_id: Parent note ID
            chunks: List of chunk dictionaries with metadata
        """
        if self.store:
            try:
                from ..llm.models import TextChunk

                # Convert chunks to the appropriate format
                processed_chunks = []
                for chunk in chunks:
                    if isinstance(chunk, TextChunk):
                        # For TextChunks, extract metadata
                        chunk_dict = {
                            "text": chunk.text,
                            "summary": chunk.summary,
                            "token_count": chunk.token_count,
                            "chunking_model": chunk.chunking_model,
                            "chunking_provider": chunk.chunking_provider,
                            "embedding": chunk.embedding,
                            "embedding_model": chunk.embedding_model,
                            "embedding_provider": chunk.embedding_provider,
                        }
                        processed_chunks.append(chunk_dict)
                    elif isinstance(chunk, dict):
                        processed_chunks.append(chunk)
                    else:
                        processed_chunks.append({"text": str(chunk)})

                self.store.create_chunks(notion_id, processed_chunks)
                logger.info(f"Created chunks for {notion_id} in Pinecone")
            except Exception as e:
                logger.error(f"Failed to create chunks in Pinecone: {str(e)}")
                raise

    def create_relationships(
        self, notion_id: str, relationships: List[Dict[str, str]], timestamp: str
    ) -> None:
        """Create relationships in Pinecone store.

        Args:
            notion_id: Parent note ID
            relationships: List of relationships
            timestamp: When the relationships were created
        """
        if self.store:
            try:
                self.store.create_relationships(notion_id, relationships, timestamp)
                logger.info(f"Created relationships for {notion_id} in Pinecone")
            except Exception as e:
                logger.error(f"Failed to create relationships in Pinecone: {str(e)}")
                raise

    def get_note_hash(self, notion_id: str) -> Optional[str]:
        """Get note hash from store.

        Args:
            notion_id: Note ID

        Returns:
            Hash if found, None otherwise
        """
        if self.store:
            try:
                return self.store.get_note_hash(notion_id)
            except Exception as e:
                logger.error(f"Failed to get note hash from Pinecone: {str(e)}")
        return None

    def close(self) -> None:
        """Close store connection."""
        if self.store:
            try:
                self.store.close()
                logger.info("Closed connection to Pinecone")
            except Exception as e:
                logger.error(f"Error closing Pinecone connection: {str(e)}")

    def get_store(self, store_name: str) -> Optional[DocumentStore]:
        """Get the Pinecone store if it matches the name.

        Args:
            store_name: Name of the store to retrieve

        Returns:
            Document store if found and enabled, None otherwise
        """
        return self.store if store_name == "pinecone" else None
