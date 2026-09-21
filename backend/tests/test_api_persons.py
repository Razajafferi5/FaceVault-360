import pytest
import pytest_asyncio
from app.db.repositories.person_repo import PersonRepository
from app.db.repositories.embedding_repo import EmbeddingRepository
from app.db.repositories.event_repo import EventRepository
from app.schemas.person import PersonCreate, PersonUpdate
from app.schemas.events import EventFilter

@pytest.mark.asyncio
async def test_person_repo_create(db_session):
    p_in = PersonCreate(name="John Doe", person_identifier="EMP001", role="employee")
    person = await PersonRepository.create(db_session, p_in)
    assert person.id is not None
    assert person.name == "John Doe"

@pytest.mark.asyncio
async def test_person_repo_get_by_id(db_session):
    p_in = PersonCreate(name="Jane Doe", person_identifier="EMP002", role="employee")
    created = await PersonRepository.create(db_session, p_in)
    fetched = await PersonRepository.get_by_id(db_session, created.id)
    assert fetched is not None
    assert fetched.person_identifier == "EMP002"

@pytest.mark.asyncio
async def test_person_repo_list_all(db_session):
    await PersonRepository.create(db_session, PersonCreate(name="P1", person_identifier="ID1"))
    await PersonRepository.create(db_session, PersonCreate(name="P2", person_identifier="ID2"))
    persons, total = await PersonRepository.list_all(db_session)
    assert len(persons) >= 2
    assert total >= 2

@pytest.mark.asyncio
async def test_person_repo_update(db_session):
    person = await PersonRepository.create(db_session, PersonCreate(name="Old Name", person_identifier="ID3"))
    updated = await PersonRepository.update(db_session, person.id, PersonUpdate(name="New Name"))
    assert updated.name == "New Name"

@pytest.mark.asyncio
async def test_person_repo_delete(db_session):
    person = await PersonRepository.create(db_session, PersonCreate(name="To Delete", person_identifier="ID4"))
    success = await PersonRepository.delete(db_session, person.id)
    assert success is True
    fetched = await PersonRepository.get_by_id(db_session, person.id)
    assert fetched.status == "deleted"

@pytest.mark.asyncio
async def test_person_repo_count_active(db_session):
    initial_count = await PersonRepository.count_active(db_session)
    await PersonRepository.create(db_session, PersonCreate(name="Active", person_identifier="ID5"))
    new_count = await PersonRepository.count_active(db_session)
    assert new_count == initial_count + 1

@pytest.mark.asyncio
async def test_embedding_repo_create(db_session, sample_embedding):
    person = await PersonRepository.create(db_session, PersonCreate(name="Emb Person", person_identifier="ID6"))
    emb = await EmbeddingRepository.create(
        session=db_session,
        person_id=person.id,
        embedding_bytes=sample_embedding.tobytes(),
        faiss_id=1,
        pose_label="front",
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        quality_score=0.9
    )
    assert emb.id is not None
    assert emb.faiss_id == 1

@pytest.mark.asyncio
async def test_embedding_repo_get_by_person(db_session, sample_embedding):
    person = await PersonRepository.create(db_session, PersonCreate(name="Emb Person 2", person_identifier="ID7"))
    await EmbeddingRepository.create(
        session=db_session, person_id=person.id, embedding_bytes=sample_embedding.tobytes(),
        faiss_id=2, pose_label="left", yaw=-20.0, pitch=0.0, roll=0.0, quality_score=0.9
    )
    await EmbeddingRepository.create(
        session=db_session, person_id=person.id, embedding_bytes=sample_embedding.tobytes(),
        faiss_id=3, pose_label="right", yaw=20.0, pitch=0.0, roll=0.0, quality_score=0.9
    )
    
    embs = await EmbeddingRepository.get_by_person(db_session, person.id)
    assert len(embs) == 2

@pytest.mark.asyncio
async def test_embedding_repo_delete_by_person(db_session, sample_embedding):
    person = await PersonRepository.create(db_session, PersonCreate(name="Emb Person 3", person_identifier="ID8"))
    await EmbeddingRepository.create(
        session=db_session, person_id=person.id, embedding_bytes=sample_embedding.tobytes(),
        faiss_id=4, pose_label="front", yaw=0.0, pitch=0.0, roll=0.0, quality_score=0.9
    )
    
    deleted_ids = await EmbeddingRepository.delete_by_person(db_session, person.id)
    assert 4 in deleted_ids
    embs = await EmbeddingRepository.get_by_person(db_session, person.id)
    assert len(embs) == 0

@pytest.mark.asyncio
async def test_embedding_repo_get_max_faiss_id(db_session, sample_embedding):
    person = await PersonRepository.create(db_session, PersonCreate(name="Emb Person 4", person_identifier="ID9"))
    await EmbeddingRepository.create(
        session=db_session, person_id=person.id, embedding_bytes=sample_embedding.tobytes(),
        faiss_id=100, pose_label="front", yaw=0.0, pitch=0.0, roll=0.0, quality_score=0.9
    )
    await EmbeddingRepository.create(
        session=db_session, person_id=person.id, embedding_bytes=sample_embedding.tobytes(),
        faiss_id=105, pose_label="up", yaw=0.0, pitch=-20.0, roll=0.0, quality_score=0.9
    )
    
    max_id = await EmbeddingRepository.get_max_faiss_id(db_session)
    assert max_id >= 105

@pytest.mark.asyncio
async def test_event_repo_create(db_session):
    person = await PersonRepository.create(db_session, PersonCreate(name="Event Person", person_identifier="ID10"))
    event = await EventRepository.create(db_session, {
        "person_id": person.id,
        "recognized_name": person.name,
        "confidence": 0.95,
        "status": "authorized",
        "authorization_result": "granted",
        "camera_id": "cam1"
    })
    assert event.id is not None
    assert event.status == "authorized"

@pytest.mark.asyncio
async def test_event_repo_list_events(db_session):
    person = await PersonRepository.create(db_session, PersonCreate(name="Event Person 2", person_identifier="ID11"))
    await EventRepository.create(db_session, {
        "person_id": person.id, "confidence": 0.92, "status": "authorized", "authorization_result": "granted", "camera_id": "cam1"
    })
    await EventRepository.create(db_session, {
        "person_id": person.id, "confidence": 0.35, "status": "denied", "authorization_result": "denied", "camera_id": "cam1"
    })
    
    events, total = await EventRepository.list_events(db_session, EventFilter(), skip=0, limit=10)
    assert total >= 2
    assert len(events) >= 2
