import chromadb
from config import CHROMA_PATH
from retrieval.schemas import TranscriptChunk
from retrieval.embeddings import EmbeddingClient


class VectorStore:
    COLLECTION_NAME = "lumina_transcript_chunks"

    def __init__(self, embedder: EmbeddingClient | None = None):
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.collection = self.client.get_or_create_collection(self.COLLECTION_NAME)
        self.embedder = embedder or EmbeddingClient()

    def add_chunks(self, chunks: list[TranscriptChunk]):
        if not chunks:
            return
        # Skip chunks we've already embedded (id collision = already indexed)
        existing = set(self.collection.get(ids=[c.chunk_id for c in chunks])["ids"])
        new_chunks = [c for c in chunks if c.chunk_id not in existing]
        if not new_chunks:
            return

        embeddings = self.embedder.embed_batch([c.text for c in new_chunks])
        self.collection.add(
            ids=[c.chunk_id for c in new_chunks],
            embeddings=embeddings,
            documents=[c.text for c in new_chunks],
            metadatas=[
                {"video_id": c.video_id, "start": c.start, "end": c.end}
                for c in new_chunks
            ],
        )

    def query(self, topic: str, top_k: int = 15, video_ids: list[str] | None = None) -> list[TranscriptChunk]:
        query_embedding = self.embedder.embed(topic)
        where = {"video_id": {"$in": video_ids}} if video_ids else None

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
        )

        chunks = []
        ids = results["ids"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        for chunk_id, text, meta in zip(ids, docs, metas):
            chunks.append(TranscriptChunk(
                video_id=meta["video_id"],
                chunk_id=chunk_id,
                text=text,
                start=meta["start"],
                end=meta["end"],
            ))
        return chunks
