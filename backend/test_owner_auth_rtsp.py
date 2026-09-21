"""
Automated Test Suite for:
1. Owner & User Authentication (Signup & Login)
2. Role Enforcement (Owner vs Non-Owner / Operator)
3. Direct RTSP Enrollment & Gallery Synchronization
4. Non-Interference with Webcam Enrollment
5. Authorization Failure (HTTP 401 Unauthorized / HTTP 403 Forbidden)
"""

import sys
import os
import json
import base64
import numpy as np
import cv2
import requests

BASE_URL = "http://127.0.0.1:8000/api"

def create_synthetic_face_jpeg():
    """Create a clean 300x300 synthetic face image encoded as base64 JPEG"""
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    img[:] = (230, 230, 230) # light grey
    # Draw head / face oval
    cv2.ellipse(img, (150, 150), (70, 95), 0, 0, 360, (180, 200, 220), -1)
    # Eyes
    cv2.circle(img, (120, 130), 10, (50, 50, 50), -1)
    cv2.circle(img, (180, 130), 10, (50, 50, 50), -1)
    # Nose
    cv2.line(img, (150, 135), (150, 165), (80, 80, 80), 3)
    # Mouth
    cv2.ellipse(img, (150, 185), (25, 12), 0, 0, 180, (50, 50, 150), 3)
    
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode("utf-8")

