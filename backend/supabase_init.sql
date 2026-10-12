-- Run once in Supabase SQL Editor (Dashboard → SQL → New query)

CREATE EXTENSION IF NOT EXISTS vector;

-- Tables are created automatically by the backend on startup via SQLAlchemy.
-- To explicitly ensure high-performance HNSW indexes for sub-millisecond vector similarity search:
CREATE INDEX IF NOT EXISTS ix_embeddings_vector_hnsw 
ON embeddings USING hnsw (vector vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS ix_detections_embedding_vector_hnsw 
ON detections USING hnsw (embedding_vector vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);
