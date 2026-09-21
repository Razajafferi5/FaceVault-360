from typing import List
from pydantic import BaseModel

class DashboardSummary(BaseModel):
    todays_entries: int
    authorized_count: int
    denied_count: int
    registered_people: int
    system_online: bool

class DailyStats(BaseModel):
    date: str
    total: int
    authorized: int
    denied: int

class AnalyticsResponse(BaseModel):
    daily_stats: List[DailyStats]
    total_entries: int
    success_rate: float
    unknown_attempts: int

class SystemStatusResponse(BaseModel):
    status: str
    camera_online: bool
    fps: float
    avg_inference_ms: float
    recognition_latency_ms: float
    cpu_percent: float
    ram_percent: float
    ram_used_mb: float
    registered_persons: int
    total_embeddings: int
    faiss_index_size: int
    uptime_seconds: float
