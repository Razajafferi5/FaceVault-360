"""Recognition service — core identity matching engine for FaceVault 360."""

import logging
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.face_detector import FaceDetector, DetectedFace
from app.services.face_quality import FaceQualityChecker
from app.services.head_pose import HeadPoseEstimator, PoseResult
from app.services.faiss_store import FAISSVectorStore
from app.services.liveness import MediaPipeLivenessDetector
from app.services.camera_guidance import CameraGuidanceService, GuidanceResult
from app.services.authorization import AuthorizationService, AuthorizationDecision
from app.core.config import Settings
from app.db.models import FaceEmbedding, Person

logger = logging.getLogger(__name__)


class RecognitionService:
    """Core identity matching engine for FaceVault 360.

    Executes the full recognition pipeline:
    MediaPipe pose → InsightFace detection + embedding → FAISS search → Authorization.

    Time complexity:
        - Face detection: O(pixels) per frame via SCRFD
        - Embedding extraction: O(1) per face via ArcFace
        - Vector search: O(N * D) via FAISS IndexFlatIP (exact), upgradeable to IVF for O(sqrt(N))
        - Identity lookup: O(1) via in-memory dict
    """

    def __init__(
        self,
        face_detector: FaceDetector,
        face_quality: FaceQualityChecker,
        head_pose: HeadPoseEstimator,
        vector_store: FAISSVectorStore,
        liveness: MediaPipeLivenessDetector,
        guidance: CameraGuidanceService,
        authorization: AuthorizationService,
        settings: Settings,
    ):
        self.face_detector = face_detector
        self.face_quality = face_quality
        self.head_pose = head_pose
        self.vector_store = vector_store
        self.liveness = liveness
        self.guidance = guidance
        self.authorization = authorization
        self.settings = settings

        # In-memory mapping: faiss_id -> (person_id, name, status)
        self._identity_map: dict[int, tuple[int, str, str]] = {}

    # ------------------------------------------------------------------
    # Recognition pipeline
    # ------------------------------------------------------------------

    def recognize_frame(self, frame: np.ndarray) -> dict:
        """Run the full recognition pipeline on a single frame.

        Returns a dict matching RecognitionResponse structure:
        {
            "faces": [...],
            "camera_guidance": {...},
            "camera_health": None,   # filled by pipeline
            "timestamp": "..."
        }
        """
        try:
            # 1. InsightFace detection + embedding first (fast, ~30-40ms)
            detected_faces = self.face_detector.detect_and_embed(frame)

            # If no faces detected, generate guidance instantly (0ms)
            if not detected_faces:
                primary_guidance = self.guidance.assess(
                    pose=None,
                    quality=None,
                    face_detected=False,
                    face_count=0,
                    bbox=None,
                    frame_shape=frame.shape,
                    is_mirrored=True,
                )
                return {
                    "faces": [],
                    "camera_guidance": {
                        "face_detected": False,
                        "position_ok": False,
                        "message": primary_guidance.message,
                        "severity": primary_guidance.severity,
                        "status_color": primary_guidance.status_color,
                        "yaw": 0.0,
                        "pitch": 0.0,
                        "roll": 0.0,
                        "action": primary_guidance.suggested_action,
                    } if primary_guidance else None,
                    "camera_health": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            face_results: list[dict] = []
            primary_guidance: GuidanceResult | None = None

            for i, face in enumerate(detected_faces):
                # Derive pose instantaneously from facial landmarks / pose / bbox
                pose = self._derive_face_pose(face, frame)
                result = self._process_single_face(
                    frame, face, pose, len(detected_faces), i
                )
                face_results.append(result["face"])
                if result.get("guidance") and primary_guidance is None:
                    primary_guidance = result["guidance"]

            guidance_dict = None
            if primary_guidance:
                guidance_dict = {
                    "face_detected": primary_guidance.face_detected,
                    "position_ok": primary_guidance.position_ok,
                    "message": primary_guidance.message,
                    "severity": primary_guidance.severity,
                    "status_color": primary_guidance.status_color,
                    "yaw": primary_guidance.yaw,
                    "pitch": primary_guidance.pitch,
                    "roll": primary_guidance.roll,
                    "action": primary_guidance.suggested_action,
                }

            return {
                "faces": face_results,
                "camera_guidance": guidance_dict,
                "camera_health": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Recognition pipeline error: {e}", exc_info=True)
            return {
                "faces": [],
                "camera_guidance": None,
                "camera_health": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _derive_face_pose(self, face: DetectedFace, frame: np.ndarray) -> PoseResult:
        """Derive 3D head pose instantaneously from 5-point landmarks or bbox (0.1ms vs 720ms)."""
        from app.services.head_pose import PoseResult

        landmarks = getattr(face, "landmarks", None)
        if landmarks is not None and len(landmarks) == 5:
            try:
                lm = np.array(landmarks)
                if lm.shape == (5, 2) and np.any(lm):
                    e_left = lm[0]
                    e_right = lm[1]
                    nose = lm[2]
                    eye_center = (e_left + e_right) / 2.0
                    eye_dist = max(float(np.linalg.norm(e_right - e_left)), 1.0)
                    dy = float(e_right[1] - e_left[1])
                    dx = float(e_right[0] - e_left[0])
                    roll = float(np.degrees(np.arctan2(dy, dx))) if dx != 0 else 0.0

                    offset_x = float(nose[0] - eye_center[0]) / eye_dist
                    yaw = -float(offset_x * 70.0)

                    offset_y = float(nose[1] - eye_center[1]) / eye_dist
                    pitch = float((offset_y - 0.52) * 70.0)

                    yaw = round(max(-75.0, min(75.0, yaw)), 1)
                    pitch = round(max(-60.0, min(60.0, pitch)), 1)

                    return PoseResult(
                        yaw=yaw,
                        pitch=pitch,
                        roll=round(roll, 1),
                        label=self.head_pose.get_label(yaw, pitch),
                        is_frontal=abs(yaw) < 15 and abs(pitch) < 15,
                        is_within_recognition_range=self.head_pose.is_within_recognition_range(yaw, pitch),
                    )
            except Exception:
                pass

        if face.pose and len(face.pose) >= 2:
            yaw = round(float(face.pose[1]), 1)
            pitch = round(float(face.pose[0]), 1)
            roll = round(float(face.pose[2]), 1) if len(face.pose) > 2 else 0.0
            return PoseResult(
                yaw=yaw,
                pitch=pitch,
                roll=roll,
                label=self.head_pose.get_label(yaw, pitch),
                is_frontal=abs(yaw) < 15 and abs(pitch) < 15,
                is_within_recognition_range=self.head_pose.is_within_recognition_range(yaw, pitch),
            )

        if face.bbox and len(face.bbox) >= 4:
            return self.head_pose.estimate_from_bbox(frame, face.bbox)

        return PoseResult(0.0, 0.0, 0.0, "frontal", True, True)

    def _process_single_face(
        self,
        frame: np.ndarray,
        face: DetectedFace,
        pose: PoseResult | None = None,
        total_faces: int = 1,
        index: int = 0,
    ) -> dict:
        """Process a single detected face through quality, pose, liveness, and matching."""
        if pose is None:
            pose = self._derive_face_pose(face, frame)

        # Assess quality
        bbox = face.bbox if isinstance(face.bbox, list) else face.bbox.tolist()
        quality = self.face_quality.assess(frame, bbox, face.landmarks)

        # Generate guidance with spatial framing
        guidance_result = self.guidance.assess(
            pose=pose,
            quality=quality,
            face_detected=True,
            face_count=total_faces,
            bbox=bbox,
            frame_shape=frame.shape,
            is_mirrored=True,
        )

        # Build base result
        face_dict = {
            "bbox": bbox,
            "confidence": float(face.confidence),
            "name": None,
            "person_id": None,
            "similarity": 0.0,
            "authorized": False,
            "status": "unknown",
            "is_too_small": getattr(quality, "is_too_small", False),
            "min_dimension": getattr(quality, "min_dimension", min(bbox[2], bbox[3]) if len(bbox) >= 4 else 0),
            "pose_label": pose.label if pose else "unknown",
            "pose_yaw": pose.yaw if pose else 0.0,
            "pose_pitch": pose.pitch if pose else 0.0,
            "quality_score": quality.overall_score,
            "liveness_score": 0.0,
        }

        # Gate -1: Validate human face candidate (reject inanimate objects: fans, chairs, walls, doors)
        is_valid_face = getattr(quality, "is_valid_face", True)
        if not is_valid_face or "invalid_aspect_ratio" in quality.issues or "missing_landmarks" in quality.issues:
            face_dict["status"] = "non_face_object"
            face_dict["name"] = "Object / Non-Face"
            face_dict["is_unknown"] = False
            face_dict["is_valid_face"] = False
            return {"face": face_dict, "guidance": guidance_result}

        # Gate 0: Distance check - Face is too small to extract reliable biometric embedding
        if getattr(quality, "is_too_small", False):
            face_dict["status"] = "face_too_small"
            face_dict["name"] = "Face Too Small"
            face_dict["is_unknown"] = False
            face_dict["is_valid_face"] = False
            return {"face": face_dict, "guidance": guidance_result}

        # Gate 1: Quality check
        if quality.overall_score < self.settings.MIN_FACE_QUALITY or quality.blur_score < 0.15:
            face_dict["status"] = "low_quality"
            face_dict["name"] = "Low Quality"
            face_dict["is_unknown"] = False
            face_dict["is_valid_face"] = False
            return {"face": face_dict, "guidance": guidance_result}

        # Gate 2: Pose check
        pose_within_range = True
        if pose:
            if abs(pose.yaw) > self.settings.MAX_POSE_YAW or abs(pose.pitch) > self.settings.MAX_POSE_PITCH:
                pose_within_range = False
                face_dict["status"] = "bad_pose"
                face_dict["name"] = "Angle Too Steep"
                face_dict["is_unknown"] = False
                face_dict["is_valid_face"] = False
                return {"face": face_dict, "guidance": guidance_result}

        # Gate 3: Liveness check
        try:
            liveness_result = self.liveness.check(None, frame)
            face_dict["liveness_score"] = liveness_result.score
            if not liveness_result.is_live and liveness_result.status != "insufficient_data":
                face_dict["status"] = "liveness_failed"
                face_dict["is_unknown"] = False
                face_dict["is_valid_face"] = False
                return {"face": face_dict, "guidance": guidance_result}
        except Exception as e:
            logger.warning(f"Liveness check failed: {e}")
            face_dict["liveness_score"] = 0.5  # Benefit of doubt

        # Gate 4: Genuine ArcFace embedding must exist
        if face.embedding is None:
            face_dict["status"] = "no_embedding"
            face_dict["name"] = "No Biometrics"
            face_dict["is_unknown"] = False
            face_dict["is_valid_face"] = False
            return {"face": face_dict, "guidance": guidance_result}

        # Face is confirmed to be a valid human face
        face_dict["is_valid_face"] = True

        # FAISS search — returns list[SearchResult(id, similarity)]
        search_results = self.vector_store.search(face.embedding, k=5)

        if search_results:
            best = search_results[0]
            face_dict["similarity"] = best.similarity

            if best.similarity >= self.settings.RECOGNITION_THRESHOLD:
                person_info = self._get_person_for_faiss_id(best.id)
                if person_info:
                    p_id, p_name, p_status = person_info

                    # Run authorization
                    auth_decision = self.authorization.check(
                        person_id=p_id,
                        person_status=p_status,
                        confidence=best.similarity,
                        quality_score=quality.overall_score,
                        liveness_score=face_dict["liveness_score"],
                        pose_within_range=pose_within_range,
                    )

                    face_dict["person_id"] = p_id
                    face_dict["name"] = p_name
                    face_dict["authorized"] = auth_decision.granted
                    face_dict["status"] = "authorized" if auth_decision.granted else "denied"
                    face_dict["is_unknown"] = False
                else:
                    face_dict["name"] = "Unknown Person"
                    face_dict["status"] = "unknown"
                    face_dict["authorized"] = False
                    face_dict["is_unknown"] = True
            else:
                face_dict["name"] = "Unknown Person"
                face_dict["status"] = "unknown"
                face_dict["authorized"] = False
                face_dict["is_unknown"] = True
        else:
            face_dict["name"] = "Unknown Person"
            face_dict["status"] = "unknown"
            face_dict["authorized"] = False
            face_dict["is_unknown"] = True

        logger.info(
            f"Recognition result: person='{face_dict.get('name')}' id={face_dict.get('person_id')} "
            f"similarity={face_dict.get('similarity', 0.0):.3f} threshold={self.settings.RECOGNITION_THRESHOLD:.2f} "
            f"authorized={face_dict.get('authorized')} is_unknown={face_dict.get('is_unknown')}"
        )

        return {"face": face_dict, "guidance": guidance_result}

    # ------------------------------------------------------------------
    # Identity map management
    # ------------------------------------------------------------------

    def _get_person_for_faiss_id(self, faiss_id: int) -> tuple[int, str, str] | None:
        """Retrieve person details from the in-memory cache.

        Returns (person_id, name, status) or None.
        Time complexity: O(1) dict lookup.
        """
        return self._identity_map.get(faiss_id)

    async def load_identity_map(self, db_session: AsyncSession) -> None:
        """Load the faiss_id → (person_id, name, status) mapping from the database.

        Called once at startup and after enrollment/deletion changes.
        """
        try:
            stmt = (
                select(FaceEmbedding.faiss_id, Person.id, Person.name, Person.status)
                .join(Person, FaceEmbedding.person_id == Person.id)
                .where(Person.status != "deleted")
            )
            result = await db_session.execute(stmt)
            rows = result.all()

            self._identity_map.clear()
            for faiss_id, person_id, name, status in rows:
                self._identity_map[faiss_id] = (person_id, name, status)

            logger.info(f"Identity map loaded: {len(self._identity_map)} entries")
        except Exception as e:
            logger.error(f"Failed to load identity map: {e}", exc_info=True)

    def update_identity_map(
        self, faiss_id: int, person_id: int, name: str, status: str = "active"
    ) -> None:
        """Add or update an entry in the identity map."""
        self._identity_map[faiss_id] = (person_id, name, status)

    def remove_from_identity_map(self, faiss_ids: list[int]) -> None:
        """Remove specific FAISS IDs from the identity map."""
        for fid in faiss_ids:
            self._identity_map.pop(fid, None)
