#!/usr/bin/env python3
import os

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def execute_migration():
    # Get database connection settings from environment
    db_settings = {
        "host": os.getenv("AGE_HOST", "localhost"),
        "port": os.getenv("AGE_PORT", "5432"),
        "database": os.getenv("AGE_DATABASE", "notion"),
        "user": os.getenv("AGE_USER", "postgres"),
        "password": os.getenv("AGE_PASSWORD", ""),
    }

    # Connect to PostgreSQL
    conn = psycopg2.connect(**db_settings)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    try:
        with conn.cursor() as cur:
            # Add last_modified column if it doesn't exist
            cur.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'note_embeddings'
                        AND column_name = 'last_modified'
                    ) THEN
                        ALTER TABLE note_embeddings ADD COLUMN last_modified timestamptz;
                    END IF;
                END $$;
            """
            )

            # Load AGE extension
            cur.execute("CREATE EXTENSION IF NOT EXISTS age")
            cur.execute("SET search_path TO ag_catalog, public")

            # Drop and recreate graph
            cur.execute("SELECT ag_catalog._drop_graph('notion', true)")
            cur.execute("SELECT ag_catalog.create_graph('notion')")

            # Create source references for existing relationships
            cur.execute(
                """
                SELECT * FROM ag_catalog.cypher('notion', $$
                    MATCH (s:Entity)-[r:RELATION]->(o:Entity)
                    WHERE exists(r.note_id)
                    WITH s, o, r
                    CREATE (sr:SourceReference {
                        note_id: r.note_id,
                        timestamp: datetime(),
                        type: 'relationship'
                    })
                    MERGE (r)-[:HAS_SOURCE]->(sr)
                    MERGE (s)-[:HAS_SOURCE]->(sr)
                    MERGE (o)-[:HAS_SOURCE]->(sr)
                    REMOVE r.note_id
                    RETURN count(*) as updated
                $$) as (updated agtype)
            """
            )

            # Create source references for existing entity mentions
            cur.execute(
                """
                SELECT * FROM ag_catalog.cypher('notion', $$
                    MATCH (n:Note)-[:CONTAINS]->(e:Entity)
                    WITH n, e
                    CREATE (sr:SourceReference {
                        note_id: n.id,
                        timestamp: coalesce(n.last_modified, datetime()),
                        type: 'entity_mention'
                    })
                    MERGE (e)-[:HAS_SOURCE]->(sr)
                    RETURN count(*) as updated
                $$) as (updated agtype)
            """
            )

            # Remove old CONTAINS relationships
            cur.execute(
                """
                SELECT * FROM ag_catalog.cypher('notion', $$
                    MATCH (n:Note)-[r:CONTAINS]->(e:Entity)
                    DELETE r
                    RETURN count(*) as deleted
                $$) as (deleted agtype)
            """
            )

            # Create indexes for the SourceReference properties
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_source_ref_note_id
                ON ag_catalog.ag_label."SourceReference"
                USING btree ((properties->>'note_id'))
            """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_source_ref_timestamp
                ON ag_catalog.ag_label."SourceReference"
                USING btree ((properties->>'timestamp'))
            """
            )

            # Analyze to update statistics
            cur.execute('ANALYZE ag_catalog.ag_label."SourceReference"')

            print("Migration completed successfully")

    except Exception as e:
        print(f"Error during migration: {str(e)}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    execute_migration()
