import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class SearchResult:
    """Represents a vector similarity search result."""
    id: int
    similarity: float

class VectorStore(ABC):
    """Abstract interface for face embedding vector stores."""
    
    @abstractmethod
    def add(self, embedding: np.ndarray, id: int) -> None:
        """Add a single embedding to the store."""
        pass
    
    @abstractmethod
    def add_batch(self, embeddings: np.ndarray, ids: np.ndarray) -> None:
        """Add multiple embeddings to the store."""
        pass
    
    @abstractmethod
    def search(self, embedding: np.ndarray, k: int = 5) -> list[SearchResult]:
        """Search for the top k most similar embeddings."""
        pass
    
    @abstractmethod
    def remove(self, id: int) -> bool:
        """Remove an embedding by ID."""
        pass
    
    @abstractmethod
    def rebuild(self, embeddings: np.ndarray, ids: np.ndarray) -> None:
        """Rebuild the index entirely with new embeddings."""
        pass
    
    @abstractmethod
    def save(self, path: str) -> None:
        """Save the vector index to disk."""
        pass
    
    @abstractmethod
    def load(self, path: str) -> bool:
        """Load the vector index from disk."""
        pass
    
    @property
    @abstractmethod
    def count(self) -> int:
        """Return the number of stored vectors."""
        pass
