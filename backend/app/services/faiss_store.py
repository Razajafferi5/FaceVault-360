import logging
import os
import threading
import numpy as np
import faiss
from .vector_store import VectorStore, SearchResult

logger = logging.getLogger(__name__)

class FAISSVectorStore(VectorStore):
    """FAISS-based vector store implementation using inner product for cosine similarity."""
    
    def __init__(self, dimension: int = 512):
        """Initialize the FAISS store."""
        self.dimension = dimension
        self._lock = threading.RLock()
        
        # Inner product + L2 normalization = Cosine similarity
        base_index = faiss.IndexFlatIP(self.dimension)
        self.index = faiss.IndexIDMap2(base_index)

    def _normalize(self, vectors: np.ndarray) -> np.ndarray:
        """L2-normalize vectors for cosine similarity search."""
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        vectors = vectors.astype(np.float32)
        faiss.normalize_L2(vectors)
        return np.ascontiguousarray(vectors)

    def add(self, embedding: np.ndarray, id: int) -> None:
        """Add a normalized embedding to the index."""
        with self._lock:
            try:
                normed = self._normalize(embedding)
                ids = np.array([id], dtype=np.int64)
                self.index.add_with_ids(normed, ids)
            except Exception as e:
                logger.error(f"Error adding vector: {e}")

    def add_batch(self, embeddings: np.ndarray, ids: np.ndarray) -> None:
        """Add a batch of embeddings to the index."""
        with self._lock:
            try:
                normed = self._normalize(embeddings)
                ids = ids.astype(np.int64)
                self.index.add_with_ids(normed, ids)
            except Exception as e:
                logger.error(f"Error adding vector batch: {e}")

    def search(self, embedding: np.ndarray, k: int = 5) -> list[SearchResult]:
        """Search the index for the most similar faces."""
        with self._lock:
            if self.index.ntotal == 0:
                return []
            try:
                normed = self._normalize(embedding)
                distances, indices = self.index.search(normed, k)
                
                results = []
                for dist, idx in zip(distances[0], indices[0]):
                    if idx != -1:
                        results.append(SearchResult(id=int(idx), similarity=float(dist)))
                return results
            except Exception as e:
                logger.error(f"Error during search: {e}")
                return []

    def remove(self, id: int) -> bool:
        """Remove a face embedding by ID."""
        with self._lock:
            try:
                self.index.remove_ids(np.array([id], dtype=np.int64))
                return True
            except Exception as e:
                logger.error(f"Error removing ID {id}: {e}")
                return False

    def rebuild(self, embeddings: np.ndarray, ids: np.ndarray) -> None:
        """Rebuild the index from scratch."""
        with self._lock:
            try:
                base_index = faiss.IndexFlatIP(self.dimension)
                self.index = faiss.IndexIDMap2(base_index)
                if len(embeddings) > 0:
                    normed = self._normalize(embeddings)
                    ids = ids.astype(np.int64)
                    self.index.add_with_ids(normed, ids)
            except Exception as e:
                logger.error(f"Error rebuilding index: {e}")

    def save(self, path: str) -> None:
        """Save the FAISS index to disk."""
        with self._lock:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                faiss.write_index(self.index, path)
            except Exception as e:
                logger.error(f"Error saving FAISS index to {path}: {e}")

    def load(self, path: str) -> bool:
        """Load the FAISS index from disk."""
        with self._lock:
            if not os.path.exists(path):
                return False
            try:
                self.index = faiss.read_index(path)
                return True
            except Exception as e:
                logger.error(f"Error loading FAISS index from {path}: {e}")
                return False

    @property
    def count(self) -> int:
        """Get the total number of vectors in the index."""
        with self._lock:
            return self.index.ntotal
