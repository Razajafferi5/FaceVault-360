import asyncio
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.core.security import require_owner, get_current_user
from app.api.deps import get_recognition_service, get_pipeline
from app.db.repositories.attendance_repo import AttendanceRepository
from app.db.repositories.person_repo import PersonRepository
from app.utils.image import decode_base64_frame

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/attendance", tags=["Attendance"])


class VerifyAndMarkRequest(BaseModel):
    frame: str  # Base64 encoded JPEG
    action: Optional[str] = "auto"  # "check_in", "check_out", "auto"


class MarkAttendanceRequest(BaseModel):
    employee_id: int
    employee_name: Optional[str] = None
    match_score: float = 1.0
    action: Optional[str] = "check_in"  # "check_in", "check_out", "auto"
    camera_name: Optional[str] = "Manual Portal"


@router.get("/today")
async def get_today_attendance(
    current_user: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db)
):
    """Fetch all attendance records and aggregated daily employee summaries for today (Owner only)."""
    today_str = AttendanceRepository.get_today_date_str()
    records = await AttendanceRepository.list_today(db)
    summaries = await AttendanceRepository.get_daily_summaries(db, today_str)
    return {
        "success": True,
        "date": today_str,
        "count": len(records),
        "records": [AttendanceRepository.to_dict(r) for r in records],
        "summaries": summaries
    }


@router.get("/history")
async def get_attendance_history(
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db)
):
    """Fetch recent attendance session records organization-wide (Owner only)."""
    records = await AttendanceRepository.list_history(db, limit=limit)
    return {
        "success": True,
        "count": len(records),
        "records": [AttendanceRepository.to_dict(r) for r in records]
    }


@router.get("/by-date")
async def get_attendance_by_date(
    date: str = Query(..., description="Date formatted as DD-MM-YYYY"),
    current_user: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db)
):
    """Fetch attendance records and aggregated daily employee summaries for a specific date (Owner only)."""
    records = await AttendanceRepository.list_by_date(db, date)
    summaries = await AttendanceRepository.get_daily_summaries(db, date)
    return {
        "success": True,
        "date": date,
        "count": len(records),
        "records": [AttendanceRepository.to_dict(r) for r in records],
        "summaries": summaries
    }


