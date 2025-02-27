import logging
import time
from datetime import datetime
from typing import Dict, Optional, Set

from langchain_ollama import OllamaEmbeddings

from .api.notion import NotionAPI
from .config import Config
from .llm.extractor import RelationshipExtractor
from .storage.store_manager import StoreManager
from .utils.stats import get_stats
from .utils.text import clean_markdown, should_skip_document, split_text

logger = logging.getLogger(__name__)


class NotionSync:
    def __init__(self):
        self.stats = get_stats()
        self.notion = NotionAPI(stats=self.stats)
        self.store_manager = StoreManager()
        self.embeddings = OllamaEmbeddings(
            base_url=f"https://{Config.REQUIRED_ENV_VARS['OLLAMA_HOST']}",
            model="nomic-embed-text",
        )
        self.extractor = RelationshipExtractor()

    def _process_page(self, page_id: str, page_data: dict) -> None:
        """Process a single Notion page.

        Args:
            page_id: Notion page ID
            page_data: Page data from Notion API
        """
        # Get page content and metadata
        title = self.notion.get_page_title(page_data)
        logger.info(f"Starting to process document: {title} ({page_id})")
        markdown_content = self.notion.get_page_markdown(page_id)

        if not markdown_content:
            logger.warning(f"Empty content for page: {title} ({page_id})")
            self._clean_empty_document(page_id)
            self.stats.increment_counter("documents_errored")
            return

        markdown_content = clean_markdown(markdown_content)

        if should_skip_document(markdown_content):
            logger.warning(f"Skipping page marked with #skip: {title} ({page_id})")
            self._clean_empty_document(page_id)
            self.stats.increment_counter("documents_skipped")
            self.stats.increment_counter("documents_processed")
            logger.info(
                f"{self.stats.get_processed_total()} of {self.stats.total_documents} files processed"
            )
            return

        final_content = f"# {title}\n\n{markdown_content}"

        # Check if document needs updating
        if not self._should_update_document(page_data, page_id):
            logger.info(f"Document is up to date: {title} ({page_id})")
            self.stats.increment_counter("documents_processed")
            logger.info(
                f"{self.stats.get_processed_total()} of {self.stats.total_documents} files processed"
            )
            return

        logger.info(f"Updating document: {title} ({page_id})")

        # Get last modified time with fallback to current time
        try:
            last_modified = page_data.get("last_edited_time")
            if not last_modified:
                raise ValueError("No last_edited_time in page data")
            # Convert Notion's ISO format to our datetime string format
            last_modified = datetime.strptime(
                last_modified, "%Y-%m-%dT%H:%M:%S.%fZ"
            ).strftime("%Y-%m-%d %H:%M:%S.%f")
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(
                f"Could not parse last_edited_time, using current time: {str(e)}"
            )
            last_modified = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        # Generate embeddings and extract relationships
        embedding = self.embeddings.embed_query(final_content)
        relationships = self.extractor.process_document(title, markdown_content)

        try:
            # Clean existing data and track deletions
            self.store_manager.clean_document(page_id)
            if "memgraph" in self.store_manager.stores:
                self.stats.increment_counter("memgraph_deletions")
            if "chroma" in self.store_manager.stores:
                self.stats.increment_counter("chroma_deletions")

            # Generate chunks once to use for both storage systems
            logger.info("Generating semantic chunks...")
            # Generate chunks
            chunks = split_text(final_content, use_semantic=True, stats=self.stats)

            # Update stores with chunks and metadata
            self.store_manager.create_note(
                page_id, title, final_content, embedding, last_modified
            )

            # Update Memgraph if enabled
            if "memgraph" in self.store_manager.stores:
                self.stats.increment_counter("memgraph_nodes_created")
                self.store_manager.create_chunks(page_id, chunks)
                self.stats.increment_counter("memgraph_nodes_created", len(chunks))

                self.store_manager.create_relationships(
                    page_id, relationships, last_modified
                )
                self.stats.increment_counter(
                    "memgraph_relationships_created", len(relationships)
                )

            # Update Chroma if enabled
            if "chroma" in self.store_manager.stores:
                self.store_manager.stores["chroma"].update_document(
                    page_id, chunks, title, last_modified
                )
                self.stats.increment_counter("chroma_insertions", len(chunks))

            self.stats.increment_counter("documents_processed")
            logger.info(
                f"{self.stats.get_processed_total()} of {self.stats.total_documents} files processed"
            )
            logger.info(f"Document successfully processed: {title} ({page_id})")
        except Exception as e:
            logger.error(f"Error processing document {page_id}: {str(e)}")
            self.stats.increment_counter("documents_errored")

    def _clean_empty_document(self, notion_id: str) -> None:
        """Clean up empty or skipped documents from storage.

        Args:
            notion_id: Notion page ID
        """
        self.store_manager.clean_document(notion_id)
        if "memgraph" in self.store_manager.stores:
            self.stats.increment_counter("memgraph_deletions")
        if "chroma" in self.store_manager.stores:
            self.stats.increment_counter("chroma_deletions")

    def _should_update_document(
        self,
        page_data: dict,
        notion_id: str,
    ) -> bool:
        """Check if document needs updating based on last_modified timestamp.

        Args:
            page_data: Page data from Notion API
            notion_id: Notion page ID

        Returns:
            True if document should be updated, False otherwise
        """
        try:
            notion_last_updated = datetime.strptime(
                page_data["last_edited_time"], "%Y-%m-%dT%H:%M:%S.%fZ"
            )

            # Handle Memgraph store comparison
            if "memgraph" in self.store_manager.stores:
                stored_last_modified = self.store_manager.stores[
                    "memgraph"
                ].get_last_modified(notion_id)
                if not stored_last_modified:
                    return True

                stored_last_updated = datetime.strptime(
                    stored_last_modified, "%Y-%m-%d %H:%M:%S.%f"
                )
                if stored_last_updated < notion_last_updated:
                    return True

            # Handle Chroma store comparison independently
            if "chroma" in self.store_manager.stores:
                chroma_metadata = self.store_manager.stores[
                    "chroma"
                ].get_document_metadata(notion_id)
                if not chroma_metadata:
                    return True

                chroma_last_updated = datetime.strptime(
                    chroma_metadata["last_updated"], "%Y-%m-%d %H:%M:%S.%f"
                )
                if chroma_last_updated < notion_last_updated:
                    return True

            # If neither store needs an update
            return False

        except (ValueError, KeyError, TypeError) as e:
            # If we can't parse dates, update to be safe
            logger.warning(
                f"Error comparing timestamps, will update document: {str(e)}"
            )
            return True

    def find_deleted_documents(self, notion_pages: list) -> Set[str]:
        """Find documents that exist in storage but not in Notion.

        Args:
            notion_pages: List of pages from Notion API

        Returns:
            Set of document IDs that should be deleted
        """
        notion_ids = {page.get("id") for page in notion_pages if page.get("id")}

        if "memgraph" in self.store_manager.stores:
            stored_ids = {
                doc["notion_id"]
                for doc in self.store_manager.stores["memgraph"].get_documents()
            }
            return stored_ids - notion_ids

        return set()

    def _get_deletion_impact(self, notion_id: str) -> Dict:
        """Get information about what would be deleted for a document.

        Args:
            notion_id: Notion page ID

        Returns:
            Dict containing deletion impact information
        """
        if "memgraph" not in self.store_manager.stores:
            return {}

        store = self.store_manager.stores["memgraph"]
        with store.driver.session() as session:
            # Get note title
            result = session.run(
                """
                MATCH (n:Note {id: $notion_id})
                RETURN n.title as title
                """,
                notion_id=notion_id,
            ).single()

            # Count chunks
            chunks = session.run(
                """
                MATCH (n:Note {id: $notion_id})-[:HAS_CHUNK]->(c:NoteChunk)
                RETURN count(c) as chunk_count
                """,
                notion_id=notion_id,
            ).single()

            # Count relationships that would be affected
            relationships = session.run(
                """
                MATCH (sr:SourceReference {note_id: $notion_id})
                RETURN count(sr) as ref_count
                """,
                notion_id=notion_id,
            ).single()

            return {
                "title": result["title"] if result else None,
                "chunk_count": chunks["chunk_count"] if chunks else 0,
                "relationship_count": (
                    relationships["ref_count"] if relationships else 0
                ),
            }

    def sync(self) -> None:
        """Synchronize all Notion pages to configured document stores."""
        logger.info("Starting Notion sync...")

        # Reset stats before starting new sync
        self.stats.reset()

        try:
            pages = self.notion.search_pages()
            self.stats.total_documents = len(pages)
            logger.info(f"Found {len(pages)} pages to process")

            # Check for deleted documents
            if "memgraph" in self.store_manager.stores:
                deleted_ids = self.find_deleted_documents(pages)
                for notion_id in deleted_ids:
                    impact = self._get_deletion_impact(notion_id)
                    if impact.get("title"):
                        logger.warning(
                            f"Document deletion detected: {impact['title']} ({notion_id})\n"
                            f"Would delete:\n"
                            f"- {impact['chunk_count']} chunks\n"
                            f"- {impact['relationship_count']} relationships"
                        )
                    else:
                        logger.warning(
                            f"Document deletion detected for unknown title ({notion_id})"
                        )

            # Process current pages
            for page in pages:
                try:
                    self._process_page(page.get("id"), page)
                except Exception as e:
                    logger.error(f"Error processing page {page.get('id')}: {str(e)}")
                    self.stats.increment_counter("documents_errored")
                    continue

        except Exception as e:
            logger.error(f"Sync failed: {str(e)}")
            raise
        finally:
            self.store_manager.close()
            self.stats.mark_complete()

        logger.info("Sync completed successfully")
        logger.info("\n" + self.stats.generate_report())

    def clear_databases(self) -> None:
        """Clear all document stores."""
        logger.info("Clearing databases...")
        if "chroma" in self.store_manager.stores:
            self.store_manager.stores["chroma"].clear_collection()
        if "memgraph" in self.store_manager.stores:
            self.store_manager.stores["memgraph"].clean_document(
                "*"
            )  # Wildcard to clean all documents
        logger.info("Databases cleared")
