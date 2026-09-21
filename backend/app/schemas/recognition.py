from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from .enrollment import CameraGuidanceResponse

class FaceDetectionResult(BaseModel):
    bbox: List[int]
    confidence: float
    name: Optional[str] = None
    person_id: Optional[int] = None
    similarity: float
    authorized: bool
    status: str
    pose_label: str
    pose_yaw: float
    pose_pitch: float
    quality_score: float
    liveness_score: float

class CameraHealthResponse(BaseModel):
    online: bool
    fps: float
    latency_ms: float
    last_frame: Optional[str] = None

class RecognitionResponse(BaseModel):
    faces: List[FaceDetectionResult]
    camera_guidance: CameraGuidanceResponse
    camera_health: CameraHealthResponse
    timestamp: str

class PipelineEvent(BaseModel):
    type: str
    data: Dict[str, Any]
