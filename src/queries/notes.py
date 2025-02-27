"""Queries for retrieving notes and their components from the graph database."""

# Example usage:
# MATCH (n:Note {title: 'CSV Sync'})
# Returns a single note with its chunks ordered by chunk_number
GET_NOTE_WITH_CHUNKS_BY_TITLE = """
MATCH (n:Note {title: $title})
OPTIONAL MATCH (n)-[:HAS_CHUNK]->(c:NoteChunk)
WITH n, c ORDER BY c.chunkNumber
RETURN n.id as note_id,
       n.title as title,
       n.content as content,
       COLLECT({
         content: c.content,
         chunk_number: c.chunkNumber
       }) as chunks
"""
