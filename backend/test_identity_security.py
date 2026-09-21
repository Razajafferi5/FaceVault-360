import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"

def log_result(test_name, passed, details=""):
    badge = "[PASS]" if passed else "[FAIL]"
    print(f"{badge} {test_name} {details}")
    if not passed:
        sys.exit(1)

def run_tests():
    print("==================================================")
    print("STARTING FACEVAULT 360 IDENTITY & SECURITY AUDIT")
    print("==================================================")

    # 1. Test Owner Login
    res = requests.post(f"{BASE_URL}/api/auth/login-json", json={
        "username": "owner",
        "password": "ownerpassword123"
    })
    log_result("Owner Login JSON", res.status_code == 200, f"status={res.status_code}")
    owner_data = res.json()
    owner_token = owner_data["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    
    log_result("Owner Role in Login Response", owner_data["role"] == "owner", f"role={owner_data.get('role')}")
    log_result("Owner is_owner flag", owner_data.get("is_owner") is True)
    
    # Verify Owner /api/auth/me
    res_me = requests.get(f"{BASE_URL}/api/auth/me", headers=owner_headers)
    log_result("Owner /api/auth/me status", res_me.status_code == 200)
    me_data = res_me.json()
    log_result("Owner /api/auth/me Role is 'owner'", me_data.get("role") == "owner", f"role={me_data.get('role')}")
    log_result("Owner /api/auth/me is NOT Usman", me_data.get("name") != "usman", f"name={me_data.get('name')}")
    log_result("Owner /api/auth/me is NOT Rabia", me_data.get("name") != "rabia", f"name={me_data.get('name')}")
    print(f"   -> Authenticated Owner verified: Name='{me_data.get('name')}', Role='{me_data.get('role')}'")

    # 2. Test Usman Staff Login
    res_usman = requests.post(f"{BASE_URL}/api/auth/login-json", json={
        "username": "usman",
        "password": "usman123"
    })
    log_result("Usman Staff Login JSON", res_usman.status_code == 200, f"status={res_usman.status_code}")
    usman_data = res_usman.json()
    usman_token = usman_data["access_token"]
    usman_headers = {"Authorization": f"Bearer {usman_token}"}
    
    log_result("Usman Role is 'staff'", usman_data["role"] == "staff", f"role={usman_data.get('role')}")
    log_result("Usman is_owner is False", usman_data.get("is_owner") is False)

    res_usman_me = requests.get(f"{BASE_URL}/api/auth/me", headers=usman_headers)
    usman_me_data = res_usman_me.json()
    log_result("Usman /api/auth/me Role is 'staff'", usman_me_data.get("role") == "staff", f"role={usman_me_data.get('role')}")
    log_result("Usman /api/auth/me Name is 'usman'", "usman" in usman_me_data.get("name").lower(), f"name={usman_me_data.get('name')}")
    print(f"   -> Authenticated Staff verified: Name='{usman_me_data.get('name')}', Role='{usman_me_data.get('role')}'")

    # 3. Test Rabia Staff Login
    res_rabia = requests.post(f"{BASE_URL}/api/auth/login-json", json={
        "username": "rabia",
        "password": "rabia123"
    })
    log_result("Rabia Staff Login JSON", res_rabia.status_code == 200, f"status={res_rabia.status_code}")
    rabia_data = res_rabia.json()
    log_result("Rabia Role is 'staff'", rabia_data["role"] == "staff", f"role={rabia_data.get('role')}")

    # 4. Strict Server-Side 403 Forbidden Enforcement for Staff
    print("\n--- Testing Server-Side 403 Forbidden on Privileged Endpoints ---")
    
    # 4a. DELETE /api/persons/{id}
    res_del_person = requests.delete(f"{BASE_URL}/api/persons/9999", headers=usman_headers)
    log_result("Staff DELETE /api/persons/9999 -> 403 Forbidden", res_del_person.status_code == 403, f"got {res_del_person.status_code}")

    # 4b. POST /api/unknown-persons/1/approve
    res_appr = requests.post(f"{BASE_URL}/api/unknown-persons/1/approve", headers=usman_headers)
    log_result("Staff POST /api/unknown-persons/1/approve -> 403 Forbidden", res_appr.status_code == 403, f"got {res_appr.status_code}")

    # 4c. POST /api/cameras
    res_cam = requests.post(f"{BASE_URL}/api/cameras", json={
        "name": "Hacker Cam", "rtsp_url": "rtsp://1.1.1.1"
    }, headers=usman_headers)
    log_result("Staff POST /api/cameras -> 403 Forbidden", res_cam.status_code == 403, f"got {res_cam.status_code}")

    # 4d. POST /api/auth/change-owner
    res_transfer = requests.post(f"{BASE_URL}/api/auth/change-owner", json={
        "target_username": "usman"
    }, headers=usman_headers)
    log_result("Staff POST /api/auth/change-owner -> 403 Forbidden", res_transfer.status_code == 403, f"got {res_transfer.status_code}")

    # 4e. GET /api/attendance/history (Org-wide)
    res_org_att = requests.get(f"{BASE_URL}/api/attendance/history", headers=usman_headers)
    log_result("Staff GET /api/attendance/history -> 403 Forbidden", res_org_att.status_code == 403, f"got {res_org_att.status_code}")

    # 4f. GET /api/attendance/today (Org-wide)
    res_org_today = requests.get(f"{BASE_URL}/api/attendance/today", headers=usman_headers)
    log_result("Staff GET /api/attendance/today -> 403 Forbidden", res_org_today.status_code == 403, f"got {res_org_today.status_code}")

    # 4g. GET /api/auth/audit-logs
    res_audit_staff = requests.get(f"{BASE_URL}/api/auth/audit-logs", headers=usman_headers)
    log_result("Staff GET /api/auth/audit-logs -> 403 Forbidden", res_audit_staff.status_code == 403, f"got {res_audit_staff.status_code}")

    # 5. Staff Personal Attendance Access (Anti-IDOR)
    print("\n--- Testing Staff Personal Attendance Access ---")
    res_my_today = requests.get(f"{BASE_URL}/api/attendance/my-today", headers=usman_headers)
    log_result("Staff GET /api/attendance/my-today -> 200 OK", res_my_today.status_code == 200)
    my_today_data = res_my_today.json()
    log_result("my-today contains employee_id", "employee_id" in my_today_data)
    log_result("my-today contains formatted_duration", "formatted_duration" in my_today_data)
    print(f"   -> Staff Attendance Status: {my_today_data.get('status')}, Duration: {my_today_data.get('formatted_duration')}")

    res_my_hist = requests.get(f"{BASE_URL}/api/attendance/my-history", headers=usman_headers)
    log_result("Staff GET /api/attendance/my-history -> 200 OK", res_my_hist.status_code == 200)

    # 6. Owner Privileged Operations
    print("\n--- Testing Owner Privileged Operations ---")
    res_owner_today = requests.get(f"{BASE_URL}/api/attendance/today", headers=owner_headers)
    log_result("Owner GET /api/attendance/today -> 200 OK", res_owner_today.status_code == 200)

    res_owner_audit = requests.get(f"{BASE_URL}/api/auth/audit-logs", headers=owner_headers)
    log_result("Owner GET /api/auth/audit-logs -> 200 OK", res_owner_audit.status_code == 200)
    audit_data = res_owner_audit.json()
    log_result("Owner receives audit logs list", "logs" in audit_data)

    print("\n==================================================")
    print("ALL IDENTITY AND AUTHORIZATION CHECKS PASSED 100%!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()

