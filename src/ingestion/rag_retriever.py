"""
EduScribe AI - RAG Retriever Module
Indexes and retrieves relevant context chunks from ingested syllabus standards and past papers.
"""

from typing import List, Dict, Any, Optional

class RAGRetriever:
    def __init__(self):
        self.corpus_chunks: List[Dict[str, Any]] = []

    def add_document(self, doc_data: Dict[str, Any]):
        """Chunks and stores a parsed document into the local retrieval store."""
        full_text = doc_data.get("full_text", "")
        filename = doc_data.get("filename", "unknown")
        
        # Simple semantic chunking by sections or paragraphs
        raw_chunks = full_text.split("\n\n")
        current_chunk = ""
        
        for p in raw_chunks:
            p_clean = p.strip()
            if not p_clean:
                continue
            if len(current_chunk) + len(p_clean) < 1200:
                current_chunk += "\n\n" + p_clean
            else:
                if current_chunk:
                    self.corpus_chunks.append({
                        "filename": filename,
                        "content": current_chunk.strip()
                    })
                current_chunk = p_clean

        if current_chunk:
            self.corpus_chunks.append({
                "filename": filename,
                "content": current_chunk.strip()
            })

    def retrieve_context(self, query: str, top_k: int = 3) -> str:
        """Simple keyword/relevance match when Vertex Search is not connected."""
        if not self.corpus_chunks:
            return ""

        query_terms = set(query.lower().split())
        scored_chunks = []
        for chunk in self.corpus_chunks:
            content_lower = chunk["content"].lower()
            score = sum(1 for term in query_terms if term in content_lower)
            scored_chunks.append((score, chunk["content"]))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        top_matches = [c[1] for c in scored_chunks[:top_k] if c[0] > 0]
        
        if not top_matches:
            # Fallback to first few chunks
            top_matches = [c["content"] for c in self.corpus_chunks[:top_k]]

        return "\n\n---\n\n".join(top_matches)
