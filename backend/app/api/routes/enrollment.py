import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.db.database import get_db
from app.db.repositories.person_repo import PersonRepository
from app.schemas.enrollment import EnrollmentStartRequest, EnrollmentStartResponse, EnrollmentFrameResponse, EnrollmentCompleteResponse
from app.core.security import get_current_user, require_role, require_owner, Role
from app.db.models import SystemUser
from app.api.deps import get_enrollment_service, get_recognition_service
from app.utils.image import decode_base64_frame
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/enrollment", tags=["Enrollment"])

class FrameRequest(BaseModel):
    frame: str

@router.post("/start", response_model=EnrollmentStartResponse)
async def start_enrollment(
    req: EnrollmentStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_owner),
    enrollment_service = Depends(get_enrollment_service)
):
    person = await PersonRepository.get_by_id(db, req.person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
        
    session = enrollment_service.start_session(req.person_id, person.name)
    from app.services.enrollment import POSE_STEPS
    return EnrollmentStartResponse(
        session_id=session.session_id,
        person_name=person.name,
        total_poses=len(POSE_STEPS),
        poses=[{
            "step": ps.step,
            "label": ps.label,
            "instruction": ps.instruction,
            "target_yaw_range": ps.target_yaw,
            "target_pitch_range": ps.target_pitch,
        } for ps in POSE_STEPS],
    )

@router.post("/frame", response_model=EnrollmentFrameResponse)
async def process_enrollment_frame(
    frame_req: FrameRequest,
    session_id: str = Query(...),
    enrollment_service = Depends(get_enrollment_service)
):
    try:
        frame = await asyncio.to_thread(decode_base64_frame, frame_req.frame)
        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid frame data")
        return await asyncio.to_thread(enrollment_service.process_frame, session_id, frame)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="Invalid session ID")

@router.post("/complete", response_model=EnrollmentCompleteResponse)
async def complete_enrollment(
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_owner),
    enrollment_service = Depends(get_enrollment_service),
    recognition_service = Depends(get_recognition_service)
):
    logger.info(f"complete_enrollment called for session_id: {session_id}")
    try:
        res = await enrollment_service.complete_session(session_id, db)
        if not res.get("success", False):
            raise HTTPException(status_code=400, detail=res.get("message", "Enrollment failed"))
        
        # Instantly update identity map in memory (0ms) and reload from DB
        session = enrollment_service.get_session(session_id)
        if session:
            for pose in session.captured_poses:
                if pose.faiss_id:
                    recognition_service.update_identity_map(
                        pose.faiss_id, session.person_id, session.person_name, "active"
                    )
        await recognition_service.load_identity_map(db)
        logger.info(f"Enrollment completed successfully for session: {session_id}")
        return res

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/cancel")
async def cancel_enrollment(
    session_id: str = Query(...),
    current_user: dict = Depends(require_owner),
    enrollment_service = Depends(get_enrollment_service)
):
    enrollment_service.cancel_session(session_id)
    return {"status": "Cancelled"}
