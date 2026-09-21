import asyncio
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import AsyncSessionLocal
from app.db.repositories.attendance_repo import AttendanceRepository
from app.db.repositories.person_repo import PersonRepository

async def run_tests():
    print("=== STARTING MULTI-SESSION ATTENDANCE VERIFICATION ===")
    async with AsyncSessionLocal() as session:
        # Get an active person
        persons, total = await PersonRepository.list_all(session)
        if not persons:
            print("ERROR: No persons found in DB!")
            return
        test_person = persons[0]
        emp_id = test_person.id
        emp_name = test_person.name
        print(f"Testing with Employee: {emp_name} (ID: {emp_id})")

        today_date = AttendanceRepository.get_today_date_str()

        # Step 0: Ensure no dangling open session for a clean test
        open_sess = await AttendanceRepository.get_open_session(session, emp_id)
        if open_sess:
            print(f"Closing dangling open session #{open_sess.id} before test...")
            open_sess.check_out_time = "08:50 AM"
            open_sess.status = "Completed"
            await session.commit()

        # TEST 1: First Check-In (e.g. 09:00 AM)
        print("\n--- TEST 1: Initial Check-In ---")
        sess1, is_new, msg = await AttendanceRepository.mark_check_in(
            session, emp_id, emp_name, match_score=0.92, camera_name="Entrance Gate"
        )
        assert is_new is True, "First check-in should create a new session"
        assert sess1.check_in_time is not None, "Check-in time must be set"
        assert sess1.check_out_time is None, "Check-out time must be None"
        print(f"PASS: Session #{sess1.id} created at {sess1.check_in_time} (Status: {sess1.status})")

        # TEST 2: Second Check-In without Check-Out (should debounce)
        print("\n--- TEST 2: Repeated Check-In without Check-Out ---")
        sess1_dup, is_new_dup, msg_dup = await AttendanceRepository.mark_check_in(
            session, emp_id, emp_name, match_score=0.88, camera_name="Entrance Gate"
        )
        assert is_new_dup is False, "Repeated check-in should NOT create a new session"
        assert sess1_dup.id == sess1.id, "Should return existing open session"
        assert msg_dup == "ALREADY_CHECKED_IN", "Message should be ALREADY_CHECKED_IN"
        print(f"PASS: Repeated check-in debounced as expected ({msg_dup})")

        # TEST 3: Check-Out from Session 1
        print("\n--- TEST 3: Check-Out Session 1 ---")
        sess1_out, is_closed, msg_out = await AttendanceRepository.mark_check_out(
            session, emp_id, emp_name, match_score=0.91, camera_name="Exit Gate"
        )
        assert is_closed is True, "Check-out should succeed"
        assert sess1_out.id == sess1.id, "Must close session 1"
        assert sess1_out.check_out_time is not None, "Check-out time must be set"
        assert sess1_out.status == "Completed", "Status must be Completed"
        print(f"PASS: Session #{sess1_out.id} closed at {sess1_out.check_out_time} (Duration: {AttendanceRepository.calculate_duration(sess1_out.check_in_time, sess1_out.check_out_time)})")

        # Verify no open session now exists
        open_check = await AttendanceRepository.get_open_session(session, emp_id)
        assert open_check is None, "There should be NO open session after check-out"
        print("PASS: Verified no open session exists after check-out")

        # TEST 4: Check-In AGAIN on the SAME DAY (Session 2)
        print("\n--- TEST 4: Second Check-In on SAME DAY (Session 2) ---")
        sess2, is_new2, msg2 = await AttendanceRepository.mark_check_in(
            session, emp_id, emp_name, match_score=0.95, camera_name="Entrance Gate"
        )
        assert is_new2 is True, "Second check-in MUST create a new session"
        assert sess2.id != sess1.id, "Session 2 ID must be different from Session 1"
        assert sess2.check_in_time is not None, "Check-in time must be set"
        assert sess2.check_out_time is None, "Check-out time must be None"
        print(f"PASS: Brand new Session #{sess2.id} created at {sess2.check_in_time} (Status: {sess2.status})")

        # Verify open session is Session 2
        open_check2 = await AttendanceRepository.get_open_session(session, emp_id)
        assert open_check2 is not None and open_check2.id == sess2.id, "Open session must be Session 2"
        print(f"PASS: Active open session verified as Session #{open_check2.id}")

        # TEST 5: Check-Out Session 2
        print("\n--- TEST 5: Check-Out Session 2 ---")
        sess2_out, is_closed2, msg_out2 = await AttendanceRepository.mark_check_out(
            session, emp_id, emp_name, match_score=0.93, camera_name="Exit Gate"
        )
        assert is_closed2 is True, "Check-out 2 should succeed"
        assert sess2_out.id == sess2.id, "Must close session 2"
        print(f"PASS: Session #{sess2_out.id} closed at {sess2_out.check_out_time}")

        # TEST 6: Check-Out with NO open session
        print("\n--- TEST 6: Check-Out when NO open session exists ---")
        no_sess, no_closed, no_msg = await AttendanceRepository.mark_check_out(
            session, emp_id, emp_name, match_score=0.90, camera_name="Exit Gate"
        )
        assert no_sess is None, "No session should be modified"
        assert no_closed is False, "Should report false"
        assert no_msg == "NO_CHECK_IN_FOUND", "Should report NO_CHECK_IN_FOUND"
        print(f"PASS: Reject check-out when no open session ({no_msg})")

        # TEST 7: Check-In Session 3
        print("\n--- TEST 7: Third Check-In on SAME DAY (Session 3) ---")
        sess3, is_new3, msg3 = await AttendanceRepository.mark_check_in(
            session, emp_id, emp_name, match_score=0.94, camera_name="Entrance Gate"
        )
        assert is_new3 is True, "Session 3 should be created"
        print(f"PASS: Session #{sess3.id} created (currently OPEN)")

        # TEST 8: Daily Summary Calculation
        print("\n--- TEST 8: Daily Attendance Summary Aggregation ---")
        summaries = await AttendanceRepository.get_daily_summaries(session, today_date)
        emp_summary = next((s for s in summaries if s["employee_id"] == emp_id), None)
        assert emp_summary is not None, "Summary for employee must exist"
        print(f"Summary for {emp_summary['employee_name']}:")
        print(f" - Date: {emp_summary['date']}")
        print(f" - Current Status: {emp_summary['current_status']}")
        print(f" - First Check-In: {emp_summary['first_check_in']}")
        print(f" - Last Check-Out: {emp_summary['last_check_out']}")
        print(f" - Total Sessions Today: {emp_summary['session_count']}")
        print(f" - Total Worked Duration: {emp_summary['total_worked_duration']}")
        print(f" - Active Session ID: {emp_summary['active_session_id']}")
        assert emp_summary["current_status"] == "CHECKED IN", "Current status must be CHECKED IN because Session 3 is open"
        assert emp_summary["session_count"] >= 3, "Must have at least 3 sessions today"

        # Now close Session 3
        sess3_out, _, _ = await AttendanceRepository.mark_check_out(session, emp_id, emp_name, 0.90)
        summaries_after = await AttendanceRepository.get_daily_summaries(session, today_date)
        emp_summary_after = next((s for s in summaries_after if s["employee_id"] == emp_id), None)
        assert emp_summary_after["current_status"] == "CHECKED OUT", "Current status must become CHECKED OUT"
        print(f"PASS: Status successfully switched to {emp_summary_after['current_status']} after closing Session 3")

        print("\n=== ALL MULTI-SESSION TESTS PASSED PERFECTLY! ===")

if __name__ == "__main__":
    asyncio.run(run_tests())
