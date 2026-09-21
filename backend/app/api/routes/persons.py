"""Person management API routes — CRUD for enrolled persons."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.repositories.person_repo import PersonRepository
from app.db.repositories.embedding_repo import EmbeddingRepository
from app.schemas.person import PersonCreate, PersonUpdate, PersonResponse, PersonListResponse
from app.core.security import get_current_user, require_role, require_owner, Role
from app.db.models import SystemUser
from app.api.deps import get_vector_store, get_recognition_service
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/persons", tags=["Persons"])


@router.post("", response_model=PersonResponse, status_code=201)
async def create_person(
    person_in: PersonCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_owner),
):
    """Create a new person. Strictly requires OWNER role."""
    from app.core.security import log_security_audit

    existing = await PersonRepository.get_by_identifier(db, person_in.person_identifier)
    if existing:
        raise HTTPException(status_code=400, detail="Person identifier already exists")

    person = await PersonRepository.create(db, person_in)

    actor_id = current_user.get("user_id") or current_user.get("id")
    actor_name = current_user.get("name") or current_user.get("username")
    await log_security_audit(
        db=db,
        actor_id=actor_id,
        actor_name=actor_name,
        actor_role="owner",
        action="CREATE_PERSON",
        target_entity=f"Person:{person.name}",
        details=f"Created employee {person.name} ({person.person_identifier}, {person.department})"
    )
    await db.commit()

    return PersonResponse(
        id=person.id,
        person_identifier=person.person_identifier,
        name=person.name,
        department=person.department,
        role=person.role,
        notes=person.notes,
        status=person.status,
        created_at=person.created_at,
        updated_at=person.updated_at,
        embedding_count=0,
    )


@router.get("", response_model=PersonListResponse)
async def list_persons(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: SystemUser = Depends(get_current_user),
):
    """List persons with pagination and optional status filter."""
    persons, total = await PersonRepository.list_all(db, skip=skip, limit=limit, status=status)
    items = [
        PersonResponse(
            id=p.id,
            person_identifier=p.person_identifier,
            name=p.name,
            department=p.department,
            role=p.role,
            notes=p.notes,
            status=p.status,
            created_at=p.created_at,
            updated_at=p.updated_at,
            embedding_count=len(p.embeddings) if p.embeddings else 0,
        )
        for p in persons
    ]
    return PersonListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{person_id}", response_model=PersonResponse)
async def get_person(
    person_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SystemUser = Depends(get_current_user),
):
    """Get a single person by ID with embedding count."""
    person = await PersonRepository.get_by_id(db, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    return PersonResponse(
        id=person.id,
        person_identifier=person.person_identifier,
        name=person.name,
        department=person.department,
        role=person.role,
        notes=person.notes,
        status=person.status,
        created_at=person.created_at,
        updated_at=person.updated_at,
        embedding_count=len(person.embeddings) if person.embeddings else 0,
    )


@router.put("/{person_id}", response_model=PersonResponse)
async def update_person(
    person_id: int,
    person_in: PersonUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_owner),
):
    """Update a person's non-biometric fields. Owner only."""
    from app.core.security import log_security_audit

    person = await PersonRepository.update(db, person_id, person_in)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    actor_id = current_user.get("user_id") or current_user.get("id")
    actor_name = current_user.get("name") or current_user.get("username")
    await log_security_audit(
        db=db,
        actor_id=actor_id,
        actor_name=actor_name,
        actor_role="owner",
        action="UPDATE_PERSON",
        target_entity=f"Person:{person.name}",
        details=f"Updated employee {person.name} ({person.person_identifier})"
    )
    await db.commit()

    return PersonResponse(
        id=person.id,
        person_identifier=person.person_identifier,
        name=person.name,
        department=person.department,
        role=person.role,
        notes=person.notes,
        status=person.status,
        created_at=person.created_at,
        updated_at=person.updated_at,
        embedding_count=len(person.embeddings) if person.embeddings else 0,
    )


@router.delete("/{person_id}")
async def delete_person(
    person_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_owner),
    vector_store=Depends(get_vector_store),
    recognition_service=Depends(get_recognition_service),
    settings=Depends(get_settings),
):
    """Delete a person and all their biometric data (embeddings + FAISS entries).

    Strictly requires OWNER role. Non-owners receive 403 Forbidden.
    """
    from app.core.security import log_security_audit

    person = await PersonRepository.get_by_id(db, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    person_name = person.name
    person_ident = person.person_identifier

    # 1. Remove embeddings from DB and FAISS
    faiss_ids = await EmbeddingRepository.delete_by_person(db, person_id)
    for fid in faiss_ids:
        vector_store.remove(fid)
    vector_store.save(settings.FAISS_INDEX_PATH)

    # 2. Remove from in-memory identity map
    recognition_service.remove_from_identity_map(faiss_ids)

    # 3. Permanently hard-delete the person from database
    await PersonRepository.hard_delete(db, person_id)

    # 4. Reload identity map from DB so all workers immediately drop this identity
    await recognition_service.load_identity_map(db)

    actor_id = current_user.get("user_id") or current_user.get("id")
    actor_name = current_user.get("name") or current_user.get("username")
    await log_security_audit(
        db=db,
        actor_id=actor_id,
        actor_name=actor_name,
        actor_role="owner",
        action="DELETE_PERSON",
        target_entity=f"Person:{person_name}",
        details=f"Permanently deleted employee {person_name} ({person_ident}) and removed {len(faiss_ids)} embeddings"
    )
    await db.commit()

    logger.info(f"Person {person_id} permanently deleted with {len(faiss_ids)} embeddings removed")
    return {"status": "deleted", "embeddings_removed": len(faiss_ids)}
