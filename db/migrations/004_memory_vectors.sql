-- Migration: Story Memory with Vector Embeddings
-- Enables long-term memory for contextual retrieval

-- Enable pgvector extension (requires postgres with pgvector installed)
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop existing table if it exists with wrong dimensions
DROP TABLE IF EXISTS story_memory CASCADE;

-- Story memory table for storing embeddings
CREATE TABLE story_memory (
    id SERIAL PRIMARY KEY,
    story_id UUID NOT NULL, -- Link to story (not necessarily a strict FK if story deleted but memory kept)
    content TEXT NOT NULL,
    embedding vector(384),  -- bge-small-en-v1.5 dimension
    memory_type VARCHAR(50) DEFAULT 'summary',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for vector similarity search (cosine distance)
CREATE INDEX IF NOT EXISTS idx_story_memory_embedding 
ON story_memory USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Index for memory type filtering
CREATE INDEX IF NOT EXISTS idx_story_memory_type ON story_memory(memory_type);

-- Index for story lookup
CREATE INDEX IF NOT EXISTS idx_story_memory_story_id ON story_memory(story_id);

-- Add comment explaining the table purpose
COMMENT ON TABLE story_memory IS 'Stores vector embeddings for story content to enable semantic similarity search and long-term memory retrieval';
