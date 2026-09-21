import os
import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from app.core.config import get_settings
from app.core.logging_config import setup_logging
from app.db.database import init_db, AsyncSessionLocal

from app.services.face_detector import FaceDetector
from app.services.face_quality import FaceQualityChecker
from app.services.head_pose import HeadPoseEstimator
from app.services.faiss_store import FAISSVectorStore
from app.services.camera_guidance import CameraGuidanceService
from app.services.liveness import MediaPipeLivenessDetector
from app.services.enrollment import EnrollmentService
from app.services.recognition import RecognitionService
from app.services.authorization import AuthorizationService
from app.services.camera import CameraManager
from app.services.pipeline import RecognitionPipeline

from app.services.rtsp_manager import RTSPManager

from app.api.routes.auth import router as auth_router
from app.api.routes.persons import router as persons_router
from app.api.routes.enrollment import router as enrollment_router
from app.api.routes.recognition import router as recognition_router
from app.api.routes.logs import router as logs_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.system import router as system_router
from app.api.routes.attendance import router as attendance_router
from app.api.routes.cameras import router as cameras_router
from app.api.routes.unknowns import router as unknowns_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info('Starting FaceVault 360...')
    
    settings = get_settings()
    
    await init_db()
    logger.info('Database initialized')
    
    face_detector = FaceDetector(model_name=settings.INSIGHTFACE_MODEL)
    face_quality = FaceQualityChecker()
    head_pose = HeadPoseEstimator()
    camera_guidance = CameraGuidanceService()
    liveness = MediaPipeLivenessDetector()
    logger.info('CV services initialized')
    
    vector_store = FAISSVectorStore(dimension=settings.EMBEDDING_DIMENSION)
    vector_store.load(settings.FAISS_INDEX_PATH)
    logger.info(f'FAISS index loaded: {vector_store.count} vectors')
    
    authorization = AuthorizationService(settings)
    enrollment_service = EnrollmentService(face_detector, face_quality, head_pose, vector_store, camera_guidance, settings)
    recognition_service = RecognitionService(face_detector, face_quality, head_pose, vector_store, liveness, camera_guidance, authorization, settings)
    
    async with AsyncSessionLocal() as session:
        await recognition_service.load_identity_map(session)
    logger.info('Identity map loaded')
    
    camera = CameraManager(camera_id=0, target_fps=settings.CAMERA_FPS)
    logger.info('Camera manager initialized (on-demand mode)')
    
    pipeline = RecognitionPipeline(
        camera=camera,
        recognition_service=recognition_service,
        enrollment_service=enrollment_service,
        head_pose=head_pose,
        face_quality=face_quality,
        camera_guidance=camera_guidance,
        liveness=liveness,
        settings=settings
    )

    rtsp_manager = RTSPManager(
        recognition_service=recognition_service,
        loop=None
    )
    
    app.state.settings = settings
    app.state.face_detector = face_detector
    app.state.vector_store = vector_store
    app.state.enrollment_service = enrollment_service
    app.state.recognition_service = recognition_service
    app.state.camera = camera
    app.state.pipeline = pipeline
    app.state.rtsp_manager = rtsp_manager
    app.state.startup_time = time.time()
    
    import asyncio
    rtsp_manager.set_event_loop(asyncio.get_running_loop())
    
    # Auto-seed or update Check-In and Check-Out cameras from settings/environment if configured
    try:
        from app.db.repositories.camera_repo import RTSPCameraRepository
        async with AsyncSessionLocal() as session:
            existing_cams = await RTSPCameraRepository.list_all(session)

            # 1. Check-In Camera from environment if configured
            checkin_url = settings.effective_checkin_url
            if checkin_url:
                checkin_cams = [c for c in existing_cams if c.mode == "CHECK-IN"]
                if checkin_cams:
                    await RTSPCameraRepository.update(
                        session=session,
                        camera_id=checkin_cams[0].id,
                        rtsp_url=checkin_url,
                        username=settings.CHECKIN_CAMERA_USERNAME or None,
                        password=settings.CHECKIN_CAMERA_PASSWORD or None,
                        location=settings.CHECKIN_CAMERA_LOCATION or "Main Entrance",
                        enabled=settings.CHECKIN_CAMERA_ENABLED,
                    )
                    logger.info(f"Updated Check-In RTSP Camera from environment URL: {checkin_url}")
                else:
                    await RTSPCameraRepository.create(
                        session=session,
                        name=settings.CHECKIN_CAMERA_NAME,
                        rtsp_url=checkin_url,
                        username=settings.CHECKIN_CAMERA_USERNAME or None,
                        password=settings.CHECKIN_CAMERA_PASSWORD or None,
                        location=settings.CHECKIN_CAMERA_LOCATION or "Main Entrance",
                        mode="CHECK-IN",
                        enabled=settings.CHECKIN_CAMERA_ENABLED,
                    )
                    logger.info(f"Initialized Check-In RTSP Camera from environment URL: {checkin_url}")

            # 2. Check-Out Camera from environment if configured
            checkout_url = settings.effective_checkout_url
            if checkout_url:
                checkout_cams = [c for c in existing_cams if c.mode == "CHECK-OUT"]
                if checkout_cams:
                    await RTSPCameraRepository.update(
                        session=session,
                        camera_id=checkout_cams[0].id,
                        rtsp_url=checkout_url,
                        username=settings.CHECKOUT_CAMERA_USERNAME or None,
                        password=settings.CHECKOUT_CAMERA_PASSWORD or None,
                        location=settings.CHECKOUT_CAMERA_LOCATION or "Turnstile Exit Gate",
                        enabled=settings.CHECKOUT_CAMERA_ENABLED,
                    )
                    logger.info(f"Updated Check-Out RTSP Camera from environment URL: {checkout_url}")
                else:
                    await RTSPCameraRepository.create(
                        session=session,
                        name=settings.CHECKOUT_CAMERA_NAME,
                        rtsp_url=checkout_url,
                        username=settings.CHECKOUT_CAMERA_USERNAME or None,
                        password=settings.CHECKOUT_CAMERA_PASSWORD or None,
                        location=settings.CHECKOUT_CAMERA_LOCATION or "Turnstile Exit Gate",
                        mode="CHECK-OUT",
                        enabled=settings.CHECKOUT_CAMERA_ENABLED,
                    )
                    logger.info(f"Initialized Check-Out RTSP Camera from environment URL: {checkout_url}")
    except Exception as e:
        logger.warning(f"Failed to auto-seed RTSP cameras from environment: {e}")

    await rtsp_manager.load_and_start_all()

    logger.info('FaceVault 360 ready!')
    
    yield
    
    logger.info('Shutting down FaceVault 360...')
    rtsp_manager.shutdown()
    camera.stop()
    head_pose.close()
    vector_store.save(settings.FAISS_INDEX_PATH)
    logger.info('Shutdown complete')

app = FastAPI(
    title='FaceVault 360',
    description='Intelligent Facial Access Control System',
    version='1.0.0',
    lifespan=lifespan
)

settings_cors = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router)
app.include_router(persons_router)
app.include_router(enrollment_router)
app.include_router(recognition_router)
app.include_router(logs_router)
app.include_router(analytics_router)
app.include_router(system_router)
app.include_router(attendance_router)
app.include_router(cameras_router)
app.include_router(unknowns_router)

@app.get('/')
async def root():
    return {'name': 'FaceVault 360', 'tagline': 'Recognize. Verify. Protect.', 'version': '1.0.0'}

