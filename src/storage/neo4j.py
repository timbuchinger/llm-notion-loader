import logging
from typing import Dict, List, Optional

from neo4j import GraphDatabase

from ..config import Config
from .base import DocumentStore

logger = logging.getLogger(__name__)


class Neo4jStore(DocumentStore):
    def __init__(self):
        """Initialize Neo4j store with database connection."""
        store_config = (
            Config._load_config()
            .get("document_stores", {})
            .get("neo4j", {})
            .get("settings", {})
        )

        self.driver = GraphDatabase.driver(
            store_config.get("uri", Config.REQUIRED_ENV_VARS.get("NEO4J_URI")),
            auth=(
                store_config.get("user", Config.REQUIRED_ENV_VARS.get("NEO4J_USER")),
                store_config.get(
                    "password", Config.REQUIRED_ENV_VARS.get("NEO4J_PASSWORD")
                ),
            ),
        )
        self.database = store_config.get(
            "database", Config.REQUIRED_ENV_VARS.get("NEO4J_DATABASE", "notion")
        )
        self._initialize_database()

    def _initialize_database(self) -> None:
        """Initialize Neo4j database with required constraints."""
        with self.driver.session(database=self.database) as session:
            try:
                # Set up constraints and indexes
                session.run(
                    "CREATE CONSTRAINT note_id IF NOT EXISTS FOR (n:Note) REQUIRE n.id IS UNIQUE"
                )
                session.run(
                    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:NoteChunk) REQUIRE c.id IS UNIQUE"
                )
                session.run(
                    "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE"
                )
                session.run(
                    """CREATE CONSTRAINT source_ref IF NOT EXISTS
                    FOR (sr:SourceReference)
                    REQUIRE (sr.note_id, sr.timestamp) IS NODE KEY"""
                )
                logger.info(
                    f"Neo4j database '{self.database}' initialized with constraints"
                )
            except Exception as e:
                logger.error(f"Error setting up Neo4j constraints: {str(e)}")
                raise

    def clean_document(self, notion_id: str) -> None:
        """Remove all nodes and relationships for a document.

        Args:
            notion_id: Notion page ID
        """
        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MATCH (n:Note {id: $notion_id})
                OPTIONAL MATCH (n)-[:HAS_CHUNK]->(chunk:NoteChunk)
                OPTIONAL MATCH (chunk)-[next:NEXT_CHUNK]->()
                DETACH DELETE n, chunk, next
                WITH n

                // Find orphaned entities after removing references
                CALL {
                    WITH n
                    MATCH (sr:SourceReference {note_id: $notion_id})
                    OPTIONAL MATCH (e:Entity)-[:HAS_SOURCE]->(sr)
                    WITH e, sr
                    DELETE sr
                    WITH e
                    WHERE e IS NOT NULL
                    OPTIONAL MATCH (e)-[:HAS_SOURCE]->(remaining_sr:SourceReference)
                    WITH e, COUNT(remaining_sr) as ref_count
                    WHERE ref_count = 0
                    DETACH DELETE e
                }
                """,
                notion_id=notion_id,
            )

    def create_note(
        self,
        notion_id: str,
        title: str,
        content: str,
        embedding: List[float],
        last_modified: str,
    ) -> None:
        """Create a new note node.

        Args:
            notion_id: Notion page ID
            title: Note title
            content: Note content
            embedding: Vector embedding of content
        """
        with self.driver.session(database=self.database) as session:
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

    def create_chunks(self, notion_id: str, chunks: List[Dict]) -> None:
        """Create note chunk nodes and relationships.

        Args:
            notion_id: Parent note ID
            chunks: List of chunk dictionaries with metadata
        """
        with self.driver.session() as session:
            previous_chunk_id = None

            for i, chunk in enumerate(chunks):
                chunk_id = f"{notion_id}-chunk-{i}"

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
                        embedding: $embedding,
                        embedding_model: $embedding_model,
                        embedding_provider: $embedding_provider
                    })
                    CREATE (n)-[:HAS_CHUNK]->(c)
                    """,
                    notion_id=notion_id,
                    chunk_id=chunk_id,
                    content=chunk.get("text", ""),
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

    def create_relationships(
        self, notion_id: str, relationships: List[Dict[str, str]], timestamp: str
    ) -> None:
        """Create entity nodes and relationships.

        Args:
            notion_id: Parent note ID
            relationships: List of relationship dictionaries
        """
        with self.driver.session(database=self.database) as session:
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

                    # Execute Neo4j operation
                    try:
                        session.run(
                            """
                            MATCH (n:Note {id: $notion_id})
                            MERGE (s:Entity {name: $subject})
                            MERGE (o:Entity {name: $object})
                            // Create source reference for relationship
                            CREATE (sr:SourceReference {
                                note_id: $notion_id,
                                timestamp: $timestamp,
                                type: "relationship"
                            })
                            MERGE (s)-[r:RELATION {type: $relation}]->(o)
                            MERGE (r)-[:HAS_SOURCE]->(sr)

                            // Add entity references
                            MERGE (s)-[:HAS_SOURCE]->(sr)
                            MERGE (o)-[:HAS_SOURCE]->(sr)
                            """,
                            notion_id=notion_id,
                            subject=subject,
                            relation=relation,
                            object=obj,
                            timestamp=timestamp,
                        )
                    except Exception as e:
                        logger.error(
                            f"Neo4j operation failed for relationship {rel}: {str(e)}"
                        )
                        continue
                except (KeyError, AttributeError) as e:
                    logger.error(f"Failed to process relationship {rel}: {str(e)}")
                    continue

    def get_note_hash(self, notion_id: str) -> Optional[str]:
        """Get the stored hash for a note.

        Args:
            notion_id: Note ID

        Returns:
            Stored hash if found, None otherwise
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (n:Note {id: $notion_id})
                RETURN n.hash as hash
                """,
                notion_id=notion_id,
            ).single()

            return result["hash"] if result else None

    def add_entity_reference(
        self, entity_name: str, notion_id: str, timestamp: str
    ) -> None:
        """Add a reference from a note to an entity.

        Args:
            entity_name: Name of the entity
            notion_id: ID of the note referencing the entity
            timestamp: When the reference was created
        """
        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MERGE (e:Entity {name: $entity_name})
                CREATE (sr:SourceReference {
                    note_id: $notion_id,
                    timestamp: $timestamp,
                    type: "entity_mention"
                })
                MERGE (e)-[:HAS_SOURCE]->(sr)
                """,
                entity_name=entity_name,
                notion_id=notion_id,
                timestamp=timestamp,
            )

    def remove_note_references(self, notion_id: str) -> Set[str]:
        """Remove all references from a note and return orphaned entities.

        Args:
            notion_id: ID of the note

        Returns:
            Set of entity names that no longer have any references
        """
        orphaned_entities = set()
        with self.driver.session(database=self.database) as session:
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
        """Delete specified entities.

        Args:
            entity_names: Set of entity names to delete
        """
        if not entity_names:
            return

        with self.driver.session(database=self.database) as session:
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
