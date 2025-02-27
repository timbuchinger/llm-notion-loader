-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS age;
CREATE EXTENSION IF NOT EXISTS vector;

-- Create graph
SELECT * FROM ag_catalog.create_graph('notion');

-- Create vertex labels
SELECT * FROM ag_catalog.create_vlabel('notion', 'Note');
SELECT * FROM ag_catalog.create_vlabel('notion', 'NoteChunk');
SELECT * FROM ag_catalog.create_vlabel('notion', 'Entity');

-- Create edge labels
SELECT * FROM ag_catalog.create_elabel('notion', 'HAS_CHUNK');
SELECT * FROM ag_catalog.create_elabel('notion', 'NEXT_CHUNK');
SELECT * FROM ag_catalog.create_elabel('notion', 'CONTAINS');
SELECT * FROM ag_catalog.create_elabel('notion', 'RELATION');

-- Create vector tables
CREATE TABLE IF NOT EXISTS note_embeddings (
    notion_id TEXT PRIMARY KEY,
    embedding vector(768),  -- Assuming 768-dimensional embeddings from nomic-embed-text
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id TEXT PRIMARY KEY,
    embedding vector(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create vector similarity search indexes
CREATE INDEX IF NOT EXISTS note_embedding_idx ON note_embeddings
USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS chunk_embedding_idx ON chunk_embeddings
USING ivfflat (embedding vector_cosine_ops);

-- Create trigger function to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for timestamp updates
CREATE TRIGGER update_note_embeddings_updated_at
    BEFORE UPDATE ON note_embeddings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_chunk_embeddings_updated_at
    BEFORE UPDATE ON chunk_embeddings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
