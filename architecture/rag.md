# RAG architecture

Target pipeline (Sprint 1):

Documents → loader → parser → chunker → metadata → embeddings → ChromaDB → retriever → reranker → context builder → security gateway → LLM.

Chunk metadata must include `document_id`, `category`, `security_classification`, `effective_date`, `owner`, and `version`.
