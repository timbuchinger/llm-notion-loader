import logging
import time
from datetime import datetime
from typing import Dict, Optional, Set, Union

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
        self.extractor = None

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

        # Check which stores need updating
        update_info = self._should_update_document(page_data, page_id)
        if not update_info["needs_update"]:
            logger.info(f"Document is up to date in all stores: {title} ({page_id})")
            self.stats.increment_counter("documents_processed")
            logger.info(
                f"{self.stats.get_processed_total()} of {self.stats.total_documents} files processed"
            )
            return

        store_statuses = update_info["store_statuses"]
        updating_stores = [
            store for store, needs_update in store_statuses.items() if needs_update
        ]
        logger.info(
            f"Updating document in stores {updating_stores}: {title} ({page_id})"
        )

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
        embedding = self.embeddings.embed_query(f"# {title}\n\n{markdown_content}")

        # Only extract relationships if enabled globally and any store supports them
        relationships = []
        if self.store_manager.config.get("relationship_extraction", {}).get(
            "enabled", False
        ):
            supports_relationships = any(
                store_config.get("supports_relationships", False)
                for store_config in self.store_manager.config.get(
                    "document_stores", {}
                ).values()
            )
            if supports_relationships:
                # Initialize extractor only when needed
                if self.extractor is None:
                    self.extractor = RelationshipExtractor()
                relationships = self.extractor.process_document(title, markdown_content)

        try:
            # Only clean stores that need updating
            for store_name in updating_stores:
                if store_name in self.store_manager.stores:
                    self.store_manager.stores[store_name].clean_document(page_id)
                    if store_name == "memgraph":
                        self.stats.increment_counter("memgraph_deletions")
                    elif store_name == "chroma":
                        self.stats.increment_counter("chroma_deletions")

            # Generate chunks once to use for both storage systems
            logger.info("Generating semantic chunks...")
            # Extract title and generate chunks
            title = self.notion.get_page_title(page_data)
            chunks = split_text(
                markdown_content,
                use_semantic=True,
                stats=self.stats,
                document_title=title,
            )

            # Update store-specific handling
            # Add consistent metadata to chunks
            for i, chunk in enumerate(chunks):
                chunk_metadata = {
                    "title": title,
                    "last_modified": last_modified,
                    "total_chunks": len(chunks),
                    "chunk_number": i,
                }
                chunk.metadata = chunk_metadata

            # Only update stores that need updating
            for store_name in updating_stores:
                if store_name == "pinecone" and "pinecone" in self.store_manager.stores:
                    self.store_manager.stores["pinecone"].create_chunks(page_id, chunks)

                elif (
                    store_name == "memgraph" and "memgraph" in self.store_manager.stores
                ):
                    self.stats.increment_counter("memgraph_nodes_created")
                    self.store_manager.stores["memgraph"].create_chunks(page_id, chunks)
                    self.stats.increment_counter("memgraph_nodes_created", len(chunks))

                    # Only create relationships if store needs update, supports them, and we have relationships
                    if (
                        store_name == "memgraph"
                        and self.store_manager.config["document_stores"][
                            "memgraph"
                        ].get("supports_relationships", False)
                        and relationships
                    ):
                        self.store_manager.stores["memgraph"].create_relationships(
                            page_id, relationships, last_modified
                        )
                        self.stats.increment_counter(
                            "memgraph_relationships_created", len(relationships)
                        )

                elif store_name == "chroma" and "chroma" in self.store_manager.stores:
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
        # Clean each store individually
        for store_name, store in self.store_manager.stores.items():
            store.clean_document(notion_id)
            if store_name == "memgraph":
                self.stats.increment_counter("memgraph_deletions")
            elif store_name == "chroma":
                self.stats.increment_counter("chroma_deletions")

    def _should_update_document(
        self,
        page_data: dict,
        notion_id: str,
    ) -> Dict[str, Union[bool, Dict[str, bool]]]:
        """Check if document needs updating based on last_modified timestamp.

        Args:
            page_data: Page data from Notion API
            notion_id: Notion page ID

        Returns:
            Dictionary containing:
                - needs_update: True if any store needs update
                - store_statuses: Dict of store names to update status
        """
        store_statuses = {}
        try:
            notion_last_updated = datetime.strptime(
                page_data["last_edited_time"], "%Y-%m-%dT%H:%M:%S.%fZ"
            )

            # Handle Memgraph store comparison
            if "memgraph" in self.store_manager.stores:
                try:
                    stored_last_modified = self.store_manager.stores[
                        "memgraph"
                    ].get_last_modified(notion_id)
                    needs_update = (
                        True
                        if not stored_last_modified
                        else datetime.strptime(
                            stored_last_modified, "%Y-%m-%d %H:%M:%S.%f"
                        )
                        < notion_last_updated
                    )
                    store_statuses["memgraph"] = needs_update
                except Exception as e:
                    logger.warning(f"Error checking Memgraph status: {str(e)}")
                    store_statuses["memgraph"] = True

            # Handle Chroma store comparison
            if "chroma" in self.store_manager.stores:
                try:
                    chroma_metadata = self.store_manager.stores[
                        "chroma"
                    ].get_document_metadata(notion_id)
                    needs_update = (
                        True
                        if not chroma_metadata
                        else datetime.strptime(
                            chroma_metadata["last_updated"], "%Y-%m-%d %H:%M:%S.%f"
                        )
                        < notion_last_updated
                    )
                    store_statuses["chroma"] = needs_update
                except Exception as e:
                    logger.warning(f"Error checking Chroma status: {str(e)}")
                    store_statuses["chroma"] = True

            # Handle Pinecone store comparison
            if "pinecone" in self.store_manager.stores:
                try:
                    # Query for the document in Pinecone
                    response = self.store_manager.stores["pinecone"].index.query(
                        vector=[0] * 768,  # Dummy vector to get metadata
                        filter={
                            "notion_id": notion_id,
                            "chunk_number": 0,
                        },  # Main document chunk
                        top_k=1,
                        include_metadata=True,
                        namespace=self.store_manager.stores["pinecone"].namespace,
                    )

                    needs_update = True
                    if (
                        response.matches
                        and "last_modified" in response.matches[0].metadata
                    ):
                        pinecone_last_updated = datetime.strptime(
                            response.matches[0].metadata["last_modified"],
                            "%Y-%m-%d %H:%M:%S.%f",
                        )
                        needs_update = pinecone_last_updated < notion_last_updated
                    store_statuses["pinecone"] = needs_update
                except Exception as e:
                    logger.warning(f"Error checking Pinecone status: {str(e)}")
                    store_statuses["pinecone"] = True

            # Determine if any store needs updating
            needs_update = any(store_statuses.values())
            return {"needs_update": needs_update, "store_statuses": store_statuses}

        except (ValueError, KeyError, TypeError) as e:
            # If we can't parse dates, update all stores to be safe
            logger.warning(
                f"Error comparing timestamps, will update all stores: {str(e)}"
            )
            return {
                "needs_update": True,
                "store_statuses": {name: True for name in self.store_manager.stores},
            }

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

        for store_name, store in self.store_manager.stores.items():
            try:
                # Use store-specific clear methods
                if store_name == "chroma":
                    store.clear_collection()
                    logger.info("Cleared Chroma database")
                else:
                    # Other stores use clean_document with wildcard
                    store.clean_document("*")
                    logger.info(f"Cleared {store_name} database")
            except Exception as e:
                logger.error(f"Error clearing {store_name} database: {str(e)}")

        logger.info("Database clearing completed")
