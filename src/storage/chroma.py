import hashlib
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Set, Union

import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

from ..config import Config
from ..llm.chunker import TextChunk
from .base import DocumentStore

logger = logging.getLogger(__name__)


class ChromaStore(DocumentStore):
    def add_entity_reference(
        self, entity_name: str, notion_id: str, timestamp: str
    ) -> None:
        """Add a reference from a note to an entity (no-op for Chroma).

        Args:
            entity_name: Name of the entity
            notion_id: ID of the note referencing the entity
            timestamp: When the reference was created
        """
        pass  # ChromaDB doesn't support relationships

    def remove_note_references(self, notion_id: str) -> Set[str]:
        """Remove all references from a note and return orphaned entities (no-op for Chroma).

        Args:
            notion_id: ID of the note

        Returns:
            Empty set as ChromaDB doesn't support relationships
        """
        return set()  # ChromaDB doesn't support relationships

    def delete_entities(self, entity_names: Set[str]) -> None:
        """Delete specified entities (no-op for Chroma).

        Args:
            entity_names: Set of entity names to delete
        """
        pass  # ChromaDB doesn't support relationships

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        store_config = (
            (Config._load_config() if config is None else config)
            .get("document_stores", {})
            .get("chroma", {})
            .get("settings", {})
        )

        self.vector_store = self._initialize_chroma_client(store_config)

    def _initialize_chroma_client(self, store_config: Dict[str, Any]) -> Chroma:
        """Initialize ChromaDB client with proper configuration.

        Args:
            store_config: Store-specific configuration dictionary

        Returns:
            Configured Chroma client instance
        """
        chroma_client = chromadb.HttpClient(
            settings=Settings(
                anonymized_telemetry=False,
                chroma_client_auth_provider="chromadb.auth.token_authn.TokenAuthClientProvider",
                chroma_client_auth_credentials=store_config.get(
                    "auth_token", Config.REQUIRED_ENV_VARS.get("CHROMA_AUTH_TOKEN")
                ),
            ),
            host=store_config.get("host", Config.REQUIRED_ENV_VARS.get("CHROMA_HOST")),
            port=store_config.get("port", "443"),
            ssl=store_config.get("ssl", True),
        )
        chroma_client.heartbeat()

        embeddings = OllamaEmbeddings(
            base_url=f"https://{Config.REQUIRED_ENV_VARS.get('OLLAMA_HOST')}",
            model=store_config.get("embedding_model", "nomic-embed-text"),
        )

        collection_name = store_config.get(
            "collection", Config.REQUIRED_ENV_VARS.get("CHROMA_COLLECTION", "notion")
        )
        chroma_client.get_or_create_collection(collection_name)

        return Chroma(
            client=chroma_client,
            collection_name=collection_name,
            embedding_function=embeddings,
        )

    def clean_document(self, notion_id: str) -> None:
        """Remove all nodes and relationships for a document.

        Args:
            notion_id: Notion page ID
        """
        self.delete_document(notion_id)

    def create_chunks(self, notion_id: str, chunks: List[Dict]) -> None:
        """Create note chunks with consistent metadata.

        Args:
            notion_id: Parent note ID
            chunks: List of chunk dictionaries with metadata
        """
        logger.debug(f"Storing {len(chunks)} chunks in Chroma")

        for index, chunk in enumerate(chunks):
            # Get text and metadata from chunk
            chunk_text = chunk["text"]
            metadata = chunk.get("metadata", {}).copy()

            # Ensure required metadata fields
            metadata.update(
                {
                    "notion_id": notion_id,
                    "chunk_number": index,
                    "total_chunks": len(chunks),
                }
            )

            # Add chunk metadata if available
            if chunk.get("summary"):
                metadata["summary"] = chunk["summary"]
                chunk_text = f"Summary: {chunk['summary']}\n\n{chunk_text}"

            # Add any additional metadata from the chunk
            for field in [
                "token_count",
                "chunking_model",
                "chunking_provider",
                "summary_model",
                "summary_provider",
                "embedding_model",
                "embedding_provider",
            ]:
                if chunk.get(field):
                    metadata[field] = chunk[field]

            document = Document(
                page_content=chunk_text,
                metadata=metadata,
                id=str(uuid.uuid4()),
            )

            self.vector_store.add_documents([document])

        logger.info(
            f"Successfully created {len(chunks)} chunks for document {notion_id}"
        )

    def create_relationships(
        self, notion_id: str, relationships: List[Dict[str, str]], timestamp: str
    ) -> None:
        """Create relationships (no-op for Chroma as it doesn't support graph relationships).

        Args:
            notion_id: Parent note ID
            relationships: List of relationships
        """
        pass  # ChromaDB doesn't support relationships

    def delete_document(self, notion_id: str) -> None:
        """Delete all chunks associated with a document.

        Args:
            notion_id: Notion page ID to delete
        """
        results = self.vector_store.get(where={"notion_id": {"$eq": notion_id}})
        if (
            "ids" in results and results["ids"]
        ):  # Check if there are actually IDs to delete
            logger.info(
                f"Deleting {len(results['ids'])} chunks for document {notion_id}"
            )
            self.vector_store.delete(ids=results["ids"])
        else:
            logger.info(f"No chunks found to delete for document {notion_id}")

    def get_document_hash(self, content: str) -> str:
        """Generate hash of document content.

        Args:
            content: Document content to hash

        Returns:
            SHA-256 hash of content
        """
        return hashlib.sha256(content.encode()).hexdigest()

    def get_documents(self, notion_id: Optional[str] = None) -> Iterator[Dict]:
        """Get all documents or a specific document.

        Args:
            notion_id: Optional Notion page ID to retrieve specific document

        Returns:
            Iterator of document dictionaries
        """
        # If notion_id is provided, filter for that document
        where = {"notion_id": {"$eq": notion_id}} if notion_id else None

        # Get all documents (or filtered by notion_id)
        results = self.vector_store.get(where=where)

        # Group chunks by notion_id
        docs_by_id = {}
        for i, metadata in enumerate(results["metadatas"]):
            notion_id = metadata["notion_id"]
            if notion_id not in docs_by_id:
                content = results["documents"][i]
                # Log retrieved content
                logger.debug("Chroma retrieved content for %s:\n%s", notion_id, content)
                logger.debug("Chroma content newlines count: %d", content.count("\n"))

                docs_by_id[notion_id] = {
                    "notion_id": notion_id,
                    "title": metadata["title"],
                    "content": content,
                }

        yield from docs_by_id.values()

    def get_chunks(self, notion_id: str) -> List[Dict]:
        """Get all chunks for a document.

        Args:
            notion_id: Parent note ID

        Returns:
            List of chunk dictionaries with content and metadata
        """
        results = self.vector_store.get(where={"notion_id": {"$eq": notion_id}})

        chunks = []
        for i, content in enumerate(results["documents"]):
            metadata = results["metadatas"][i]  # Get metadata for current chunk
            chunk_dict = {
                "content": content,
                "chunk_number": metadata.get(
                    "chunk_number", i
                ),  # Default to index if not set
                "total_chunks": metadata.get("total_chunks"),
                "summary": metadata.get("summary"),
                "token_count": metadata.get("token_count"),
                "chunking_model": metadata.get("chunking_model"),
                "chunking_provider": metadata.get("chunking_provider"),
                "summary_model": metadata.get("summary_model"),
                "summary_provider": metadata.get("summary_provider"),
                "embedding_model": metadata.get("embedding_model"),
                "embedding_provider": metadata.get("embedding_provider"),
            }
            chunks.append(chunk_dict)

        # Sort by chunk number
        return sorted(chunks, key=lambda x: x["chunk_number"])

    def get_document_metadata(self, notion_id: str) -> Optional[Dict]:
        """Get metadata for a document.

        Args:
            notion_id: Notion page ID

        Returns:
            Document metadata if found, None otherwise
        """
        results = self.vector_store.get(where={"notion_id": {"$eq": notion_id}})
        if results and results["metadatas"]:
            return results["metadatas"][0]
        return None

    def get_note_hash(self, notion_id: str) -> Optional[str]:
        """Get the stored hash for a note.

        Args:
            notion_id: Note ID

        Returns:
            Hash if found, None otherwise
        """
        metadata = self.get_document_metadata(notion_id)
        return metadata.get("hash") if metadata else None

    def clear_collection(self) -> None:
        """Clear the entire vector store collection."""
        self.vector_store.delete_collection()
        logger.info("Vector store collection cleared.")

    def close(self) -> None:
        """Close any connections (no-op for Chroma as it handles this internally)."""
        pass
