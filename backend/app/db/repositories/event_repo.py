from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict, Any, Optional
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AccessEvent
from app.schemas.events import EventFilter

class EventRepository:
    
    @staticmethod
    async def create(session: AsyncSession, data: dict) -> AccessEvent:
        event = AccessEvent(**data)
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event

    @staticmethod
    async def list_events(session: AsyncSession, filters: EventFilter, skip: int = 0, limit: int = 50) -> Tuple[List[AccessEvent], int]:
        query = select(AccessEvent)
        
        conditions = []
        if filters.date_from:
            conditions.append(AccessEvent.timestamp >= filters.date_from)
        if filters.date_to:
            conditions.append(AccessEvent.timestamp <= filters.date_to)
        if filters.person_id is not None:
            conditions.append(AccessEvent.person_id == filters.person_id)
        if filters.status:
            conditions.append(AccessEvent.status == filters.status)
        if filters.camera_id:
            conditions.append(AccessEvent.camera_id == filters.camera_id)
        if filters.min_confidence is not None:
            conditions.append(AccessEvent.confidence >= filters.min_confidence)
        if filters.max_confidence is not None:
            conditions.append(AccessEvent.confidence <= filters.max_confidence)
            
        if conditions:
            query = query.where(and_(*conditions))
            
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar_one()
        
        stmt = query.order_by(desc(AccessEvent.timestamp)).offset(skip).limit(limit)
        result = await session.execute(stmt)
        items = list(result.scalars().all())
        
        return items, total

    @staticmethod
    async def get_today_stats(session: AsyncSession) -> Dict[str, int]:
        today_local = datetime.now().strftime('%Y-%m-%d')
        today_utc = datetime.utcnow().strftime('%Y-%m-%d')
        
        stmt = select(AccessEvent).where(
            func.date(AccessEvent.timestamp).in_([today_local, today_utc])
        )
        result = await session.execute(stmt)
        events = result.scalars().all()
        
        total = len(events)
        authorized = sum(1 for e in events if e.authorization_result == 'granted')
        denied = total - authorized
        
        return {
            "total_entries": total,
            "authorized_count": authorized,
            "denied_count": denied
        }

    @staticmethod
    async def get_analytics(session: AsyncSession, days: int = 7) -> List[Dict[str, Any]]:
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        stmt = select(AccessEvent).where(func.date(AccessEvent.timestamp) >= start_date)
        result = await session.execute(stmt)
        events = result.scalars().all()
        
        daily_stats = {}
        for event in events:
            if isinstance(event.timestamp, str):
                date_str = event.timestamp.split(' ')[0]
            elif hasattr(event.timestamp, 'strftime'):
                date_str = event.timestamp.strftime('%Y-%m-%d')
            else:
                date_str = str(event.timestamp)[:10]

            if date_str not in daily_stats:
                daily_stats[date_str] = {"date": date_str, "total": 0, "authorized": 0, "denied": 0}
            
            daily_stats[date_str]["total"] += 1
            if event.authorization_result == 'granted':
                daily_stats[date_str]["authorized"] += 1
            else:
                daily_stats[date_str]["denied"] += 1
                
        # Sort and return
        sorted_stats = sorted(daily_stats.values(), key=lambda x: x["date"])
        return sorted_stats

    @staticmethod
    async def get_recent(session: AsyncSession, limit: int = 10) -> List[AccessEvent]:
        stmt = select(AccessEvent).order_by(desc(AccessEvent.timestamp)).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())
