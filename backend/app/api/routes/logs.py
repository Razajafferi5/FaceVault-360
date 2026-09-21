"""Entry logs API routes — paginated, filterable access event history."""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.repositories.event_repo import EventRepository
from app.schemas.events import EventListResponse, EventFilter, AccessEventResponse
from app.core.security import get_current_user
from app.db.models import SystemUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["Logs"])


@router.get("", response_model=EventListResponse)
async def list_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    person_id: Optional[int] = None,
    status: Optional[str] = None,
    camera_id: Optional[str] = None,
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
    current_user: SystemUser = Depends(get_current_user),
):
    """List access events with filters and server-side pagination."""
    filters = EventFilter(
        date_from=date_from,
        date_to=date_to,
        person_id=person_id,
        status=status,
        camera_id=camera_id,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
    )

    events, total = await EventRepository.list_events(db, filters, skip=skip, limit=limit)
    items = [
        AccessEventResponse.model_validate(e) for e in events
    ]
    return EventListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/recent")
async def get_recent_logs(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: SystemUser = Depends(get_current_user),
):
    """Get most recent access events (for dashboard widget)."""
    events = await EventRepository.get_recent(db, limit=limit)
    return [AccessEventResponse.model_validate(e) for e in events]