@router.get("/my-today")
async def get_my_today_attendance(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Staff / Personal endpoint: Returns attendance records and daily summary for the authenticated user only.
    Anti-IDOR: employee_id is derived strictly from the verified JWT.
    """
    from app.db.models import Person, SystemUser

    user_id = current_user.get("user_id") or current_user.get("id")
    person_id = current_user.get("person_id")

    if not person_id:
        if user_id:
            u_res = await db.execute(select(SystemUser).where(SystemUser.id == user_id))
            u = u_res.scalars().first()
            if u and u.person_id:
                person_id = u.person_id
        if not person_id:
            uname = current_user.get("username")
            if uname:
                p_res = await db.execute(select(Person).where(Person.name == uname))
                p = p_res.scalars().first()
                if p:
                    person_id = p.id

    today_str = AttendanceRepository.get_today_date_str()
    if not person_id:
        return {
            "success": True,
            "date": today_str,
            "employee_id": None,
            "employee_name": current_user.get("name"),
            "status": "NOT_ENROLLED",
            "first_check_in": None,
            "last_check_out": None,
            "total_duration_minutes": 0,
            "formatted_duration": "0m",
            "sessions_count": 0,
            "records": []
        }

    sessions = await AttendanceRepository.list_sessions_for_employee_date(db, person_id, today_str)
    open_session = await AttendanceRepository.get_open_session(db, person_id)
    status_str = "CHECKED_IN" if open_session else ("CHECKED_OUT" if sessions else "NOT_CHECKED_IN")

    total_minutes = 0
    first_check_in = None
    last_check_out = None

    for s in sessions:
        if s.check_in_time and not first_check_in:
            first_check_in = s.check_in_time
        if s.check_out_time:
            last_check_out = s.check_out_time
            total_minutes += AttendanceRepository.calculate_duration_minutes(s.check_in_time, s.check_out_time)

    formatted_dur = AttendanceRepository.format_duration(total_minutes)

    return {
        "success": True,
        "date": today_str,
        "employee_id": person_id,
        "employee_name": current_user.get("name"),
        "status": status_str,
        "first_check_in": first_check_in,
        "last_check_out": last_check_out,
        "total_duration_minutes": total_minutes,
        "formatted_duration": formatted_dur,
        "sessions_count": len(sessions),
        "records": [AttendanceRepository.to_dict(s) for s in sessions]
    }


@router.get("/my-history")
async def get_my_attendance_history(
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Staff / Personal endpoint: Returns historical attendance records for the authenticated user only.
    Anti-IDOR: employee_id is derived strictly from the verified JWT.
    """
    from app.db.models import Person, SystemUser, Attendance

    user_id = current_user.get("user_id") or current_user.get("id")
    person_id = current_user.get("person_id")
    if not person_id:
        if user_id:
            u_res = await db.execute(select(SystemUser).where(SystemUser.id == user_id))
            u = u_res.scalars().first()
            if u and u.person_id:
                person_id = u.person_id
        if not person_id:
            uname = current_user.get("username")
            if uname:
                p_res = await db.execute(select(Person).where(Person.name == uname))
                p = p_res.scalars().first()
                if p:
                    person_id = p.id

    if not person_id:
        return {
            "success": True,
            "count": 0,
            "employee_id": None,
            "records": []
        }

    stmt = (
        select(Attendance)
        .where(Attendance.employee_id == person_id)
        .order_by(Attendance.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    return {
        "success": True,
        "count": len(records),
        "employee_id": person_id,
        "records": [AttendanceRepository.to_dict(r) for r in records]
    }


@router.post("/check-in")
async def check_in_employee(
    req: MarkAttendanceRequest,
    db: AsyncSession = Depends(get_db)
):
    """Explicitly mark check-in for an employee."""
    person = await PersonRepository.get_by_id(db, req.employee_id)
    if not person:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee_name = req.employee_name or person.name
    camera_name = req.camera_name or "Manual Check-In"
    record, is_new, action_msg = await AttendanceRepository.mark_check_in(
        session=db,
        employee_id=person.id,
        employee_name=employee_name,
        match_score=req.match_score,
        camera_name=camera_name
    )

    return {
        "success": True,
        "status": "marked" if is_new else "already_marked",
        "action": action_msg,
        "message": action_msg,
        "is_new": is_new,
        "record": AttendanceRepository.to_dict(record)
    }


@router.post("/check-out")
async def check_out_employee(
    req: MarkAttendanceRequest,
    db: AsyncSession = Depends(get_db)
):
    """Explicitly mark check-out for an employee's current open session."""
    person = await PersonRepository.get_by_id(db, req.employee_id)
    if not person:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee_name = req.employee_name or person.name
    camera_name = req.camera_name or "Manual Check-Out"
    record, is_closed, action_msg = await AttendanceRepository.mark_check_out(
        session=db,
        employee_id=person.id,
        employee_name=employee_name,
        match_score=req.match_score,
        camera_name=camera_name
    )

    if not record:
        return {
            "success": False,
            "status": "no_open_session",
            "action": action_msg,
            "message": "NO ACTIVE CHECK-IN SESSION FOUND",
            "is_new": False,
            "record": None
        }

    return {
        "success": True,
        "status": "checked_out",
        "action": action_msg,
        "message": action_msg,
        "is_new": is_closed,
        "record": AttendanceRepository.to_dict(record)
    }


@router.post("/mark")
async def mark_attendance_direct(
    req: MarkAttendanceRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Mark attendance for an employee using Open Session State Machine.
    Supports multiple sessions per day.
    """
    person = await PersonRepository.get_by_id(db, req.employee_id)
    if not person:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee_name = req.employee_name or person.name
    action = (req.action or "check_in").lower()
    camera_name = req.camera_name or "Attendance Portal"

    if action == "check_out":
        record, success, action_msg = await AttendanceRepository.mark_check_out(
            session=db,
            employee_id=person.id,
            employee_name=employee_name,
            match_score=req.match_score,
            camera_name=camera_name
        )
    elif action == "auto":
        record, success, action_msg = await AttendanceRepository.process_rtsp_attendance(
            session=db,
            employee_id=person.id,
            employee_name=employee_name,
            match_score=req.match_score,
            camera_name=camera_name,
            camera_mode="COMBINED"
        )
    else:  # check_in default
        record, success, action_msg = await AttendanceRepository.mark_check_in(
            session=db,
            employee_id=person.id,
            employee_name=employee_name,
            match_score=req.match_score,
            camera_name=camera_name
        )

    return {
        "success": True if record else False,
        "status": "marked" if success else "already_marked",
        "action": action_msg,
        "message": action_msg,
        "is_new": success,
        "record": AttendanceRepository.to_dict(record) if record else None
    }


@router.post("/verify-and-mark")
async def verify_and_mark(
    req: VerifyAndMarkRequest,
    recognition_service=Depends(get_recognition_service),
    pipeline=Depends(get_pipeline),
    db: AsyncSession = Depends(get_db)
):
    """
    One-step capture:
    Takes webcam frame, performs deep ArcFace recognition, enforces strict threshold.
    - If unknown or score < threshold: Returns UNKNOWN PERSON / ATTENDANCE REJECTED.
    - If recognized: Applies Open Session state machine.
    """
    frame = decode_base64_frame(req.frame)
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image data")

    try:
        result = await asyncio.to_thread(recognition_service.recognize_frame, frame)
        faces = result.get("faces", [])
        guidance = result.get("camera_guidance")

        if not faces:
            return {
                "success": False,
                "status": "no_face",
                "message": "NO FACE DETECTED",
                "guidance": guidance
            }

        # Select primary face (highest confidence)
        best_face = max(faces, key=lambda f: f.get("confidence", 0.0))
        person_id = best_face.get("person_id")
        name = best_face.get("name")
        similarity = best_face.get("similarity", 0.0)
        authorized = best_face.get("authorized", False)
        is_unknown = best_face.get("is_unknown", True)

        # Log recognition details clearly
        logger.info(
            f"Verify & Mark: name={name} person_id={person_id} similarity={similarity:.3f} "
            f"threshold={recognition_service.settings.RECOGNITION_THRESHOLD:.2f} authorized={authorized}"
        )

        # STRICT UNKNOWN REJECTION:
        # If not authorized, or unknown, or similarity < threshold:
        # NEVER mark attendance.
        if is_unknown or not authorized or not person_id or similarity < recognition_service.settings.RECOGNITION_THRESHOLD:
            try:
                from app.db.models import AccessEvent
                denied_event = AccessEvent(
                    person_id=None,
                    recognized_name="Unknown Person",
                    confidence=round(float(similarity), 3),
                    status="denied",
                    authorization_result="denied",
                    camera_id="Webcam Portal",
                    failure_reason="UNKNOWN_OR_UNAUTHORIZED"
                )
                db.add(denied_event)
                await db.commit()
            except Exception as log_err:
                logger.warning(f"Failed to log denied access event: {log_err}")

            return {
                "success": False,
                "status": "unknown",
                "message": "UNKNOWN PERSON / ATTENDANCE REJECTED",
                "similarity": round(float(similarity), 3),
                "threshold": recognition_service.settings.RECOGNITION_THRESHOLD,
                "guidance": guidance,
                "bbox": best_face.get("bbox")
            }

        # Valid recognized employee -> Execute state machine
        action = (req.action or "auto").lower()
        if action == "check_out":
            record, success, action_msg = await AttendanceRepository.mark_check_out(
                session=db,
                employee_id=person_id,
                employee_name=name,
                match_score=similarity,
                camera_name="Webcam"
            )
        elif action == "check_in":
            record, success, action_msg = await AttendanceRepository.mark_check_in(
                session=db,
                employee_id=person_id,
                employee_name=name,
                match_score=similarity,
                camera_name="Webcam"
            )
        else:
            record, success, action_msg = await AttendanceRepository.process_rtsp_attendance(
                session=db,
                employee_id=person_id,
                employee_name=name,
                match_score=similarity,
                camera_name="Webcam",
                camera_mode="COMBINED"
            )

        return {
            "success": True if record else False,
            "status": "marked" if success else "already_marked",
            "action": action_msg,
            "message": action_msg,
            "is_new": success,
            "employee_id": person_id,
            "employee_name": name,
            "similarity": round(float(similarity), 3),
            "record": AttendanceRepository.to_dict(record) if record else None,
            "guidance": guidance,
            "bbox": best_face.get("bbox")
        }

    except Exception as e:
        logger.error(f"Error in verify_and_mark: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Attendance verification failed")
