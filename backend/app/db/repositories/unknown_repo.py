import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any
import numpy as np
import cv2
from sqlalchemy import select, func, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UnknownPersonEvent

logger = logging.getLogger(__name__)

class UnknownPersonRepository:
    # In-memory cache of recent unknown embeddings: event_id -> (embedding, timestamp)
    _recent_embeddings: Dict[int, Tuple[np.ndarray, float]] = {}

    @staticmethod
    async def record_or_update_unknown(
        session: AsyncSession,
        camera_name: str,
        camera_role: str,
        camera_id: Optional[int] = None,
        face_confidence: float = 0.0,
        quality_score: float = 0.0,
        face_crop: Optional[np.ndarray] = None,
        face_embedding: Optional[np.ndarray] = None,
        cooldown_seconds: float = 60.0,
        notes: Optional[str] = None
    ) -> Tuple[UnknownPersonEvent, bool]:
        """
        Deduplicates repeated detections of the same unknown person within cooldown_seconds
        into ONE single visit event.
        - Updates last_seen_at, detection_count, duration_seconds.
        - Replaces snapshot if a higher quality face crop is captured.
        - Returns (event, is_new: bool).
        """
        now_dt = datetime.now()
        cutoff = now_dt - timedelta(seconds=cooldown_seconds)

        # 1. Clean up stale embeddings in cache older than 10 minutes
        stale_threshold = now_dt.timestamp() - 600
        stale_keys = [k for k, v in UnknownPersonRepository._recent_embeddings.items() if v[1] < stale_threshold]
        for k in stale_keys:
            UnknownPersonRepository._recent_embeddings.pop(k, None)

        # 2. Query recent active unknown events on the same camera / role within cooldown
        stmt = (
            select(UnknownPersonEvent)
            .where(
                (UnknownPersonEvent.camera_name == camera_name) | (UnknownPersonEvent.camera_id == camera_id),
                UnknownPersonEvent.last_seen_at >= cutoff,
                UnknownPersonEvent.access_status.in_(["PENDING", "APPROVED", "DENIED"])
            )
            .order_by(desc(UnknownPersonEvent.last_seen_at))
            .limit(10)
        )
        candidates = (await session.execute(stmt)).scalars().all()

        matched_event: Optional[UnknownPersonEvent] = None

        if candidates:
            if face_embedding is not None and len(face_embedding) > 0:
                # Compare cosine similarity against recent embeddings in cache
                emb_norm = np.linalg.norm(face_embedding)
                query_vec = (face_embedding / emb_norm) if emb_norm > 0 else face_embedding

                best_sim = -1.0
                best_cand = None

                for cand in candidates:
                    if cand.id in UnknownPersonRepository._recent_embeddings:
                        stored_emb, _ = UnknownPersonRepository._recent_embeddings[cand.id]
                        c_norm = np.linalg.norm(stored_emb)
                        target_vec = (stored_emb / c_norm) if c_norm > 0 else stored_emb
                        sim = float(np.dot(query_vec, target_vec))
                        if sim > best_sim:
                            best_sim = sim
                            best_cand = cand

                # If cosine similarity >= 0.42, it's the exact same visitor
                if best_sim >= 0.42 and best_cand is not None:
                    matched_event = best_cand
                elif len(candidates) == 1 and best_sim == -1.0:
                    # Single active unknown person in frame on this camera
                    matched_event = candidates[0]
            else:
                # No embedding provided; match the single active unknown person in the cooldown window
                matched_event = candidates[0]

        if matched_event is not None:
            # UPDATE EXISTING VISIT EVENT
            matched_event.last_seen_at = now_dt
            matched_event.last_seen_time_str = now_dt.strftime("%I:%M:%S %p")
            matched_event.detection_count = (matched_event.detection_count or 1) + 1
            if matched_event.first_seen_at:
                matched_event.duration_seconds = max(0, int((now_dt - matched_event.first_seen_at).total_seconds()))

            # Check if current snapshot has higher quality score
            if quality_score > (matched_event.best_quality_score or 0.0) and face_crop is not None and face_crop.size > 0:
                matched_event.best_quality_score = round(float(quality_score), 3)
                matched_event.face_confidence = max(matched_event.face_confidence, round(float(face_confidence), 3))
                if matched_event.snapshot_path:
                    try:
                        cv2.imwrite(matched_event.snapshot_path, face_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                    except Exception as err:
                        logger.warning(f"Could not upgrade snapshot for event #{matched_event.id}: {err}")

            if face_embedding is not None and len(face_embedding) > 0:
                UnknownPersonRepository._recent_embeddings[matched_event.id] = (face_embedding, now_dt.timestamp())

            await session.commit()
            await session.refresh(matched_event)
            logger.info(
                f"Updated existing UnknownPersonEvent #{matched_event.id} ({matched_event.camera_name}): "
                f"count={matched_event.detection_count}, duration={matched_event.duration_seconds}s"
            )
            return matched_event, False

        # CREATE NEW VISIT EVENT (First detection or cooldown expired)
        event_uuid = str(uuid.uuid4())
        date_str = now_dt.strftime("%Y-%m-%d")
        time_str = now_dt.strftime("%I:%M:%S %p")

        snapshots_dir = os.path.join(os.getcwd(), "data", "unknown_snapshots")
        os.makedirs(snapshots_dir, exist_ok=True)
        filename = f"unknown_{event_uuid[:8]}_{int(now_dt.timestamp())}.jpg"
        filepath = os.path.join(snapshots_dir, filename)
        snapshot_url = f"/api/unknown-persons/snapshots/{filename}"

        if face_crop is not None and face_crop.size > 0:
            try:
                cv2.imwrite(filepath, face_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            except Exception as err:
                logger.error(f"Failed to save unknown face snapshot: {err}")

        new_event = UnknownPersonEvent(
            event_uuid=event_uuid,
            detected_at=now_dt,
            first_seen_at=now_dt,
            last_seen_at=now_dt,
            date_str=date_str,
            time_str=time_str,
            first_seen_time_str=time_str,
            last_seen_time_str=time_str,
            camera_id=camera_id,
            camera_name=camera_name,
            camera_role=camera_role.upper(),
            snapshot_path=filepath,
            snapshot_url=snapshot_url,
            face_confidence=round(float(face_confidence), 3),
            best_quality_score=round(float(quality_score), 3),
            detection_count=1,
            duration_seconds=0,
            recognition_status="UNKNOWN",
            access_status="PENDING",
            notes=notes or "Unrecognized visitor detected on RTSP camera feed"
        )
        session.add(new_event)
        await session.commit()
        await session.refresh(new_event)

        if face_embedding is not None and len(face_embedding) > 0:
            UnknownPersonRepository._recent_embeddings[new_event.id] = (face_embedding, now_dt.timestamp())

        logger.info(f"Created new UnknownPersonEvent #{new_event.id} ({event_uuid[:8]}) from camera '{camera_name}'")
        return new_event, True

    @staticmethod
    async def update_session_heartbeat(
        session: AsyncSession,
        event_id: int,
        added_count: int = 1,
        quality_score: float = 0.0,
        face_crop: Optional[np.ndarray] = None
    ) -> Optional[UnknownPersonEvent]:
        """
        Efficient throttled heartbeat update for an active unknown visit session.
        Increments detection_count, updates last_seen_at, duration_seconds, and upgrades snapshot.
        """
        event = await session.get(UnknownPersonEvent, event_id)
        if not event:
            return None

        now_dt = datetime.now()
        event.last_seen_at = now_dt
        event.last_seen_time_str = now_dt.strftime("%I:%M:%S %p")
        event.detection_count = (event.detection_count or 1) + added_count
        if event.first_seen_at:
            event.duration_seconds = max(0, int((now_dt - event.first_seen_at).total_seconds()))

        if quality_score > (event.best_quality_score or 0.0) and face_crop is not None and face_crop.size > 0:
            event.best_quality_score = round(float(quality_score), 3)
            if event.snapshot_path:
                try:
                    cv2.imwrite(event.snapshot_path, face_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                except Exception as e:
                    logger.warning(f"Could not update snapshot for event #{event_id}: {e}")

        await session.commit()
        await session.refresh(event)
        return event

    @staticmethod
    async def create_event(
        session: AsyncSession,
        event_uuid: str,
        date_str: str,
        time_str: str,
        camera_name: str,
        camera_role: str,
        snapshot_path: str,
        snapshot_url: str,
        camera_id: Optional[int] = None,
        face_confidence: float = 0.0,
        notes: Optional[str] = None
    ) -> UnknownPersonEvent:
        """Legacy helper for direct event creation with backward compatibility."""
        now_dt = datetime.now()
        event = UnknownPersonEvent(
            event_uuid=event_uuid,
            detected_at=now_dt,
            first_seen_at=now_dt,
            last_seen_at=now_dt,
            date_str=date_str,
            time_str=time_str,
            first_seen_time_str=time_str,
            last_seen_time_str=time_str,
            camera_id=camera_id,
            camera_name=camera_name,
            camera_role=camera_role.upper(),
            snapshot_path=snapshot_path,
            snapshot_url=snapshot_url,
            face_confidence=round(float(face_confidence), 3),
            best_quality_score=0.0,
            detection_count=1,
            duration_seconds=0,
            recognition_status="UNKNOWN",
            access_status="PENDING",
            notes=notes
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event

    @staticmethod
    async def list_events(
        session: AsyncSession,
        skip: int = 0,
        limit: int = 50,
        date_str: Optional[str] = None,
        access_status: Optional[str] = None,
        camera_role: Optional[str] = None
    ) -> Tuple[List[UnknownPersonEvent], int]:
        """Lists unknown person events with pagination and filtering."""
        query = select(UnknownPersonEvent)

        if date_str and date_str.lower() != "all":
            query = query.where(UnknownPersonEvent.date_str == date_str)

        if access_status and access_status.lower() != "all":
            query = query.where(func.upper(UnknownPersonEvent.access_status) == access_status.upper())

        if camera_role and camera_role.lower() != "all":
            query = query.where(func.upper(UnknownPersonEvent.camera_role) == camera_role.upper())

        # Count total matching
        count_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_query)).scalar() or 0

        # Execute paginated query ordered by newest first
        query = query.order_by(desc(UnknownPersonEvent.detected_at)).offset(skip).limit(limit)
        result = await session.execute(query)
        items = result.scalars().all()

        return list(items), total

    @staticmethod
    async def get_by_id(session: AsyncSession, event_id: int) -> Optional[UnknownPersonEvent]:
        """Fetch an unknown person event by integer ID."""
        result = await session.execute(select(UnknownPersonEvent).where(UnknownPersonEvent.id == event_id))
        return result.scalars().first()

    @staticmethod
    async def get_by_uuid(session: AsyncSession, event_uuid: str) -> Optional[UnknownPersonEvent]:
        """Fetch an unknown person event by UUID string."""
        result = await session.execute(select(UnknownPersonEvent).where(UnknownPersonEvent.event_uuid == event_uuid))
        return result.scalars().first()

    @staticmethod
    async def approve_event(
        session: AsyncSession,
        event_id: int,
        approved_by_id: Optional[int],
        approved_by_name: str
    ) -> Optional[UnknownPersonEvent]:
        """Owner approval action for an unknown visitor."""
        event = await UnknownPersonRepository.get_by_id(session, event_id)
        if not event:
            return None

        event.access_status = "APPROVED"
        event.approved_by_id = approved_by_id
        event.approved_by_name = approved_by_name
        event.approved_at = datetime.now()
        event.updated_at = datetime.now()

        await session.commit()
        await session.refresh(event)
        logger.info(f"UnknownPersonEvent #{event_id} APPROVED by {approved_by_name} (ID: {approved_by_id})")
        return event

    @staticmethod
    async def deny_event(
        session: AsyncSession,
        event_id: int,
        denied_by_id: Optional[int],
        denied_by_name: str
    ) -> Optional[UnknownPersonEvent]:
        """Owner denial action for an unknown person."""
        event = await UnknownPersonRepository.get_by_id(session, event_id)
        if not event:
            return None

        event.access_status = "DENIED"
        event.denied_by_id = denied_by_id
        event.denied_by_name = denied_by_name
        event.denied_at = datetime.now()
        event.updated_at = datetime.now()

        await session.commit()
        await session.refresh(event)
        logger.info(f"UnknownPersonEvent #{event_id} DENIED by {denied_by_name} (ID: {denied_by_id})")
        return event

    @staticmethod
    async def mark_enrolled(
        session: AsyncSession,
        event_id: int,
        enrolled_person_id: int
    ) -> Optional[UnknownPersonEvent]:
        """Links an unknown person record to their newly enrolled Person ID."""
        event = await UnknownPersonRepository.get_by_id(session, event_id)
        if not event:
            return None

        event.access_status = "ENROLLED"
        event.enrolled_person_id = enrolled_person_id
        event.updated_at = datetime.now()

        await session.commit()
        await session.refresh(event)
        logger.info(f"UnknownPersonEvent #{event_id} marked ENROLLED -> Person #{enrolled_person_id}")
        return event

    @staticmethod
    async def delete_event(session: AsyncSession, event_id: int) -> bool:
        """Deletes unknown person record and deletes local snapshot file."""
        event = await UnknownPersonRepository.get_by_id(session, event_id)
        if not event:
            return False

        snapshot_file = event.snapshot_path
        await session.delete(event)
        await session.commit()

        # Safely remove snapshot file from disk
        if snapshot_file and os.path.isfile(snapshot_file):
            try:
                os.remove(snapshot_file)
            except Exception as e:
                logger.warning(f"Could not remove snapshot file {snapshot_file}: {e}")

        logger.info(f"UnknownPersonEvent #{event_id} deleted successfully.")
        return True

    @staticmethod
    async def get_today_stats(session: AsyncSession, date_str: Optional[str] = None) -> Dict[str, int]:
        """Aggregates summary statistics for unknown persons on a given date (defaults to today)."""
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        base = select(UnknownPersonEvent).where(UnknownPersonEvent.date_str == date_str)

        total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
        pending = (await session.execute(select(func.count()).select_from(base.where(UnknownPersonEvent.access_status == "PENDING").subquery()))).scalar() or 0
        approved = (await session.execute(select(func.count()).select_from(base.where(UnknownPersonEvent.access_status == "APPROVED").subquery()))).scalar() or 0
        denied = (await session.execute(select(func.count()).select_from(base.where(UnknownPersonEvent.access_status == "DENIED").subquery()))).scalar() or 0
        enrolled = (await session.execute(select(func.count()).select_from(base.where(UnknownPersonEvent.access_status == "ENROLLED").subquery()))).scalar() or 0

        return {
            "total_today": total,
            "pending_count": pending,
            "approved_count": approved,
            "denied_count": denied,
            "enrolled_count": enrolled
        }
