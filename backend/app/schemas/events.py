from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

class AccessEventResponse(BaseModel):
    id: int
    person_id: Optional[int] = None
    recognized_name: Optional[str] = None
    timestamp: datetime
    confidence: float
    status: str
    authorization_result: str
    pose_yaw: Optional[float] = None
    pose_pitch: Optional[float] = None
    quality_score: Optional[float] = None
    camera_id: str
    failure_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class EventFilter(BaseModel):
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    person_id: Optional[int] = None
    status: Optional[str] = None
    camera_id: Optional[str] = None
    min_confidence: Optional[float] = None
    max_confidence: Optional[float] = None

class EventListResponse(BaseModel):
    items: List[AccessEventResponse]
    total: int
    skip: int
    limit: int
