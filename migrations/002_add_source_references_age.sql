-- Add last_modified column to note_embeddings if it doesn't exist
SELECT 'ALTER TABLE note_embeddings ADD COLUMN last_modified timestamptz'
WHERE NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'note_embeddings'
    AND column_name = 'last_modified'
);

-- Initialize graph
CREATE EXTENSION IF NOT EXISTS age;
ALTER DATABASE current SET search_path = ag_catalog, public;

-- Drop existing constraints
SELECT ag_catalog._drop_graph('notion', true);
SELECT ag_catalog.create_graph('notion');

-- Move existing relationships to new structure
WITH source_refs AS (
    SELECT ag_catalog.cypher('notion', $$
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
    UNION ALL
    SELECT ag_catalog.cypher('notion', $$
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
    UNION ALL
    SELECT ag_catalog.cypher('notion', $$
        MATCH (n:Note)-[r:CONTAINS]->(e:Entity)
        DELETE r
        RETURN count(*) as updated
    $$) as (updated agtype)
)
SELECT COUNT(*) FROM source_refs;

-- Create Indexes
CREATE INDEX IF NOT EXISTS idx_source_ref_note_id ON ag_catalog.ag_label."SourceReference" USING btree ((properties->>'note_id'));
CREATE INDEX IF NOT EXISTS idx_source_ref_timestamp ON ag_catalog.ag_label."SourceReference" USING btree ((properties->>'timestamp'));

-- Run analyze to gather statistics
ANALYZE ag_catalog.ag_label."SourceReference";
