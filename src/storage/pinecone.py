import logging
import time
import uuid
from typing import Dict, Iterator, List, Optional, Set

from pinecone import Pinecone, PineconeException

from ..config import Config
from ..llm.models import TextChunk
from .base import DocumentStore

logger = logging.getLogger(__name__)


class PineconeStore(DocumentStore):
    """Pinecone implementation of document store."""

    def __init__(self, config: Optional[Dict] = None):
        """Initialize Pinecone store with configuration.

        Args:
            config: Optional configuration override
        """
        store_config = (
            (Config._load_config() if config is None else config)
            .get("document_stores", {})
            .get("pinecone", {})
            .get("settings", {})
        )

        # Create Pinecone client instance
        api_key = store_config.get(
            "api_key", Config.REQUIRED_ENV_VARS.get("PINECONE_API_KEY")
        )
        self.pc = Pinecone(api_key=api_key)

        # Get index and namespace
        index_name = store_config.get(
            "index_name", Config.REQUIRED_ENV_VARS.get("PINECONE_INDEX")
        )
        self.namespace = store_config.get(
            "namespace", Config.REQUIRED_ENV_VARS.get("PINECONE_NAMESPACE", "")
        )
        self.index = self.pc.Index(index_name)

        logger.info(
            f"Initialized Pinecone store with index: {index_name}, namespace: {self.namespace}"
        )

    def clean_document(self, notion_id: str) -> None:
        """Remove all vectors for a document.

        Args:
            notion_id: Notion page ID
        """
        # Initialize counters
        total_deleted = 0
        page_size = 10000

        # Keep querying and deleting until no more vectors found
        while True:
            response = self.index.query(
                vector=[0] * 768,  # Dummy vector to get IDs
                filter={"notion_id": notion_id},
                top_k=page_size,
                include_metadata=True,
                namespace=self.namespace,
            )

            if not response.matches:
                break

            ids_to_delete = [match.id for match in response.matches]
            self.index.delete(ids=ids_to_delete, namespace=self.namespace)

            total_deleted += len(ids_to_delete)

            # If we got less than page_size results, we're done
            if len(ids_to_delete) < page_size:
                break

            # Small delay to prevent rate limiting
            time.sleep(0.1)

        # Add delay before verification for eventual consistency
        initial_delay = 2.0
        time.sleep(initial_delay)

        # Verify cleanup with retries
        max_retries = 5
        base_delay = 2.0

        for attempt in range(max_retries):
            verification = self.index.query(
                vector=[0] * 768,
                filter={"notion_id": notion_id},
                top_k=1,
                include_metadata=True,
                namespace=self.namespace,
            )

            if not verification.matches:
                if attempt > 0:
                    logger.debug(
                        f"Document cleanup verification succeeded on attempt {attempt + 1}"
                    )
                break

            if attempt == max_retries - 1:
                # Last attempt failed
                logger.error(
                    f"Document cleanup failed after {max_retries} attempts - "
                    f"vectors still exist for {notion_id}"
                )
                raise Exception(f"Failed to clean document {notion_id}")

            # Wait with exponential backoff before next attempt
            delay = base_delay * (2**attempt)
            logger.debug(
                f"Document cleanup verification attempt {attempt + 1} failed, "
                f"waiting {delay}s before retry"
            )
            time.sleep(delay)

        logger.info(
            f"Cleaned document {notion_id} from Pinecone - removed {total_deleted} vectors"
        )

    def create_chunks(
        self, notion_id: str, chunks: List[Dict], batch_size: int = 100
    ) -> None:
        """Create note chunks.

        Args:
            notion_id: Parent note ID
            chunks: List of chunk dictionaries
            batch_size: Number of vectors to upsert in each batch
        """
        logger.debug(f"Storing {len(chunks)} chunks in Pinecone for {notion_id}")

        if not chunks:
            logger.warning(f"No chunks provided for document {notion_id}")
            return

        total_chunks = len(chunks)
        processed_chunks = 0
        chunk_ids = []

        # Process chunks in batches
        for start_idx in range(0, total_chunks, batch_size):
            vectors = []
            batch = chunks[start_idx : start_idx + batch_size]

            for chunk in batch:
                # First handle TextChunk objects properly
                if isinstance(chunk, TextChunk):
                    chunk_id = str(uuid.uuid4())
                    chunk_ids.append(chunk_id)

                    # Get the base metadata from the chunk
                    metadata = (
                        chunk.metadata.copy() if hasattr(chunk, "metadata") else {}
                    )

                    # Add or update required fields, including summary
                    metadata_update = {
                        "notion_id": notion_id,
                        "chunk_number": processed_chunks,
                        "total_chunks": total_chunks,
                        "text": chunk.format_with_summary(),
                    }
                    if chunk.summary:
                        metadata_update["summary"] = chunk.summary

                    metadata.update(metadata_update)
                else:
                    # Fall back to dict handling
                    if "text" not in chunk:
                        logger.warning(
                            f"Skipping chunk without text content for {notion_id}"
                        )
                        continue

                    chunk_id = str(uuid.uuid4())
                    chunk_ids.append(chunk_id)

                    metadata = chunk.get("metadata", {}).copy()

                    # Ensure chunk has valid chunk_number from input metadata
                    chunk_number = metadata.get("chunk_number")
                    if chunk_number is None or chunk_number == "":
                        chunk_number = processed_chunks
                        logger.warning(
                            f"Found missing/invalid chunk_number for {notion_id}, using {chunk_number}"
                        )
                    else:
                        try:
                            chunk_number = int(chunk_number)
                        except (ValueError, TypeError):
                            chunk_number = processed_chunks
                            logger.warning(
                                f"Invalid chunk_number format for {notion_id}, using {chunk_number}"
                            )

                    # Format text with summary for dict input, mirroring TextChunk behavior
                    text_parts = []
                    if "summary" in chunk:
                        metadata["summary"] = chunk["summary"]
                        text_parts.extend([chunk["summary"], ""])

                    if "title" in chunk:
                        text_parts.extend([f"# {chunk['title']}", ""])

                    text_parts.append(chunk["text"])
                    formatted_text = "\n".join(text_parts)

                    metadata.update(
                        {
                            "notion_id": notion_id,
                            "chunk_number": chunk_number,
                            "total_chunks": total_chunks,
                            "text": formatted_text,
                        }
                    )

                # Add optional metadata from either TextChunk object or dict
                if isinstance(chunk, TextChunk):
                    # Add TextChunk fields if they have values
                    for field in [
                        "token_count",
                        "chunking_model",
                        "chunking_provider",
                        "summary_model",
                        "summary_provider",
                        "embedding_model",
                        "embedding_provider",
                    ]:
                        value = getattr(chunk, field, None)
                        if value is not None:
                            metadata[field] = value
                else:
                    # Add dict fields if they exist and aren't None
                    for field in [
                        "token_count",
                        "chunking_model",
                        "chunking_provider",
                        "summary_model",
                        "summary_provider",
                    ]:
                        if chunk.get(field) is not None:
                            metadata[field] = chunk[field]

                # Get embedding (handle both TextChunk and dict)
                if isinstance(chunk, TextChunk):
                    embedding = chunk.embedding
                else:
                    embedding = chunk.get("embedding", [])

                if not embedding:
                    logger.warning(
                        f"Skipping chunk {processed_chunks} without embedding for {notion_id}"
                    )
                    continue

                vectors.append(
                    {
                        "id": chunk_id,
                        "values": embedding,
                        "metadata": metadata,
                    }
                )

                processed_chunks += 1

            # Batch upsert
            if vectors:
                try:
                    self.index.upsert(vectors=vectors, namespace=self.namespace)
                    logger.debug(
                        f"Uploaded batch of {len(vectors)} chunks for {notion_id}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to upsert chunk batch for {notion_id}: {str(e)}"
                    )
                    raise

        # Verify all chunks were created
        if processed_chunks > 0:
            for chunk_id in chunk_ids:
                max_retries = 5
                base_delay = 2.0  # Start with 2 second delay
                initial_delay = 2.0  # Initial delay before first attempt

                # Add initial delay for eventual consistency
                time.sleep(initial_delay)

                for attempt in range(max_retries):
                    try:
                        # Use query to verify by ID
                        response = self.index.query(
                            vector=[0] * 768,  # Dummy vector for metadata query
                            filter={
                                "notion_id": notion_id,
                                "chunk_number": processed_chunks
                                - (len(chunk_ids) - chunk_ids.index(chunk_id)),
                            },
                            top_k=1,
                            include_metadata=True,
                            namespace=self.namespace,
                        )

                        if response.matches:
                            if attempt > 0:
                                logger.debug(
                                    f"Verified chunk {chunk_id} on attempt {attempt + 1}"
                                )
                            break

                        # If no matches found, wait with exponential backoff
                        delay = base_delay * (2**attempt)
                        logger.debug(
                            f"Chunk {chunk_id} not found on attempt {attempt + 1}, "
                            f"waiting {delay}s before retry"
                        )
                        time.sleep(delay)

                    except PineconeException as e:
                        if attempt == max_retries - 1:
                            logger.error(
                                f"Failed to verify chunk {chunk_id} after {max_retries} "
                                f"attempts: {str(e)}"
                            )
                            raise
                        delay = base_delay * (2**attempt)
                        time.sleep(delay)
                    except Exception as e:
                        logger.error(
                            f"Unexpected error verifying chunk {chunk_id}: {str(e)}"
                        )
                        raise
                else:
                    # Loop completed without finding the chunk
                    logger.warning(
                        f"Note creation successful but verification timed out for chunk {chunk_id}. "
                        "The document may still be available after indexing completes."
                    )
                    # Don't raise an exception since the upsert was successful

            logger.info(
                f"Successfully created and verified {processed_chunks} chunks for document {notion_id}"
            )
        else:
            logger.warning(f"No chunks were created for document {notion_id}")

    def create_relationships(
        self, notion_id: str, relationships: List[Dict[str, str]], timestamp: str
    ) -> None:
        """Store relationships in metadata.

        Args:
            notion_id: Parent note ID
            relationships: List of relationships
            timestamp: When relationships were created
        """
        # Query for all chunks of the document
        response = self.index.query(
            vector=[0] * 768,  # Dummy vector to get metadata
            filter={"notion_id": notion_id},
            top_k=10000,
            include_metadata=True,
            namespace=self.namespace,
        )

        if response.matches:
            # Add relationships to all chunks' metadata
            for match in response.matches:
                doc_id = match.id
                metadata = match.metadata
                metadata["relationships"] = relationships
                metadata["relationship_timestamp"] = timestamp

                # Re-upsert with updated metadata
                self.index.upsert(
                    vectors=[
                        {
                            "id": doc_id,
                            "values": match.values,
                            "metadata": metadata,
                        }
                    ],
                    namespace=self.namespace,
                )

            logger.info(
                f"Added {len(relationships)} relationships to all chunks of document {notion_id}"
            )

    def get_documents(self, notion_id: Optional[str] = None) -> Iterator[Dict]:
        """Get all documents or a specific document.

        Args:
            notion_id: Optional Notion page ID

        Returns:
            Iterator of document dictionaries
        """
        filter_dict = {}
        if notion_id:
            filter_dict["notion_id"] = notion_id

        # Get list of all unique notion_ids if no specific id given
        if not notion_id:
            # Query all chunks to get unique notion_ids
            response = self.index.query(
                vector=[0] * 768,  # Dummy vector for metadata query
                filter={},
                top_k=10000,
                include_metadata=True,
                namespace=self.namespace,
            )

            # Filter matches that have valid notion_id in metadata
            notion_ids = set()
            for match in response.matches:
                try:
                    if match.metadata and "notion_id" in match.metadata:
                        notion_ids.add(match.metadata["notion_id"])
                    else:
                        logger.warning(
                            f"Document found without notion_id in metadata: {match.id}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Error accessing metadata for document {match.id}: {str(e)}"
                    )
                    continue

            if not notion_ids:
                logger.warning("No documents found with valid notion_id in metadata")
                return
        else:
            notion_ids = {notion_id}

        # For each notion_id, get the first chunk (contains title)
        for nid in notion_ids:
            try:
                response = self.index.query(
                    vector=[0] * 768,
                    filter={"notion_id": nid, "chunk_number": 0},
                    top_k=1,
                    include_metadata=True,
                    namespace=self.namespace,
                )
                if response.matches:
                    metadata = response.matches[0].metadata
                    if not metadata:
                        logger.warning(f"Document {nid} has no metadata")
                        continue

                    if "notion_id" not in metadata:
                        logger.warning(f"Document {nid} missing notion_id in metadata")
                        continue

                    if "text" not in metadata:
                        logger.warning(f"Document {nid} missing text in metadata")
                        continue

                    yield {
                        "notion_id": metadata["notion_id"],
                        "title": metadata.get("title", ""),
                        "content": metadata["text"],
                    }
            except Exception as e:
                logger.warning(f"Error fetching document {nid}: {str(e)}")
                continue

    def get_chunks(self, notion_id: str) -> List[Dict]:
        """Get all chunks for a document.

        Args:
            notion_id: Parent note ID

        Returns:
            List of chunk dictionaries
        """
        # Query for chunks with matching notion_id
        response = self.index.query(
            vector=[0] * 768,  # Dummy vector to get metadata
            filter={"notion_id": notion_id},
            top_k=10000,
            include_metadata=True,
            namespace=self.namespace,
        )

        # Sort chunks by chunk_number
        chunks = []
        for match in response.matches:
            metadata = match.metadata
            chunk_dict = {
                "content": metadata["text"],
                "chunk_number": metadata["chunk_number"],
            }

            # Add optional fields if present
            for field in ["summary", "token_count"]:
                if field in metadata:
                    chunk_dict[field] = metadata[field]

            chunks.append(chunk_dict)

        # Sort by chunk number and return
        return sorted(chunks, key=lambda x: x["chunk_number"])

    def add_entity_reference(
        self, entity_name: str, notion_id: str, timestamp: str
    ) -> None:
        """Add a reference from a note to an entity.

        Args:
            entity_name: Name of the entity
            notion_id: ID of the note referencing the entity
            timestamp: When the reference was created
        """
        # Query for all chunks by notion_id
        response = self.index.query(
            vector=[0] * 768,  # Dummy vector to get metadata
            filter={"notion_id": notion_id},
            top_k=10000,
            include_metadata=True,
            namespace=self.namespace,
        )

        if response.matches:
            # Update all chunks with entity reference
            for match in response.matches:
                doc_id = match.id
                metadata = match.metadata

                if "entity_references" not in metadata:
                    metadata["entity_references"] = {}

                metadata["entity_references"][entity_name] = timestamp

                # Re-upsert with updated metadata
                self.index.upsert(
                    vectors=[
                        {
                            "id": doc_id,
                            "values": match.values,
                            "metadata": metadata,
                        }
                    ],
                    namespace=self.namespace,
                )

            logger.info(
                f"Added entity reference {entity_name} to all chunks of document {notion_id}"
            )

    def remove_note_references(self, notion_id: str) -> Set[str]:
        """Remove all references from a note and return orphaned entities.

        Args:
            notion_id: ID of the note

        Returns:
            Set of entity names that no longer have any references
        """
        # Query for all chunks by notion_id
        response = self.index.query(
            vector=[0] * 768,  # Dummy vector to get metadata
            filter={"notion_id": notion_id},
            top_k=10000,
            include_metadata=True,
            namespace=self.namespace,
        )

        orphaned = set()
        if response.matches:
            # Get orphaned entities from first chunk
            metadata = response.matches[0].metadata
            if "entity_references" in metadata:
                orphaned = set(metadata["entity_references"].keys())

            # Remove references from all chunks
            for match in response.matches:
                doc_id = match.id
                metadata = match.metadata

                if "entity_references" in metadata:
                    del metadata["entity_references"]

                # Re-upsert without the references
                self.index.upsert(
                    vectors=[
                        {
                            "id": doc_id,
                            "values": match.values,
                            "metadata": metadata,
                        }
                    ],
                    namespace=self.namespace,
                )

        return orphaned

    def delete_entities(self, entity_names: Set[str]) -> None:
        """Delete specified entities.

        Args:
            entity_names: Set of entity names to delete
        """
        # Since entities are stored in metadata, we don't need an explicit deletion
        # They are removed when their references are removed
        pass

    def close(self) -> None:
        """Clean up Pinecone resources."""
        # Pinecone client doesn't require explicit cleanup
        pass
