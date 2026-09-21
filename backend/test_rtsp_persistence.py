import asyncio
import time
from app.services.rtsp_manager import RTSPManager, RTSPCameraWorker

class MockRecognitionService:
    settings = None

def test_rtsp_manager_persistence():
    print("Testing RTSPManager methods and persistence...")
    rec_service = MockRecognitionService()
    loop = asyncio.new_event_loop()
    manager = RTSPManager(recognition_service=rec_service, loop=loop)

    class MockCamera:
        id = 99
        name = "Test Gate Camera"
        rtsp_url = "rtsp://127.0.0.1:8554/live"
        mode = "CHECK-IN"
        location = "Gate 1"
        username = None
        password = None
        enabled = True

    cam = MockCamera()

    # 1. ensure_camera_running starts worker
    w1 = manager.ensure_camera_running(cam)
    assert w1 is not None, "Worker should be created"
    assert w1.camera_id == 99
    assert w1.running is True

    # 2. ensure_camera_running returns existing running worker without duplicate
    w2 = manager.ensure_camera_running(cam)
    assert w1 is w2, "Should return exact same worker instance"

    # 3. get_worker_by_mode
    by_mode = manager.get_worker_by_mode("CHECK-IN")
    assert by_mode is w1, "Should find worker by mode"

    # 4. Status summary reporting
    summary = w1.get_status_summary()
    assert summary["id"] == 99
    assert "status" in summary
    assert "is_receiving_frames" in summary

    # 5. Reachability & connection test helper
    test_res = manager.test_rtsp_connection("rtsp://127.0.0.1:9999/dummy", timeout_seconds=0.5)
    assert "success" in test_res
    assert test_res["success"] is False

    # 6. Shutdown
    manager.shutdown()
    assert len(manager.workers) == 0, "All workers should be cleanly shut down"
    assert w1.running is False, "Worker should be stopped"

    print("All RTSPManager persistence unit tests passed successfully!")

if __name__ == "__main__":
    test_rtsp_manager_persistence()

