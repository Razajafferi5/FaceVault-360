from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    APP_NAME: str = 'FaceVault 360'
    VERSION: str = '1.0.0'
    SECRET_KEY: str = "default-insecure-key-override-in-env"
    DATABASE_URL: str = 'sqlite+aiosqlite:///./facevault.db'
    RECOGNITION_THRESHOLD: float = 0.50  # Balanced threshold (well above cross-person max 0.114)
    DETECTION_THRESHOLD: float = 0.40    # SCRFD face detector confidence for distance detection
    MIN_FACE_SIZE_PIXELS: int = 36       # Minimum bounding box size in pixels for recognition
    MIN_FACE_QUALITY: float = 0.30       # Quality score cutoff
    MAX_POSE_YAW: float = 55.0           # Allow slight head turn angles
    MAX_POSE_PITCH: float = 40.0         # Allow slight vertical tilt
    LIVENESS_THRESHOLD: float = 0.6
    CAMERA_FPS: int = 30
    TARGET_STREAM_FPS: int = 15
    RECOGNITION_INTERVAL: int = 10
    MAX_INFERENCE_WIDTH: int = 1280      # High resolution inference to preserve distance facial detail
    RECOGNITION_CONFIRMATION_FRAMES: int = 2  # Frames of consistent match before confirmation
    RECOGNITION_HOLD_TIME: float = 2.5   # Seconds to hold confirmed identity during brief turns/occlusion
    UNKNOWN_HOLD_TIME: float = 1.5       # Seconds of consistent unknown frames before confirming unknown
    STORE_ENROLLMENT_IMAGES: bool = False
    INSIGHTFACE_MODEL: str = 'buffalo_sc'
    EMBEDDING_DIMENSION: int = 512
    FAISS_INDEX_PATH: str = './faiss_index.bin'
    ADMIN_USERNAME: str = 'admin'
    ADMIN_PASSWORD: str = 'facevault360'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    CORS_ORIGINS: List[str] = ['http://localhost:5173', 'http://localhost:3000']
    # RTSP Cameras Configuration
    CHECK_IN_RTSP_URL: str = ""
    CHECKIN_CAMERA_RTSP_URL: str = ""
    CHECKIN_CAMERA_NAME: str = "Check-In Camera"
    CHECKIN_CAMERA_LOCATION: str = "Main Entrance Gate"
    CHECKIN_CAMERA_USERNAME: str = ""
    CHECKIN_CAMERA_PASSWORD: str = ""
    CHECKIN_CAMERA_ENABLED: bool = True

    CHECK_OUT_RTSP_URL: str = ""
    CHECKOUT_CAMERA_RTSP_URL: str = ""
    CHECKOUT_CAMERA_NAME: str = "Check-Out Camera"
    CHECKOUT_CAMERA_LOCATION: str = "Turnstile Exit Gate"
    CHECKOUT_CAMERA_USERNAME: str = ""
    CHECKOUT_CAMERA_PASSWORD: str = ""
    CHECKOUT_CAMERA_ENABLED: bool = True

    @property
    def effective_checkin_url(self) -> str:
        return self.CHECK_IN_RTSP_URL or self.CHECKIN_CAMERA_RTSP_URL or ""

    @property
    def effective_checkout_url(self) -> str:
        return self.CHECK_OUT_RTSP_URL or self.CHECKOUT_CAMERA_RTSP_URL or ""

    # Unknown Persons & Access Approval
    UNKNOWN_SNAPSHOTS_DIR: str = "data/unknown_snapshots"
    UNKNOWN_COOLDOWN_SECONDS: float = 8.0
    UNKNOWN_EVENT_COOLDOWN_SECONDS: float = 60.0  # Configurable session window (default 60s)
    UNKNOWN_SIMILARITY_THRESHOLD: float = 0.42     # Cosine similarity for grouping same unknown visitor

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
