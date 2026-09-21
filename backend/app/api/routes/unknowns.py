import logging
import os
import cv2
import numpy as np
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.database import get_db
from app.core.security import get_current_user, require_owner, require_authenticated_user
from app.db.repositories.unknown_repo import UnknownPersonRepository
from app.schemas.unknown import (
    UnknownPersonEventResponse,
    UnknownPersonListResponse,
    UnknownPersonStatsResponse,
    UnknownActionRequest
)
from app.schemas.person import PersonResponse
from app.services.rtsp_manager import RTSPManager
from app.services.rtsp_enrollment import RTSPEnrollmentService
from app.api.deps import get_recognition_service, get_vector_store, get_rtsp_manager
from app.core.config import get_settings
from app.utils.image import decode_base64_frame

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/unknown-persons", tags=["Unknown Persons"])


class FrameEvalRequest(BaseModel):
    frame_base64: Optional[str] = None
    camera_id: Optional[int] = None
    camera_role: Optional[str] = None


class RtspEnrollRequest(BaseModel):
    name: str
    department: Optional[str] = "General"
    person_identifier: Optional[str] = None
    role: Optional[str] = "Employee"
    notes: Optional[str] = None
    sample_frames_base64: Optional[List[str]] = None


class RtspEnrollResponse(BaseModel):
    success: bool
    message: str
    person: PersonResponse
    unknown_event: Optional[UnknownPersonEventResponse] = None


@router.get("", response_model=UnknownPersonListResponse)
async def list_unknown_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    date: Optional[str] = Query(None, description="Date filter YYYY-MM-DD or 'all'"),
    status: Optional[str] = Query(None, description="Status filter: PENDING, APPROVED, DENIED, ENROLLED or 'all'"),
    camera_role: Optional[str] = Query(None, description="Camera role filter: CHECK-IN, CHECK-OUT or 'all'"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List unknown person detection events with pagination and filtering.
    Readable by authenticated users (Owner and Staff).
    """
    items, total = await UnknownPersonRepository.list_events(
        session=db,
        skip=skip,
        limit=limit,
        date_str=date,
        access_status=status,
        camera_role=camera_role
    )
    return UnknownPersonListResponse(
        items=[UnknownPersonEventResponse.model_validate(item) for item in items],
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/stats/today", response_model=UnknownPersonStatsResponse)
async def get_today_stats(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get summary statistics for today's unknown person visits.
    """
    stats = await UnknownPersonRepository.get_today_stats(db)
    return UnknownPersonStatsResponse(**stats)


@router.get("/snapshots/{filename}")
async def get_snapshot_image(filename: str):
    """
    Serve raw snapshot image file from disk.
    """
    # Sanitize filename
    safe_filename = os.path.basename(filename)
    snapshots_dir = os.path.join(os.getcwd(), "data", "unknown_snapshots")
    filepath = os.path.join(snapshots_dir, safe_filename)

    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snapshot image not found"
        )
    return FileResponse(filepath, media_type="image/jpeg")


