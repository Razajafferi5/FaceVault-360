# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import numpy as np
import cv2

# Ensure backend directory is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import get_settings
from app.db.database import AsyncSessionLocal, init_db
from app.services.face_detector import FaceDetector, DetectedFace
from app.services.face_quality import FaceQualityChecker
from app.services.recognition import RecognitionService
from app.db.repositories.unknown_repo import UnknownPersonRepository
from app.db.models import UnknownPersonEvent
from sqlalchemy import select, func

async def run_tests():
    print("\n========================================================")
    print("RUNNING AUTOMATED VERIFICATION: OBJECT REJECTION & DEDUP")
    print("========================================================\n")

    await init_db()
    settings = get_settings()

    # ---------------------------------------------------------
    # TEST 1: INANIMATE OBJECT & PATTERN REJECTION (Problem 1)
    # ---------------------------------------------------------
    print("TEST 1: Inanimate Object & Texture Rejection")
    from app.services.head_pose import HeadPoseEstimator
    from app.services.camera_guidance import CameraGuidanceService
    from app.services.liveness import MediaPipeLivenessDetector
    from app.services.faiss_store import FAISSVectorStore
    from app.services.authorization import AuthorizationService

    detector = FaceDetector(model_name=settings.INSIGHTFACE_MODEL)
    quality_checker = FaceQualityChecker()
    head_pose = HeadPoseEstimator()
    camera_guidance = CameraGuidanceService()
    liveness = MediaPipeLivenessDetector()
    vector_store = FAISSVectorStore(dimension=settings.EMBEDDING_DIMENSION)
    authorization = AuthorizationService(settings)

    recognition_service = RecognitionService(
        detector, quality_checker, head_pose, vector_store, liveness, camera_guidance, authorization, settings
    )

    # 1a. Blank white and black frames
    white_frame = np.ones((480, 640, 3), dtype=np.uint8) * 255
    black_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    res_white = recognition_service.recognize_frame(white_frame)
    res_black = recognition_service.recognize_frame(black_frame)

    assert len(res_white["faces"]) == 0, f"Expected 0 faces on blank white frame, got {len(res_white['faces'])}"
    assert len(res_black["faces"]) == 0, f"Expected 0 faces on blank black frame, got {len(res_black['faces'])}"
    print("  [OK] Blank frames produced 0 faces")

    # 1b. Repeating striped pattern (simulating fan grilles / chair slats)
    striped = np.zeros((480, 640, 3), dtype=np.uint8)
    for y in range(0, 480, 8):
        striped[y:y+4, :, :] = 255
    res_striped = recognition_service.recognize_frame(striped)
    # Even if detector found anything, none must be unknown
    for f in res_striped.get("faces", []):
        assert not f.get("is_unknown", False), f"Striped pattern marked as unknown! {f}"
        assert not f.get("is_valid_face", False), f"Striped pattern marked as valid face! {f}"
    print("  [OK] Striped texture produced NO unknown person events")

    # 1c. Extreme aspect ratio rectangle (simulating wall, desk, door)
    assert not FaceDetector.is_valid_face_candidate([10, 10, 400, 50], None, 0.90), "Wide rectangle should be rejected!"
    assert not FaceDetector.is_valid_face_candidate([10, 10, 40, 300], None, 0.90), "Tall rectangle should be rejected!"
    print("  [OK] Extreme aspect ratios (walls, doors, desks) rejected by geometry validator")

    # 1d. Low detection score rejection
    assert not FaceDetector.is_valid_face_candidate([10, 10, 80, 80], None, 0.30), "Low confidence should be rejected!"
    print("  [OK] Low confidence noise rejected (< 0.45)")

    # 1e. Fake / zeroed landmarks without ArcFace embedding
    quality_checker2 = FaceQualityChecker()
    fake_face = DetectedFace(
        bbox=[50, 50, 80, 80],
        confidence=0.70,
        landmarks=np.zeros((5, 2)),
        embedding=None
    )
    q_res = quality_checker2.assess(white_frame, fake_face.bbox, fake_face.landmarks)
    assert not q_res.is_acceptable, "Missing landmarks must not be acceptable!"
    assert "missing_landmarks" in q_res.issues, "Should flag missing_landmarks issue!"

    proc_res = recognition_service._process_single_face(white_frame, fake_face, None, 1, 0)
    assert not proc_res["face"]["is_unknown"], f"Face with zero landmarks must NOT be marked unknown! {proc_res}"
    assert not proc_res["face"]["is_valid_face"], "Face with zero landmarks must not be valid face!"
    print("  [OK] Candidate with zero landmarks or missing embedding strictly rejected from unknown logging")

    # ---------------------------------------------------------
    # TEST 2: UNKNOWN PERSON DEDUPLICATION & VISIT SESSION (Problem 2)
    # ---------------------------------------------------------
    print("\nTEST 2: Unknown Person Deduplication & Sessionization")

    # Synthetic realistic ArcFace 512-d normalized embedding for Visitor A
    np.random.seed(42)
    emb_a = np.random.randn(512).astype(np.float32)
    emb_a /= np.linalg.norm(emb_a)

    face_crop_low = np.ones((80, 80, 3), dtype=np.uint8) * 100
    face_crop_high = np.ones((120, 120, 3), dtype=np.uint8) * 200

    async with AsyncSessionLocal() as session:
        # Frame 1: Visitor A first appears
        event1, is_new1 = await UnknownPersonRepository.record_or_update_unknown(
            session=session,
            camera_name="Test Entrance Camera",
            camera_role="CHECK-IN",
            camera_id=99,
            face_confidence=0.88,
            quality_score=0.65,
            face_crop=face_crop_low,
            face_embedding=emb_a,
            cooldown_seconds=60.0
        )
        assert is_new1 is True, "First detection must create a new visit event!"
        assert event1.detection_count == 1, f"Expected count=1, got {event1.detection_count}"
        assert event1.best_quality_score == 0.65, f"Expected quality=0.65, got {event1.best_quality_score}"
        print(f"  [OK] Frame 1: Created new visit event #{event1.id} (count=1, quality={event1.best_quality_score})")

        # Frame 2-5: Visitor A remains in frame, higher quality snapshot arrives
        event2, is_new2 = await UnknownPersonRepository.record_or_update_unknown(
            session=session,
            camera_name="Test Entrance Camera",
            camera_role="CHECK-IN",
            camera_id=99,
            face_confidence=0.94,
            quality_score=0.91,
            face_crop=face_crop_high,
            face_embedding=emb_a + np.random.randn(512).astype(np.float32) * 0.05,  # slight angle variation
            cooldown_seconds=60.0
        )
        assert is_new2 is False, "Same visitor within cooldown MUST NOT create a new row!"
        assert event2.id == event1.id, f"Expected same event ID #{event1.id}, got #{event2.id}"
        assert event2.detection_count == 2, f"Expected count=2, got {event2.detection_count}"
        assert event2.best_quality_score == 0.91, f"Expected quality upgraded to 0.91, got {event2.best_quality_score}"
        print(f"  [OK] Frame 2: Deduplicated into event #{event2.id} (count=2, quality upgraded to {event2.best_quality_score})")

        # Heartbeat update simulation: 10 frames processed in 2 seconds
        hb_event = await UnknownPersonRepository.update_session_heartbeat(
            session=session,
            event_id=event1.id,
            added_count=10,
            quality_score=0.91
        )
        assert hb_event is not None
        assert hb_event.detection_count == 12, f"Expected count=12 after heartbeat, got {hb_event.detection_count}"
        print(f"  [OK] Throttled Heartbeat: Event #{hb_event.id} detection_count incremented to {hb_event.detection_count}")

        # ---------------------------------------------------------
        # TEST 3: DIFFERENT VISITOR SEPARATION (Problem 2)
        # ---------------------------------------------------------
        print("\nTEST 3: Different Unknown Visitors Remain Independent")
        # Visitor B: Orthogonal face vector
        emb_b = np.random.randn(512).astype(np.float32)
        emb_b /= np.linalg.norm(emb_b)

        event_b, is_new_b = await UnknownPersonRepository.record_or_update_unknown(
            session=session,
            camera_name="Test Entrance Camera",
            camera_role="CHECK-IN",
            camera_id=99,
            face_confidence=0.85,
            quality_score=0.72,
            face_crop=face_crop_low,
            face_embedding=emb_b,
            cooldown_seconds=60.0
        )
        assert is_new_b is True, "Different visitor must create an independent event!"
        assert event_b.id != event1.id, f"Visitor B should have different ID than Visitor A, got #{event_b.id}"
        print(f"  [OK] Visitor B created distinct event #{event_b.id} without merging into Visitor A")

        # ---------------------------------------------------------
        # TEST 4: COOLDOWN EXPIRY (Problem 2)
        # ---------------------------------------------------------
        print("\nTEST 4: Cooldown Expiry Creates New Visit")
        # Simulate Visitor A returning after cooldown expires
        await asyncio.sleep(0.15)
        event_a_return, is_new_return = await UnknownPersonRepository.record_or_update_unknown(
            session=session,
            camera_name="Test Entrance Camera",
            camera_role="CHECK-IN",
            camera_id=99,
            face_confidence=0.89,
            quality_score=0.70,
            face_crop=face_crop_low,
            face_embedding=emb_a,
            cooldown_seconds=0.10  # 100ms cooldown window has expired
        )
        assert is_new_return is True, "Returning visitor after cooldown must create a new visit event!"
        assert event_a_return.id != event1.id, "New visit event must have new ID"
        print(f"  [OK] Returning Visitor A after cooldown created new visit event #{event_a_return.id}")

        # Clean up test rows
        from sqlalchemy import delete
        await session.execute(delete(UnknownPersonEvent).where(UnknownPersonEvent.camera_id == 99))
        await session.commit()
        print("\n  [OK] Test records cleaned up from database")

    print("\n========================================================")
    print("ALL TESTS PASSED SUCCESSFULLY! (100% VERIFIED)")
    print("========================================================\n")

if __name__ == "__main__":
    asyncio.run(run_tests())
