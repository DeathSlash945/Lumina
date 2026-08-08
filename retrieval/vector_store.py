import math
import re
import logging
from typing import List, Dict, Any, Optional

log = logging.getLogger("lumina.vector_store")
class VectorStore:
    def __init__(self):
        self.documents: List[Dict[str, Any]] = []
        self.avg_doc_len: float = 0.0
        self.k1: float = 1.5
        self.b: float = 0.75

    def _tokenize(self, text: str) -> List[str]:
        #Normalizes and tokenizes raw transcript text lol.
        return re.findall(r'\b\w+\b', text.lower())

    def add_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """
        Indexes transcript chunks into the store.
        Each chunk dict should contain:
          - text: str
          - video_id: str
          - start_time: float
          - end_time: float
          - embedding: Optional[List[float]]
        """
        for chunk in chunks:
            tokens = self._tokenize(chunk.get("text", ""))
            doc_entry = {
                "text": chunk.get("text", ""),
                "video_id": chunk.get("video_id", ""),
                "start_time": chunk.get("start_time", 0.0),
                "end_time": chunk.get("end_time", 0.0),
                "tokens": tokens,
                "doc_len": len(tokens),
                "embedding": chunk.get("embedding", None)
            }
            self.documents.append(doc_entry)

        # Recalculate collection statistics
        total_len = sum(d["doc_len"] for d in self.documents)
        self.avg_doc_len = (total_len / len(self.documents)) if self.documents else 0.0

    def _bm25_score(self, query_tokens: List[str], doc: Dict[str, Any]) -> float:
        """Computes BM25 relevance score for exact technical term precision."""
        if not doc["doc_len"] or self.avg_doc_len == 0:
            return 0.0

        score = 0.0
        doc_tokens = doc["tokens"]
        total_docs = len(self.documents)

        for token in query_tokens:
            tf = doc_tokens.count(token)
            if tf == 0:
                continue
            # Document frequency across index
            df = sum(1 for d in self.documents if token in d["tokens"])
            idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)
            # BM25 term weight calculation
            num = tf * (self.k1 + 1.0)
            den = tf + self.k1 * (1.0 - self.b + self.b * (doc["doc_len"] / self.avg_doc_len))
            score += idf * (num / den)

        return score

    def _cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Computes cosine similarity between dual embedding vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def search(
        self, 
        query: str, 
        query_embedding: Optional[List[float]] = None, 
        limit: int = 3,
        video_id_filter: Optional[str] = None,
        alpha: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Executes hybrid retrieval (BM25 + Cosine Similarity).
        - alpha = 1.0 -> Pure BM25 keyword matching
        - alpha = 0.0 -> Pure Vector embedding matching
        - alpha = 0.5 -> Balanced Hybrid
        """
        if not self.documents:
            return []
        query_tokens = self._tokenize(query)
        scored_results = []

        for doc in self.documents:
            # Metadata pre-filtering
            if video_id_filter and doc["video_id"] != video_id_filter:
                continue
            bm25 = self._bm25_score(query_tokens, doc)
            vector_sim = 0.0
            if query_embedding and doc["embedding"]:
                vector_sim = self._cosine_similarity(query_embedding, doc["embedding"])
            # Normalized hybrid fusion score
            hybrid_score = (alpha * bm25) + ((1.0 - alpha) * vector_sim)

            result_item = doc.copy()
            result_item["score"] = round(hybrid_score, 4)
            scored_results.append(result_item)

        # Sort by relevance score descending
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:limit]