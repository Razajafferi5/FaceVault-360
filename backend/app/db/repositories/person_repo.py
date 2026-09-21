from typing import List, Tuple, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Person
from app.schemas.person import PersonCreate, PersonUpdate

class PersonRepository:
    
    @staticmethod
    async def create(session: AsyncSession, data: PersonCreate) -> Person:
        new_person = Person(**data.model_dump())
        session.add(new_person)
        await session.commit()
        await session.refresh(new_person)
        return new_person

    @staticmethod
    async def get_by_id(session: AsyncSession, id: int) -> Optional[Person]:
        stmt = select(Person).options(selectinload(Person.embeddings)).where(Person.id == id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_identifier(session: AsyncSession, identifier: str) -> Optional[Person]:
        stmt = select(Person).where(Person.person_identifier == identifier)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(session: AsyncSession, skip: int = 0, limit: int = 50, status: Optional[str] = None) -> Tuple[List[Person], int]:
        query = select(Person)
        if status:
            query = query.where(Person.status == status)
        else:
            query = query.where(Person.status != 'deleted')
            
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar_one()
        
        stmt = query.options(selectinload(Person.embeddings)).order_by(Person.id.desc()).offset(skip).limit(limit)
        result = await session.execute(stmt)
        items = list(result.scalars().all())
        
        return items, total

    @staticmethod
    async def update(session: AsyncSession, id: int, data: PersonUpdate) -> Optional[Person]:
        person = await PersonRepository.get_by_id(session, id)
        if not person:
            return None
            
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(person, key, value)
            
        await session.commit()
        await session.refresh(person)
        return person

    @staticmethod
    async def delete(session: AsyncSession, id: int) -> bool:
        """Permanently delete person record from database."""
        return await PersonRepository.hard_delete(session, id)

    @staticmethod
    async def hard_delete(session: AsyncSession, id: int) -> bool:
        person = await PersonRepository.get_by_id(session, id)
        if not person:
            return False
            
        await session.delete(person)
        await session.commit()
        return True
        
    @staticmethod
    async def count_active(session: AsyncSession) -> int:
        stmt = select(func.count()).select_from(Person).where(Person.status == 'active')
        result = await session.execute(stmt)
        return result.scalar_one()
