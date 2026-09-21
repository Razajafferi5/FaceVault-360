import pytest
import pytest_asyncio
import numpy as np
from app.services.faiss_store import FAISSVectorStore
from app.services.authorization import AuthorizationService
from app.db.repositories.person_repo import PersonRepository
from app.db.repositories.embedding_repo import EmbeddingRepository
from app.schemas.person import PersonCreate
from app.services.face_detector import DetectedFace

class MockFaceDetector:
    def __init__(self, sample_embedding):
        self.sample_embedding = sample_embedding
        
    def detect(self, frame):
        face = DetectedFace(
            bbox=[100, 100, 200, 200],
            confidence=0.99,
            landmarks=np.zeros((5, 2)),
            embedding=None,
            pose=[0, 0, 0]
        )
        return [face]
        
    def extract_embedding(self, frame, face_data=None):
        return self.sample_embedding
        
    def detect_and_embed(self, frame):
        faces = self.detect(frame)
        for f in faces:
            f.embedding = self.extract_embedding(frame)
        return faces

class MockHeadPoseEstimator:
    def is_within_recognition_range(self, yaw, pitch, max_yaw=45, max_pitch=30):
        return abs(yaw) <= max_yaw and abs(pitch) <= max_pitch
    def estimate(self, face_image):
        return []

@pytest_asyncio.fixture
async def integration_setup(db_session, settings, sample_embedding):
    vector_store = FAISSVectorStore(dimension=512)
    auth_service = AuthorizationService(settings)
    detector = MockFaceDetector(sample_embedding)
    pose_estimator = MockHeadPoseEstimator()
    
    return {
        "db": db_session,
        "vector_store": vector_store,
        "auth_service": auth_service,
        "detector": detector,
        "pose_estimator": pose_estimator,
        "sample_embedding": sample_embedding,
        "settings": settings
    }

@pytest.mark.asyncio
async def test_full_enrollment_flow(integration_setup):
    setup = integration_setup
    db = setup["db"]
    p_data = PersonCreate(name="Integration User", person_identifier="INT001")
    person = await PersonRepository.create(db, p_data)
    
    for i in range(7):
        emb_id = i + 1
        await EmbeddingRepository.create(
            session=db,
            person_id=person.id,
            embedding_bytes=setup["sample_embedding"].tobytes(),
            faiss_id=emb_id,
            pose_label="front",
            yaw=0.0,
            pitch=0.0,
            roll=0.0,
            quality_score=0.95
        )
        setup["vector_store"].add(setup["sample_embedding"], emb_id)
    
    assert setup["vector_store"].count == 7
    embs = await EmbeddingRepository.get_by_person(db, person.id)
    assert len(embs) == 7

@pytest.mark.asyncio
async def test_recognition_after_enrollment(integration_setup):
    setup = integration_setup
    db = setup["db"]
    p_data = PersonCreate(name="Recog User", person_identifier="REC001")
    person = await PersonRepository.create(db, p_data)
    await EmbeddingRepository.create(
        session=db,
        person_id=person.id,
        embedding_bytes=setup["sample_embedding"].tobytes(),
        faiss_id=100,
        pose_label="front",
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        quality_score=0.95
    )
    setup["vector_store"].add(setup["sample_embedding"], 100)
    
    # Simulate Recognition
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    faces = setup["detector"].detect_and_embed(frame)
    assert len(faces) == 1
    
    # Search in FAISS
    results = setup["vector_store"].search(faces[0].embedding, k=1)
    assert len(results) > 0
    match = results[0]
    assert match.id == 100
    assert match.similarity > 0.95  # Cosine similarity ~1.0

@pytest.mark.asyncio
async def test_unknown_person_denied(integration_setup):
    setup = integration_setup
    assert setup["vector_store"].count == 0
    
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    faces = setup["detector"].detect_and_embed(frame)
    results = setup["vector_store"].search(faces[0].embedding, k=1)
    assert len(results) == 0
    
    auth_result = setup["auth_service"].check(
        person_id=None,
        person_status=None,
        confidence=0.0,
        quality_score=0.9,
        liveness_score=0.9,
        pose_within_range=True
    )
    assert auth_result.granted is False
    assert auth_result.reason == "unknown_person"

@pytest.mark.asyncio
async def test_authorization_fail_closed(integration_setup):
    setup = integration_setup
    db = setup["db"]
    p_data = PersonCreate(name="Fail Closed", person_identifier="FC001")
    person = await PersonRepository.create(db, p_data)
    
    # Simulate correct match but poor quality
    auth_result = setup["auth_service"].check(
        person_id=person.id,
        person_status="active",
        confidence=0.9,
        quality_score=0.2, # below min_quality (0.5)
        liveness_score=0.9,
        pose_within_range=True
    )
    assert auth_result.granted is False
    assert auth_result.reason == "poor_quality"

@pytest.mark.asyncio
async def test_person_deletion_removes_from_faiss(integration_setup):
    setup = integration_setup
    db = setup["db"]
    p_data = PersonCreate(name="Delete User", person_identifier="DEL001")
    person = await PersonRepository.create(db, p_data)
    
    # Add embedding
    await EmbeddingRepository.create(
        session=db,
        person_id=person.id,
        embedding_bytes=setup["sample_embedding"].tobytes(),
        faiss_id=200,
        pose_label="front",
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        quality_score=0.95
    )
    setup["vector_store"].add(setup["sample_embedding"], 200)
    assert setup["vector_store"].count == 1
    
    # Delete person flow
    faiss_ids = await EmbeddingRepository.delete_by_person(db, person.id)
    for fid in faiss_ids:
        setup["vector_store"].remove(fid)
    success = await PersonRepository.delete(db, person.id)
    assert success is True
    assert setup["vector_store"].count == 0
