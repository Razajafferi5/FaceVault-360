import uuid
import time
import logging
from datetime import datetime
from dataclasses import dataclass, field
import numpy as np

from app.services.face_detector import FaceDetector
from app.services.face_quality import FaceQualityChecker
from app.services.head_pose import HeadPoseEstimator, PoseResult
from app.services.faiss_store import FAISSVectorStore
from app.services.camera_guidance import CameraGuidanceService
from app.core.config import Settings
from app.db.repositories.embedding_repo import EmbeddingRepository
from app.db.repositories.person_repo import PersonRepository

logger = logging.getLogger(__name__)


@dataclass
class PoseStepDef:
    step: int
    label: str
    instruction: str
    target_yaw: tuple[float, float]
    target_pitch: tuple[float, float]


POSE_STEPS = [
    PoseStepDef(
        step=1,
        label='front',
        instruction='Look directly at the camera',
        target_yaw=(-8.0, 8.0),
        target_pitch=(-8.0, 8.0)
    ),
    PoseStepDef(
        step=2,
        label='left',
        instruction='Turn your head slightly LEFT',
        target_yaw=(-60.0, -3.5),
        target_pitch=(-35.0, 35.0)
    ),
    PoseStepDef(
        step=3,
        label='right',
        instruction='Turn your head slightly RIGHT',
        target_yaw=(3.5, 60.0),
        target_pitch=(-35.0, 35.0)
    ),
    PoseStepDef(
        step=4,
        label='up',
        instruction='Tilt your head slightly UP',
        target_yaw=(-35.0, 35.0),
        target_pitch=(-60.0, -2.5)
    ),
    PoseStepDef(
        step=5,
        label='down',
        instruction='Tilt your head slightly DOWN',
        target_yaw=(-35.0, 35.0),
        target_pitch=(2.5, 60.0)
    ),
    PoseStepDef(
        step=6,
        label='far_left',
        instruction='Turn your head further LEFT',
        target_yaw=(-60.0, -8.0),
        target_pitch=(-35.0, 35.0)
    ),
    PoseStepDef(
        step=7,
        label='far_right',
        instruction='Turn your head further RIGHT',
        target_yaw=(8.0, 60.0),
        target_pitch=(-35.0, 35.0)
    ),
]


@dataclass
class CapturedPose:
    label: str
    embedding: np.ndarray
    yaw: float
    pitch: float
    roll: float
    quality_score: float
    faiss_id: int | None = None


@dataclass
class EnrollmentSession:
    session_id: str
    person_id: int
    person_name: str
    current_step: int = 0
    hold_count: int = 0
    hold_target: int = 2
    captured_poses: list[CapturedPose] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = 'active'  # 'active', 'completed', 'saved', 'cancelled'
    baseline_yaw: float = 0.0
    baseline_pitch: float = 0.0
    last_capture_time: float = 0.0


def extract_head_angles(face, frame, head_pose_estimator) -> tuple[float, float, float]:
    """Extract (yaw, pitch, roll) accurately from facial landmarks or pose."""
    # 1. Primary: 5-point facial keypoints (SCRFD / InsightFace) - instantaneous and mathematically precise
    landmarks = getattr(face, 'landmarks', None)
    if landmarks is None and hasattr(face, 'raw_face') and getattr(face.raw_face, 'kps', None) is not None:
        landmarks = face.raw_face.kps

    if landmarks is not None:
        try:
            lm = np.array(landmarks)
            if lm.shape == (5, 2) and np.any(lm):
                e_left = lm[0]   # image left
                e_right = lm[1]  # image right
                nose = lm[2]
                eye_center = (e_left + e_right) / 2.0
                eye_dist = max(float(np.linalg.norm(e_right - e_left)), 1.0)

                dy = float(e_right[1] - e_left[1])
                dx = float(e_right[0] - e_left[0])
                roll = float(np.degrees(np.arctan2(dy, dx)))

                # When user turns head to their LEFT, nose shifts towards image-right (larger x).
                # To follow sign convention where turning LEFT = negative yaw:
                offset_x = float(nose[0] - eye_center[0]) / eye_dist
                yaw = -float(offset_x * 70.0)

                # When user tilts head UP, nose shifts closer to eye level (offset_y < 0.52 -> negative pitch)
                # When user tilts head DOWN, nose shifts lower (offset_y > 0.52 -> positive pitch)
                offset_y = float(nose[1] - eye_center[1]) / eye_dist
                pitch = float((offset_y - 0.52) * 70.0)

                return round(yaw, 1), round(pitch, 1), round(roll, 1)
        except Exception as e:
            logger.debug(f"Landmarks angle extraction error: {e}")

    # 2. Fallback: estimate from bbox
    if hasattr(face, 'bbox') and face.bbox and len(face.bbox) >= 4:
        try:
            pose_res = head_pose_estimator.estimate_from_bbox(frame, face.bbox)
            if pose_res:
                return pose_res.yaw, pose_res.pitch, pose_res.roll
        except Exception:
            pass

    return 0.0, 0.0, 0.0


