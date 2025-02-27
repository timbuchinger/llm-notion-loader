import logging
from typing import Dict, List, Optional, Set

import psycopg2
from age import Age
from psycopg2.extras import Json

from ..config import Config
from .base import DocumentStore

logger = logging.getLogger(__name__)


class AgeStore(DocumentStore):
    def _execute_cypher(self, cursor, query: str) -> List[Dict]:
        """Execute a Cypher query using the AGE cursor.

        Args:
            cursor: Database cursor
            query: The complete query string including cypher() function call

        Returns:
            List of result rows as dictionaries
        """
        cursor.execute(query)
        results = cursor.fetchall()
        return results if results else []

    def __init__(self):
        """Initialize AGE store with PostgreSQL connection."""
        store_config = (
            Config._load_config()
            .get("document_stores", {})
            .get("age", {})
            .get("settings", {})
        )

        self.conn = psycopg2.connect(
            host=store_config.get("host", Config.REQUIRED_ENV_VARS.get("AGE_HOST")),
            port=store_config.get("port", Config.REQUIRED_ENV_VARS.get("AGE_PORT")),
            database=store_config.get(
                "database", Config.REQUIRED_ENV_VARS.get("AGE_DATABASE")
            ),
            user=store_config.get("user", Config.REQUIRED_ENV_VARS.get("AGE_USER")),
            password=store_config.get(
                "password", Config.REQUIRED_ENV_VARS.get("AGE_PASSWORD")
            ),
        )
        self.age = Age()  # Initialize without connection
        self.age.connection = self.conn  # Set connection directly
        self.graph_name = "notion"
        self._initialize_database()  # Initialize database connection

    def _initialize_database(self) -> None:
        """Initialize AGE database connection.

        Note: Database schema must be initialized using the SQL migration files.
        """
        try:
            with self.conn.cursor() as cur:
                # Load AGE extension and set up schema
                cur.execute("LOAD 'age'")
                cur.execute("SET search_path TO ag_catalog, public")
                self.conn.commit()

                # Verify connection using a simple cypher query
                result = self._execute_cypher(
                    cur,
                    f"SELECT * FROM cypher('{self.graph_name}', $$RETURN 1 as test$$) as (test agtype)",
                )
            self.conn.commit()
            logger.info(f"Connected to AGE graph '{self.graph_name}'")
        except Exception as e:
            logger.error(f"Error initializing AGE connection: {str(e)}")
            raise

    def clean_document(self, notion_id: str) -> None:
        """Remove all nodes and relationships for a document.

        Args:
            notion_id: Notion page ID
        """
        with self.conn.cursor() as cur:
            try:
                # Delete from vector tables first due to foreign key constraints
                cur.execute(
                    """
                    DELETE FROM note_embeddings WHERE notion_id = %s;
                    DELETE FROM chunk_embeddings WHERE chunk_id LIKE %s;
                """,
                    (notion_id, f"{notion_id}-chunk-%"),
                )

                # Delete graph nodes and relationships
                cypher_query = f"""
                    SELECT * FROM cypher('{self.graph_name}', $$
                        MATCH (n:Note {{id: '{notion_id}'}})
                        OPTIONAL MATCH (n)-[:HAS_CHUNK]->(chunk:NoteChunk)
                        OPTIONAL MATCH (chunk)-[next:NEXT_CHUNK]->()
                        DETACH DELETE n, chunk, next

                        WITH n
                        MATCH (sr:SourceReference {{note_id: '{notion_id}'}})
                        OPTIONAL MATCH (e:Entity)-[:HAS_SOURCE]->(sr)
                        WITH e, sr
                        DELETE sr
                        WITH e
                        WHERE e IS NOT NULL
                        OPTIONAL MATCH (e)-[:HAS_SOURCE]->(remaining_sr:SourceReference)
                        WITH e, COUNT(remaining_sr) as ref_count
                        WHERE ref_count = 0
                        DETACH DELETE e
                        RETURN count(*) as deleted
                    $$) as (deleted agtype)
                """
                self._execute_cypher(cur, cypher_query)
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Error cleaning document: {str(e)}")
                raise

    def create_note(
        self,
        notion_id: str,
        title: str,
        content: str,
        embedding: List[float],
        last_modified: str,
    ) -> None:
        """Create a new note node with vector embedding.

        Args:
            notion_id: Notion page ID
            title: Note title
            content: Note content
            embedding: Vector embedding of content
            last_modified: Last modification timestamp
        """
        with self.conn.cursor() as cur:
            try:
                # Create note node
                # Escape single quotes in title and content
                safe_title = title.replace("'", "\\'")
                safe_content = content.replace("'", "\\'")

                cypher_query = f"""
                    SELECT * FROM cypher('{self.graph_name}', $$
                        CREATE (n:Note {{
                            id: '{notion_id}',
                            title: '{safe_title}',
                            content: '{safe_content}',
                            last_modified: '{last_modified}'
                        }})
                        RETURN n
                    $$) as (node agtype)
                """
                self._execute_cypher(cur, cypher_query)

                # Store embedding
                cur.execute(
                    """
                    INSERT INTO note_embeddings (notion_id, embedding)
                    VALUES (%s, %s)
                """,
                    (notion_id, embedding),
                )

                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Error creating note: {str(e)}")
                raise

    def create_chunks(self, notion_id: str, chunks: List[Dict]) -> None:
        """Create note chunk nodes and relationships.

        Args:
            notion_id: Parent note ID
            chunks: List of chunk dictionaries with metadata
        """
        with self.conn.cursor() as cur:
            try:
                previous_chunk_id = None

                for i, chunk in enumerate(chunks):
                    chunk_id = f"{notion_id}-chunk-{i}"

                    # Create chunk node with all metadata
                    # Escape single quotes in content
                    safe_content = chunk.get("text", "").replace("'", "\\'")

                    cypher_query = f"""
                        SELECT * FROM cypher('{self.graph_name}', $$
                            MATCH (n:Note {{id: '{notion_id}'}})
                            CREATE (c:NoteChunk {{
                                id: '{chunk_id}',
                                content: '{safe_content}',
                                parentNote: '{notion_id}',
                                chunkNumber: {i},
                                token_count: {chunk.get('token_count')},
                                chunking_model: '{chunk.get('chunking_model', '')}',
                                chunking_provider: '{chunk.get('chunking_provider', '')}',
                                summary: '{chunk.get('summary', '')}',
                                summary_model: '{chunk.get('summary_model', '')}',
                                summary_provider: '{chunk.get('summary_provider', '')}',
                                embedding: {Json(chunk.get('embedding'))} if '{chunk.get('embedding')}' != 'None' else null,
                                embedding_model: '{chunk.get('embedding_model', '')}',
                                embedding_provider: '{chunk.get('embedding_provider', '')}'
                            }})
                            CREATE (n)-[:HAS_CHUNK]->(c)
                            RETURN c
                        $$) as (node agtype)
                    """
                    self._execute_cypher(cur, cypher_query)

                    # Create NEXT_CHUNK relationship if not the first chunk
                    if previous_chunk_id:
                        cypher_query = f"""
                            SELECT * FROM cypher('{self.graph_name}', $$
                                MATCH (prev:NoteChunk {{id: '{previous_chunk_id}'}})
                                MATCH (curr:NoteChunk {{id: '{chunk_id}'}})
                                CREATE (prev)-[:NEXT_CHUNK]->(curr)
                                RETURN count(*) as created
                            $$) as (created agtype)
                        """
                        self._execute_cypher(cur, cypher_query)

                    previous_chunk_id = chunk_id

                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Error creating chunks: {str(e)}")
                raise

    def create_relationships(
        self, notion_id: str, relationships: List[Dict[str, str]], timestamp: str
    ) -> None:
        """Create entity nodes and relationships.

        Args:
            notion_id: Parent note ID
            relationships: List of relationship dictionaries
            timestamp: When the relationships were created
        """
        with self.conn.cursor() as cur:
            try:
                for rel in relationships:
                    try:
                        # Defensive validation
                        if not all(
                            isinstance(rel.get(k), str) and rel.get(k)
                            for k in ["subject", "relationship", "object"]
                        ):
                            logger.warning(f"Skipping invalid relationship: {rel}")
                            continue

                        subject = rel["subject"].strip().replace("'", "\\'")
                        relation = rel["relationship"].strip().replace("'", "\\'")
                        obj = rel["object"].strip().replace("'", "\\'")

                        # Additional validation
                        if not all([subject, relation, obj]):
                            logger.warning(
                                f"Skipping relationship with empty values: {rel}"
                            )
                            continue

                        # Create/match entities and relationship with source reference
                        cypher_query = f"""
                            SELECT * FROM cypher('{self.graph_name}', $$
                                MATCH (n:Note {{id: '{notion_id}'}})
                                MERGE (s:Entity {{name: '{subject}'}})
                                MERGE (o:Entity {{name: '{obj}'}})

                                CREATE (sr:SourceReference {{
                                    note_id: '{notion_id}',
                                    timestamp: '{timestamp}',
                                    type: 'relationship'
                                }})

                                MERGE (s)-[r:RELATION {{type: '{relation}'}}]->(o)
                                MERGE (r)-[:HAS_SOURCE]->(sr)
                                MERGE (s)-[:HAS_SOURCE]->(sr)
                                MERGE (o)-[:HAS_SOURCE]->(sr)

                                RETURN count(*) as created
                            $$) as (created agtype)
                        """
                        self._execute_cypher(cur, cypher_query)

                    except (KeyError, AttributeError) as e:
                        logger.error(f"Failed to process relationship {rel}: {str(e)}")
                        continue

                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Error creating relationships: {str(e)}")
                raise

    def add_entity_reference(
        self, entity_name: str, notion_id: str, timestamp: str
    ) -> None:
        """Add a reference from a note to an entity.

        Args:
            entity_name: Name of the entity
            notion_id: ID of the note referencing the entity
            timestamp: When the reference was created
        """
        with self.conn.cursor() as cur:
            try:
                safe_name = entity_name.replace("'", "\\'")
                cypher_query = f"""
                    SELECT * FROM cypher('{self.graph_name}', $$
                        MERGE (e:Entity {{name: '{safe_name}'}})
                        CREATE (sr:SourceReference {{
                            note_id: '{notion_id}',
                            timestamp: '{timestamp}',
                            type: 'entity_mention'
                        }})
                        MERGE (e)-[:HAS_SOURCE]->(sr)
                        RETURN count(*) as created
                    $$) as (created agtype)
                """
                self._execute_cypher(cur, cypher_query)
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Error adding entity reference: {str(e)}")
                raise

    def remove_note_references(self, notion_id: str) -> Set[str]:
        """Remove all references from a note and return orphaned entities.

        Args:
            notion_id: ID of the note

        Returns:
            Set of entity names that no longer have any references
        """
        orphaned_entities = set()
        with self.conn.cursor() as cur:
            try:
                cypher_query = f"""
                    SELECT * FROM cypher('{self.graph_name}', $$
                        MATCH (sr:SourceReference {{note_id: '{notion_id}'}})
                        OPTIONAL MATCH (e:Entity)-[:HAS_SOURCE]->(sr)
                        WITH e, sr
                        DELETE sr
                        WITH e
                        WHERE e IS NOT NULL
                        OPTIONAL MATCH (e)-[:HAS_SOURCE]->(remaining_sr:SourceReference)
                        WITH e, COUNT(remaining_sr) as ref_count
                        WHERE ref_count = 0
                        RETURN e.name as name
                    $$) as (name agtype)
                """
                result = self._execute_cypher(cur, cypher_query)
                for row in result:
                    if row.get("name"):
                        orphaned_entities.add(row["name"])
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Error removing note references: {str(e)}")
                raise
        return orphaned_entities

    def delete_entities(self, entity_names: Set[str]) -> None:
        """Delete specified entities.

        Args:
            entity_names: Set of entity names to delete
        """
        if not entity_names:
            return

        with self.conn.cursor() as cur:
            try:
                for name in entity_names:
                    safe_name = name.replace("'", "\\'")
                    cypher_query = f"""
                        SELECT * FROM cypher('{self.graph_name}', $$
                            MATCH (e:Entity {{name: '{safe_name}'}})
                            DETACH DELETE e
                            RETURN count(*) as deleted
                        $$) as (deleted agtype)
                    """
                    self._execute_cypher(cur, cypher_query)
                self.conn.commit()
                logger.info(f"Deleted {len(entity_names)} orphaned entities")
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Error deleting entities: {str(e)}")
                raise

    def get_note_hash(self, notion_id: str) -> Optional[str]:
        """Get the stored hash for a note.

        Args:
            notion_id: Note ID

        Returns:
            Stored hash if found, None otherwise
        """
        with self.conn.cursor() as cur:
            cypher_query = f"""
                SELECT * FROM cypher('{self.graph_name}', $$
                    MATCH (n:Note {{id: '{notion_id}'}})
                    RETURN n.hash as hash
                $$) as (hash agtype)
            """
            result = self._execute_cypher(cur, cypher_query)
            return result[0]["hash"] if result else None

    def create_chunk_summary(
        self, notion_id: str, chunk_number: int, summary: str
    ) -> None:
        """Update a chunk node with its summary.

        Args:
            notion_id: Parent note ID
            chunk_number: Index of the chunk
            summary: Summary text for the chunk
        """
        chunk_id = f"{notion_id}-chunk-{chunk_number}"
        with self.conn.cursor() as cur:
            try:
                # Escape single quotes in summary
                safe_summary = summary.replace("'", "\\'")

                cypher_query = f"""
                    SELECT * FROM cypher('{self.graph_name}', $$
                        MATCH (c:NoteChunk {{id: '{chunk_id}'}})
                        SET c.summary = '{safe_summary}'
                        RETURN c
                    $$) as (node agtype)
                """
                self._execute_cypher(cur, cypher_query)
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Error creating chunk summary: {str(e)}")
                raise

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()
