from abc import ABC, abstractmethod
from typing import Dict, Iterator, List, Optional, Set


class DocumentStore(ABC):
    """Base interface for document stores."""

    @abstractmethod
    def clean_document(self, notion_id: str) -> None:
        """Remove all nodes and relationships for a document.

        Args:
            notion_id: Notion page ID
        """
        pass

    @abstractmethod
    def create_chunks(self, notion_id: str, chunks: List[Dict]) -> None:
        """Create note chunks with consistent metadata.

        Args:
            notion_id: Parent note ID
            chunks: List of chunk dictionaries containing:
                - text: Chunk text content
                - metadata: Dictionary containing:
                    - title: Document title
                    - last_modified: Last modification timestamp
                    - chunk_number: Position in document (0-based)
                    - total_chunks: Total number of chunks in document
                    - token_count: Number of tokens in chunk
                    - chunking_model: Model used for semantic chunking
                    - chunking_provider: Provider used for chunking
                    - summary: Optional chunk summary
                    - summary_model: Optional model used for summary
                    - summary_provider: Optional provider used for summary
                    - embedding: Vector embedding
                    - embedding_model: Optional model used for embedding
                    - embedding_provider: Optional provider used for embedding
        """
        pass

    @abstractmethod
    def create_relationships(
        self, notion_id: str, relationships: List[Dict[str, str]], timestamp: str
    ) -> None:
        """Create entity nodes and relationships with reference tracking.

        Args:
            notion_id: Parent note ID
            relationships: List of relationship dictionaries
            timestamp: Timestamp when the relationships were created
        """
        pass

    @abstractmethod
    def add_entity_reference(
        self, entity_name: str, notion_id: str, timestamp: str
    ) -> None:
        """Add a reference from a note to an entity.

        Args:
            entity_name: Name of the entity
            notion_id: ID of the note referencing the entity
            timestamp: When the reference was created
        """
        pass

    @abstractmethod
    def remove_note_references(self, notion_id: str) -> Set[str]:
        """Remove all references from a note and return orphaned entities.

        Args:
            notion_id: ID of the note

        Returns:
            Set of entity names that no longer have any references
        """
        pass

    @abstractmethod
    def delete_entities(self, entity_names: Set[str]) -> None:
        """Delete specified entities.

        Args:
            entity_names: Set of entity names to delete
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close any open connections."""
        pass

    @abstractmethod
    def get_documents(self, notion_id: Optional[str] = None) -> Iterator[Dict]:
        """Get all documents or a specific document.

        Args:
            notion_id: Optional Notion page ID to retrieve specific document

        Returns:
            Iterator of document dictionaries containing:
                - notion_id: Notion page ID
                - title: Document title
                - content: Document content
        """
        pass

    @abstractmethod
    def get_chunks(self, notion_id: str) -> List[Dict]:
        """Get all chunks for a document.

        Args:
            notion_id: Parent note ID

        Returns:
            List of chunk dictionaries containing:
                - content: Formatted chunk text content with summary prefix if available
                - chunk_number: Position in document (0-based)
                - summary: Optional chunk summary
                - token_count: Optional token count
        """
        pass