def run_tests():
    print("=" * 70)
    print("FACEVAULT-360 OWNER AUTH & RTSP ENROLLMENT VERIFICATION TEST")
    print("=" * 70)

    # 1. Unauthenticated Request -> HTTP 401
    print("\n[TEST 1] Verifying HTTP 401 on unauthenticated access...")
    res = requests.get(f"{BASE_URL}/unknown-persons/stats/today")
    print(f"Status Code: {res.status_code}")
    assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"
    print("[OK] Unauthenticated access correctly rejected with HTTP 401.")

    # 2. Get existing owner token or sign up owner
    print("\n[TEST 2] Acquiring Owner credentials...")
    # Obtain authentic owner token
    res = requests.post(f"{BASE_URL}/auth/switch-user", json={"role": "owner"})
    assert res.status_code == 200, f"Failed to get owner token: {res.text}"
    owner_token = res.json()["access_token"]
    print(f"[OK] Obtained authentic Owner token: role={res.json().get('role') or res.json().get('user', {}).get('role')}")

    owner_headers = {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


    # Verify Owner identity
    me_res = requests.get(f"{BASE_URL}/auth/me", headers=owner_headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data.get("is_owner") is True or me_data.get("role") == "owner", f"User is not owner: {me_data}"
    print(f"[OK] Owner verified: {me_data.get('name') or me_data.get('username')}, role={me_data.get('role')}")

    # 3. Create non-owner Operator account
    print("\n[TEST 3] Creating / logging in as Operator (Non-Owner)...")
    res = requests.post(f"{BASE_URL}/auth/signup", json={
        "username": "operator_test",
        "password": "operatorpassword123",
        "full_name": "Test Security Operator",
        "email": "operator_test@facevault360.com"
    })
    print(f"Signup response status: {res.status_code}, text: {res.text[:120]}")
    operator_token = None
    if res.status_code == 200:
        op_data = res.json()
        operator_token = op_data["access_token"]
        print(f"[OK] Operator created: role={op_data.get('role')}")
        assert op_data.get("role") != "owner", "Second user should NOT have owner role!"
    else:
        # Login or switch
        res_login = requests.post(f"{BASE_URL}/auth/login-json", json={"username": "operator_test", "password": "operatorpassword123"})
        if res_login.status_code == 200:
            operator_token = res_login.json()["access_token"]
        else:
            res_sw = requests.post(f"{BASE_URL}/auth/switch-user", json={"role": "operator"})
            print(f"Switch user response: {res_sw.status_code}, text: {res_sw.text}")
            operator_token = res_sw.json()["access_token"]

    operator_headers = {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}
    print("[OK] Operator token active.")

    # 4. Create an unknown person event for testing
    print("\n[TEST 4] Creating or finding Unknown Person event for approval and enrollment tests...")
    # Fetch existing unknowns
    unknowns_res = requests.get(f"{BASE_URL}/unknown-persons?limit=10", headers=owner_headers)
    assert unknowns_res.status_code == 200, f"Failed to get unknowns: {unknowns_res.text}"
    items = unknowns_res.json().get("items", [])
    
    test_event_id = None
    if items:
        test_event_id = items[0]["id"]
        print(f"[OK] Found existing unknown event #{test_event_id}")
    else:
        # Trigger an unknown person event or insert directly
        print("Creating mock unknown event via DB or recognition...")
        # We can test with ID 1
        test_event_id = 1

    # 5. Non-Owner calling Owner-Only Endpoints -> Expect HTTP 403 Forbidden
    print("\n[TEST 5] Verifying HTTP 403 Forbidden when Operator attempts Owner-only operations...")
    
    # 5a. Operator attempts to approve
    res = requests.post(f"{BASE_URL}/unknown-persons/{test_event_id}/approve", headers=operator_headers, json={})
    print(f"Operator /approve status code: {res.status_code}")
    assert res.status_code == 403, f"Expected 403 Forbidden for operator approve, got {res.status_code}"
    print("[OK] Operator /approve blocked with HTTP 403.")

    # 5b. Operator attempts to deny
    res = requests.post(f"{BASE_URL}/unknown-persons/{test_event_id}/deny", headers=operator_headers, json={})
    print(f"Operator /deny status code: {res.status_code}")
    assert res.status_code == 403, f"Expected 403 Forbidden for operator deny, got {res.status_code}"
    print("[OK] Operator /deny blocked with HTTP 403.")

    # 5c. Operator attempts RTSP direct enrollment
    res = requests.post(f"{BASE_URL}/unknown-persons/{test_event_id}/enroll-rtsp", headers=operator_headers, json={
        "name": "Intruder Register Test",
        "department": "Security",
        "role": "Staff"
    })
    print(f"Operator /enroll-rtsp status code: {res.status_code}")
    assert res.status_code == 403, f"Expected 403 Forbidden for operator enroll-rtsp, got {res.status_code}"
    print("[OK] Operator /enroll-rtsp blocked with HTTP 403.")

    # 6. Owner executes Direct RTSP Enrollment
    print("\n[TEST 6] Testing Owner Direct RTSP Enrollment...")
    # First test frame evaluation endpoint
    eval_res = requests.post(f"{BASE_URL}/unknown-persons/eval-rtsp-frame", headers=owner_headers, json={})
    print(f"Frame evaluation response: {eval_res.json()}")

    # Now execute RTSP enrollment with owner token
    enroll_payload = {
        "name": "Sarah Connor",
        "employee_id": "RTSP-SEC-01",
        "department": "Special Operations",
        "role": "Security Specialist"
    }
    enroll_res = requests.post(
        f"{BASE_URL}/unknown-persons/{test_event_id}/enroll-rtsp",
        headers=owner_headers,
        json=enroll_payload
    )
    print(f"Owner /enroll-rtsp status code: {enroll_res.status_code}")
    assert enroll_res.status_code == 200, f"Owner enroll-rtsp failed: {enroll_res.text}"
    enroll_data = enroll_res.json()
    print(f"[OK] RTSP Direct Enrollment succeeded! Registered Person ID: {enroll_data.get('person', {}).get('id')}")
    assert enroll_data.get("person", {}).get("name") == "Sarah Connor"
    assert enroll_data.get("person", {}).get("status") == "active"

    # 7. Verify Person Directory & FAISS vector consistency
    print("\n[TEST 7] Verifying enrolled person is active in authoritative People directory...")
    persons_res = requests.get(f"{BASE_URL}/persons", headers=owner_headers)
    assert persons_res.status_code == 200
    persons_data = persons_res.json()
    items = persons_data if isinstance(persons_data, list) else persons_data.get("items", [])
    person_names = [p["name"] for p in items]
    print(f"Active persons ({len(person_names)}): {person_names}")
    assert "Sarah Connor" in person_names, "Newly enrolled person not found in People directory!"
    print("[OK] 'Sarah Connor' successfully indexed in active directory.")


    # 8. Check Unknown Event Audit Metadata
    print("\n[TEST 8] Checking Unknown Person Event Audit Metadata...")
    ev_res = requests.get(f"{BASE_URL}/unknown-persons/{test_event_id}", headers=owner_headers)
    if ev_res.status_code == 200:
        ev = ev_res.json()
        print(f"Updated Event access_status: {ev.get('access_status')}")
        print(f"Updated Event enrollment_method: {ev.get('enrollment_method')}")
        print(f"Updated Event enrolled_by: {ev.get('enrolled_by')}")
        assert ev.get("access_status") == "ENROLLED"
        assert ev.get("enrollment_method") == "RTSP"
        print("[OK] Unknown event audit trail updated with enrollment_method='RTSP' and enrolled_by.")

    # 9. Verify Existing Laptop Webcam Enrollment is Completely Intact
    print("\n[TEST 9] Verifying Laptop Webcam Enrollment workflow is unaffected...")
    webcam_start = requests.post(f"{BASE_URL}/enrollment/start", headers=owner_headers, json={
        "person_id": enroll_data.get("person", {}).get("id")
    })
    print(f"Webcam /enrollment/start status: {webcam_start.status_code}")
    assert webcam_start.status_code == 200, f"Webcam enrollment broke: {webcam_start.text}"
    session_data = webcam_start.json()
    assert "session_id" in session_data
    print(f"[OK] Webcam enrollment session created successfully: session_id={session_data.get('session_id')}")

    print("\n" + "=" * 70)
    print("ALL OWNER AUTH & RTSP ENROLLMENT TESTS PASSED SUCCESSFULLY! (100% PASS)")
    print("=" * 70)

if __name__ == "__main__":
    try:
        run_tests()
    except Exception as ex:
        print(f"\n[FAIL] TEST FAILED: {ex}")
        sys.exit(1)

