import asyncio
import os
import sys
import time
import requests

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.db.database import AsyncSessionLocal, init_db
from app.core.security import create_access_token
from app.db.repositories.unknown_repo import UnknownPersonRepository

BASE_URL = "http://127.0.0.1:8000"

async def setup_test_data():
    await init_db()
    async with AsyncSessionLocal() as session:
        import uuid
        event = await UnknownPersonRepository.create_event(
            session=session,
            event_uuid=str(uuid.uuid4()),
            date_str="2026-09-18",
            time_str="02:30:00 PM",
            camera_name="Check-In Camera",
            camera_role="CHECK-IN",
            snapshot_path="data/unknown_snapshots/test.jpg",
            snapshot_url="/api/unknown-persons/snapshots/test.jpg",
            face_confidence=0.85
        )
        return event.id

def test_security():
    # Wait for backend to be ready
    for _ in range(10):
        try:
            r = requests.get(f"{BASE_URL}/", timeout=2)
            if r.status_code == 200:
                print("Backend server is healthy and responding.")
                break
        except Exception:
            time.sleep(1)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    event_id = loop.run_until_complete(setup_test_data())
    print(f"Created test UnknownPersonEvent ID: {event_id}")

    # Generate tokens:
    # 1. Owner token (Syed Raza Abbas, role: owner)
    owner_token = create_access_token(data={"sub": "owner@facevault.local", "name": "Syed Raza Abbas", "role": "owner", "user_id": 1})
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # 2. Staff token (usman, role: staff)
    staff_token = create_access_token(data={"sub": "usman@facevault.local", "name": "usman", "role": "staff", "user_id": 3})
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    # 3. Read list of unknown persons (both owner and staff can read)
    resp = requests.get(f"{BASE_URL}/api/unknown-persons", headers=staff_headers)
    assert resp.status_code == 200, f"Staff reading unknowns failed: {resp.status_code} {resp.text}"
    print(f"[PASS] Staff can view unknown persons list (200 OK, total items: {resp.json().get('total')})")

    # 4. Read today stats
    resp = requests.get(f"{BASE_URL}/api/unknown-persons/stats/today", headers=staff_headers)
    assert resp.status_code == 200, f"Stats failed: {resp.status_code}"
    print(f"[PASS] Unknown persons stats today: {resp.json()}")

    # 5. Non-Owner attempts to APPROVE unknown person -> MUST RETURN 403 FORBIDDEN
    resp = requests.post(f"{BASE_URL}/api/unknown-persons/{event_id}/approve", headers=staff_headers)
    assert resp.status_code == 403, f"Expected 403 Forbidden for staff approve, got {resp.status_code}: {resp.text}"
    print("[PASS] Non-owner (staff) approve blocked with 403 Forbidden as required!")

    # 6. Non-Owner attempts to DENY unknown person -> MUST RETURN 403 FORBIDDEN
    resp = requests.post(f"{BASE_URL}/api/unknown-persons/{event_id}/deny", headers=staff_headers)
    assert resp.status_code == 403, f"Expected 403 Forbidden for staff deny, got {resp.status_code}: {resp.text}"
    print("[PASS] Non-owner (staff) deny blocked with 403 Forbidden as required!")

    # 7. Non-Owner attempts to DELETE unknown person -> MUST RETURN 403 FORBIDDEN
    resp = requests.delete(f"{BASE_URL}/api/unknown-persons/{event_id}", headers=staff_headers)
    assert resp.status_code == 403, f"Expected 403 Forbidden for staff delete, got {resp.status_code}: {resp.text}"
    print("[PASS] Non-owner (staff) delete unknown blocked with 403 Forbidden as required!")

    # 8. Non-Owner attempts to DELETE a person -> MUST RETURN 403 FORBIDDEN
    resp = requests.delete(f"{BASE_URL}/api/persons/99999", headers=staff_headers)
    assert resp.status_code == 403, f"Expected 403 Forbidden for staff delete person, got {resp.status_code}: {resp.text}"
    print("[PASS] Non-owner (staff) delete person blocked with 403 Forbidden as required!")

    # 9. OWNER approves unknown person -> MUST SUCCEED (200 OK)
    resp = requests.post(f"{BASE_URL}/api/unknown-persons/{event_id}/approve", headers=owner_headers)
    assert resp.status_code == 200, f"Owner approve failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["access_status"] == "APPROVED"
    assert data["approved_by_name"] == "Syed Raza Abbas"
    print("[PASS] Owner approve succeeded (200 OK, status: APPROVED, approved_by: Syed Raza Abbas)")

    # 10. OWNER denies unknown person -> MUST SUCCEED (200 OK)
    resp = requests.post(f"{BASE_URL}/api/unknown-persons/{event_id}/deny", headers=owner_headers)
    assert resp.status_code == 200, f"Owner deny failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["access_status"] == "DENIED"
    print("[PASS] Owner deny succeeded (200 OK, status: DENIED)")

    # 11. OWNER deletes unknown person -> MUST SUCCEED (200 OK)
    resp = requests.delete(f"{BASE_URL}/api/unknown-persons/{event_id}", headers=owner_headers)
    assert resp.status_code == 200, f"Owner delete failed: {resp.status_code} {resp.text}"
    print("[PASS] Owner delete unknown succeeded (200 OK)")

    print("\n========================================================")
    print("ALL BACKEND SECURITY & WORKFLOW TESTS PASSED PERFECTLY!")
    print("========================================================")

if __name__ == "__main__":
    test_security()
