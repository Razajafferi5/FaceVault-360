import pytest
import pytest_asyncio
import numpy as np
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.database import Base
from app.core.config import Settings

@pytest.fixture
def settings():
    """Test settings with overrides."""
    return Settings(
        SECRET_KEY='test-secret-key',
        DATABASE_URL='sqlite+aiosqlite:///:memory:',
        RECOGNITION_THRESHOLD=0.45,
        MIN_FACE_QUALITY=0.5,
        MAX_POSE_YAW=45.0,
        MAX_POSE_PITCH=30.0,
        LIVENESS_THRESHOLD=0.6,
        FAISS_INDEX_PATH='./test_faiss.bin',
    )

@pytest_asyncio.fixture
async def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()

@pytest.fixture
def sample_embedding():
    """Generate a random 512-d L2-normalized embedding."""
    vec = np.random.randn(512).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec

@pytest.fixture
def sample_frame():
    """Generate a synthetic 480x640x3 BGR frame."""
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

@pytest.fixture
def bright_face_crop():
    """Generate a well-lit face crop (medium brightness, good contrast)."""
    crop = np.full((112, 112, 3), 128, dtype=np.uint8)
    noise = np.random.randint(-30, 30, crop.shape, dtype=np.int16)
    crop = np.clip(crop.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return crop

@pytest.fixture
def dark_face_crop():
    """Generate a dark face crop."""
    return np.full((112, 112, 3), 20, dtype=np.uint8)

@pytest.fixture
def blurry_face_crop():
    """Generate a blurry face crop (very smooth, low Laplacian variance)."""
    import cv2
    crop = np.random.randint(100, 160, (112, 112, 3), dtype=np.uint8)
    crop = cv2.GaussianBlur(crop, (31, 31), 15)
    return crop

@pytest.fixture
def small_bbox():
    """Face bbox that's too small relative to a 640x480 frame."""
    return [300, 220, 20, 20]

@pytest.fixture
def good_bbox():
    """Well-sized face bbox."""
    return [200, 100, 200, 250]
