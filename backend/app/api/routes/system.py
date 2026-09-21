"""System management and diagnostics API routes."""

import time
import psutil
from fastapi import APIRouter, Depends, Request
from app.core.security import get_current_user, require_role, Role
from app.schemas.analytics import SystemStatusResponse
from app.core.config import get_settings

router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(request: Request, current_user: dict = Depends(get_current_user)):
    """Retrieve system diagnostics, camera health, and inference metrics."""
    camera = request.app.state.camera
    vector_store = request.app.state.vector_store
    startup_time = getattr(request.app.state, "startup_time", time.time())
    
    uptime = time.time() - startup_time
    cpu_usage = psutil.cpu_percent()
    ram = psutil.virtual_memory()
    
    # Safe check of camera status
    is_online = camera.is_online() if hasattr(camera, "is_online") else False
    cam_health = camera.get_health() if hasattr(camera, "get_health") else None
    fps = cam_health.fps if cam_health else 0.0
    
    return SystemStatusResponse(
        status="operational",
        camera_online=is_online,
        fps=fps,
        avg_inference_ms=35.0,
        recognition_latency_ms=cam_health.latency_ms if cam_health else 0.0,
        cpu_percent=cpu_usage,
        ram_percent=ram.percent,
        ram_used_mb=ram.used / (1024 * 1024),
        registered_persons=0,
        total_embeddings=vector_store.count if vector_store else 0,
        faiss_index_size=vector_store.count if vector_store else 0,
        uptime_seconds=uptime
    )


@router.get("/settings")
async def get_system_settings(current_user: dict = Depends(get_current_user)):
    """Retrieve current system configuration."""
    settings = get_settings()
    return {
        "app_name": settings.APP_NAME,
        "version": settings.VERSION,
        "recognition_threshold": settings.RECOGNITION_THRESHOLD,
        "min_face_quality": settings.MIN_FACE_QUALITY,
        "max_pose_yaw": settings.MAX_POSE_YAW,
        "max_pose_pitch": settings.MAX_POSE_PITCH,
        "liveness_threshold": settings.LIVENESS_THRESHOLD,
        "camera_fps": settings.CAMERA_FPS,
        "recognition_interval": settings.RECOGNITION_INTERVAL,
        "store_enrollment_images": settings.STORE_ENROLLMENT_IMAGES,
        "insightface_model": settings.INSIGHTFACE_MODEL,
        "embedding_dimension": settings.EMBEDDING_DIMENSION
    }


@router.put("/settings")
async def update_system_settings(
    settings_update: dict,
    current_user: dict = Depends(require_role(Role.ADMIN))
):
    """Update runtime configurable system settings."""
    settings = get_settings()
    updated = {}
    for key, value in settings_update.items():
        attr_upper = key.upper()
        if hasattr(settings, attr_upper):
            setattr(settings, attr_upper, value)
            updated[attr_upper] = value
        elif hasattr(settings, key):
            setattr(settings, key, value)
            updated[key] = value
            
    return {"status": "Settings updated", "updated": updated}


@router.post("/camera/release")
async def release_camera(request: Request):
    """Explicitly release the camera hardware so the browser or other apps can use it."""
    if hasattr(request.app.state, "camera") and request.app.state.camera:
        request.app.state.camera.stop()
    return {"status": "Camera released"}


@router.post("/camera/start")
async def start_camera_endpoint(request: Request):
    """Start the camera hardware for backend streaming."""
    if hasattr(request.app.state, "camera") and request.app.state.camera:
        request.app.state.camera.start()
    return {"status": "Camera started"}
