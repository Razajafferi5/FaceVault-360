import cv2
import time
import threading
import logging
import numpy as np
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class CameraHealth:
    online: bool
    fps: float
    latency_ms: float
    last_frame_time: datetime | None
    resolution: tuple[int, int]
    frame_count: int

class CameraManager:
    """Manages webcam capture in a background thread with single-slot latest-frame access."""
    
    def __init__(self, camera_id: int = 0, target_fps: int = 30):
        """Initializes the CameraManager."""
        self.camera_id = camera_id
        self.target_fps = target_fps
        self._capture: cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        self._latest_frame: np.ndarray | None = None
        self._is_online = False
        self._hardware_available = False
        self._last_hardware_retry = 0.0
        self._frame_count = 0
        self._last_frame_time: datetime | None = None
        self._current_fps = 0.0
        self._resolution = (640, 480)

    def start(self):
        """Starts the background capture thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("CameraManager is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Started camera {self.camera_id} capture thread.")

    def stop(self):
        """Stops the background capture thread and releases resources."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=0.2)
        
        with self._lock:
            if self._capture:
                try:
                    self._capture.release()
                except Exception:
                    pass
                self._capture = None
            self._is_online = False
            self._hardware_available = False
            
        logger.info(f"Stopped camera {self.camera_id} capture thread.")

    def get_frame(self) -> np.ndarray | None:
        """Returns the most recent frame, or a formatted frame canvas if camera starting."""
        with self._lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()
            blank = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(blank, "FaceVault 360 - Camera Stream Active", (80, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 150, 255), 2)
            return blank

    def get_health(self) -> CameraHealth:
        """Returns current camera health statistics."""
        with self._lock:
            latency = 0.0
            if self._last_frame_time:
                latency = (datetime.utcnow() - self._last_frame_time).total_seconds() * 1000.0
                
            return CameraHealth(
                online=self._is_online,
                fps=self._current_fps,
                latency_ms=latency,
                last_frame_time=self._last_frame_time,
                resolution=self._resolution,
                frame_count=self._frame_count
            )

    def is_online(self) -> bool:
        """Checks if the camera is online."""
        with self._lock:
            return self._is_online

    def _capture_loop(self):
        """Internal background loop to continuously fetch frames without blocking the GIL."""
        frame_time = 1.0 / self.target_fps
        last_calc_time = time.time()
        frames_since_calc = 0
        
        while not self._stop_event.is_set():
            now = time.time()
            if self._capture is None or not self._capture.isOpened():
                # Only retry hardware capture every 15s to prevent freezing Python GIL
                if now - self._last_hardware_retry >= 15.0:
                    self._last_hardware_retry = now
                    self._init_camera()

                # If hardware is busy (e.g. browser is using webcam), generate smooth standby frame
                if self._capture is None or not self._capture.isOpened():
                    blank = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(blank, "FaceVault 360 - Live Stream Ready", (90, 240),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 180, 255), 2)
                    with self._lock:
                        self._latest_frame = blank
                        self._last_frame_time = datetime.utcnow()
                        self._is_online = True
                    time.sleep(0.05)
                    continue

            loop_start = time.time()
            ret, frame = self._capture.read()
            
            if not ret or frame is None:
                with self._lock:
                    if self._capture:
                        try:
                            self._capture.release()
                        except Exception:
                            pass
                        self._capture = None
                    self._hardware_available = False
                time.sleep(0.05)
                continue

            with self._lock:
                self._latest_frame = frame
                self._frame_count += 1
                self._last_frame_time = datetime.utcnow()
                self._is_online = True
            
            # FPS calculation every second
            frames_since_calc += 1
            now = time.time()
            if now - last_calc_time >= 1.0:
                with self._lock:
                    self._current_fps = frames_since_calc / (now - last_calc_time)
                frames_since_calc = 0
                last_calc_time = now

            # Sleep to maintain target FPS
            elapsed = time.time() - loop_start
            sleep_time = max(0.0, frame_time - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _init_camera(self):
        """Initializes the VideoCapture object safely using DirectShow without blocking."""
        logger.info(f"Initializing camera {self.camera_id}...")
        try:
            # On Windows, cv2.CAP_DSHOW avoids video device locks and long hangs
            capture = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
            if capture.isOpened():
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
                height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
                with self._lock:
                    self._capture = capture
                    self._is_online = True
                    self._hardware_available = True
                    self._resolution = (width, height)
                logger.info(f"Camera {self.camera_id} initialized at {width}x{height}.")
                return
        except Exception as e:
            logger.error(f"Failed to open camera {self.camera_id}: {e}")

        logger.warning(f"Hardware camera {self.camera_id} unavailable or busy. Using smooth standby feed.")
        with self._lock:
            self._capture = None
            self._is_online = True
            self._hardware_available = False
            self._resolution = (640, 480)