class EnrollmentService:
    """Manages multi-angle 360-degree biometric face enrollment with real-time pose guidance."""
    
    def __init__(
        self,
        face_detector: FaceDetector,
        face_quality: FaceQualityChecker,
        head_pose: HeadPoseEstimator,
        vector_store: FAISSVectorStore,
        camera_guidance: CameraGuidanceService,
        settings: Settings
    ):
        self.face_detector = face_detector
        self.face_quality = face_quality
        self.head_pose = head_pose
        self.vector_store = vector_store
        self.camera_guidance = camera_guidance
        self.settings = settings
        self._sessions: dict[str, EnrollmentSession] = {}

    def start_session(self, person_id: int, person_name: str) -> EnrollmentSession:
        """Starts a new enrollment session for a person."""
        session_id = str(uuid.uuid4())
        session = EnrollmentSession(
            session_id=session_id,
            person_id=person_id,
            person_name=person_name,
            current_step=0,
            hold_count=0
        )
        self._sessions[session_id] = session
        logger.info(f"Started 360 enrollment session {session_id} for person {person_id} ({person_name})")
        return session

    def process_frame(self, session_id: str, frame: np.ndarray) -> dict:
        """Processes a single frame across all 7 takes with real-time direction guidance."""
        session = self.get_session(session_id)
        total_steps = len(POSE_STEPS)

        if not session or session.status not in ('active', 'completed'):
            return {
                "status": "error",
                "captured": False,
                "message": "SESSION EXPIRED",
                "instruction": "Invalid or inactive enrollment session",
                "status_color": "red",
                "detected_bbox": None,
                "face_count": 0,
                "hold_progress": 0.0,
                "current_step": 1,
                "total_steps": total_steps,
                "pose_label": "front",
                "completed": False,
                "guidance": None
            }

        # If already completed all takes
        if session.current_step >= total_steps or session.status == 'completed':
            return {
                "status": "completed",
                "captured": True,
                "message": "FACE ENROLLED SUCCESSFULLY",
                "instruction": f"All {total_steps} angles captured successfully!",
                "status_color": "green",
                "detected_bbox": None,
                "face_count": 1,
                "hold_progress": 1.0,
                "current_step": total_steps,
                "total_steps": total_steps,
                "pose_label": "completed",
                "completed": True,
                "guidance": {
                    "face_detected": True,
                    "position_ok": True,
                    "message": "FACE ENROLLED SUCCESSFULLY",
                    "severity": "good",
                    "yaw": 0.0,
                    "pitch": 0.0,
                    "roll": 0.0,
                    "action": "none"
                }
            }

        target_pose = POSE_STEPS[session.current_step]
        step_num = session.current_step + 1

        # 1. Detect faces in frame
        detected_faces = self.face_detector.detect(frame)
        face_count = len(detected_faces)

        # 2. No face detected
        if face_count == 0:
            session.hold_count = 0
            return {
                "status": "no_face",
                "captured": False,
                "message": "FACE NOT DETECTED",
                "instruction": f"Angle {step_num}/{total_steps}: {target_pose.instruction}",
                "status_color": "red",
                "detected_bbox": None,
                "face_count": 0,
                "hold_progress": 0.0,
                "current_step": step_num,
                "total_steps": total_steps,
                "pose_label": target_pose.label,
                "quality_score": 0.0,
                "completed": False,
                "current_yaw": 0.0,
                "current_pitch": 0.0,
            }

        # 3. Multiple faces — reject
        if face_count > 1:
            session.hold_count = 0
            return {
                "status": "multiple_faces",
                "captured": False,
                "message": "ONE PERSON ONLY",
                "instruction": "Multiple people detected! Only one person allowed.",
                "status_color": "red",
                "detected_bbox": detected_faces[0].bbox,
                "face_count": face_count,
                "hold_progress": 0.0,
                "current_step": step_num,
                "total_steps": total_steps,
                "pose_label": target_pose.label,
                "quality_score": 0.0,
                "completed": False,
                "current_yaw": 0.0,
                "current_pitch": 0.0,
            }

        # Exactly one face
        face = detected_faces[0]
        bbox = face.bbox
        bx, by, bw, bh = bbox
        frame_h, frame_w = frame.shape[:2]

        # 4. Estimate head pose & quality
        cur_yaw, cur_pitch, cur_roll = extract_head_angles(face, frame, self.head_pose)
        quality = self.face_quality.assess(frame, bbox, face.landmarks)

        # Transition Cooldown: allow 500ms after previous capture to read new prompt
        now_t = time.time()
        if session.last_capture_time > 0 and (now_t - session.last_capture_time) < 0.55:
            session.hold_count = 0
            return {
                "status": "transition",
                "captured": False,
                "message": target_pose.instruction,
                "instruction": f"Angle {step_num}/{total_steps}: {target_pose.instruction}",
                "status_color": "yellow",
                "detected_bbox": bbox,
                "face_count": 1,
                "hold_progress": 0.0,
                "current_step": step_num,
                "total_steps": total_steps,
                "pose_label": target_pose.label,
                "quality_score": round(float(quality.overall_score), 2),
                "completed": False,
                "current_yaw": cur_yaw,
                "current_pitch": cur_pitch,
            }

        # 5. Dynamic Pose Validation relative to baseline
        delta_yaw = cur_yaw - session.baseline_yaw
        delta_pitch = cur_pitch - session.baseline_pitch

        is_valid_pose = False
        guidance_message = target_pose.instruction
        status_color = "yellow"

        if target_pose.label == 'front':
            # Front pose: look directly at camera
            if abs(cur_yaw) < 8.0 and abs(cur_pitch) < 8.0:
                is_valid_pose = True
                guidance_message = "HOLD STILL (FRONT)"
                status_color = "green"
            else:
                guidance_message = "LOOK DIRECTLY AT CAMERA"
                status_color = "yellow"

        elif target_pose.label == 'left':
            if cur_yaw <= -3.5 or delta_yaw <= -3.0:
                is_valid_pose = True
                guidance_message = "HOLD STILL (LEFT)"
                status_color = "green"
            elif cur_yaw >= 4.0 or delta_yaw >= 3.5:
                guidance_message = "WRONG WAY! TURN LEFT ⬅️"
                status_color = "red"
            else:
                guidance_message = "TURN HEAD LEFT ⬅️"
                status_color = "yellow"

        elif target_pose.label == 'right':
            if cur_yaw >= 3.5 or delta_yaw >= 3.0:
                is_valid_pose = True
                guidance_message = "HOLD STILL (RIGHT)"
                status_color = "green"
            elif cur_yaw <= -4.0 or delta_yaw <= -3.5:
                guidance_message = "WRONG WAY! TURN RIGHT ➡️"
                status_color = "red"
            else:
                guidance_message = "TURN HEAD RIGHT ➡️"
                status_color = "yellow"

        elif target_pose.label == 'up':
            if cur_pitch <= -2.5 or delta_pitch <= -2.0:
                is_valid_pose = True
                guidance_message = "HOLD STILL (UP)"
                status_color = "green"
            elif cur_pitch >= 3.0 or delta_pitch >= 2.5:
                guidance_message = "WRONG WAY! TILT UP ⬆️"
                status_color = "red"
            else:
                guidance_message = "TILT HEAD UP ⬆️"
                status_color = "yellow"

        elif target_pose.label == 'down':
            if cur_pitch >= 2.5 or delta_pitch >= 2.0:
                is_valid_pose = True
                guidance_message = "HOLD STILL (DOWN)"
                status_color = "green"
            elif cur_pitch <= -3.0 or delta_pitch <= -2.5:
                guidance_message = "WRONG WAY! TILT DOWN ⬇️"
                status_color = "red"
            else:
                guidance_message = "TILT HEAD DOWN ⬇️"
                status_color = "yellow"

        elif target_pose.label == 'far_left':
            if cur_yaw <= -7.5 or delta_yaw <= -6.5:
                is_valid_pose = True
                guidance_message = "HOLD STILL (FAR LEFT)"
                status_color = "green"
            else:
                guidance_message = "TURN FURTHER LEFT ⟵"
                status_color = "yellow"

        elif target_pose.label == 'far_right':
            if cur_yaw >= 7.5 or delta_yaw >= 6.5:
                is_valid_pose = True
                guidance_message = "HOLD STILL (FAR RIGHT)"
                status_color = "green"
            else:
                guidance_message = "TURN FURTHER RIGHT ⟶"
                status_color = "yellow"

        # If pose is not in target angle, reset hold count
        if not is_valid_pose:
            session.hold_count = max(0, session.hold_count - 1)
            return {
                "status": "reposition",
                "captured": False,
                "message": guidance_message,
                "instruction": target_pose.instruction,
                "status_color": status_color,
                "detected_bbox": bbox,
                "face_count": 1,
                "hold_progress": 0.0,
                "current_step": step_num,
                "total_steps": total_steps,
                "pose_label": target_pose.label,
                "quality_score": round(float(quality.overall_score), 2),
                "completed": False,
                "current_yaw": cur_yaw,
                "current_pitch": cur_pitch,
            }

        # 6. Pose is valid! Check stability (2 frames ~300ms)
        session.hold_count += 1
        hold_needed = 2
        progress = min(session.hold_count / hold_needed, 1.0)

        if session.hold_count < hold_needed:
            return {
                "status": "hold_still",
                "captured": False,
                "message": guidance_message,
                "instruction": "Hold position for capture...",
                "status_color": "green",
                "detected_bbox": bbox,
                "face_count": 1,
                "hold_progress": round(progress, 2),
                "current_step": step_num,
                "total_steps": total_steps,
                "pose_label": target_pose.label,
                "quality_score": round(float(quality.overall_score), 2),
                "completed": False,
                "current_yaw": cur_yaw,
                "current_pitch": cur_pitch,
            }

        # 7. AUTOMATIC CAPTURE! Extract 512-D ArcFace embedding for this angle
        emb = self.face_detector.extract_embedding(frame, face)
        if emb is None:
            emb = np.zeros(512, dtype=np.float32)

        # Calibrate baseline from frontal capture
        if target_pose.label == 'front':
            session.baseline_yaw = cur_yaw
            session.baseline_pitch = cur_pitch

        captured_pose = CapturedPose(
            label=target_pose.label,
            embedding=emb,
            yaw=cur_yaw,
            pitch=cur_pitch,
            roll=cur_roll,
            quality_score=float(quality.overall_score)
        )
        session.captured_poses.append(captured_pose)
        session.current_step += 1
        session.hold_count = 0
        session.last_capture_time = time.time()

        is_all_completed = session.current_step >= total_steps
        if is_all_completed:
            session.status = "completed"

        logger.info(
            f"Session {session_id} captured angle {step_num}/{total_steps} ({target_pose.label}) for {session.person_name}"
        )

        return {
            "status": "completed" if is_all_completed else "captured",
            "captured": True,
            "message": f"{target_pose.label.upper()} CAPTURED" if not is_all_completed else "ALL 7 ANGLES CAPTURED!",
            "instruction": "Generating 360° biometric profile..." if is_all_completed else f"Next angle...",
            "status_color": "green",
            "detected_bbox": bbox,
            "face_count": 1,
            "hold_progress": 1.0,
            "current_step": session.current_step,
            "total_steps": total_steps,
            "pose_label": target_pose.label,
            "quality_score": round(float(quality.overall_score), 2),
            "completed": is_all_completed,
            "current_yaw": cur_yaw,
            "current_pitch": cur_pitch,
        }

    async def complete_session(self, session_id: str, db_session) -> dict:
        """Completes the session, saves all captured 360-degree angle embeddings to DB and FAISS vector store."""
        session = self.get_session(session_id)
        if not session:
            return {
                "success": False,
                "status": "error",
                "person_name": "Unknown",
                "poses_captured": 0,
                "average_quality": 0.0,
                "message": "Invalid enrollment session",
            }

        # If already saved to DB (idempotent call), return success
        if session.status == 'saved':
            return {
                "success": True,
                "status": "success",
                "person_name": session.person_name,
                "poses_captured": len(session.captured_poses),
                "average_quality": 0.0,
                "message": f"Already enrolled ({len(session.captured_poses)}/7 angles saved)",
            }

        # Require at least 1 pose to complete enrollment
        if len(session.captured_poses) < 1:
            return {
                "success": False,
                "status": "error",
                "person_name": session.person_name,
                "poses_captured": len(session.captured_poses),
                "average_quality": 0.0,
                "message": "Incomplete enrollment: no face angles captured yet",
            }

        max_id = await EmbeddingRepository.get_max_faiss_id(db_session)
        next_faiss_id = (max_id or 0) + 1

        bulk_records = []
        for pose in session.captured_poses:
            pose.faiss_id = next_faiss_id
            bulk_records.append({
                "person_id": session.person_id,
                "embedding_bytes": pose.embedding.tobytes(),
                "faiss_id": next_faiss_id,
                "pose_label": pose.label,
                "yaw": pose.yaw,
                "pitch": pose.pitch,
                "roll": pose.roll,
                "quality_score": pose.quality_score,
            })
            # Save to FAISS index (in-memory)
            self.vector_store.add(pose.embedding, next_faiss_id)
            next_faiss_id += 1

        # High-speed single transaction insert
        await EmbeddingRepository.bulk_create(db_session, bulk_records)
        self.vector_store.save(self.settings.FAISS_INDEX_PATH)

        # Set Person status to ACTIVE in database
        person = await PersonRepository.get_by_id(db_session, session.person_id)
        if person:
            person.status = 'active'
            await db_session.commit()
            await db_session.refresh(person)

        session.status = 'saved'  # mark as saved to DB

        avg_quality = sum(p.quality_score for p in session.captured_poses) / len(session.captured_poses)
        logger.info(
            f"Enrollment session {session_id} saved {len(session.captured_poses)} face angles to DB and FAISS for {session.person_name}"
        )

        return {
            "success": True,
            "status": "success",
            "person_name": session.person_name,
            "poses_captured": len(session.captured_poses),
            "average_quality": round(avg_quality, 2),
            "message": f"FACE ENROLLED SUCCESSFULLY ({len(session.captured_poses)}/7 360-degree angles saved)",
        }

    def cancel_session(self, session_id: str):
        """Cancels an active session and cleans it up."""
        if session_id in self._sessions:
            self._sessions[session_id].status = 'cancelled'
            del self._sessions[session_id]

    def get_session(self, session_id: str) -> EnrollmentSession | None:
        """Retrieves a session by ID."""
        return self._sessions.get(session_id)
