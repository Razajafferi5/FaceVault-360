import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.services.camera import CameraManager
from app.services.recognition import RecognitionService
from app.services.enrollment import EnrollmentService
from app.services.head_pose import HeadPoseEstimator
from app.services.face_quality import FaceQualityChecker
from app.services.camera_guidance import CameraGuidanceService
from app.services.liveness import MediaPipeLivenessDetector
from app.core.config import Settings
from app.utils.image import encode_frame_to_jpeg
from app.db.database import AsyncSessionLocal
from app.db.repositories.event_repo import EventRepository
from app.db.repositories.attendance_repo import AttendanceRepository

logger = logging.getLogger(__name__)

@dataclass
class PipelineState:
    mode: str  # 'entry', 'testing', 'monitoring'
    is_running: bool = False
    frame_count: int = 0
    last_recognition_time: float = 0.0
    cached_results: list = field(default_factory=list)
    cached_guidance: dict | None = None

@dataclass
class PipelineEvent:
    frame_jpeg: bytes
    faces: list
    guidance: dict | None
    health: dict

class RecognitionPipeline:
    """Central orchestrator tying services together for real-time WebSocket streaming and attendance logging."""
    
    def __init__(
        self,
        camera: CameraManager,
        recognition_service: RecognitionService,
        enrollment_service: EnrollmentService,
        head_pose: HeadPoseEstimator,
        face_quality: FaceQualityChecker,
        camera_guidance: CameraGuidanceService,
        liveness: MediaPipeLivenessDetector,
        settings: Settings
    ):
        self.camera = camera
        self.recognition_service = recognition_service
        self.enrollment_service = enrollment_service
        self.head_pose = head_pose
        self.face_quality = face_quality
        self.camera_guidance = camera_guidance
        self.liveness = liveness
        self.settings = settings
        
        self.state = PipelineState(mode='entry')
        self.recognition_interval = 10
        self._last_logged_time: dict[str, float] = {}  # Throttle duplicate attendance logs per person
        self._client_count = 0
        self._worker_task: asyncio.Task | None = None
        self._latest_event: PipelineEvent | None = None
        self._is_recognizing: bool = False

    def get_latest_event(self) -> PipelineEvent | None:
        """Returns the most recently processed pipeline event."""
        return self._latest_event

    async def _run_loop(self):
        """Single background worker loop that processes frames at a steady rate."""
        logger.info("Pipeline background worker loop started.")
        while self.state.is_running:
            try:
                event = await self.process_frame()
                if isinstance(event, PipelineEvent):
                    self._latest_event = event
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in pipeline loop: {e}", exc_info=True)
            await asyncio.sleep(0.08)  # ~12 FPS
        logger.info("Pipeline background worker loop terminated.")

    async def start(self, mode: str = 'entry'):
        """Starts the pipeline processing."""
        self._client_count += 1
        self.state.mode = mode
        self.state.is_running = True
        self.camera.start()
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._run_loop())
        logger.info(f"Recognition pipeline started in {mode} mode (clients: {self._client_count}).")

    async def stop(self):
        """Stops the pipeline processing when no clients connected."""
        self._client_count = max(0, self._client_count - 1)
        if self._client_count == 0:
            self.state.is_running = False
            if self._worker_task and not self._worker_task.done():
                self._worker_task.cancel()
                self._worker_task = None
            self.camera.stop()
            logger.info("Recognition pipeline stopped (all clients disconnected).")
        else:
            logger.info(f"Recognition pipeline client disconnected (remaining: {self._client_count}).")

    async def _log_access_event(self, face_dict: dict):
        """Record attendance event into database asynchronously."""
        person_id = face_dict.get("person_id")
        name = face_dict.get("name")
        status = face_dict.get("status", "unknown")
        confidence = face_dict.get("similarity", 0.0)
        # STRICT REQUIREMENT: Unknown faces must NEVER be marked or recorded in attendance!
        if not face_dict.get("authorized", False) or face_dict.get("is_unknown", True) or not person_id:
            logger.debug("Unregistered/Unknown person detected — attendance NOT marked.")
            return

        # Debounce repeated logs for the same recognized person within 15 seconds
        now = datetime.now(timezone.utc).timestamp()
        key = str(person_id)
        if key in self._last_logged_time and (now - self._last_logged_time[key] < 15.0):
            return
            
        self._last_logged_time[key] = now
        auth_result = "granted"

        try:
            async with AsyncSessionLocal() as session:
                await EventRepository.create(
                    session=session,
                    data={
                        "person_id": person_id,
                        "recognized_name": name,
                        "confidence": float(confidence),
                        "status": status,
                        "authorization_result": auth_result,
                        "pose_yaw": float(face_dict.get("pose_yaw", 0.0)),
                        "pose_pitch": float(face_dict.get("pose_pitch", 0.0)),
                        "quality_score": float(face_dict.get("quality_score", 0.0)),
                        "camera_id": "default",
                        "failure_reason": None if auth_result == "granted" else status
                    }
                )
                att_record, is_new = await AttendanceRepository.mark_attendance(
                    session=session,
                    employee_id=person_id,
                    employee_name=name,
                    match_score=float(confidence),
                    status="Present"
                )
                status_label = "NEW MARKED" if is_new else "ALREADY MARKED TODAY"
                logger.info(f"Attendance/Access event recorded for {name} -> {auth_result.upper()} ({status_label})")
        except Exception as e:
            logger.error(f"Failed to record access/attendance event: {e}")

    async def process_frame(self) -> PipelineEvent | dict:
        """The core real-time loop called by the WebSocket handler."""
        if not self.state.is_running:
            return {"error": "Pipeline not running"}

        frame = self.camera.get_frame()
        if frame is None:
            return {"error": "No frame available from camera"}

        self.state.frame_count += 1
        
        # TIER 1: Head pose guidance (paced every 3 frames for zero latency)
        if self.state.frame_count % 3 == 0 or self.state.cached_guidance is None:
            pose_results = await asyncio.to_thread(self.head_pose.estimate, frame)
            if pose_results:
                pose = pose_results[0]
                guidance = self.camera_guidance.assess(pose, None, True)
            else:
                guidance = self.camera_guidance.assess(None, None, False)
            self.state.cached_guidance = guidance

        # TIER 2: Periodic deep facial recognition and identity verification
        if self.state.frame_count % self.recognition_interval == 0 and not self._is_recognizing:
            self._is_recognizing = True
            async def _do_recog(f):
                try:
                    recog_dict = await asyncio.to_thread(
                        self.recognition_service.recognize_frame, f
                    )
                    faces = recog_dict.get("faces", [])
                    self.state.cached_results = faces
                    self.state.last_recognition_time = datetime.now(timezone.utc).timestamp()
                    for face in faces:
                        asyncio.create_task(self._log_access_event(face))
                except Exception as e:
                    logger.error(f"Async recognition error: {e}")
                finally:
                    self._is_recognizing = False

            asyncio.create_task(_do_recog(frame.copy()))

        # Encode frame to JPEG for live WebSocket video rendering
        frame_jpeg = await asyncio.to_thread(encode_frame_to_jpeg, frame)

        cam_health = self.camera.get_health()
        health_dict = {
            "online": cam_health.online,
            "fps": cam_health.fps,
            "latency_ms": cam_health.latency_ms,
            "resolution": cam_health.resolution
        }

        return PipelineEvent(
            frame_jpeg=frame_jpeg,
            faces=self.state.cached_results,
            guidance=self.state.cached_guidance,
            health=health_dict
        )

    async def process_enrollment_frame(self, session_id: str) -> dict:
        """Processes a frame specifically for an active multi-angle enrollment session."""
        frame = self.camera.get_frame()
        if frame is None:
            return {"error": "No frame available"}

        result = await asyncio.to_thread(
            self.enrollment_service.process_frame, session_id, frame
        )
        
        frame_jpeg = await asyncio.to_thread(encode_frame_to_jpeg, frame)
        result["frame_jpeg"] = frame_jpeg
        return result

    def get_state(self) -> PipelineState:
        return self.state
