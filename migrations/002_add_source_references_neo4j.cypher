// Drop existing constraints
DROP CONSTRAINT note_id IF EXISTS;
DROP CONSTRAINT chunk_id IF EXISTS;
DROP CONSTRAINT entity_name IF EXISTS;

// Migration: Move to Source Reference Pattern

// Create source references from existing relationships
MATCH (s:Entity)-[r:RELATION]->(o:Entity)
WHERE exists(r.note_id)
CREATE (sr:SourceReference {
    note_id: r.note_id,
    timestamp: datetime(), // Current time as we don't have historical data
    type: "relationship"
})
WITH s, o, r, sr
MERGE (r)-[:HAS_SOURCE]->(sr)
MERGE (s)-[:HAS_SOURCE]->(sr)
MERGE (o)-[:HAS_SOURCE]->(sr)
REMOVE r.note_id;

// Create source references for entity mentions
MATCH (n:Note)-[:CONTAINS]->(e:Entity)
CREATE (sr:SourceReference {
    note_id: n.id,
    timestamp: n.last_modified,
    type: "entity_mention"
})
MERGE (e)-[:HAS_SOURCE]->(sr);

// Clean up old CONTAINS relationships
MATCH (n:Note)-[r:CONTAINS]->(e:Entity)
DELETE r;

// Create new constraints
CREATE CONSTRAINT note_id IF NOT EXISTS FOR (n:Note) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:NoteChunk) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE;
CREATE CONSTRAINT source_ref IF NOT EXISTS FOR (sr:SourceReference) REQUIRE (sr.note_id, sr.timestamp) IS NODE KEY;
