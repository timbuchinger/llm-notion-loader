/* Part 1: Drop existing indices */
DROP INDEX ON :Note(id);
DROP INDEX ON :NoteChunk(id);
DROP INDEX ON :Entity(name);

/* Part 2: Data Migration */
/* Create source references from existing relationships */
MATCH (s:Entity)-[r:RELATION]->(o:Entity)
WITH s, o, r, r.note_id as note_id, r.type as rel_type
WHERE note_id IS NOT NULL
CREATE (sr:SourceReference {
    note_id: note_id,
    timestamp: timestamp(), /* Using timestamp() for current time */
    type: 'relationship',
    relation_type: rel_type
})
MERGE (s)-[:HAS_SOURCE]->(sr)
MERGE (o)-[:HAS_SOURCE]->(sr)
SET r = {};

/* Create source references for entity mentions */
MATCH (n:Note)-[:CONTAINS]->(e:Entity)
CREATE (sr:SourceReference {
    note_id: n.id,
    timestamp: COALESCE(n.last_modified, timestamp()),
    type: 'entity_mention'
})
MERGE (e)-[:HAS_SOURCE]->(sr);

/* Clean up old CONTAINS relationships */
MATCH (n:Note)-[r:CONTAINS]->(e:Entity)
DELETE r;

/* Part 3: Create new indices */
CREATE INDEX ON :Note(id);
CREATE INDEX ON :NoteChunk(id);
CREATE INDEX ON :Entity(name);
CREATE INDEX ON :SourceReference(note_id);
CREATE INDEX ON :SourceReference(timestamp);
