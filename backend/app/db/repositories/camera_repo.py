import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RTSPCamera

logger = logging.getLogger(__name__)


class RTSPCameraRepository:
    """Repository for RTSP Camera persistence and management."""

    @staticmethod
    def sanitize(camera: RTSPCamera, include_password: bool = False) -> Dict[str, Any]:
        """Convert RTSPCamera to a safe dictionary, ensuring password is never leaked."""
        return {
            "id": camera.id,
            "name": camera.name,
            "rtsp_url": camera.rtsp_url,
            "username": camera.username,
            "location": camera.location,
            "mode": camera.mode,
            "enabled": camera.enabled,
            "status": camera.status,
            "last_seen": camera.last_seen.isoformat() if camera.last_seen else None,
            "has_password": bool(camera.password),
            "created_at": camera.created_at.isoformat() if camera.created_at else None,
            "updated_at": camera.updated_at.isoformat() if camera.updated_at else None,
            # Explicitly omit password unless explicitly requested for internal worker connection
            **({"password": camera.password} if include_password else {})
        }

    @staticmethod
    async def create(
        session: AsyncSession,
        name: str,
        rtsp_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        location: Optional[str] = None,
        mode: str = "CHECK-IN",
        enabled: bool = True,
    ) -> RTSPCamera:
        camera = RTSPCamera(
            name=name,
            rtsp_url=rtsp_url,
            username=username,
            password=password,
            location=location,
            mode=mode.upper(),
            enabled=enabled,
            status="disconnected",
        )
        session.add(camera)
        await session.commit()
        await session.refresh(camera)
        logger.info(f"Created RTSP Camera: ID={camera.id}, Name='{camera.name}', Mode='{camera.mode}'")
        return camera

    @staticmethod
    async def get_by_id(session: AsyncSession, camera_id: int) -> Optional[RTSPCamera]:
        stmt = select(RTSPCamera).where(RTSPCamera.id == camera_id)
        result = await session.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def list_all(session: AsyncSession, enabled_only: bool = False) -> List[RTSPCamera]:
        stmt = select(RTSPCamera)
        if enabled_only:
            stmt = stmt.where(RTSPCamera.enabled == True)
        stmt = stmt.order_by(desc(RTSPCamera.id))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update(
        session: AsyncSession,
        camera_id: int,
        name: Optional[str] = None,
        rtsp_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        location: Optional[str] = None,
        mode: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[RTSPCamera]:
        camera = await RTSPCameraRepository.get_by_id(session, camera_id)
        if not camera:
            return None

        if name is not None:
            camera.name = name
        if rtsp_url is not None:
            camera.rtsp_url = rtsp_url
        if username is not None:
            camera.username = username
        if password is not None and password.strip() != "":
            camera.password = password
        if location is not None:
            camera.location = location
        if mode is not None:
            camera.mode = mode.upper()
        if enabled is not None:
            camera.enabled = enabled

        camera.updated_at = datetime.now()
        await session.commit()
        await session.refresh(camera)
        logger.info(f"Updated RTSP Camera ID={camera_id}")
        return camera

    @staticmethod
    async def update_status(
        session: AsyncSession,
        camera_id: int,
        status: str,
        last_seen: Optional[datetime] = None
    ) -> None:
        camera = await RTSPCameraRepository.get_by_id(session, camera_id)
        if camera:
            camera.status = status
            if last_seen:
                camera.last_seen = last_seen
            await session.commit()

    @staticmethod
    async def delete(session: AsyncSession, camera_id: int) -> bool:
        camera = await RTSPCameraRepository.get_by_id(session, camera_id)
        if not camera:
            return False
        await session.delete(camera)
        await session.commit()
        logger.info(f"Deleted RTSP Camera ID={camera_id}")
        return True

