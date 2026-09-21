import asyncio
import logging
import time
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.api.deps import get_rtsp_manager, get_recognition_service
from app.db.repositories.camera_repo import RTSPCameraRepository
from app.services.rtsp_manager import RTSPManager
from app.core.security import require_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cameras", tags=["RTSP Cameras"])


class CameraCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    rtsp_url: str = Field(..., min_length=1, max_length=255)
    username: Optional[str] = None
    password: Optional[str] = None
    location: Optional[str] = None
    mode: str = Field(default="CHECK-IN")  # "CHECK-IN", "CHECK-OUT", "COMBINED"
    enabled: bool = True


class CameraUpdateRequest(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # None or empty string means keep existing
    location: Optional[str] = None
    mode: Optional[str] = None
    enabled: Optional[bool] = None


class TestConnectionRequest(BaseModel):
    rtsp_url: str
    username: Optional[str] = None
    password: Optional[str] = None


@router.get("")
async def list_cameras(
    enabled_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """
    List all configured RTSP cameras with live status and full diagnostics.
    Passwords are NEVER exposed.
    """
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=enabled_only)
    items = []
    for cam in cameras:
        data = RTSPCameraRepository.sanitize(cam, include_password=False)
        worker = rtsp_manager.get_worker(cam.id)
        if cam.enabled and (not worker or not worker.running):
            worker = rtsp_manager.ensure_camera_running(cam)
        if worker:
            summary = worker.get_status_summary()
            data["live_status"] = summary.get("status", worker.status)
            data["status_message"] = summary.get("status_message", worker.status_message)
            data["stream_fps"] = summary.get("stream_fps", summary.get("actual_fps", 0.0))
            data["display_fps"] = summary.get("display_fps", 0.0)
            data["ai_fps"] = summary.get("ai_fps", 0.0)
            data["actual_fps"] = summary.get("actual_fps", 0.0)
            data["avg_inference_ms"] = summary.get("avg_inference_ms", 0.0)
            data["latency_ms"] = summary.get("latency_ms", 0.0)
            data["dropped_frames"] = summary.get("dropped_frames", 0)
            data["queue_size"] = summary.get("queue_size", 0)
            data["is_receiving_frames"] = summary.get("is_receiving_frames", False)
            data["reconnect_attempt"] = summary.get("reconnect_attempt", 0)
            data["last_connected_time"] = summary.get("last_connected_time")
            data["last_frame_time"] = summary.get("last_frame_time")
            data["diagnostics"] = summary.get("diagnostics", {})
            data["redacted_url"] = summary.get("rtsp_url", data.get("rtsp_url"))
            data["active_persons"] = summary.get("active_persons_count", 0)
            data["recent_events"] = summary.get("recent_events", [])
            data["latest_detections"] = summary.get("latest_detections", [])
        else:
            data["live_status"] = "disconnected"
            data["status_message"] = "Camera disabled or inactive"
            data["stream_fps"] = 0.0
            data["display_fps"] = 0.0
            data["ai_fps"] = 0.0
            data["actual_fps"] = 0.0
            data["avg_inference_ms"] = 0.0
            data["latency_ms"] = 0.0
            data["dropped_frames"] = 0
            data["queue_size"] = 0
            data["is_receiving_frames"] = False
            data["reconnect_attempt"] = 0
            data["diagnostics"] = {}
            data["active_persons"] = 0
            data["recent_events"] = []
            data["latest_detections"] = []
        items.append(data)

    return {
        "success": True,
        "count": len(items),
        "items": items
    }


@router.post("")
async def create_camera(
    req: CameraCreateRequest,
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager),
    current_user: dict = Depends(require_owner)
):
    """Register a new RTSP camera."""
    mode_clean = req.mode.upper()
    if mode_clean not in ("CHECK-IN", "CHECK-OUT", "COMBINED"):
        mode_clean = "CHECK-IN"

    camera = await RTSPCameraRepository.create(
        session=db,
        name=req.name,
        rtsp_url=req.rtsp_url,
        username=req.username,
        password=req.password,
        location=req.location,
        mode=mode_clean,
        enabled=req.enabled
    )

    # Start worker if enabled
    if camera.enabled:
        rtsp_manager.start_camera(
            camera_id=camera.id,
            name=camera.name,
            rtsp_url=camera.rtsp_url,
            mode=camera.mode,
            location=camera.location,
            username=camera.username,
            password=camera.password
        )

    return {
        "success": True,
        "message": f"Camera '{camera.name}' added successfully",
        "camera": RTSPCameraRepository.sanitize(camera, include_password=False)
    }


