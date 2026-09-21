import pytest
import numpy as np
import os
from app.services.faiss_store import FAISSVectorStore

@pytest.fixture
def vector_store():
    # FAISSVectorStore takes dimension (default 512)
    return FAISSVectorStore(dimension=512)

def normalize(vec):
    vec = vec.astype(np.float32)
    return vec / np.linalg.norm(vec)

def test_add_and_count(vector_store):
    vectors = [normalize(np.random.randn(512)) for _ in range(5)]
    for i, v in enumerate(vectors):
        vector_store.add(v, i)
    assert vector_store.count == 5

def test_search_finds_exact_match(vector_store, sample_embedding):
    vector_store.add(sample_embedding, 1)
    results = vector_store.search(sample_embedding, k=1)
    assert len(results) == 1
    assert results[0].id == 1
    assert results[0].similarity >= 0.99  # Cosine similarity for exact match is ~1.0

def test_search_finds_closest(vector_store):
    v1 = normalize(np.ones(512))
    v2 = normalize(np.zeros(512) + 0.5)
    v2[0] = -1.0
    v3 = normalize(-np.ones(512))
    
    vector_store.add(v1, 1)
    vector_store.add(v2, 2)
    vector_store.add(v3, 3)
    
    # Search for v1
    results = vector_store.search(v1, k=3)
    assert results[0].id == 1
    # Check ordering
    assert results[0].similarity > results[1].similarity > results[2].similarity

def test_search_empty_index(vector_store, sample_embedding):
    results = vector_store.search(sample_embedding)
    assert len(results) == 0

def test_remove(vector_store):
    for i in range(3):
        vector_store.add(normalize(np.random.randn(512)), i)
    assert vector_store.count == 3
    
    vector_store.remove(1)
    assert vector_store.count == 2
    
    # Ensure 1 is not found
    for result in vector_store.search(normalize(np.random.randn(512)), k=3):
        assert result.id != 1

def test_rebuild(vector_store):
    for i in range(3):
        vector_store.add(normalize(np.random.randn(512)), i)
    
    new_vectors = np.array([normalize(np.random.randn(512)) for _ in range(2)])
    ids = np.array([10, 11])
    vector_store.rebuild(new_vectors, ids)
    
    assert vector_store.count == 2
    results = vector_store.search(new_vectors[0], k=2)
    res_ids = [r.id for r in results]
    assert 10 in res_ids
    assert 0 not in res_ids

def test_save_and_load(tmp_path):
    index_path = str(tmp_path / "test_faiss.bin")
    store1 = FAISSVectorStore(dimension=512)
    vec = normalize(np.random.randn(512))
    store1.add(vec, 42)
    store1.save(index_path)
    
    assert os.path.exists(index_path)
    
    store2 = FAISSVectorStore(dimension=512)
    loaded = store2.load(index_path)
    assert loaded is True
    assert store2.count == 1
    results = store2.search(vec)
    assert results[0].id == 42

def test_search_returns_cosine_similarity(vector_store, sample_embedding):
    vector_store.add(sample_embedding, 1)
    results = vector_store.search(sample_embedding)
    assert 0.99 <= results[0].similarity <= 1.01

def test_large_batch(vector_store):
    np.random.seed(42)
    vectors = np.array([normalize(np.random.randn(512)) for _ in range(100)])
    ids = np.arange(100)
    vector_store.add_batch(vectors, ids)
    assert vector_store.count == 100
    
    results = vector_store.search(vectors[50], k=5)
    assert results[0].id == 50
    assert results[0].similarity > 0.99

def test_thread_safety(vector_store):
    import concurrent.futures
    vectors = [normalize(np.random.randn(512)) for _ in range(50)]
    
    def add_vector(i):
        vector_store.add(vectors[i], i)
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(add_vector, range(50)))
        
    assert vector_store.count == 50
