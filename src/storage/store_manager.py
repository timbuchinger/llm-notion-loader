import logging
import os
from pathlib import Path
from string import Template
from typing import Dict, List, Optional

import yaml

from .base import DocumentStore

logger = logging.getLogger(__name__)


class StoreManager:
    """Manages multiple document stores."""

    def __init__(self, config_input: Optional[str | Dict] = None):
        """Initialize store manager.

        Args:
            config_input: Path to YAML config file or config dictionary. If None, uses default path.
        """
        self.stores: Dict[str, DocumentStore] = {}
        self.config = (
            config_input
            if isinstance(config_input, dict)
            else self._load_config(config_input)
        )
        self._initialize_stores()

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

    def _initialize_stores(self) -> None:
        """Initialize enabled document stores based on configuration."""
        store_configs = self.config.get("document_stores", {})

        # Initialize each enabled store
        if store_configs.get("chroma", {}).get("enabled", False):
            try:
                from .chroma import ChromaStore

                self.stores["chroma"] = ChromaStore(config=self.config)
                logger.info("Initialized ChromaDB store")
            except Exception as e:
                logger.error(f"Failed to initialize ChromaDB store: {str(e)}")

        if store_configs.get("neo4j", {}).get("enabled", False):
            try:
                from .neo4j import Neo4jStore

                self.stores["neo4j"] = Neo4jStore(config=self.config)
                logger.info("Initialized Neo4j store")
            except Exception as e:
                logger.error(f"Failed to initialize Neo4j store: {str(e)}")

        if store_configs.get("memgraph", {}).get("enabled", False):
            try:
                from .memgraph import MemgraphStore

                self.stores["memgraph"] = MemgraphStore(config=self.config)
                logger.info("Initialized Memgraph store")
            except Exception as e:
                logger.error(f"Failed to initialize Memgraph store: {str(e)}")

        if store_configs.get("age", {}).get("enabled", False):
            try:
                from .age import AgeStore

                self.stores["age"] = AgeStore(config=self.config)
                logger.info("Initialized Apache AGE store")
            except Exception as e:
                logger.error(f"Failed to initialize Apache AGE store: {str(e)}")

        if store_configs.get("pinecone", {}).get("enabled", False):
            try:
                from .pinecone import PineconeStore

                self.stores["pinecone"] = PineconeStore(config=self.config)
                logger.info("Initialized Pinecone store")
            except Exception as e:
                logger.error(f"Failed to initialize Pinecone store: {str(e)}")

    def clean_document(self, notion_id: str) -> None:
        """Remove document from all stores.

        Args:
            notion_id: Notion page ID
        """
        for store_name, store in self.stores.items():
            try:
                store.clean_document(notion_id)
                logger.info(f"Cleaned document {notion_id} from {store_name}")
            except Exception as e:
                logger.error(f"Failed to clean document from {store_name}: {str(e)}")

    def create_chunks(self, notion_id: str, chunks: List[Dict]) -> None:
        """Create chunks in all stores.

        Args:
            notion_id: Parent note ID
            chunks: List of chunk dictionaries for graph stores, or text chunks for vector stores
        """
        for store_name, store in self.stores.items():
            try:
                from ..llm.models import TextChunk

                # Convert chunks to the appropriate format for each store type
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
                        # For dictionary chunks, use as-is
                        processed_chunks.append(chunk)
                    else:
                        # For raw text chunks, wrap in dict
                        processed_chunks.append({"text": str(chunk)})

                if store.__class__.__name__ in ["ChromaStore", "PineconeStore"]:
                    # For vector stores, we need the appropriate format
                    if store.__class__.__name__ == "ChromaStore":
                        # ChromaStore only needs text content
                        text_chunks = [chunk["text"] for chunk in processed_chunks]
                        store.create_chunks(notion_id, text_chunks)
                    else:
                        # PineconeStore needs full chunk dictionaries
                        store.create_chunks(notion_id, processed_chunks)
                else:
                    # For graph stores, pass all metadata
                    store.create_chunks(notion_id, processed_chunks)
                logger.info(f"Created chunks for {notion_id} in {store_name}")
            except Exception as e:
                logger.error(f"Failed to create chunks in {store_name}: {str(e)}")

    def create_relationships(
        self, notion_id: str, relationships: List[Dict[str, str]], timestamp: str
    ) -> None:
        """Create relationships in stores that support them.

        Args:
            notion_id: Parent note ID
            relationships: List of relationships
            timestamp: When the relationships were created
        """
        for store_name, store in self.stores.items():
            # Skip stores that don't support relationships
            store_config = self.config.get("document_stores", {}).get(store_name, {})
            if not store_config.get("supports_relationships", False):
                continue

            try:
                store.create_relationships(notion_id, relationships, timestamp)
                logger.info(f"Created relationships for {notion_id} in {store_name}")
            except Exception as e:
                logger.error(
                    f"Failed to create relationships in {store_name}: {str(e)}"
                )

    def get_note_hash(self, notion_id: str) -> Optional[str]:
        """Get note hash from any available store.

        Args:
            notion_id: Note ID

        Returns:
            Hash from first available store or None if not found
        """
        for store_name, store in self.stores.items():
            try:
                hash_value = store.get_note_hash(notion_id)
                if hash_value:
                    return hash_value
            except Exception as e:
                logger.error(f"Failed to get note hash from {store_name}: {str(e)}")
        return None

    def close(self) -> None:
        """Close all store connections."""
        for store_name, store in self.stores.items():
            try:
                store.close()
                logger.info(f"Closed connection to {store_name}")
            except Exception as e:
                logger.error(f"Error closing {store_name} connection: {str(e)}")

    def get_store(self, store_name: str) -> Optional[DocumentStore]:
        """Get a specific document store by name.

        Args:
            store_name: Name of the store to retrieve

        Returns:
            Document store if found and enabled, None otherwise
        """
        return self.stores.get(store_name)
