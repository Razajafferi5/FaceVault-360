import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Attendance, Person, AccessEvent

logger = logging.getLogger(__name__)

class AttendanceRepository:
    """
    Repository for Attendance Sessions and Multi-Session Management.
    Supports multiple check-in / check-out sessions per employee per day.
    Guarantees:
      - At most ONE OPEN session per employee at any given time.
      - Multiple CLOSED sessions allowed for the same employee on the same date.
      - Total daily worked time aggregation.
    """

    @staticmethod
    def get_today_date_str() -> str:
        """Returns today's date formatted as DD-MM-YYYY."""
        return datetime.now().strftime("%d-%m-%Y")

    @staticmethod
    def get_current_time_str() -> str:
        """Returns current local time formatted as HH:MM AM/PM."""
        return datetime.now().strftime("%I:%M %p")

    @staticmethod
    async def get_open_session(
        session: AsyncSession,
        employee_id: int
    ) -> Optional[Attendance]:
        """
        Finds the current OPEN attendance session for an employee.
        An open session has check_in_time != NULL and check_out_time == NULL.
        """
        stmt = (
            select(Attendance)
            .where(
                and_(
                    Attendance.employee_id == employee_id,
                    Attendance.check_in_time.isnot(None),
                    Attendance.check_out_time.is_(None)
                )
            )
            .order_by(desc(Attendance.id))
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def get_latest_session_today(
        session: AsyncSession,
        employee_id: int,
        date_str: Optional[str] = None
    ) -> Optional[Attendance]:
        """Returns the most recent attendance session for an employee on a given date."""
        target_date = date_str or AttendanceRepository.get_today_date_str()
        stmt = (
            select(Attendance)
            .where(
                and_(
                    Attendance.employee_id == employee_id,
                    Attendance.date == target_date
                )
            )
            .order_by(desc(Attendance.id))
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def list_sessions_for_employee_date(
        session: AsyncSession,
        employee_id: int,
        date_str: str
    ) -> List[Attendance]:
        """Returns all sessions for an employee on a given date in chronological order."""
        stmt = (
            select(Attendance)
            .where(
                and_(
                    Attendance.employee_id == employee_id,
                    Attendance.date == date_str
                )
            )
            .order_by(Attendance.id.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def calculate_duration_minutes(check_in_str: Optional[str], check_out_str: Optional[str]) -> int:
        """Calculates working duration in total minutes between two 12-hour time strings."""
        if not check_in_str or not check_out_str:
            return 0
        try:
            t1 = datetime.strptime(check_in_str.strip(), "%I:%M %p")
            t2 = datetime.strptime(check_out_str.strip(), "%I:%M %p")
            diff = (t2 - t1).total_seconds()
            if diff < 0:
                diff += 24 * 3600  # Cross midnight
            return max(0, int(diff // 60))
        except Exception:
            return 0

    @staticmethod
    def format_duration(total_minutes: int) -> str:
        """Formats integer minutes into a readable duration string (e.g. '7h 15m' or '45m')."""
        if total_minutes <= 0:
            return "0m"
        hours = total_minutes // 60
        mins = total_minutes % 60
        if hours > 0:
            return f"{hours}h {mins:02d}m"
        return f"{mins}m"

    @staticmethod
    def calculate_duration(check_in_str: Optional[str], check_out_str: Optional[str]) -> Optional[str]:
        """Calculates human-readable working duration between check_in_time and check_out_time."""
        if not check_in_str:
            return "Checked Out" if check_out_str else None
        if not check_out_str:
            return "In Progress"
        mins = AttendanceRepository.calculate_duration_minutes(check_in_str, check_out_str)
        return AttendanceRepository.format_duration(mins)

    @staticmethod
    async def mark_check_in(
        session: AsyncSession,
        employee_id: int,
        employee_name: str,
        match_score: float,
        camera_name: str = "Main Entrance"
    ) -> Tuple[Attendance, bool, str]:
        """
        Marks Check-In for an employee.
        State Machine Rule:
          - If the employee currently has an OPEN session:
              Reject check-in, do not create duplicate row.
              Return (open_session, False, 'ALREADY_CHECKED_IN').
          - If the employee does NOT have an open session (even if previous closed sessions exist today):
              Create a BRAND NEW attendance session.
              Return (new_session, True, 'CHECK-IN SUCCESSFUL').
        """
        today_date = AttendanceRepository.get_today_date_str()
        current_time = AttendanceRepository.get_current_time_str()

        # Check for active OPEN session
        open_session = await AttendanceRepository.get_open_session(session, employee_id)
        if open_session:
            logger.info(
                f"Check-In debounced: {employee_name} (ID {employee_id}) already has an OPEN session "
                f"(Session #{open_session.id} started at {open_session.check_in_time})"
            )
            return open_session, False, "ALREADY_CHECKED_IN"

        # No open session -> Create a NEW session row
        new_session = Attendance(
            employee_id=employee_id,
            employee_name=employee_name,
            date=today_date,
            time=current_time,
            status="In Progress",
            match_score=round(float(match_score), 3),
            check_in_time=current_time,
            check_out_time=None,
            check_in_camera=camera_name,
            check_out_camera=None
        )
        # Automatically sync with access_events for real-time dashboard telemetry, analytics & entry logs
        access_event = AccessEvent(
            person_id=employee_id,
            recognized_name=employee_name,
            timestamp=datetime.now(),
            confidence=round(float(match_score), 3),
            status="authorized",
            authorization_result="granted",
            camera_id=camera_name or "Check-In"
        )
        try:
            session.add(new_session)
            session.add(access_event)
            await session.commit()
            await session.refresh(new_session)
            logger.info(
                f"CHECK-IN SUCCESSFUL (New Session #{new_session.id}): "
                f"{employee_name} at {current_time} via {camera_name}"
            )
            return new_session, True, "CHECK-IN SUCCESSFUL"
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to create check-in session for {employee_name}: {e}", exc_info=True)
            raise

    @staticmethod
    async def mark_check_out(
        session: AsyncSession,
        employee_id: int,
        employee_name: str,
        match_score: float,
        camera_name: str = "Main Exit"
    ) -> Tuple[Optional[Attendance], bool, str]:
        """
        Marks Check-Out for an employee.
        State Machine Rule:
          - If an OPEN session exists for this employee:
              Set check_out_time = current_time, compute duration, mark session CLOSED ('Completed').
              Return (open_session, True, 'CHECK-OUT SUCCESSFUL').
          - If NO open session exists:
              Do NOT create a fake/ghost check-out record.
              Return (None, False, 'NO_CHECK_IN_FOUND').
        """
        current_time = AttendanceRepository.get_current_time_str()

        open_session = await AttendanceRepository.get_open_session(session, employee_id)
        if not open_session:
            logger.info(f"Check-Out rejected: {employee_name} (ID {employee_id}) has no open check-in session")
            return None, False, "NO_CHECK_IN_FOUND"

        open_session.check_out_time = current_time
        open_session.check_out_camera = camera_name
        open_session.status = "Completed"

        # Automatically sync with access_events for real-time dashboard telemetry, analytics & entry logs
        access_event = AccessEvent(
            person_id=employee_id,
            recognized_name=employee_name,
            timestamp=datetime.now(),
            confidence=round(float(match_score), 3),
            status="authorized",
            authorization_result="granted",
            camera_id=camera_name or "Check-Out"
        )
        try:
            session.add(access_event)
            await session.commit()
            await session.refresh(open_session)
            dur = AttendanceRepository.calculate_duration(open_session.check_in_time, open_session.check_out_time)
            logger.info(
                f"CHECK-OUT SUCCESSFUL (Closed Session #{open_session.id}): "
                f"{employee_name} at {current_time} via {camera_name} (Duration: {dur})"
            )
            return open_session, True, "CHECK-OUT SUCCESSFUL"
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to close check-out session for {employee_name}: {e}", exc_info=True)
            raise

    @staticmethod
    async def mark_attendance(
        session: AsyncSession,
        employee_id: int,
        employee_name: str,
        match_score: float,
        status: str = "Present",
        camera_name: str = "Webcam"
    ) -> Tuple[Attendance, bool]:
        """
        Compatibility method for manual/webcam attendance.
        Delegates to mark_check_in.
        """
        record, is_new, _ = await AttendanceRepository.mark_check_in(
            session=session,
            employee_id=employee_id,
            employee_name=employee_name,
            match_score=match_score,
            camera_name=camera_name
        )
        return record, is_new

    @staticmethod
    async def process_rtsp_attendance(
        session: AsyncSession,
        employee_id: int,
        employee_name: str,
        match_score: float,
        camera_name: str = "RTSP Camera",
        camera_mode: str = "COMBINED",
        cooldown_seconds: int = 60
    ) -> Tuple[Optional[Attendance], bool, str]:
        """
        Unified RTSP Attendance Automation:
        - Mode CHECK-IN: Creates new session if no open session exists; debounces if already open.
        - Mode CHECK-OUT: Closes active open session; rejects if no open session exists.
        - Mode COMBINED: Automatically checks in if no open session; checks out if open session exists and cooldown elapsed.
        """
        mode = camera_mode.upper() if camera_mode else "COMBINED"

        if mode == "CHECK-IN":
            return await AttendanceRepository.mark_check_in(
                session, employee_id, employee_name, match_score, camera_name
            )

        elif mode == "CHECK-OUT":
            return await AttendanceRepository.mark_check_out(
                session, employee_id, employee_name, match_score, camera_name
            )

        else:  # COMBINED / AUTO
            open_session = await AttendanceRepository.get_open_session(session, employee_id)
            if not open_session:
                return await AttendanceRepository.mark_check_in(
                    session, employee_id, employee_name, match_score, camera_name
                )
            else:
                # Open session exists: enforce cooldown to avoid immediate check-out on consecutive frames
                if open_session.created_at and cooldown_seconds > 0:
                    now_utc = datetime.utcnow()
                    created_naive = open_session.created_at.replace(tzinfo=None) if open_session.created_at.tzinfo else open_session.created_at
                    elapsed = (now_utc - created_naive).total_seconds()
                    if elapsed < cooldown_seconds:
                        logger.info(
                            f"RTSP Check-In grace period active for {employee_name} "
                            f"(checked in {int(elapsed)}s ago). Immediate check-out suppressed."
                        )
                        return open_session, False, "ALREADY_CHECKED_IN"

                return await AttendanceRepository.mark_check_out(
                    session, employee_id, employee_name, match_score, camera_name
                )

    @staticmethod
    def to_dict(record: Attendance) -> dict:
        """Helper to serialize an individual attendance session record."""
        return {
            "id": record.id,
            "employee_id": record.employee_id,
            "employee_name": record.employee_name,
            "date": record.date,
            "time": record.time,
            "status": record.status,
            "match_score": record.match_score,
            "check_in_time": record.check_in_time,
            "check_out_time": record.check_out_time,
            "duration": AttendanceRepository.calculate_duration(record.check_in_time, record.check_out_time),
            "check_in_camera": record.check_in_camera,
            "check_out_camera": record.check_out_camera,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    @staticmethod
    async def list_today(session: AsyncSession) -> List[Attendance]:
        """Fetch all attendance records for today ordered from newest to oldest."""
        today_date = AttendanceRepository.get_today_date_str()
        stmt = (
            select(Attendance)
            .where(Attendance.date == today_date)
            .order_by(desc(Attendance.id))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_date(session: AsyncSession, date_str: str) -> List[Attendance]:
        """Fetch all attendance records for a specific date (DD-MM-YYYY)."""
        stmt = (
            select(Attendance)
            .where(Attendance.date == date_str)
            .order_by(desc(Attendance.id))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_history(session: AsyncSession, limit: int = 100) -> List[Attendance]:
        """Fetch recent attendance records."""
        stmt = (
            select(Attendance)
            .order_by(desc(Attendance.id))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_daily_summaries(
        session: AsyncSession,
        date_str: str
    ) -> List[Dict[str, Any]]:
        """
        Aggregates attendance sessions by employee for a specific date.
        Returns a list of employee daily summary dictionaries:
          - employee_id, employee_name
          - current_status: 'CHECKED IN' if currently in an open session, else 'CHECKED OUT'
          - first_check_in: earliest check-in time of the day
          - last_check_out: latest check-out time of the day (or None if currently checked in)
          - total_worked_minutes: sum of completed session durations (plus current session elapsed if open)
          - total_worked_duration: human readable string (e.g. '7h 15m')
          - session_count: total sessions today
          - sessions: list of individual session dicts
        """
        # Fetch all records for the date ordered chronologically
        stmt = (
            select(Attendance)
            .where(Attendance.date == date_str)
            .order_by(Attendance.employee_id.asc(), Attendance.id.asc())
        )
        result = await session.execute(stmt)
        all_records = list(result.scalars().all())

        # Group by employee_id
        grouped: Dict[int, List[Attendance]] = {}
        for r in all_records:
            if r.employee_id not in grouped:
                grouped[r.employee_id] = []
            grouped[r.employee_id].append(r)

        summaries = []
        now_time_str = AttendanceRepository.get_current_time_str()
        is_today = (date_str == AttendanceRepository.get_today_date_str())

        for emp_id, records in grouped.items():
            emp_name = records[0].employee_name
            session_dicts = [AttendanceRepository.to_dict(r) for r in records]

            # Find if there is an active open session
            open_sess = next((r for r in records if r.check_in_time and not r.check_out_time), None)
            current_status = "CHECKED IN" if open_sess is not None else "CHECKED OUT"

            first_check_in = records[0].check_in_time
            # Last checkout is from the last closed session
            closed_sessions = [r for r in records if r.check_out_time]
            last_check_out = closed_sessions[-1].check_out_time if closed_sessions else None

            # Sum durations
            total_minutes = 0
            for r in records:
                if r.check_in_time and r.check_out_time:
                    total_minutes += AttendanceRepository.calculate_duration_minutes(r.check_in_time, r.check_out_time)
                elif r.check_in_time and is_today:
                    # Ongoing session: add elapsed minutes up to now
                    total_minutes += AttendanceRepository.calculate_duration_minutes(r.check_in_time, now_time_str)

            summaries.append({
                "employee_id": emp_id,
                "employee_name": emp_name,
                "date": date_str,
                "current_status": current_status,
                "first_check_in": first_check_in,
                "last_check_out": last_check_out,
                "total_worked_minutes": total_minutes,
                "total_worked_duration": AttendanceRepository.format_duration(total_minutes),
                "session_count": len(records),
                "active_session_id": open_sess.id if open_sess else None,
                "current_check_in": open_sess.check_in_time if open_sess else None,
                "sessions": session_dicts
            })

        return summaries
