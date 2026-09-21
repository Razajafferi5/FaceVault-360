from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

class UnknownPersonEventResponse(BaseModel):
    id: int
    event_uuid: str
    detected_at: datetime
    date_str: str
    time_str: str
    camera_id: Optional[int] = None
    camera_name: str
    camera_role: str
    snapshot_path: Optional[str] = None
    snapshot_url: Optional[str] = None
    face_confidence: float = 0.0
    recognition_status: str = "UNKNOWN"
    access_status: str = "PENDING"
    approved_by_id: Optional[int] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    enrolled_person_id: Optional[int] = None

    enrollment_method: Optional[str] = None
    enrolled_by: Optional[str] = None
    enrolled_at: Optional[datetime] = None

    # Sessionization & Visit tracking
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    first_seen_time_str: Optional[str] = None
    last_seen_time_str: Optional[str] = None
    detection_count: int = 1
    duration_seconds: int = 0
    best_quality_score: float = 0.0

    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UnknownPersonListResponse(BaseModel):
    items: List[UnknownPersonEventResponse]
    total: int
    skip: int
    limit: int

class UnknownPersonStatsResponse(BaseModel):
    total_today: int
    pending_count: int
    approved_count: int
    denied_count: int
    enrolled_count: int

class UnknownActionRequest(BaseModel):
    notes: Optional[str] = None

