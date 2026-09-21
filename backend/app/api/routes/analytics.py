"""Analytics API routes — dashboard summary and trend data."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.repositories.event_repo import EventRepository
from app.db.repositories.person_repo import PersonRepository
from app.schemas.analytics import DashboardSummary, DailyStats, AnalyticsResponse
from app.core.security import get_current_user
from app.db.models import SystemUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: SystemUser = Depends(get_current_user),
):
    """Dashboard summary: today's stats + registered people count."""
    today_stats = await EventRepository.get_today_stats(db)
    active_persons = await PersonRepository.count_active(db)

    return DashboardSummary(
        todays_entries=today_stats["total_entries"],
        authorized_count=today_stats["authorized_count"],
        denied_count=today_stats["denied_count"],
        registered_people=active_persons,
        system_online=True,
    )


@router.get("/trends", response_model=AnalyticsResponse)
async def get_trends(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: SystemUser = Depends(get_current_user),
):
    """Time-series analytics: daily entries, success rate, unknown attempts."""
    analytics_data = await EventRepository.get_analytics(db, days=days)

    daily_stats = [
        DailyStats(
            date=d["date"],
            total=d["total"],
            authorized=d["authorized"],
            denied=d["denied"],
        )
        for d in analytics_data
    ]

    total = sum(d["total"] for d in analytics_data)
    authorized = sum(d["authorized"] for d in analytics_data)
    denied = sum(d["denied"] for d in analytics_data)

    success_rate = (authorized / total * 100) if total > 0 else 0.0
    unknown_attempts = denied  # Approximation: denied includes unknown

    return AnalyticsResponse(
        daily_stats=daily_stats,
        total_entries=total,
        success_rate=round(success_rate, 1),
        unknown_attempts=unknown_attempts,
    )
