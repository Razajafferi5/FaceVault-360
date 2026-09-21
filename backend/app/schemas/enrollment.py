from typing import Tuple, List, Optional
from pydantic import BaseModel

class CameraGuidanceResponse(BaseModel):
    face_detected: bool
    position_ok: bool
    message: str
    severity: str  # 'good', 'warning', 'error'
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    action: Optional[str] = "none"

class PoseStep(BaseModel):
    step: int
    label: str
    instruction: str
    target_yaw_range: Tuple[float, float]
    target_pitch_range: Tuple[float, float]

class EnrollmentStartRequest(BaseModel):
    person_id: int

class EnrollmentStartResponse(BaseModel):
    session_id: str
    person_name: str
    total_poses: int
    poses: List[PoseStep]

class EnrollmentFrameResponse(BaseModel):
    status: str  # 'no_face', 'multiple_faces', 'reposition', 'hold_still', 'captured', 'completed', 'error'
    captured: bool = False
    message: str = "FACE NOT DETECTED"
    instruction: str = "Align face in the guide box"
    status_color: str = "red"  # 'red', 'green', 'yellow'
    detected_bbox: Optional[List[int]] = None  # [x, y, w, h]
    face_count: int = 0
    hold_progress: float = 0.0  # 0.0 to 1.0 (stabilization countdown)
    current_step: int = 1
    total_steps: int = 1
    pose_label: str = "frontal"
    guidance: Optional[CameraGuidanceResponse] = None
    quality_score: Optional[float] = None
    completed: bool = False
    current_yaw: Optional[float] = None
    current_pitch: Optional[float] = None

class EnrollmentCompleteResponse(BaseModel):
    success: bool
    status: str = "success"
    person_name: str
    poses_captured: int
    average_quality: float
    message: str
