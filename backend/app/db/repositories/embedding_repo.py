from typing import List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FaceEmbedding

class EmbeddingRepository:
    
    @staticmethod
    async def create(
        session: AsyncSession, 
        person_id: int, 
        embedding_bytes: bytes, 
        faiss_id: int, 
        pose_label: str, 
        yaw: float, 
        pitch: float, 
        roll: float, 
        quality_score: float
    ) -> FaceEmbedding:
        new_embedding = FaceEmbedding(
            person_id=person_id,
            embedding=embedding_bytes,
            faiss_id=faiss_id,
            pose_label=pose_label,
            yaw=yaw,
            pitch=pitch,
            roll=roll,
            quality_score=quality_score
        )
        session.add(new_embedding)
        await session.commit()
        await session.refresh(new_embedding)
        return new_embedding

    @staticmethod
    async def bulk_create(
        session: AsyncSession,
        records: list[dict]
    ) -> None:
        """Insert all enrollment angle embeddings in a single high-speed database transaction."""
        if not records:
            return
        embeddings = [
            FaceEmbedding(
                person_id=r["person_id"],
                embedding=r["embedding_bytes"],
                faiss_id=r["faiss_id"],
                pose_label=r["pose_label"],
                yaw=r["yaw"],
                pitch=r["pitch"],
                roll=r["roll"],
                quality_score=r["quality_score"]
            )
            for r in records
        ]
        session.add_all(embeddings)
        await session.commit()

    @staticmethod
    async def get_by_person(session: AsyncSession, person_id: int) -> List[FaceEmbedding]:
        stmt = select(FaceEmbedding).where(FaceEmbedding.person_id == person_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_all(session: AsyncSession) -> List[FaceEmbedding]:
        stmt = select(FaceEmbedding)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def delete_by_person(session: AsyncSession, person_id: int) -> List[int]:
        embeddings = await EmbeddingRepository.get_by_person(session, person_id)
        faiss_ids = [emb.faiss_id for emb in embeddings]
        
        for emb in embeddings:
            await session.delete(emb)
            
        await session.commit()
        return faiss_ids

    @staticmethod
    async def get_max_faiss_id(session: AsyncSession) -> int:
        stmt = select(func.max(FaceEmbedding.faiss_id))
        result = await session.execute(stmt)
        max_id = result.scalar_one_or_none()
        return max_id if max_id is not None else 0
