// First drop existing constraints
CALL db.dropConstraint("note_id_unique");
CALL db.dropConstraint("chunk_id_unique");
CALL db.dropConstraint("entity_name_unique");

// Migration: Move to Source Reference Pattern
// Create source references from existing relationships
MATCH (s:Entity)-[r:RELATION]->(o:Entity)
WHERE exists(r.note_id)
CREATE (sr:SourceReference {
    note_id: r.note_id,
    timestamp: datetime(), // Current time as we don't have historical data
    type: "relationship"
})
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

// Re-create constraints with new schema
CALL db.createConstraint("note_id_unique", "Note", ["id"], "UNIQUE");
CALL db.createConstraint("chunk_id_unique", "NoteChunk", ["id"], "UNIQUE");
CALL db.createConstraint("entity_name_unique", "Entity", ["name"], "UNIQUE");
CALL db.createConstraint("source_reference_unique", "SourceReference", ["note_id", "timestamp"], "UNIQUE");
