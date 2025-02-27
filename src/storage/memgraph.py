import logging
from typing import Dict, Iterator, List, Optional, Set

from neo4j import GraphDatabase

from ..config import Config
from .base import DocumentStore

logger = logging.getLogger(__name__)


class MemgraphStore(DocumentStore):
    def __init__(self, config: Optional[Dict] = None):
        """Initialize Memgraph store with database connection."""
        store_config = (
            (Config._load_config() if config is None else config)
            .get("document_stores", {})
            .get("memgraph", {})
            .get("settings", {})
        )

        self.driver = GraphDatabase.driver(
            store_config.get("uri", Config.REQUIRED_ENV_VARS.get("MEMGRAPH_URI")),
            auth=(
                store_config.get("user", Config.REQUIRED_ENV_VARS.get("MEMGRAPH_USER")),
                store_config.get(
                    "password", Config.REQUIRED_ENV_VARS.get("MEMGRAPH_PASSWORD")
                ),
            ),
        )
        self._initialize_constraints()

    def _initialize_constraints(self) -> None:
        """Initialize Memgraph with required constraints."""
        with self.driver.session() as session:
            try:
                # Set up constraints and indexes
                session.run("CREATE CONSTRAINT ON (n:Note) ASSERT n.id IS UNIQUE")
                session.run("CREATE CONSTRAINT ON (c:NoteChunk) ASSERT c.id IS UNIQUE")
                session.run("CREATE CONSTRAINT ON (e:Entity) ASSERT e.name IS UNIQUE")
                logger.info("Memgraph initialized with constraints")
            except Exception as e:
                logger.error(f"Error setting up Memgraph constraints: {str(e)}")
                raise

    def clean_document(self, notion_id: str) -> None:
        """Remove all nodes and relationships for a document."""
        with self.driver.session() as session:
            # First delete note and direct relationships
            session.run(
                """
                MATCH (n:Note {id: $notion_id})
                OPTIONAL MATCH (n)-[:HAS_CHUNK]->(chunk:NoteChunk)
                OPTIONAL MATCH (chunk)-[next:NEXT_CHUNK]->()
                DETACH DELETE n, chunk, next
                """,
                notion_id=notion_id,
            )

            # Find orphaned entities after removing references
            orphaned = self.remove_note_references(notion_id)
            if orphaned:
                self.delete_entities(orphaned)

            logger.info(
                f"Cleaned document {notion_id} and its relationships from Memgraph"
            )

    def create_note(
        self,
        notion_id: str,
        title: str,
        content: str,
        embedding: List[float],
        last_modified: str,
    ) -> None:
        """Create a new note node."""
        # Debug log content before storage
        logger.debug("Memgraph pre-storage content for %s:\n%s", notion_id, content)
        logger.debug("Memgraph content newlines count: %d", content.count("\n"))
        logger.debug(f"Note embedding size: {len(embedding)}")

        with self.driver.session() as session:
            session.run(
                """
                CREATE (n:Note {
                    id: $notion_id,
                    title: $title,
                    content: $content,
                    embedding: $embedding,
                    last_modified: $last_modified
                })
                """,
                notion_id=notion_id,
                title=title,
                content=content,
                embedding=embedding,
                last_modified=last_modified,
            )
            logger.info(f"Created note {notion_id} in Memgraph")

    def create_chunks(self, notion_id: str, chunks: List[Dict]) -> None:
        """Create note chunk nodes and relationships."""
        logger.info(f"Creating chunks for note {notion_id}")
        logger.info(f"Total chunks to process: {len(chunks)}")

        with self.driver.session() as session:
            previous_chunk_id = None

            for i, chunk in enumerate(chunks):
                chunk_id = f"{notion_id}-chunk-{i}"

                # Log chunk data for debugging
                logger.info(f"Processing chunk {i} for note {notion_id}")
                logger.info(f"Available chunk data: {chunk.keys()}")
                if "text" in chunk:
                    logger.info(f"Chunk text length: {len(chunk['text'])}")
                if "embedding" in chunk:
                    logger.info(f"Chunk embedding size: {len(chunk['embedding'])}")
                    if not isinstance(chunk["embedding"], list):
                        logger.error(
                            f"Embedding is not a list: {type(chunk['embedding'])}"
                        )
                else:
                    logger.warning(f"No embedding found for chunk {i}")

                # Create chunk node with all metadata
                session.run(
                    """
                    MATCH (n:Note {id: $notion_id})
                    CREATE (c:NoteChunk {
                        id: $chunk_id,
                        content: $content,
                        parentNote: $notion_id,
                        chunkNumber: $chunk_number,
                        token_count: $token_count,
                        chunking_model: $chunking_model,
                        chunking_provider: $chunking_provider,
                        summary: $summary,
                        summary_model: $summary_model,
                        summary_provider: $summary_provider,
                        embedding_model: $embedding_model,
                        embedding_provider: $embedding_provider
                    })
                    SET c.embedding = $embedding
                    CREATE (n)-[:HAS_CHUNK]->(c)
                    """,
                    notion_id=notion_id,
                    chunk_id=chunk_id,
                    content=(
                        f"Summary: {chunk.get('summary', '')}\n\n{chunk.get('text', '')}"
                        if chunk.get("summary")
                        else chunk.get("text", "")
                    ),
                    chunk_number=i,
                    token_count=chunk.get("token_count"),
                    chunking_model=chunk.get("chunking_model"),
                    chunking_provider=chunk.get("chunking_provider"),
                    summary=chunk.get("summary"),
                    summary_model=chunk.get("summary_model"),
                    summary_provider=chunk.get("summary_provider"),
                    embedding=chunk.get("embedding"),
                    embedding_model=chunk.get("embedding_model"),
                    embedding_provider=chunk.get("embedding_provider"),
                )

                # Create NEXT_CHUNK relationship if not the first chunk
                if previous_chunk_id:
                    session.run(
                        """
                        MATCH (prev:NoteChunk {id: $prev_id})
                        MATCH (curr:NoteChunk {id: $curr_id})
                        CREATE (prev)-[:NEXT_CHUNK]->(curr)
                        """,
                        prev_id=previous_chunk_id,
                        curr_id=chunk_id,
                    )

                previous_chunk_id = chunk_id

            logger.info(
                f"Created {len(chunks)} chunks for document {notion_id} in Memgraph"
            )

    def create_relationships(
        self, notion_id: str, relationships: List[Dict[str, str]], timestamp: str
    ) -> None:
        """Create entity nodes and relationships."""
        with self.driver.session() as session:
            relationship_count = 0
            for rel in relationships:
                try:
                    # Defensive validation
                    if not all(
                        isinstance(rel.get(k), str) and rel.get(k)
                        for k in ["subject", "relationship", "object"]
                    ):
                        logger.warning(f"Skipping invalid relationship: {rel}")
                        continue

                    subject, relation, obj = (
                        rel["subject"].strip(),
                        rel["relationship"].strip(),
                        rel["object"].strip(),
                    )

                    # Additional validation
                    if not all([subject, relation, obj]):
                        logger.warning(
                            f"Skipping relationship with empty values: {rel}"
                        )
                        continue

                    # Execute Memgraph operation
                    try:
                        session.run(
                            """
                            MATCH (n:Note {id: $notion_id})
                            MERGE (s:Entity {name: $subject})
                            MERGE (o:Entity {name: $object})
                            CREATE (sr:SourceReference {
                                note_id: $notion_id,
                                timestamp: $timestamp,
                                type: 'relationship',
                                relation_type: $relation
                            })
                            MERGE (s)-[:HAS_SOURCE]->(sr)
                            MERGE (o)-[:HAS_SOURCE]->(sr)
                            MERGE (s)-[:RELATION]->(o)
                            """,
                            notion_id=notion_id,
                            subject=subject,
                            relation=relation,
                            object=obj,
                            timestamp=timestamp,
                        )
                        relationship_count += 1
                    except Exception as e:
                        logger.error(
                            f"Memgraph operation failed for relationship {rel}: {str(e)}"
                        )
                        continue
                except (KeyError, AttributeError) as e:
                    logger.error(f"Failed to process relationship {rel}: {str(e)}")
                    continue

            if relationship_count > 0:
                logger.info(
                    f"Created {relationship_count} relationships for document {notion_id} in Memgraph"
                )

    def get_last_modified(self, notion_id: str) -> Optional[str]:
        """Get the last_modified timestamp for a note.

        Args:
            notion_id: Note ID

        Returns:
            Last modified timestamp if found, None otherwise
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (n:Note {id: $notion_id})
                RETURN n.last_modified as last_modified
                """,
                notion_id=notion_id,
            ).single()
            return result["last_modified"] if result else None

    def get_documents(self, notion_id: Optional[str] = None) -> Iterator[Dict]:
        """Get all documents or a specific document."""
        with self.driver.session() as session:
            if notion_id:
                query = """
                MATCH (n:Note {id: $notion_id})
                RETURN n.id as notion_id, n.title as title, n.content as content
                """
                params = {"notion_id": notion_id}
            else:
                query = """
                MATCH (n:Note)
                RETURN n.id as notion_id, n.title as title, n.content as content
                """
                params = {}

            result = session.run(query, params)
            for record in result:
                content = record["content"]
                # Log retrieved content
                logger.debug(
                    "Memgraph retrieved content for %s:\n%s",
                    record["notion_id"],
                    content,
                )
                logger.debug(
                    "Memgraph retrieved content newlines count: %d", content.count("\n")
                )

                yield {
                    "notion_id": record["notion_id"],
                    "title": record["title"],
                    "content": content,
                }

    def create_chunk_summary(
        self, notion_id: str, chunk_number: int, summary: str
    ) -> None:
        """Create or update a summary for a chunk."""
        with self.driver.session() as session:
            session.run(
                """
                MATCH (n:Note {id: $notion_id})-[:HAS_CHUNK]->(c:NoteChunk)
                WHERE c.chunkNumber = $chunk_number
                SET c.summary = $summary,
                    c.content = CASE
                        WHEN $summary IS NOT NULL THEN "Summary: " + $summary + "\n\n" + c.content
                        ELSE c.content
                    END
                """,
                notion_id=notion_id,
                chunk_number=chunk_number,
                summary=summary,
            )

    def get_chunks(self, notion_id: str) -> List[Dict]:
        """Get all chunks for a document."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (n:Note {id: $notion_id})-[:HAS_CHUNK]->(c:NoteChunk)
                RETURN c.content as content, c.summary as summary, c.chunkNumber as chunk_number
                ORDER BY c.chunkNumber
                """,
                notion_id=notion_id,
            )

            return [
                {
                    "content": record[
                        "content"
                    ],  # Content is already formatted with summary
                    "summary": record["summary"],
                    "token_count": None,  # Memgraph doesn't store token counts
                }
                for record in result
            ]

    def add_entity_reference(
        self, entity_name: str, notion_id: str, timestamp: str
    ) -> None:
        """Add a reference from a note to an entity."""
        with self.driver.session() as session:
            session.run(
                """
                MERGE (e:Entity {name: $entity_name})
                CREATE (sr:SourceReference {
                    note_id: $notion_id,
                    timestamp: $timestamp,
                    type: 'entity_mention'
                })
                MERGE (e)-[:HAS_SOURCE]->(sr)
                """,
                entity_name=entity_name,
                notion_id=notion_id,
                timestamp=timestamp,
            )

    def remove_note_references(self, notion_id: str) -> Set[str]:
        """Remove all references from a note and return orphaned entities."""
        orphaned_entities = set()
        with self.driver.session() as session:
            # Delete source references and collect orphaned entities
            result = session.run(
                """
                MATCH (sr:SourceReference {note_id: $notion_id})
                OPTIONAL MATCH (e:Entity)-[:HAS_SOURCE]->(sr)
                WITH e, sr
                DELETE sr
                WITH e
                WHERE e IS NOT NULL
                OPTIONAL MATCH (e)-[:HAS_SOURCE]->(remaining_sr:SourceReference)
                WITH e, COUNT(remaining_sr) as ref_count
                WHERE ref_count = 0
                RETURN e.name as name
                """,
                notion_id=notion_id,
            )

            for record in result:
                orphaned_entities.add(record["name"])

        return orphaned_entities

    def delete_entities(self, entity_names: Set[str]) -> None:
        """Delete specified entities."""
        if not entity_names:
            return

        with self.driver.session() as session:
            session.run(
                """
                UNWIND $names as name
                MATCH (e:Entity {name: name})
                DETACH DELETE e
                """,
                names=list(entity_names),
            )
            logger.info(f"Deleted {len(entity_names)} orphaned entities")

    def close(self) -> None:
        """Close the database driver."""
        self.driver.close()
