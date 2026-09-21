import time
import numpy as np
import requests
from app.services.face_quality import FaceQualityChecker
from app.services.face_tracker import FaceTracker

print("=== 1. Testing Face Quality with Distance Awareness ===")
checker = FaceQualityChecker()
frame = np.ones((720, 1280, 3), dtype=np.uint8) * 128
frame[100:300, 100:300] = np.random.randint(50, 200, (200, 200, 3), dtype=np.uint8)

# Test 120px face (close)
res_120 = checker.assess(frame, [100, 100, 120, 120], np.ones((5, 2)))
print(f"120px face: is_acceptable={res_120.is_acceptable}, is_too_small={res_120.is_too_small}, score={res_120.overall_score:.2f}, guidance={res_120.guidance_message}")

# Test 60px face (medium distance)
res_60 = checker.assess(frame, [100, 100, 60, 60], np.ones((5, 2)))
print(f"60px face: is_acceptable={res_60.is_acceptable}, is_too_small={res_60.is_too_small}, score={res_60.overall_score:.2f}, guidance={res_60.guidance_message}")

# Test 40px face (far distance)
res_40 = checker.assess(frame, [100, 100, 40, 40], np.ones((5, 2)))
print(f"40px face: is_acceptable={res_40.is_acceptable}, is_too_small={res_40.is_too_small}, score={res_40.overall_score:.2f}, guidance={res_40.guidance_message}")

# Test 25px face (genuinely too small)
res_25 = checker.assess(frame, [100, 100, 25, 25], np.ones((5, 2)))
print(f"25px face: is_acceptable={res_25.is_acceptable}, is_too_small={res_25.is_too_small}, score={res_25.overall_score:.2f}, guidance={res_25.guidance_message}")

assert res_120.is_acceptable == True, "120px face should be acceptable"
assert res_60.is_acceptable == True, "60px face should be acceptable"
assert res_40.is_acceptable == True, "40px face should be acceptable at distance"
assert res_25.is_too_small == True, "25px face should be flagged as too small"

print("\n=== 2. Testing FaceTracker Temporal Multi-Frame Confirmation ===")
tracker = FaceTracker(confirmation_frames=2, recognition_hold_time=2.0, unknown_hold_time=1.0)
now = time.time()

# Frame 1: Match 1
f1 = [{'bbox': [100, 100, 60, 60], 'person_id': 1, 'name': 'Syed Raza Abbas', 'similarity': 0.65, 'is_unknown': False, 'status': 'authorized'}]
tracks = tracker.update_from_ai_results(f1, now)
print(f"Frame 1: track state={tracks[0].state}, consecutive={tracks[0].consecutive_matches}, is_confirmed={tracks[0].is_confirmed}")
assert tracks[0].state == "MATCHING", "Frame 1 should be MATCHING"

# Frame 2: Match 2 -> Should Confirm!
now += 0.1
f2 = [{'bbox': [102, 101, 60, 60], 'person_id': 1, 'name': 'Syed Raza Abbas', 'similarity': 0.68, 'is_unknown': False, 'status': 'authorized'}]
tracks = tracker.update_from_ai_results(f2, now)
print(f"Frame 2: track state={tracks[0].state}, consecutive={tracks[0].consecutive_matches}, is_confirmed={tracks[0].is_confirmed}, name={tracks[0].confirmed_name}")
assert tracks[0].state == "CONFIRMED", "Frame 2 should be CONFIRMED"

# Frame 3: Person turns head (momentary non-match / side angle) -> Should stay CONFIRMED via Hold Window!
now += 0.2
f3 = [{'bbox': [103, 102, 60, 60], 'person_id': None, 'name': 'Unknown Person', 'similarity': 0.35, 'is_unknown': True, 'status': 'bad_pose'}]
tracks = tracker.update_from_ai_results(f3, now)
print(f"Frame 3 (turn head): track state={tracks[0].state}, is_confirmed={tracks[0].is_confirmed}, name={tracks[0].confirmed_name}")
assert tracks[0].state == "CONFIRMED", "Frame 3 should remain CONFIRMED during hold window"

print("\n=== 3. Testing API /cameras response metrics ===")
r = requests.get("http://127.0.0.1:8000/api/cameras")
print("Status code:", r.status_code)
item = r.json()['items'][0]
print("Camera metrics returned:")
for k in ['stream_fps', 'display_fps', 'ai_fps', 'avg_inference_ms', 'latency_ms', 'dropped_frames', 'queue_size']:
    print(f"  {k}: {item.get(k)}")

print("\nALL AUTOMATED VERIFICATION TESTS PASSED!")

