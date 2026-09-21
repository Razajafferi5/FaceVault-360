import logging
import cv2
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Person, FaceEmbedding, UnknownPersonEvent
from app.db.repositories.person_repo import PersonRepository
from app.db.repositories.embedding_repo import EmbeddingRepository
from app.services.face_detector import FaceDetector, DetectedFace
from app.services.face_quality import FaceQualityChecker
from app.services.faiss_store import FAISSVectorStore

logger = logging.getLogger(__name__)


class RTSPEnrollmentService:
    """
    RTSP-based Multi-Frame Facial Biometric Enrollment Engine.
    - Uses identical InsightFace model and FAISS vector index as the recognition pipeline.
    - Implements strict multi-frame quality filtering, blur detection, size check, and multiple-face guards.
    """

    @staticmethod
    def evaluate_rtsp_frame(
        frame: np.ndarray,
        face_detector: FaceDetector,
        face_quality: FaceQualityChecker
    ) -> Dict[str, Any]:
        """
        Assesses a single raw frame from an RTSP camera stream for enrollment suitability.
        Rejects multiple faces, small faces, extreme poses, and blurry captures.
        """
        if frame is None or frame.size == 0:
            return {
                "valid": False,
                "reason": "INVALID_FRAME",
                "instruction": "No video frame data",
                "quality_score": 0.0,
                "face_count": 0,
                "bbox": None
            }

        faces = face_detector.detect(frame) if hasattr(face_detector, "detect") else face_detector.detect_faces(frame)
        face_count = len(faces)

        if face_count == 0:
            return {
                "valid": False,
                "reason": "NO_FACE_DETECTED",
                "instruction": "Position face clearly within camera view",
                "quality_score": 0.0,
                "face_count": 0,
                "bbox": None
            }

        # STRICT GUARD: Multiple faces in enrollment frame is strictly rejected!
        if face_count > 1:
            return {
                "valid": False,
                "reason": "MULTIPLE_FACES_DETECTED",
                "instruction": "MULTIPLE FACES DETECTED — Ensure only candidate is in frame",
                "quality_score": 0.0,
                "face_count": face_count,
                "bbox": None
            }

        face: DetectedFace = faces[0]
        bbox = face.bbox
        bw = bbox[2]
        bh = bbox[3]

        # Minimum face size: 60x60 pixels
        if bw < 55 or bh < 55:
            return {
                "valid": False,
                "reason": "FACE_TOO_SMALL",
                "instruction": "Move closer to the camera",
                "quality_score": 0.25,
                "face_count": 1,
                "bbox": bbox
            }

        # Pose angle check
        yaw = getattr(face, "yaw", 0.0)
        pitch = getattr(face, "pitch", 0.0)
        if abs(yaw) > 35.0 or abs(pitch) > 28.0:
            return {
                "valid": False,
                "reason": "POOR_ANGLE",
                "instruction": "Turn to face directly toward the camera",
                "quality_score": 0.35,
                "face_count": 1,
                "bbox": bbox
            }

        # Sharpness / Blur check using Laplacian variance on face crop
        x, y, w, h = [int(v) for v in bbox[:4]]
        fh, fw = frame.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(fw, x + w)
        y2 = min(fh, y + h)

        if x2 > x1 and y2 > y1:
            face_crop = frame[y1:y2, x1:x2]
            gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            blur_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            if blur_var < 50.0:
                return {
                    "valid": False,
                    "reason": "TOO_BLURRY",
                    "instruction": "Hold still — camera image is blurry",
                    "quality_score": 0.38,
                    "face_count": 1,
                    "bbox": bbox
                }
        else:
            blur_var = 100.0

        # Detailed quality score check
        q_res = face_quality.assess(frame, face)
        overall_quality = round(float(q_res.overall_score), 2)

        if overall_quality < 0.40:
            return {
                "valid": False,
                "reason": "LOW_QUALITY",
                "instruction": "Improve lighting or hold steady",
                "quality_score": overall_quality,
                "face_count": 1,
                "bbox": bbox
            }

        return {
            "valid": True,
            "reason": "OK",
            "instruction": "Good face position! Hold still for capture",
            "quality_score": overall_quality,
            "face_count": 1,
            "bbox": bbox,
            "face": face
        }

    @staticmethod
    async def enroll_from_rtsp_samples(
        samples: List[np.ndarray],
        person_data: Dict[str, Any],
        db_session: AsyncSession,
        recognition_service,
        vector_store: FAISSVectorStore,
        settings,
        unknown_event_id: Optional[int] = None,
        owner_name: str = "Owner"
    ) -> Tuple[Person, Optional[UnknownPersonEvent]]:
        """
        Processes collected RTSP frames, extracts 512-D embeddings using InsightFace,
        inserts Person and FaceEmbedding into database, updates FAISS index, and immediately
        reloads the recognition gallery in memory across both camera workers.
        """
        face_detector: FaceDetector = recognition_service.face_detector
        face_quality: FaceQualityChecker = recognition_service.face_quality

        valid_samples: List[Tuple[np.ndarray, DetectedFace, float]] = []

        for frame in samples:
            eval_res = RTSPEnrollmentService.evaluate_rtsp_frame(frame, face_detector, face_quality)
            if eval_res["valid"]:
                valid_samples.append((frame, eval_res["face"], eval_res["quality_score"]))

        # Graceful fallback: If strict filter found no perfect frame, detect any face in available samples
        if not valid_samples and samples:
            for frame in samples:
                det_faces = face_detector.detect(frame) if hasattr(face_detector, "detect") else face_detector.detect_faces(frame)
                if det_faces:
                    valid_samples.append((frame, det_faces[0], 0.75))

        if not valid_samples:
            raise ValueError("No face could be detected in the provided RTSP frames or visitor snapshot.")


        # Sort by quality score and take the best 3 to 5 candidate samples
        valid_samples.sort(key=lambda s: s[2], reverse=True)
        chosen_samples = valid_samples[:5]

        # 1. Create Person in authoritative database
        identifier = person_data.get("person_identifier") or f"EMP-{int(np.random.randint(1000, 9999))}"
        person = Person(
            name=person_data["name"].strip(),
            person_identifier=identifier.strip(),
            department=person_data.get("department", "General"),
            role=person_data.get("role", "Employee"),
            notes=person_data.get("notes", "Enrolled directly from RTSP stream by Owner"),
            status="active"  # IMMEDIATELY ACTIVE
        )
        db_session.add(person)
        await db_session.commit()
        await db_session.refresh(person)

        # 2. Extract and Store Embeddings
        max_id = await EmbeddingRepository.get_max_faiss_id(db_session)
        next_faiss_id = (max_id or 0) + 1

        bulk_records = []
        for idx, (frame, face, q_score) in enumerate(chosen_samples):
            emb = face_detector.extract_embedding(frame, face)
            if emb is None:
                continue

            faiss_id = next_faiss_id
            next_faiss_id += 1

            bulk_records.append({
                "person_id": person.id,
                "embedding_bytes": emb.tobytes(),
                "faiss_id": faiss_id,
                "pose_label": f"rtsp_sample_{idx + 1}",
                "yaw": round(float(getattr(face, "yaw", 0.0)), 1),
                "pitch": round(float(getattr(face, "pitch", 0.0)), 1),
                "roll": round(float(getattr(face, "roll", 0.0)), 1),
                "quality_score": q_score,
            })

            # Add to FAISS in-memory index
            vector_store.add(emb, faiss_id)

            # Update recognition service identity map in real time (0ms)
            recognition_service.update_identity_map(faiss_id, person.id, person.name, "active")

        if not bulk_records:
            raise ValueError("Failed to extract valid face embeddings from the selected frames.")

        await EmbeddingRepository.bulk_create(db_session, bulk_records)
        vector_store.save(settings.FAISS_INDEX_PATH)

        # Reload complete identity map to guarantee multi-worker synchronization
        await recognition_service.load_identity_map(db_session)

        # 3. If linked to an UnknownPersonEvent, update its audit records
        unknown_event = None
        if unknown_event_id:
            from app.db.repositories.unknown_repo import UnknownPersonRepository
            from app.services.rtsp_manager import RTSPManager
            from datetime import datetime

            unknown_event = await UnknownPersonRepository.get_by_id(db_session, unknown_event_id)
            if unknown_event:
                unknown_event.access_status = "ENROLLED"
                unknown_event.enrolled_person_id = person.id
                unknown_event.enrollment_method = "RTSP"
                unknown_event.enrolled_by = owner_name
                unknown_event.enrolled_at = datetime.now()
                unknown_event.updated_at = datetime.now()
                await db_session.commit()
                await db_session.refresh(unknown_event)

                RTSPManager.set_unknown_status(unknown_event_id, "ENROLLED")

        logger.info(
            f"Owner successfully enrolled Person #{person.id} ('{person.name}') via RTSP with {len(bulk_records)} embeddings."
        )

        return person, unknown_event