@router.get("/{event_id}", response_model=UnknownPersonEventResponse)
async def get_unknown_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get single unknown person event details.
    """
    event = await UnknownPersonRepository.get_by_id(db, event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown person event #{event_id} not found"
        )
    return UnknownPersonEventResponse.model_validate(event)


@router.post("/{event_id}/approve", response_model=UnknownPersonEventResponse)
async def approve_visitor_entry(
    event_id: int,
    action_data: Optional[UnknownActionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_owner)  # STRICT OWNER-ONLY AUTH
):
    """
    Owner-only action: Approve entry for an unknown visitor.
    Non-owners receive HTTP 403 Forbidden.
    Updates live RTSP HUD overlay immediately.
    """
    owner_id = current_user.get("user_id") or current_user.get("id")
    owner_name = current_user.get("name", "System Owner")

    event = await UnknownPersonRepository.approve_event(
        session=db,
        event_id=event_id,
        approved_by_id=owner_id,
        approved_by_name=owner_name
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown person event #{event_id} not found"
        )

    # Immediately inform RTSP camera HUD overlay
    RTSPManager.set_unknown_status(event_id, "APPROVED")
    logger.info(f"Owner {owner_name} APPROVED unknown visitor event #{event_id}")

    return UnknownPersonEventResponse.model_validate(event)


@router.post("/{event_id}/deny", response_model=UnknownPersonEventResponse)
async def deny_visitor_entry(
    event_id: int,
    action_data: Optional[UnknownActionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_owner)  # STRICT OWNER-ONLY AUTH
):
    """
    Owner-only action: Deny entry for an unknown visitor.
    Non-owners receive HTTP 403 Forbidden.
    Updates live RTSP HUD overlay immediately.
    """
    owner_id = current_user.get("user_id") or current_user.get("id")
    owner_name = current_user.get("name", "System Owner")

    event = await UnknownPersonRepository.deny_event(
        session=db,
        event_id=event_id,
        denied_by_id=owner_id,
        denied_by_name=owner_name
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown person event #{event_id} not found"
        )

    # Immediately inform RTSP camera HUD overlay
    RTSPManager.set_unknown_status(event_id, "DENIED")
    logger.info(f"Owner {owner_name} DENIED unknown visitor event #{event_id}")

    return UnknownPersonEventResponse.model_validate(event)


@router.post("/{event_id}/enroll", response_model=UnknownPersonEventResponse)
async def mark_visitor_enrolled(
    event_id: int,
    enrolled_person_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_owner)  # STRICT OWNER-ONLY AUTH
):
    """
    Owner-only action: Mark an unknown person record as ENROLLED once enrolled via webcam.
    Non-owners receive HTTP 403 Forbidden.
    """
    event = await UnknownPersonRepository.mark_enrolled(
        session=db,
        event_id=event_id,
        enrolled_person_id=enrolled_person_id
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown person event #{event_id} not found"
        )

    RTSPManager.set_unknown_status(event_id, "ENROLLED")
    logger.info(f"Owner marked unknown visitor event #{event_id} as ENROLLED")

    return UnknownPersonEventResponse.model_validate(event)


@router.post("/eval-rtsp-frame")
async def evaluate_rtsp_frame_endpoint(
    req: FrameEvalRequest,
    recognition_service = Depends(get_recognition_service),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager),
    current_user: dict = Depends(require_authenticated_user)
):
    """
    Evaluates real-time RTSP video frame for enrollment suitability.
    Checks face detection, sharpness, pose angles, face size, and multiple-face hazards.
    """
    frame = None
    if req.frame_base64:
        frame = decode_base64_frame(req.frame_base64)
    elif rtsp_manager:
        frame = rtsp_manager.get_camera_raw_frame(camera_id=req.camera_id, mode=req.camera_role)

    if frame is None or frame.size == 0:
        return {
            "valid": False,
            "reason": "NO_FRAME",
            "instruction": "Awaiting active camera frame...",
            "quality_score": 0.0,
            "face_count": 0,
            "bbox": None
        }

    eval_res = RTSPEnrollmentService.evaluate_rtsp_frame(
        frame=frame,
        face_detector=recognition_service.face_detector,
        face_quality=recognition_service.face_quality
    )
    # Exclude non-serializable object
    eval_res.pop("face", None)
    return eval_res


@router.post("/{event_id}/enroll-rtsp", response_model=RtspEnrollResponse)
async def enroll_visitor_from_rtsp(
    event_id: int,
    req: RtspEnrollRequest,
    db: AsyncSession = Depends(get_db),
    recognition_service = Depends(get_recognition_service),
    vector_store = Depends(get_vector_store),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager),
    current_user: dict = Depends(require_owner)  # STRICT SERVER-SIDE OWNER AUTH
):
    """
    STRICT OWNER-ONLY ENDPOINT: Direct RTSP Biometric Enrollment.
    - Captures and filters multiple frames from the active RTSP stream.
    - Generates 512-D InsightFace ArcFace embeddings.
    - Creates ACTIVE Person in authoritative People database.
    - Updates FAISS vector store and reloads recognition gallery across all workers.
    - Links UnknownPersonEvent with status ENROLLED, method RTSP, and owner audit trail.
    - Non-owners calling this endpoint receive HTTP 403 Forbidden.
    """
    owner_name = current_user.get("name") or current_user.get("username", "Owner")

    # 1. Verify unknown person record exists
    event = await UnknownPersonRepository.get_by_id(db, event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown person event #{event_id} not found."
        )

    # 2. Gather candidate frame samples
    raw_samples: List[np.ndarray] = []
    if req.sample_frames_base64 and len(req.sample_frames_base64) > 0:
        for b64 in req.sample_frames_base64:
            f = decode_base64_frame(b64)
            if f is not None and f.size > 0:
                raw_samples.append(f)

    # If few or no samples sent from client, harvest directly from active RTSP camera worker
    if len(raw_samples) < 3 and rtsp_manager:
        cam_frame = rtsp_manager.get_camera_raw_frame(camera_id=event.camera_id, mode=event.camera_role)
        if cam_frame is not None and cam_frame.size > 0:
            raw_samples.append(cam_frame)

    # If snapshot image on disk exists, also include snapshot as fallback sample
    if len(raw_samples) < 2 and event.snapshot_path and os.path.exists(event.snapshot_path):
        try:
            snap = cv2.imread(event.snapshot_path)
            if snap is not None and snap.size > 0:
                raw_samples.append(snap)
        except Exception:
            pass

    if not raw_samples:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No camera frames were received or captured for enrollment."
        )

    person_data = {
        "name": req.name,
        "department": req.department or "General",
        "person_identifier": req.person_identifier,
        "role": req.role or "Employee",
        "notes": req.notes or f"Enrolled via RTSP from Unknown Event #{event_id}"
    }

    try:
        settings = get_settings()
        person, updated_event = await RTSPEnrollmentService.enroll_from_rtsp_samples(
            samples=raw_samples,
            person_data=person_data,
            db_session=db,
            recognition_service=recognition_service,
            vector_store=vector_store,
            settings=settings,
            unknown_event_id=event_id,
            owner_name=owner_name
        )

        return RtspEnrollResponse(
            success=True,
            message=f"Successfully enrolled {person.name} via RTSP. Biometric gallery updated.",
            person=PersonResponse.model_validate(person),
            unknown_event=UnknownPersonEventResponse.model_validate(updated_event) if updated_event else None
        )

    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err)
        )
    except Exception as exc:
        logger.error(f"RTSP enrollment failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete RTSP biometric enrollment: {str(exc)}"
        )


@router.delete("/{event_id}")
async def delete_unknown_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_owner)  # STRICT OWNER-ONLY AUTH
):
    """
    Owner-only action: Permanently delete an unknown person log record and snapshot file.
    Non-owners receive HTTP 403 Forbidden.
    """
    success = await UnknownPersonRepository.delete_event(db, event_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown person event #{event_id} not found"
        )
    return {"success": True, "message": f"Unknown person event #{event_id} deleted successfully"}