@router.post("/test-connection")
async def test_connection(
    req: TestConnectionRequest,
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """
    Test reachability and frame grab of an RTSP stream before saving.
    Credentials are processed in memory and never logged.
    """
    result = await asyncio.to_thread(
        rtsp_manager.test_rtsp_connection,
        rtsp_url=req.rtsp_url,
        username=req.username,
        password=req.password,
        timeout_seconds=5.0
    )
    return result


@router.get("/checkin/status")
async def get_checkin_camera_status(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Find the configured Check-In RTSP camera and return its live status, diagnostics, and detections."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkin_cam = next((c for c in cameras if c.mode == "CHECK-IN" and c.enabled), None)
    if not checkin_cam:
        checkin_cam = next((c for c in cameras if c.mode == "CHECK-IN"), None)
    if not checkin_cam and cameras:
        checkin_cam = cameras[0]

    if not checkin_cam:
        return {
            "success": True,
            "configured": False,
            "message": "No Check-In camera configured yet",
            "camera": None,
            "latest_detections": [],
            "recent_events": [],
            "actual_fps": 0.0,
            "diagnostics": {}
        }

    data = RTSPCameraRepository.sanitize(checkin_cam, include_password=False)
    worker = rtsp_manager.get_worker(checkin_cam.id)
    if checkin_cam.enabled and (not worker or not worker.running):
        worker = rtsp_manager.ensure_camera_running(checkin_cam)

    if worker:
        summary = worker.get_status_summary()
        data["live_status"] = summary.get("status", worker.status)
        data["status_message"] = summary.get("status_message", worker.status_message)
        data["stream_fps"] = summary.get("stream_fps", summary.get("actual_fps", 0.0))
        data["display_fps"] = summary.get("display_fps", 0.0)
        data["ai_fps"] = summary.get("ai_fps", 0.0)
        data["actual_fps"] = summary.get("actual_fps", 0.0)
        data["avg_inference_ms"] = summary.get("avg_inference_ms", 0.0)
        data["latency_ms"] = summary.get("latency_ms", 0.0)
        data["dropped_frames"] = summary.get("dropped_frames", 0)
        data["queue_size"] = summary.get("queue_size", 0)
        data["is_receiving_frames"] = summary.get("is_receiving_frames", False)
        data["reconnect_attempt"] = summary.get("reconnect_attempt", 0)
        data["last_connected_time"] = summary.get("last_connected_time")
        data["last_frame_time"] = summary.get("last_frame_time")
        data["diagnostics"] = summary.get("diagnostics", {})
        data["redacted_url"] = summary.get("rtsp_url", data.get("rtsp_url"))
        data["active_persons"] = summary.get("active_persons_count", 0)
        data["recent_events"] = summary.get("recent_events", [])
        data["latest_detections"] = summary.get("latest_detections", [])
    else:
        data["live_status"] = "disconnected"
        data["status_message"] = "Worker inactive"
        data["stream_fps"] = 0.0
        data["display_fps"] = 0.0
        data["ai_fps"] = 0.0
        data["actual_fps"] = 0.0
        data["avg_inference_ms"] = 0.0
        data["latency_ms"] = 0.0
        data["dropped_frames"] = 0
        data["queue_size"] = 0
        data["is_receiving_frames"] = False
        data["reconnect_attempt"] = 0
        data["diagnostics"] = {}
        data["active_persons"] = 0
        data["recent_events"] = []
        data["latest_detections"] = []

    return {
        "success": True,
        "configured": True,
        "camera": data,
        "latest_detections": data.get("latest_detections", []),
        "recent_events": data.get("recent_events", []),
        "actual_fps": data.get("actual_fps", 0.0),
        "diagnostics": data.get("diagnostics", {})
    }


@router.get("/checkin/stream")
async def stream_checkin_camera_mjpeg(
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Streams live MJPEG specifically from the configured Check-In camera at 15 FPS."""
    target_interval = 1.0 / 15.0  # Exactly 15 FPS (66.67ms)

    async def frame_generator():
        try:
            while True:
                t0 = time.time()
                worker = rtsp_manager.get_worker_by_mode("CHECK-IN")
                if not worker and rtsp_manager.workers:
                    worker = next(iter(rtsp_manager.workers.values()), None)

                if worker:
                    frame_bytes, seq = worker.get_latest_jpeg_with_seq()
                else:
                    from app.services.rtsp_manager import RTSPCameraWorker
                    frame_bytes = RTSPCameraWorker.get_static_placeholder_jpeg("CHECK-IN CAMERA AWAITING CONNECTION")
                    seq = 0

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )

                elapsed = time.time() - t0
                sleep_time = max(0.002, target_interval - elapsed)
                await asyncio.sleep(sleep_time)
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/attendance/status")
async def get_attendance_camera_status(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Find the primary Attendance RTSP camera (COMBINED or CHECK-IN) and return live status & detections."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    # Prefer COMBINED, then CHECK-IN, then any enabled camera
    att_cam = next((c for c in cameras if c.mode == "COMBINED" and c.enabled), None)
    if not att_cam:
        att_cam = next((c for c in cameras if c.mode == "CHECK-IN" and c.enabled), None)
    if not att_cam:
        att_cam = next((c for c in cameras if c.enabled), None)
    if not att_cam and cameras:
        att_cam = cameras[0]

    if not att_cam:
        return {
            "success": True,
            "configured": False,
            "message": "No RTSP camera configured yet for attendance",
            "camera": None,
            "latest_detections": [],
            "recent_events": []
        }

    data = RTSPCameraRepository.sanitize(att_cam, include_password=False)
    worker = rtsp_manager.get_worker(att_cam.id)
    if worker:
        summary = worker.get_status_summary()
        data["live_status"] = worker.status
        data["status_message"] = worker.status_message
        data["active_persons"] = len(worker.active_presence)
        data["recent_events"] = summary.get("recent_events", [])
        data["latest_detections"] = summary.get("latest_detections", [])
    else:
        data["live_status"] = "disconnected"
        data["status_message"] = "Worker inactive"
        data["active_persons"] = 0
        data["recent_events"] = []
        data["latest_detections"] = []

    return {
        "success": True,
        "configured": True,
        "camera": data,
        "latest_detections": data.get("latest_detections", []),
        "recent_events": data.get("recent_events", [])
    }


@router.get("/attendance/stream")
async def stream_attendance_camera_mjpeg(
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Streams live MJPEG specifically from the primary Attendance RTSP camera at 15 FPS."""
    target_interval = 1.0 / 15.0  # Exactly 15 FPS (66.67ms)

    async def frame_generator():
        try:
            while True:
                t0 = time.time()
                worker = rtsp_manager.get_worker_by_mode("COMBINED") or rtsp_manager.get_worker_by_mode("CHECK-IN")
                if not worker and rtsp_manager.workers:
                    worker = next(iter(rtsp_manager.workers.values()), None)

                if worker:
                    frame_bytes, seq = worker.get_latest_jpeg_with_seq()
                else:
                    from app.services.rtsp_manager import RTSPCameraWorker
                    frame_bytes = RTSPCameraWorker.get_static_placeholder_jpeg("ATTENDANCE CAMERA AWAITING CONNECTION")
                    seq = 0

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )

                elapsed = time.time() - t0
                sleep_time = max(0.002, target_interval - elapsed)
                await asyncio.sleep(sleep_time)
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/checkout/status")
async def get_checkout_camera_status(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Find the configured Check-Out camera and return its live status, diagnostics, and detections."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkout_cam = next((c for c in cameras if c.mode == "CHECK-OUT" and c.enabled), None)
    if not checkout_cam:
        checkout_cam = next((c for c in cameras if c.mode == "CHECK-OUT"), None)

    if not checkout_cam:
        return {
            "success": True,
            "configured": False,
            "message": "No Check-Out camera configured yet",
            "camera": None,
            "latest_detections": [],
            "recent_events": [],
            "actual_fps": 0.0,
            "diagnostics": {}
        }

    data = RTSPCameraRepository.sanitize(checkout_cam, include_password=False)
    worker = rtsp_manager.get_worker(checkout_cam.id)
    if checkout_cam.enabled and (not worker or not worker.running):
        worker = rtsp_manager.ensure_camera_running(checkout_cam)

    if worker:
        summary = worker.get_status_summary()
        data["live_status"] = summary.get("status", worker.status)
        data["status_message"] = summary.get("status_message", worker.status_message)
        data["stream_fps"] = summary.get("stream_fps", summary.get("actual_fps", 0.0))
        data["display_fps"] = summary.get("display_fps", 0.0)
        data["ai_fps"] = summary.get("ai_fps", 0.0)
        data["actual_fps"] = summary.get("actual_fps", 0.0)
        data["avg_inference_ms"] = summary.get("avg_inference_ms", 0.0)
        data["latency_ms"] = summary.get("latency_ms", 0.0)
        data["dropped_frames"] = summary.get("dropped_frames", 0)
        data["queue_size"] = summary.get("queue_size", 0)
        data["is_receiving_frames"] = summary.get("is_receiving_frames", False)
        data["reconnect_attempt"] = summary.get("reconnect_attempt", 0)
        data["last_connected_time"] = summary.get("last_connected_time")
        data["last_frame_time"] = summary.get("last_frame_time")
        data["diagnostics"] = summary.get("diagnostics", {})
        data["redacted_url"] = summary.get("rtsp_url", data.get("rtsp_url"))
        data["active_persons"] = summary.get("active_persons_count", 0)
        data["recent_events"] = summary.get("recent_events", [])
        data["latest_detections"] = summary.get("latest_detections", [])
    else:
        data["live_status"] = "disconnected"
        data["status_message"] = "Worker inactive"
        data["stream_fps"] = 0.0
        data["display_fps"] = 0.0
        data["ai_fps"] = 0.0
        data["actual_fps"] = 0.0
        data["avg_inference_ms"] = 0.0
        data["latency_ms"] = 0.0
        data["dropped_frames"] = 0
        data["queue_size"] = 0
        data["is_receiving_frames"] = False
        data["reconnect_attempt"] = 0
        data["diagnostics"] = {}
        data["active_persons"] = 0
        data["recent_events"] = []
        data["latest_detections"] = []

    return {
        "success": True,
        "configured": True,
        "camera": data,
        "latest_detections": data.get("latest_detections", []),
        "recent_events": data.get("recent_events", []),
        "actual_fps": data.get("actual_fps", 0.0),
        "diagnostics": data.get("diagnostics", {})
    }


@router.get("/checkout/stream")
async def stream_checkout_camera_mjpeg(
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Streams live MJPEG specifically from the configured Check-Out camera at 15 FPS."""
    target_interval = 1.0 / 15.0  # Exactly 15 FPS (66.67ms)

    async def frame_generator():
        try:
            while True:
                t0 = time.time()
                worker = rtsp_manager.get_worker_by_mode("CHECK-OUT")
                if not worker and rtsp_manager.workers:
                    worker = next(iter(rtsp_manager.workers.values()), None)

                if worker:
                    frame_bytes, seq = worker.get_latest_jpeg_with_seq()
                else:
                    from app.services.rtsp_manager import RTSPCameraWorker
                    frame_bytes = RTSPCameraWorker.get_static_placeholder_jpeg("CHECK-OUT CAMERA AWAITING CONNECTION")
                    seq = 0

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )

                elapsed = time.time() - t0
                sleep_time = max(0.002, target_interval - elapsed)
                await asyncio.sleep(sleep_time)
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/checkin/config")
async def configure_checkin_camera(
    req: CameraCreateRequest,
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager),
    current_user: dict = Depends(require_owner)
):
    """
    Creates or updates the Check-In camera specifically.
    Ensures mode is strictly set to 'CHECK-IN'.
    """
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkin_cam = next((c for c in cameras if c.mode == "CHECK-IN"), None)

    if checkin_cam:
        updated = await RTSPCameraRepository.update(
            session=db,
            camera_id=checkin_cam.id,
            name=req.name or checkin_cam.name,
            rtsp_url=req.rtsp_url,
            username=req.username,
            password=req.password,
            location=req.location or checkin_cam.location,
            mode="CHECK-IN",
            enabled=req.enabled
        )
        if updated.enabled:
            rtsp_manager.start_camera(
                camera_id=updated.id,
                name=updated.name,
                rtsp_url=updated.rtsp_url,
                mode="CHECK-IN",
                location=updated.location,
                username=updated.username,
                password=updated.password,
            )
        else:
            rtsp_manager.stop_camera(updated.id)

        return {
            "success": True,
            "message": "Check-In camera updated successfully",
            "camera": RTSPCameraRepository.sanitize(updated)
        }
    else:
        created = await RTSPCameraRepository.create(
            session=db,
            name=req.name,
            rtsp_url=req.rtsp_url,
            username=req.username,
            password=req.password,
            location=req.location,
            mode="CHECK-IN",
            enabled=req.enabled
        )
        if created.enabled:
            rtsp_manager.start_camera(
                camera_id=created.id,
                name=created.name,
                rtsp_url=created.rtsp_url,
                mode="CHECK-IN",
                location=created.location,
                username=created.username,
                password=created.password,
            )

        return {
            "success": True,
            "message": "Check-In camera created successfully",
            "camera": RTSPCameraRepository.sanitize(created)
        }


@router.post("/checkout/config")
async def configure_checkout_camera(
    req: CameraCreateRequest,
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager),
    current_user: dict = Depends(require_owner)
):
    """
    Creates or updates the Check-Out camera specifically.
    Ensures mode is strictly set to 'CHECK-OUT'.
    """
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkout_cam = next((c for c in cameras if c.mode == "CHECK-OUT"), None)

    if checkout_cam:
        updated = await RTSPCameraRepository.update(
            session=db,
            camera_id=checkout_cam.id,
            name=req.name or checkout_cam.name,
            rtsp_url=req.rtsp_url,
            username=req.username,
            password=req.password,
            location=req.location or checkout_cam.location,
            mode="CHECK-OUT",
            enabled=req.enabled
        )
        if updated.enabled:
            rtsp_manager.start_camera(
                camera_id=updated.id,
                name=updated.name,
                rtsp_url=updated.rtsp_url,
                mode="CHECK-OUT",
                location=updated.location,
                username=updated.username,
                password=updated.password,
            )
        else:
            rtsp_manager.stop_camera(updated.id)

        return {
            "success": True,
            "message": "Check-Out camera updated successfully",
            "camera": RTSPCameraRepository.sanitize(updated)
        }
    else:
        created = await RTSPCameraRepository.create(
            session=db,
            name=req.name,
            rtsp_url=req.rtsp_url,
            username=req.username,
            password=req.password,
            location=req.location,
            mode="CHECK-OUT",
            enabled=req.enabled
        )
        if created.enabled:
            rtsp_manager.start_camera(
                camera_id=created.id,
                name=created.name,
                rtsp_url=created.rtsp_url,
                mode="CHECK-OUT",
                location=created.location,
                username=created.username,
                password=created.password,
            )

        return {
            "success": True,
            "message": "Check-Out camera created successfully",
            "camera": RTSPCameraRepository.sanitize(created)
        }


@router.post("/checkin/connect")
async def connect_checkin_camera(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Manually connect the Check-In camera."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkin_cam = next((c for c in cameras if c.mode == "CHECK-IN"), None)
    if not checkin_cam:
        raise HTTPException(status_code=404, detail="No Check-In camera configured")

    if not rtsp_manager.get_worker(checkin_cam.id):
        rtsp_manager.start_camera(
            camera_id=checkin_cam.id,
            name=checkin_cam.name,
            rtsp_url=checkin_cam.rtsp_url,
            mode="CHECK-IN",
            location=checkin_cam.location,
            username=checkin_cam.username,
            password=checkin_cam.password,
        )
    success = rtsp_manager.connect_camera(checkin_cam.id)
    return {"success": success, "message": "Check-In camera connect initiated"}


@router.post("/checkin/disconnect")
async def disconnect_checkin_camera(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Manually disconnect the Check-In camera without disabling it."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkin_cam = next((c for c in cameras if c.mode == "CHECK-IN"), None)
    if not checkin_cam:
        raise HTTPException(status_code=404, detail="No Check-In camera configured")
    success = rtsp_manager.disconnect_camera(checkin_cam.id)
    return {"success": success, "message": "Check-In camera disconnected"}


@router.post("/checkin/reconnect")
async def reconnect_checkin_camera(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Manually trigger immediate reconnection for Check-In camera."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkin_cam = next((c for c in cameras if c.mode == "CHECK-IN"), None)
    if not checkin_cam:
        raise HTTPException(status_code=404, detail="No Check-In camera configured")

    if not checkin_cam.enabled:
        checkin_cam = await RTSPCameraRepository.update(db, checkin_cam.id, enabled=True)

    rtsp_manager.start_camera(
        camera_id=checkin_cam.id,
        name=checkin_cam.name,
        rtsp_url=checkin_cam.rtsp_url,
        mode="CHECK-IN",
        location=checkin_cam.location,
        username=checkin_cam.username,
        password=checkin_cam.password,
    )
    return {"success": True, "message": "Check-In camera reconnection triggered"}


@router.post("/checkout/connect")
async def connect_checkout_camera(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Manually connect the Check-Out camera."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkout_cam = next((c for c in cameras if c.mode == "CHECK-OUT"), None)
    if not checkout_cam:
        raise HTTPException(status_code=404, detail="No Check-Out camera configured")

    if not checkout_cam.enabled:
        checkout_cam = await RTSPCameraRepository.update(db, checkout_cam.id, enabled=True)

    rtsp_manager.start_camera(
        camera_id=checkout_cam.id,
        name=checkout_cam.name,
        rtsp_url=checkout_cam.rtsp_url,
        mode="CHECK-OUT",
        location=checkout_cam.location,
        username=checkout_cam.username,
        password=checkout_cam.password,
    )
    return {"success": True, "message": "Check-Out camera connect initiated"}


@router.post("/checkout/disconnect")
async def disconnect_checkout_camera(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Manually disconnect the Check-Out camera without disabling it."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkout_cam = next((c for c in cameras if c.mode == "CHECK-OUT"), None)
    if not checkout_cam:
        raise HTTPException(status_code=404, detail="No Check-Out camera configured")
    success = rtsp_manager.disconnect_camera(checkout_cam.id)
    return {"success": success, "message": "Check-Out camera disconnected"}


@router.post("/checkout/reconnect")
async def reconnect_checkout_camera(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Manually trigger immediate reconnection for Check-Out camera."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkout_cam = next((c for c in cameras if c.mode == "CHECK-OUT"), None)
    if not checkout_cam:
        raise HTTPException(status_code=404, detail="No Check-Out camera configured")

    if not checkout_cam.enabled:
        checkout_cam = await RTSPCameraRepository.update(db, checkout_cam.id, enabled=True)

    rtsp_manager.start_camera(
        camera_id=checkout_cam.id,
        name=checkout_cam.name,
        rtsp_url=checkout_cam.rtsp_url,
        mode="CHECK-OUT",
        location=checkout_cam.location,
        username=checkout_cam.username,
        password=checkout_cam.password,
    )
    return {"success": True, "message": "Check-Out camera reconnection triggered"}


@router.post("/checkin/toggle")
async def toggle_checkin_camera(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Toggle Check-In camera enabled/disabled state."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkin_cam = next((c for c in cameras if c.mode == "CHECK-IN"), None)
    if not checkin_cam:
        raise HTTPException(status_code=404, detail="No Check-In camera configured")

    new_enabled = not checkin_cam.enabled
    updated = await RTSPCameraRepository.update(db, checkin_cam.id, enabled=new_enabled)
    if new_enabled:
        rtsp_manager.start_camera(
            camera_id=updated.id,
            name=updated.name,
            rtsp_url=updated.rtsp_url,
            mode="CHECK-IN",
            location=updated.location,
            username=updated.username,
            password=updated.password
        )
    else:
        rtsp_manager.stop_camera(checkin_cam.id)

    return {
        "success": True,
        "enabled": updated.enabled,
        "message": f"Check-In camera {'enabled' if updated.enabled else 'disabled'}"
    }


@router.delete("/checkin")
async def delete_checkin_camera(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager),
    current_user: dict = Depends(require_owner)
):
    """Delete Check-In camera."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkin_cam = next((c for c in cameras if c.mode == "CHECK-IN"), None)
    if not checkin_cam:
        raise HTTPException(status_code=404, detail="No Check-In camera configured")

    rtsp_manager.stop_camera(checkin_cam.id)
    await RTSPCameraRepository.delete(db, checkin_cam.id)
    return {"success": True, "message": "Check-In camera deleted successfully"}


@router.post("/checkout/toggle")
async def toggle_checkout_camera(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager),
    current_user: dict = Depends(require_owner)
):
    """Toggle Check-Out camera enabled/disabled state."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkout_cam = next((c for c in cameras if c.mode == "CHECK-OUT"), None)
    if not checkout_cam:
        raise HTTPException(status_code=404, detail="No Check-Out camera configured")

    new_enabled = not checkout_cam.enabled
    updated = await RTSPCameraRepository.update(db, checkout_cam.id, enabled=new_enabled)
    if new_enabled:
        rtsp_manager.start_camera(
            camera_id=updated.id,
            name=updated.name,
            rtsp_url=updated.rtsp_url,
            mode="CHECK-OUT",
            location=updated.location,
            username=updated.username,
            password=updated.password
        )
    else:
        rtsp_manager.stop_camera(checkout_cam.id)

    return {
        "success": True,
        "enabled": updated.enabled,
        "message": f"Check-Out camera {'enabled' if updated.enabled else 'disabled'}"
    }


@router.delete("/checkout")
async def delete_checkout_camera(
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager),
    current_user: dict = Depends(require_owner)
):
    """Delete Check-Out camera."""
    cameras = await RTSPCameraRepository.list_all(db, enabled_only=False)
    checkout_cam = next((c for c in cameras if c.mode == "CHECK-OUT"), None)
    if not checkout_cam:
        raise HTTPException(status_code=404, detail="No Check-Out camera configured")

    rtsp_manager.stop_camera(checkout_cam.id)
    await RTSPCameraRepository.delete(db, checkout_cam.id)
    return {"success": True, "message": "Check-Out camera deleted successfully"}


@router.get("/{camera_id}")
async def get_camera(
    camera_id: int,
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Retrieve details for a single camera (credentials sanitized)."""
    camera = await RTSPCameraRepository.get_by_id(db, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    data = RTSPCameraRepository.sanitize(camera, include_password=False)
    worker = rtsp_manager.get_worker(camera.id)
    if camera.enabled and (not worker or not worker.running):
        worker = rtsp_manager.ensure_camera_running(camera)
    if worker:
        summary = worker.get_status_summary()
        data["live_status"] = summary.get("status", worker.status)
        data["status_message"] = summary.get("status_message", worker.status_message)
        data["actual_fps"] = summary.get("actual_fps", 0.0)
        data["is_receiving_frames"] = summary.get("is_receiving_frames", False)
        data["reconnect_attempt"] = summary.get("reconnect_attempt", 0)
        data["last_connected_time"] = summary.get("last_connected_time")
        data["last_frame_time"] = summary.get("last_frame_time")
        data["diagnostics"] = summary.get("diagnostics", {})
        data["redacted_url"] = summary.get("rtsp_url", data.get("rtsp_url"))
        data["active_persons"] = summary.get("active_persons_count", 0)
        data["recent_events"] = summary.get("recent_events", [])
        data["latest_detections"] = summary.get("latest_detections", [])
    else:
        data["live_status"] = "disconnected"
        data["status_message"] = "Camera disabled or inactive"
        data["actual_fps"] = 0.0
        data["is_receiving_frames"] = False
        data["reconnect_attempt"] = 0
        data["diagnostics"] = {}
        data["active_persons"] = 0
        data["recent_events"] = []
        data["latest_detections"] = []

    return {"success": True, "camera": data}


@router.put("/{camera_id}")
async def update_camera(
    camera_id: int,
    req: CameraUpdateRequest,
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager),
    current_user: dict = Depends(require_owner)
):
    """Update camera configuration."""
    camera = await RTSPCameraRepository.get_by_id(db, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    updated = await RTSPCameraRepository.update(
        session=db,
        camera_id=camera_id,
        name=req.name,
        rtsp_url=req.rtsp_url,
        username=req.username,
        password=req.password,
        location=req.location,
        mode=req.mode,
        enabled=req.enabled
    )

    # If enabled, restart worker with fresh parameters; if disabled, stop worker
    if updated.enabled:
        rtsp_manager.start_camera(
            camera_id=updated.id,
            name=updated.name,
            rtsp_url=updated.rtsp_url,
            mode=updated.mode,
            location=updated.location,
            username=updated.username,
            password=updated.password
        )
    else:
        rtsp_manager.stop_camera(updated.id)

    return {
        "success": True,
        "message": f"Camera '{updated.name}' updated successfully",
        "camera": RTSPCameraRepository.sanitize(updated, include_password=False)
    }


@router.delete("/{camera_id}")
async def delete_camera(
    camera_id: int,
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager),
    current_user: dict = Depends(require_owner)
):
    """Delete an RTSP camera and stop its worker thread."""
    rtsp_manager.stop_camera(camera_id)
    deleted = await RTSPCameraRepository.delete(db, camera_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Camera not found")

    return {"success": True, "message": "Camera deleted successfully"}


@router.post("/{camera_id}/toggle")
async def toggle_camera(
    camera_id: int,
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager),
    current_user: dict = Depends(require_owner)
):
    """Toggle camera enabled/disabled state."""
    camera = await RTSPCameraRepository.get_by_id(db, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    new_enabled = not camera.enabled
    updated = await RTSPCameraRepository.update(db, camera_id, enabled=new_enabled)

    if new_enabled:
        rtsp_manager.start_camera(
            camera_id=updated.id,
            name=updated.name,
            rtsp_url=updated.rtsp_url,
            mode=updated.mode,
            location=updated.location,
            username=updated.username,
            password=updated.password
        )
    else:
        rtsp_manager.stop_camera(camera_id)

    return {
        "success": True,
        "enabled": updated.enabled,
        "message": f"Camera '{updated.name}' {'enabled' if updated.enabled else 'disabled'}"
    }


@router.post("/{camera_id}/connect")
async def connect_camera_by_id(
    camera_id: int,
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Manually connect an RTSP camera."""
    camera = await RTSPCameraRepository.get_by_id(db, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if not rtsp_manager.get_worker(camera_id):
        rtsp_manager.start_camera(
            camera_id=camera.id,
            name=camera.name,
            rtsp_url=camera.rtsp_url,
            mode=camera.mode,
            location=camera.location,
            username=camera.username,
            password=camera.password
        )
    success = rtsp_manager.connect_camera(camera_id)
    return {"success": success, "message": f"Camera '{camera.name}' connect initiated"}


@router.post("/{camera_id}/disconnect")
async def disconnect_camera_by_id(
    camera_id: int,
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Manually disconnect an RTSP camera."""
    camera = await RTSPCameraRepository.get_by_id(db, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    success = rtsp_manager.disconnect_camera(camera_id)
    return {"success": success, "message": f"Camera '{camera.name}' disconnected"}


@router.post("/{camera_id}/reconnect")
async def reconnect_camera_by_id(
    camera_id: int,
    db: AsyncSession = Depends(get_db),
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Manually reconnect an RTSP camera."""
    camera = await RTSPCameraRepository.get_by_id(db, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if not camera.enabled:
        camera = await RTSPCameraRepository.update(db, camera.id, enabled=True)

    rtsp_manager.start_camera(
        camera_id=camera.id,
        name=camera.name,
        rtsp_url=camera.rtsp_url,
        mode=camera.mode,
        location=camera.location,
        username=camera.username,
        password=camera.password
    )
    return {"success": True, "message": f"Camera '{camera.name}' reconnection triggered"}


@router.get("/{camera_id}/stream")
async def stream_camera_mjpeg(
    camera_id: int,
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """
    Real-time MJPEG video stream with HUD overlays paced at a fixed 15 FPS.
    Renderable directly inside any standard HTML `<img src="/api/cameras/{id}/stream" />`.
    """
    target_interval = 1.0 / 15.0  # Exactly 15 FPS (66.67ms)

    async def frame_generator():
        try:
            while True:
                t0 = time.time()
                worker = rtsp_manager.get_worker(camera_id)
                if worker:
                    frame_bytes, seq = worker.get_latest_jpeg_with_seq()
                else:
                    from app.services.rtsp_manager import RTSPCameraWorker
                    frame_bytes = RTSPCameraWorker.get_static_placeholder_jpeg("CAMERA INACTIVE")
                    seq = 0

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )

                # Strict 15 FPS timing compensation
                elapsed = time.time() - t0
                sleep_time = max(0.002, target_interval - elapsed)
                await asyncio.sleep(sleep_time)
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",
            "X-Accel-Buffering": "no"
        }
    )



@router.get("/{camera_id}/status")
async def get_camera_status(
    camera_id: int,
    rtsp_manager: RTSPManager = Depends(get_rtsp_manager)
):
    """Get live operational status and recent attendance events."""
    worker = rtsp_manager.get_worker(camera_id)
    if not worker:
        return {
            "success": True,
            "status": "disconnected",
            "status_message": "Camera is offline or disabled",
            "active_persons": 0,
            "recent_events": []
        }

    return {
        "success": True,
        **worker.get_status_summary()
    }

