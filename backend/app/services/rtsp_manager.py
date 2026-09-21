import asyncio
import logging
import os
import socket
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, List, Any, Tuple
from urllib.parse import urlparse, quote_plus, urlunparse
import uuid

import cv2
import numpy as np

from app.db.database import AsyncSessionLocal
from app.db.repositories.attendance_repo import AttendanceRepository
from app.db.repositories.camera_repo import RTSPCameraRepository
from app.services.face_tracker import FaceTracker, TrackedFace

logger = logging.getLogger(__name__)

# Configure OpenCV FFmpeg backend for ultra-low latency & zero internal buffering
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "rtsp_transport;tcp|"
    "fflags;nobuffer|"
    "flags;low_delay|"
    "max_delay;0|"
    "probesize;32|"
    "analyzeduration;0|"
    "stimeout;3000000|"
    "timeout;3000000"
)


@dataclass
class PresenceSession:
    employee_id: int
    employee_name: str
    first_seen: float
    last_seen: float
    action_taken: str  # "CHECK-IN SUCCESSFUL", "CHECK-OUT SUCCESSFUL", etc.
    action_time_str: str
    match_score: float
    camera_name: str
    badge_color: Tuple[int, int, int] = (0, 220, 0)
    enrollment_status: str = "Enrolled ✓"
    checkout_status: str = ""


class RTSPCameraWorker:
    """
    High-Accuracy, Ultra-Low Latency RTSP Worker Pipeline:
    - Dedicated Grabber Thread: Unblocked, continuous cap.read() over TCP.
      Buffer depth is strictly 1 frame (zero historical frame accumulation).
    - Fixed 15 FPS Video Streamer & HUD Thread: Paces display at smooth 15 FPS (66.6ms cadence).
      Completely decoupled from AI inference duration.
    - Asynchronous AI Recognition Worker: Processes the newest available frame.
      Drops stale frames when busy, preventing queue buildup and eliminating lag.
    - High-Resolution Input: Preserves up to 1280px inference resolution so distance faces
      (2-4 meters away) maintain sufficient biometric detail for ArcFace.
    - Lightweight IoU Face Tracker: Correlates faces across frames, smooths bounding boxes,
      and enforces temporal match confirmation (2 consecutive frames) and hold times.
    - Granular Diagnostics: Measures & reports Stream FPS, Display FPS, AI FPS,
      Inference Time, Latency, and Dropped Frames.
    """

    TARGET_FPS: int = 15
    FRAME_INTERVAL: float = 1.0 / 15.0  # ~66.67ms
    MAX_STREAM_WIDTH: int = 960         # Display stream width for fast transmission
    MAX_INFERENCE_WIDTH: int = 1280     # Preserves distance facial detail for ArcFace

    def __init__(
        self,
        camera_id: int,
        name: str,
        rtsp_url: str,
        mode: str,
        location: Optional[str],
        username: Optional[str],
        password: Optional[str],
        recognition_service,
        loop: asyncio.AbstractEventLoop,
    ):
        self.camera_id = camera_id
        self.name = name
        self.rtsp_url = rtsp_url
        self.mode = mode.upper()  # CHECK-IN, CHECK-OUT, COMBINED
        self.location = location or name
        self.username = username
        self.password = password
        self.recognition_service = recognition_service
        self.loop = loop

        self.running = False
        self.status = "disconnected"  # "connected", "connecting", "reconnecting", "disconnected"
        self.status_message = "Initialized"
        self.last_seen_time: Optional[float] = None
        self.last_connected_time: Optional[float] = None
        self.last_frame_time: Optional[float] = None
        self.disconnect_detected_time: Optional[float] = None
        self.reconnect_start_time: Optional[float] = None
        self.time_to_first_frame: Optional[float] = None
        self.reconnect_attempt: int = 0
        self.manual_disconnected: bool = False
        self._reconnect_trigger = threading.Event()
        self.last_error_details: Dict[str, Any] = {}

        # Granular Performance Metrics Tracking
        self._stream_timestamps: deque = deque(maxlen=60)
        self._display_timestamps: deque = deque(maxlen=60)
        self._ai_timestamps: deque = deque(maxlen=60)
        self._inference_times_ms: deque = deque(maxlen=30)
        self._latencies_ms: deque = deque(maxlen=30)

        self.raw_frames_captured: int = 0
        self.ai_frames_processed: int = 0
        self.dropped_frames_count: int = 0

        # Temporal Face Tracker (IoU correlation, multi-frame confirmation)
        cfg = getattr(self.recognition_service, 'settings', None)
        conf_frames = getattr(cfg, 'RECOGNITION_CONFIRMATION_FRAMES', 2)
        rec_hold = getattr(cfg, 'RECOGNITION_HOLD_TIME', 2.5)
        unk_hold = getattr(cfg, 'UNKNOWN_HOLD_TIME', 1.5)
        min_size = getattr(cfg, 'MIN_FACE_SIZE_PIXELS', 36)

        self.tracker = FaceTracker(
            confirmation_frames=conf_frames,
            recognition_hold_time=rec_hold,
            unknown_hold_time=unk_hold,
            min_face_size=min_size
        )

        # Thread management
        self._grabber_thread: Optional[threading.Thread] = None
        self._processor_thread: Optional[threading.Thread] = None
        self._recog_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"RTSP-Recog-{camera_id}")
        self._recognition_busy = False

        # Locks
        self._lock = threading.RLock()
        self._frame_lock = threading.Lock()

        # Frame buffers & sequences (Buffer depth strictly 1)
        self.latest_raw_frame: Optional[np.ndarray] = None
        self.latest_raw_time: float = 0.0
        self.latest_raw_seq: int = 0
        self.latest_jpeg: Optional[bytes] = None
        self.latest_jpeg_seq: int = 0

        # Presence & debounce tracking: employee_id -> PresenceSession
        self.active_presence: Dict[int, PresenceSession] = {}
        self.presence_timeout: float = 12.0  # seconds until session expires when person walks away
        self.recognition_interval: float = 0.12  # seconds between AI runs (~8 FPS AI capability)
        self.last_recognition_time: float = 0.0

        # Cached HUD detection results with original frame shape
        self.latest_detections: List[Dict[str, Any]] = []
        self.detection_frame_shape: Tuple[int, int] = (480, 640)

        # Recent events log for this camera
        self.recent_events: deque = deque(maxlen=30)

    def get_redacted_url(self) -> str:
        """Returns RTSP URL with any embedded passwords safely redacted."""
        url = self.rtsp_url.strip()
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            if parsed.password:
                netloc = f"{parsed.username}:***@{parsed.hostname}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                return urlunparse(parsed._replace(netloc=netloc))
            elif self.username and self.password:
                netloc = f"{self.username}:***@{parsed.hostname}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                return urlunparse(parsed._replace(netloc=netloc))
            return url
        except Exception:
            return url

    @staticmethod
    def _get_local_ip_hint() -> str:
        """Determine backend machine's primary local IP and subnet."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                prefix = ".".join(ip.split(".")[:3])
                return f"{ip} (subnet {prefix}.x)"
        except Exception:
            return "192.168.0.x"

    @staticmethod
    def _detect_network_issue(host: str, port: int) -> Optional[str]:
        """Analyzes IP subnets to give immediate actionable instructions to the user."""
        try:
            local_hint = RTSPCameraWorker._get_local_ip_hint()
            local_ip = local_hint.split(" ")[0]
            parts = host.split(".")
            local_parts = local_ip.split(".")
            if len(parts) == 4 and len(local_parts) == 4:
                if (parts[0] != local_parts[0]) or (parts[0] == local_parts[0] and parts[1] != local_parts[1]):
                    return (
                        f"SUBNET MISMATCH DETECTED: Backend server is on {local_ip} (Wi-Fi SSID 'Aspire Executive'), "
                        f"but camera IP is {host}. The phone is on mobile cellular data or a separate network. "
                        f"Connect your phone to the same Wi-Fi ('Aspire Executive') and use the Wi-Fi IP assigned to the phone."
                    )
        except Exception:
            pass
        return None

    def _calculate_stream_fps(self) -> float:
        """Calculates true rolling FPS of incoming frames received from the RTSP camera."""
        now = time.time()
        with self._frame_lock:
            while self._stream_timestamps and (now - self._stream_timestamps[0] > 2.0):
                self._stream_timestamps.popleft()
            n = len(self._stream_timestamps)
            if n >= 2:
                dt = self._stream_timestamps[-1] - self._stream_timestamps[0]
                if dt > 0.05:
                    return float(n) / dt
            elif n == 1 and (now - self._stream_timestamps[0] < 1.0):
                return 1.0
            return 0.0

    def _calculate_display_fps(self) -> float:
        """Calculates rolling FPS of encoded display frames sent to the frontend."""
        now = time.time()
        with self._lock:
            while self._display_timestamps and (now - self._display_timestamps[0] > 2.0):
                self._display_timestamps.popleft()
            n = len(self._display_timestamps)
            if n >= 2:
                dt = self._display_timestamps[-1] - self._display_timestamps[0]
                if dt > 0.05:
                    return float(n) / dt
            elif n == 1:
                return 1.0
            return 0.0

    def _calculate_ai_fps(self) -> float:
        """Calculates rolling FPS of completed AI face recognition inferences."""
        now = time.time()
        with self._lock:
            while self._ai_timestamps and (now - self._ai_timestamps[0] > 2.0):
                self._ai_timestamps.popleft()
            n = len(self._ai_timestamps)
            if n >= 2:
                dt = self._ai_timestamps[-1] - self._ai_timestamps[0]
                if dt > 0.05:
                    return float(n) / dt
            elif n == 1:
                return 1.0
            return 0.0

    def _get_avg_inference_ms(self) -> float:
        with self._lock:
            if self._inference_times_ms:
                return sum(self._inference_times_ms) / len(self._inference_times_ms)
            return 0.0

    def _get_avg_latency_ms(self) -> float:
        with self._lock:
            if self._latencies_ms:
                return sum(self._latencies_ms) / len(self._latencies_ms)
            return 0.0

    def _build_effective_url(self) -> str:
        """Construct RTSP URL with URL-encoded credentials if not already embedded."""
        url = self.rtsp_url.strip()
        if not url or url.isdigit() or url in ("0", "1", "2"):
            return ""

        if self.username and self.password and "@" not in url:
            try:
                parsed = urlparse(url)
                if parsed.scheme.lower() in ("rtsp", "rtsps", "http", "https"):
                    user_enc = quote_plus(self.username)
                    pass_enc = quote_plus(self.password)
                    netloc = f"{user_enc}:{pass_enc}@{parsed.hostname}"
                    if parsed.port:
                        netloc += f":{parsed.port}"
                    new_parsed = parsed._replace(netloc=netloc)
                    return urlunparse(new_parsed)
            except Exception as e:
                logger.warning(f"Failed to inject credentials into URL: {e}")
        return url

    def start(self):
        """Start both dedicated grabber and 15 FPS processor background threads."""
        if self.running:
            return
        self.running = True
        self.manual_disconnected = False
        self.status = "connecting"
        self.status_message = "Connecting to stream over TCP..."

        # 1. Start dedicated frame grabber thread (drains camera buffer at max rate)
        self._grabber_thread = threading.Thread(
            target=self._run_grabber_loop,
            name=f"RTSP-Grabber-{self.camera_id}",
            daemon=True
        )
        self._grabber_thread.start()

        # 2. Start fixed 15 FPS video streamer & HUD renderer thread
        self._processor_thread = threading.Thread(
            target=self._run_processor_loop,
            name=f"RTSP-Processor15FPS-{self.camera_id}",
            daemon=True
        )
        self._processor_thread.start()

        logger.info(f"Started RTSP Worker (Fixed 15 FPS Pipeline) for Camera {self.camera_id} ('{self.name}')")

    def stop(self):
        """Gracefully stop worker threads and release camera resources."""
        self.running = False
        self.status = "disconnected"
        self.status_message = "Worker stopped"
        self._reconnect_trigger.set()

        if self._grabber_thread and self._grabber_thread.is_alive():
            self._grabber_thread.join(timeout=2.0)
        if self._processor_thread and self._processor_thread.is_alive():
            self._processor_thread.join(timeout=2.0)
        self._recog_executor.shutdown(wait=False, cancel_futures=True)

        logger.info(f"Stopped RTSP Worker for Camera {self.camera_id} ('{self.name}')")

    def manual_disconnect(self):
        """Manually disconnect and stop reconnection loop."""
        with self._lock:
            self.manual_disconnected = True
            self.status = "disconnected"
            self.status_message = "Disconnected by user. Click [Connect] to restart."
            with self._frame_lock:
                self.latest_raw_frame = None
                self._stream_timestamps.clear()
            self.last_error_details = {
                "camera_id": self.camera_id,
                "role": self.mode,
                "redacted_url": self.get_redacted_url(),
                "status": "Disconnected by user",
                "attempt": 0,
                "hint": "Stream paused by user. Click [Connect] to re-establish connection."
            }
        self._reconnect_trigger.set()
        logger.info(f"Camera {self.camera_id} ('{self.name}' | {self.mode}) manually disconnected by user.")

    def manual_connect(self):
        """Manually connect or reconnect immediately, resetting backoff."""
        with self._lock:
            self.manual_disconnected = False
            self.reconnect_attempt = 0
            self.status = "connecting"
            self.status_message = "Manual connection requested..."
            self.last_error_details.clear()
        self._reconnect_trigger.set()
        logger.info(f"Camera {self.camera_id} ('{self.name}' | {self.mode}) manual connect requested.")

    def manual_reconnect(self):
        """Force a clean reconnect, releasing resources and attempting connection now."""
        self.manual_connect()

    @staticmethod
    def _check_reachability(url: str, timeout: float = 0.5) -> Tuple[bool, str]:
        """Rapid TCP ping to host & port (0.5s timeout) to avoid FFmpeg hangs."""
        try:
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port or (554 if parsed.scheme.lower() in ("rtsp", "rtsps") else 80)
            if not host:
                return False, "Invalid stream URL: missing host"
            with socket.create_connection((host, port), timeout=timeout):
                return True, "Reachable"
        except (socket.timeout, TimeoutError):
            return False, f"Connection timed out (host {host}:{port} did not respond)"
        except ConnectionRefusedError:
            return False, f"Connection refused (RTSP server app is not active on device at port {port})"
        except Exception as e:
            return False, str(e)

    def get_current_raw_frame(self) -> Optional[np.ndarray]:
        """Returns a copy of the latest raw video frame for zero-latency enrollment."""
        with self._frame_lock:
            if self.latest_raw_frame is not None and self.latest_raw_frame.size > 0:
                return self.latest_raw_frame.copy()
        return None

    def _run_grabber_loop(self):
        """
        Dedicated Frame Grabber Loop (Latest-Frame Zero-Lag Architecture):
        - Fast reconnect state machine: DISCONNECTED -> RECONNECTING -> AWAITING FIRST FRAME -> CONNECTED.
        - Fast reachability probes with bounded retry backoff (0.5s - 3.5s max).
        - Strictly marks CONNECTED only upon first valid frame arrival.
        - Buffer depth strictly 1: latest frame atomically replaces previous frame.
        """
        while self.running:
            if self.manual_disconnected:
                with self._lock:
                    self.status = "disconnected"
                    self.status_message = "Disconnected by user. Click [Connect] to restart."
                self._reconnect_trigger.wait(timeout=2.0)
                self._reconnect_trigger.clear()
                continue

            effective_url = self._build_effective_url()
            if not effective_url:
                with self._lock:
                    self.status = "disconnected"
                    self.status_message = "Awaiting valid RTSP stream URL (e.g. rtsp://...)"
                self._reconnect_trigger.wait(timeout=2.0)
                self._reconnect_trigger.clear()
                continue

            parsed_url = urlparse(effective_url)
            host = parsed_url.hostname or "unknown"
            port = parsed_url.port or (554 if "rtsp" in parsed_url.scheme.lower() else 80)
            path = parsed_url.path or "/live"

            # Track reconnect timing
            if not self.reconnect_start_time:
                self.reconnect_start_time = time.time()
            if not self.disconnect_detected_time:
                self.disconnect_detected_time = time.time()

            with self._lock:
                self.status = "reconnecting"
                self.status_message = f"Pinging {host}:{port} (Attempt {self.reconnect_attempt + 1})..."

            reachable, reason = self._check_reachability(effective_url, timeout=0.5)
            if not reachable:
                self.reconnect_attempt += 1
                # Fast bounded exponential backoff: 0.5s, 0.6s, 0.8s, 1.0s, 1.2s ... capped at 3.5s max
                backoff_delay = min(0.5 * (1.25 ** min(self.reconnect_attempt - 1, 6)), 3.5)
                error_msg = f"Host {host}:{port} unreachable: {reason}"
                subnet_hint = self._detect_network_issue(host, port)
                hint_str = subnet_hint or f"Backend host IP is {self._get_local_ip_hint()}. Ensure camera device is on Wi-Fi and RTSP server is active."
                with self._lock:
                    self.status = "reconnecting"
                    self.status_message = error_msg
                    self.last_error_details = {
                        "camera_id": self.camera_id,
                        "role": self.mode,
                        "redacted_url": self.get_redacted_url(),
                        "host": host,
                        "port": port,
                        "path": path,
                        "state": "RECONNECTING",
                        "transport": "TCP",
                        "attempt": self.reconnect_attempt,
                        "reconnect_count": self.reconnect_attempt,
                        "next_retry_seconds": round(backoff_delay, 1),
                        "last_error": error_msg,
                        "reconnect_started": datetime.fromtimestamp(self.reconnect_start_time).strftime("%I:%M:%S %p") if self.reconnect_start_time else "Now",
                        "last_frame_time": datetime.fromtimestamp(self.last_frame_time).isoformat() if self.last_frame_time else "Never",
                        "hint": hint_str
                    }
                logger.warning(
                    f"RTSP Camera {self.camera_id} ('{self.name}' | {self.mode}) attempt {self.reconnect_attempt} failed: {error_msg}. Fast retry in {backoff_delay:.1f}s."
                )
                self._reconnect_trigger.wait(timeout=backoff_delay)
                self._reconnect_trigger.clear()
                continue

            # Connected to host! Open stream over TCP with no buffer
            cap = None
            try:
                with self._lock:
                    self.status = "connecting"
                    self.status_message = f"Opening TCP stream from {host}:{port}..."

                cap = cv2.VideoCapture(effective_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if not cap.isOpened():
                    raise RuntimeError(f"RTSP handshake failed at {host}:{port} (stream path invalid or credentials required)")

                with self._lock:
                    # STRICT STATE MACHINE: Remain in connecting until real frame arrives!
                    self.status = "connecting"
                    self.status_message = "Stream opened. Awaiting first valid video frame..."

                first_frame = True
                consecutive_read_failures = 0
                MAX_READ_FAILURES = 12  # Fast failure detection (~480ms)
                while self.running and not self.manual_disconnected:
                    ret, frame = cap.read()
                    if not ret or frame is None or frame.size == 0:
                        consecutive_read_failures += 1
                        if consecutive_read_failures >= MAX_READ_FAILURES:
                            logger.warning(
                                f"RTSP frame read failed {consecutive_read_failures} consecutive times for Camera {self.camera_id} ('{self.name}')"
                            )
                            raise RuntimeError("RTSP stream interrupted: max consecutive read failures reached")
                        time.sleep(0.04)
                        continue

                    consecutive_read_failures = 0
                    now_f = time.time()
                    with self._frame_lock:
                        # ATOMICALLY OVERWRITE latest frame (Buffer depth = 1)
                        self.latest_raw_frame = frame
                        self.latest_raw_time = now_f
                        self.latest_raw_seq += 1
                        self.raw_frames_captured += 1
                        self.last_seen_time = now_f
                        self.last_frame_time = now_f
                        self._stream_timestamps.append(now_f)

                    # STRICT TRANSITION: ONLY MARK CONNECTED ON FIRST VALID FRAME!
                    if first_frame:
                        first_frame = False
                        ttff = round(now_f - (self.reconnect_start_time or now_f), 2)
                        self.time_to_first_frame = ttff
                        self.disconnect_detected_time = None
                        self.reconnect_start_time = None
                        with self._lock:
                            self.status = "connected"
                            self.status_message = f"Stream active over TCP ({frame.shape[1]}x{frame.shape[0]}) • First frame: {ttff}s"
                            self.last_connected_time = now_f
                            self.reconnect_attempt = 0
                            self.last_error_details = {
                                "camera_id": self.camera_id,
                                "role": self.mode,
                                "redacted_url": self.get_redacted_url(),
                                "host": host,
                                "port": port,
                                "path": path,
                                "state": "CONNECTED",
                                "transport": "TCP",
                                "attempt": 0,
                                "reconnect_count": 0,
                                "time_to_first_frame_seconds": ttff,
                                "first_frame_received_at": datetime.fromtimestamp(now_f).strftime("%I:%M:%S %p"),
                                "last_error": None,
                                "status": f"Connected over TCP ({frame.shape[1]}x{frame.shape[0]})",
                                "hint": f"Stream active. Reconnected and decoded first frame in {ttff}s."
                            }
                        logger.info(
                            f"RTSP Camera {self.camera_id} ('{self.name}' | {self.mode}) FIRST FRAME decoded in {ttff}s ({frame.shape[1]}x{frame.shape[0]}) -> STATUS: CONNECTED"
                        )

            except Exception as e:
                self.reconnect_attempt += 1
                backoff_delay = min(0.75 * (1.2 ** min(self.reconnect_attempt - 1, 5)), 3.5)
                error_msg = f"RTSP stream error: {str(e)}"
                subnet_hint = self._detect_network_issue(host, port)
                hint_str = subnet_hint or "Check RTSP URL path (e.g. /live), credentials, or restart RTSP server app."
                with self._lock:
                    self.status = "reconnecting"
                    self.status_message = error_msg
                    self.last_error_details = {
                        "camera_id": self.camera_id,
                        "role": self.mode,
                        "redacted_url": self.get_redacted_url(),
                        "host": host,
                        "port": port,
                        "path": path,
                        "state": "RECONNECTING",
                        "transport": "TCP",
                        "attempt": self.reconnect_attempt,
                        "reconnect_count": self.reconnect_attempt,
                        "next_retry_seconds": round(backoff_delay, 1),
                        "last_error": error_msg,
                        "last_frame_time": datetime.fromtimestamp(self.last_frame_time).isoformat() if self.last_frame_time else "Never",
                        "last_connected_time": datetime.fromtimestamp(self.last_connected_time).isoformat() if self.last_connected_time else "Never",
                        "hint": hint_str
                    }
                logger.error(f"RTSP grabber error on Camera {self.camera_id} ('{self.name}'): {error_msg}")

            finally:
                if cap is not None:
                    cap.release()

            if self.running and not self.manual_disconnected:
                self._reconnect_trigger.wait(timeout=backoff_delay)
                self._reconnect_trigger.clear()

        with self._lock:
            self.status = "disconnected"
            self.status_message = "Disconnected"

    def _run_processor_loop(self):
        """
        Fixed 15 FPS Video Streamer & HUD Renderer:
        - Ticks at exactly 15 FPS (66.67ms interval).
        - Grabs latest raw frame (latest-frame architecture).
        - Dispatches face recognition asynchronously on newest frame when AI is idle.
        - Drops stale frames when AI is busy, eliminating video delay and queue bloat.
        - Renders biometric HUD with tracked bounding boxes and live FPS telemetry.
        - Encodes JPEG at quality 65 for instantaneous smooth rendering.
        """
        while self.running:
            tick_start = time.time()

            frame = None
            frame_time = 0.0
            frame_seq = 0
            with self._frame_lock:
                if self.latest_raw_frame is not None:
                    frame = self.latest_raw_frame
                    frame_time = self.latest_raw_time
                    frame_seq = self.latest_raw_seq

            if frame is not None:
                now = time.time()
                self._display_timestamps.append(now)

                # Asynchronous AI Recognition Dispatch
                # If AI is idle and interval met, submit newest frame!
                if not self._recognition_busy and (now - self.last_recognition_time >= self.recognition_interval):
                    self._recognition_busy = True
                    self.last_recognition_time = now
                    self.ai_frames_processed += 1

                    h, w = frame.shape[:2]
                    # High-Resolution Adaptive Input: Preserve up to 1280px width so distance faces
                    # retain high resolution for ArcFace embeddings
                    if w > self.MAX_INFERENCE_WIDTH:
                        scale = self.MAX_INFERENCE_WIDTH / float(w)
                        infer_h = int(h * scale)
                        infer_frame = cv2.resize(frame, (self.MAX_INFERENCE_WIDTH, infer_h), interpolation=cv2.INTER_LINEAR)
                    else:
                        infer_frame = frame.copy()

                    self._recog_executor.submit(
                        self._async_recognition_worker, infer_frame, (w, h), frame_time, now
                    )
                else:
                    # AI is currently busy: we DROP this frame for AI inference.
                    # The capture thread continuously reads, and display keeps rendering live!
                    if self._recognition_busy:
                        self.dropped_frames_count += 1

                # Periodic cleanup of expired presences & tracks
                self._cleanup_expired_presences(now)
                self.tracker.cleanup_expired(now)

                # Prepare render frame for display
                h, w = frame.shape[:2]
                render_w = min(w, self.MAX_STREAM_WIDTH)
                if w != render_w:
                    scale = render_w / float(w)
                    render_h = int(h * scale)
                    render_frame = cv2.resize(frame, (render_w, render_h), interpolation=cv2.INTER_LINEAR)
                else:
                    render_frame = frame.copy()

                # Render Biometric HUD Overlay
                annotated = self._render_hud(render_frame, (w, h), now)

                # Fast JPEG Encoding (Quality 65 for instantaneous transmission)
                ret_enc, jpeg = cv2.imencode(
                    '.jpg',
                    annotated,
                    [cv2.IMWRITE_JPEG_QUALITY, 65, cv2.IMWRITE_JPEG_OPTIMIZE, 0]
                )
                if ret_enc:
                    with self._lock:
                        self.latest_jpeg = jpeg.tobytes()
                        self.latest_jpeg_seq += 1

            # Exact 15 FPS cadence sleep (target: 66.67ms per frame)
            elapsed = time.time() - tick_start
            sleep_duration = self.FRAME_INTERVAL - elapsed
            if sleep_duration > 0.001:
                time.sleep(sleep_duration)

    def _async_recognition_worker(
        self,
        frame: np.ndarray,
        orig_shape: Tuple[int, int],
        frame_capture_time: float,
        dispatch_time: float
    ):
        """
        Runs face recognition, tracking update, and attendance events in background.
        Completely decoupled from the 15 FPS video streaming thread.
        """
        t0 = time.time()
        try:
            self._process_frame_recognition(frame, orig_shape, frame_capture_time, t0)
        except Exception as e:
            logger.error(f"Error in async RTSP recognition for Camera {self.camera_id}: {e}", exc_info=True)
        finally:
            dt_infer = (time.time() - t0) * 1000.0
            latency = (time.time() - frame_capture_time) * 1000.0 if frame_capture_time > 0 else dt_infer
            with self._lock:
                self._inference_times_ms.append(dt_infer)
                self._latencies_ms.append(latency)
                self._ai_timestamps.append(time.time())
                self._recognition_busy = False

    def _process_frame_recognition(
        self,
        frame: np.ndarray,
        orig_shape: Tuple[int, int],
        frame_capture_time: float,
        now: float
    ):
        """
        Executes face detection + embedding, updates the FaceTracker,
        and triggers non-blocking attendance events.
        """
        try:
            result = self.recognition_service.recognize_frame(frame)
            raw_faces = result.get("faces", [])
            threshold = getattr(self.recognition_service.settings, 'RECOGNITION_THRESHOLD', 0.50)

            orig_w, orig_h = orig_shape
            recog_h, recog_w = frame.shape[:2]
            scale_x = orig_w / float(recog_w) if recog_w > 0 else 1.0
            scale_y = orig_h / float(recog_h) if recog_h > 0 else 1.0

            # Scale raw bounding boxes to original frame coordinates
            scaled_faces = []
            for face in raw_faces:
                raw_bbox = face.get("bbox")
                if raw_bbox and len(raw_bbox) >= 4:
                    scaled_bbox = [
                        int(raw_bbox[0] * scale_x),
                        int(raw_bbox[1] * scale_y),
                        int(raw_bbox[2] * scale_x),
                        int(raw_bbox[3] * scale_y)
                    ]
                else:
                    scaled_bbox = raw_bbox

                face_copy = dict(face)
                face_copy["bbox"] = scaled_bbox
                scaled_faces.append(face_copy)

            # Update temporal FaceTracker
            active_tracks = self.tracker.update_from_ai_results(scaled_faces, now)

            # Process tracks for attendance events and presence
            formatted_detections = []
            for track in active_tracks:
                det_info = {
                    "track_id": track.track_id,
                    "bbox": track.bbox,
                    "state": track.state,
                    "name": track.confirmed_name or track.candidate_name or "Unknown",
                    "similarity": round(float(track.confirmed_score or track.candidate_score), 3),
                    "action_badge": track.action_taken,
                    "checkout_status": track.checkout_status or "",
                    "badge_color": track.badge_color,
                    "is_confirmed": track.is_confirmed,
                    "is_unknown": (track.state == "UNKNOWN"),
                    "is_too_small": (track.state == "FACE_TOO_SMALL")
                }

                # If identity is CONFIRMED and attendance not yet dispatched for this presence
                if track.is_confirmed and track.confirmed_id is not None:
                    person_id = track.confirmed_id
                    person_name = track.confirmed_name or "Employee"

                    if person_id in self.active_presence:
                        # CONTINUOUS PRESENCE: Person is still standing in front of camera
                        presence = self.active_presence[person_id]
                        presence.last_seen = now
                        det_info["action_badge"] = presence.action_taken
                        det_info["badge_color"] = presence.badge_color
                        det_info["checkout_status"] = presence.checkout_status
                    else:
                        # NEW PRESENCE EVENT: Person just arrived and confirmed!
                        # Trigger attendance asynchronously without blocking worker thread!
                        action_badge, action_time, badge_color, checkout_status = self._trigger_attendance_event_async(
                            employee_id=person_id,
                            employee_name=person_name,
                            match_score=track.confirmed_score
                        )
                        presence = PresenceSession(
                            employee_id=person_id,
                            employee_name=person_name,
                            first_seen=now,
                            last_seen=now,
                            action_taken=action_badge,
                            action_time_str=action_time,
                            match_score=track.confirmed_score,
                            camera_name=self.name,
                            badge_color=badge_color,
                            enrollment_status="Enrolled ✓",
                            checkout_status=checkout_status
                        )
                        self.active_presence[person_id] = presence
                        track.action_taken = action_badge
                        track.action_time_str = action_time
                        track.badge_color = badge_color
                        track.checkout_status = checkout_status
                        det_info["action_badge"] = action_badge
                        det_info["badge_color"] = badge_color
                        det_info["checkout_status"] = checkout_status

                        self.recent_events.appendleft({
                            "timestamp": datetime.now().strftime("%I:%M:%S %p"),
                            "employee_id": person_id,
                            "employee_name": person_name,
                            "action": action_badge,
                            "checkout_status": checkout_status,
                            "enrollment_status": "Enrolled ✓",
                            "time": action_time,
                            "score": f"{track.confirmed_score:.2f}",
                            "camera": self.name,
                            "mode": self.mode
                        })

                elif track.state == "UNKNOWN":
                    # Check if live approval status was updated by Owner
                    if track.unknown_event_id:
                        live_status = RTSPManager.get_unknown_status(track.unknown_event_id)
                        if live_status:
                            track.access_status = live_status
                            det_info["access_status"] = live_status

                    # STRICT GATE: Only valid human faces can trigger or update Unknown Person logs
                    if not getattr(track, 'is_valid_face', False):
                        continue

                    # Extract face crop from recognition frame with 25% padding
                    try:
                        fx = int(track.bbox[0] / scale_x)
                        fy = int(track.bbox[1] / scale_y)
                        fw = int(track.bbox[2] / scale_x)
                        fh = int(track.bbox[3] / scale_y)
                        pad_x = int(fw * 0.25)
                        pad_y = int(fh * 0.25)
                        x1 = max(0, fx - pad_x)
                        y1 = max(0, fy - pad_y)
                        x2 = min(recog_w, fx + fw + pad_x)
                        y2 = min(recog_h, fy + fh + pad_y)

                        face_crop = frame[y1:y2, x1:x2].copy() if (x2 > x1 and y2 > y1) else None
                    except Exception:
                        face_crop = None

                    # If this unknown track hasn't triggered snapshot + DB event yet:
                    if not getattr(track, 'unknown_logged', False):
                        track.unknown_logged = True
                        track._denied_logged = True
                        track.last_heartbeat_time = now
                        track.best_quality_score = track.quality_score

                        self._trigger_unknown_person_event_async(
                            face_crop=face_crop,
                            track=track,
                            confidence=track.candidate_score or 0.0,
                            quality_score=track.quality_score
                        )
                        self._trigger_denied_event_async(
                            similarity=track.candidate_score or 0.0,
                            camera_name=self.name
                        )
                    else:
                        # Ongoing visitor: track detection count and heartbeat update every 2 seconds
                        track.pending_detections += 1
                        has_better_snapshot = False
                        if track.quality_score > (track.best_quality_score or 0.0) and face_crop is not None:
                            track.best_quality_score = track.quality_score
                            has_better_snapshot = True

                        if (now - getattr(track, 'last_heartbeat_time', 0.0) >= 2.0) or has_better_snapshot:
                            track.last_heartbeat_time = now
                            added = track.pending_detections
                            track.pending_detections = 0
                            if track.unknown_event_id:
                                self._trigger_unknown_heartbeat_async(
                                    event_id=track.unknown_event_id,
                                    added_count=max(1, added),
                                    quality_score=track.best_quality_score,
                                    face_crop=face_crop if has_better_snapshot else None
                                )

                formatted_detections.append(det_info)

            with self._lock:
                self.latest_detections = formatted_detections
                self.detection_frame_shape = (orig_w, orig_h)

        except Exception as e:
            logger.error(f"Error in RTSP recognition processing: {e}", exc_info=True)

    def _trigger_attendance_event_async(
        self, employee_id: int, employee_name: str, match_score: float
    ) -> Tuple[str, str, Tuple[int, int, int], str]:
        """
        Dispatches attendance recording to database asynchronously.
        Never blocks the video grabber or display thread!
        """
        action_time_str = datetime.now().strftime("%I:%M %p")

        async def _db_task():
            async with AsyncSessionLocal() as session:
                try:
                    record, is_new, action_name = await AttendanceRepository.process_rtsp_attendance(
                        session=session,
                        employee_id=employee_id,
                        employee_name=employee_name,
                        match_score=match_score,
                        camera_name=self.name,
                        camera_mode=self.mode
                    )
                    return action_name
                except Exception as err:
                    logger.error(f"Failed to record RTSP attendance in DB: {err}", exc_info=True)
                    return "ATTENDANCE FAILED"

        try:
            if self.loop and self.loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_db_task(), self.loop)
                # Short non-blocking timeout: if DB responds fast, use real action name
                try:
                    action_name = future.result(timeout=0.35)
                except Exception:
                    # If DB is busy, coroutine continues in background, return optimistic action
                    action_name = "CHECK-IN SUCCESSFUL" if self.mode == "CHECK-IN" else "CHECK-OUT SUCCESSFUL"
            else:
                action_name = asyncio.run(_db_task())

            # Format clean HUD action badge and colors
            if action_name == "NO_CHECK_IN_FOUND":
                badge = "⚠ NO CHECK-IN FOUND"
                checkout_status = "No Check-In Found"
                badge_color = (0, 165, 255)  # Amber warning
            elif "CHECK-OUT" in action_name:
                badge = f"✓ CHECK-OUT ({action_time_str})"
                checkout_status = "Check-Out Successful ✓"
                badge_color = (0, 220, 0)
            elif action_name == "ALREADY_CHECKED_OUT":
                badge = "✓ ALREADY CHECKED OUT"
                checkout_status = "Already Checked Out"
                badge_color = (0, 220, 0)
            elif "CHECK-IN" in action_name:
                badge = f"✓ CHECK-IN ({action_time_str})"
                checkout_status = "Check-In Successful ✓"
                badge_color = (0, 220, 0)
            elif "COMPLETE" in action_name:
                badge = "✓ ATTENDANCE COMPLETE"
                checkout_status = "Attendance Complete"
                badge_color = (0, 220, 0)
            elif "ALREADY" in action_name:
                badge = f"✓ {action_name}"
                checkout_status = action_name
                badge_color = (0, 220, 0)
            else:
                badge = f"✓ {action_name}"
                checkout_status = action_name
                badge_color = (0, 220, 0)

            return badge, action_time_str, badge_color, checkout_status
        except Exception as e:
            logger.error(f"Could not execute attendance DB task: {e}")
            fallback_badge = f"✓ CHECK-IN ({action_time_str})" if self.mode == "CHECK-IN" else f"✓ CHECK-OUT ({action_time_str})"
            return fallback_badge, action_time_str, (0, 220, 0), "Recorded"

    def _trigger_denied_event_async(self, similarity: float, camera_name: str):
        """Asynchronously records an unauthorized/unknown face attempt to access_events table."""
        async def _log_task():
            async with AsyncSessionLocal() as session:
                try:
                    from app.db.models import AccessEvent
                    event = AccessEvent(
                        person_id=None,
                        recognized_name="Unknown Person",
                        timestamp=datetime.now(),
                        confidence=round(float(similarity), 3),
                        status="denied",
                        authorization_result="denied",
                        camera_id=camera_name or self.name,
                        failure_reason="Unrecognized Face"
                    )
                    session.add(event)
                    await session.commit()
                except Exception as e:
                    logger.warning(f"Failed to record denied RTSP access event: {e}")

        try:
            if self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(_log_task(), self.loop)
        except Exception:
            pass

    def _trigger_unknown_person_event_async(
        self,
        face_crop: Optional[np.ndarray],
        track: TrackedFace,
        confidence: float,
        quality_score: float = 0.0
    ):
        """
        Records or deduplicates an unknown person detection into an active visit session asynchronously.
        Never blocks the grabber or display thread.
        """
        async def _db_task():
            async with AsyncSessionLocal() as session:
                try:
                    from app.core.config import get_settings
                    from app.db.repositories.unknown_repo import UnknownPersonRepository

                    cfg = get_settings()
                    cooldown = getattr(cfg, "UNKNOWN_EVENT_COOLDOWN_SECONDS", 60.0)

                    event, is_new = await UnknownPersonRepository.record_or_update_unknown(
                        session=session,
                        camera_name=self.name,
                        camera_role=self.mode,
                        camera_id=self.camera_id,
                        face_confidence=confidence,
                        quality_score=quality_score,
                        face_crop=face_crop,
                        face_embedding=track.embedding,
                        cooldown_seconds=cooldown
                    )
                    track.unknown_event_id = event.id
                    track.access_status = event.access_status
                    logger.info(
                        f"Tracked UnknownPersonEvent #{event.id} ({'NEW VISIT' if is_new else 'DEDUPED/UPDATED'}) "
                        f"from camera '{self.name}' - count={event.detection_count}"
                    )
                except Exception as e:
                    logger.error(f"Failed to record/deduplicate UnknownPersonEvent: {e}", exc_info=True)

        try:
            if self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(_db_task(), self.loop)
        except Exception as e:
            logger.warning(f"Could not schedule unknown person event async task: {e}")

    def _trigger_unknown_heartbeat_async(
        self,
        event_id: int,
        added_count: int,
        quality_score: float,
        face_crop: Optional[np.ndarray] = None
    ):
        """Dispatches lightweight heartbeat update to active visit session without locking SQLite."""
        async def _hb_task():
            async with AsyncSessionLocal() as session:
                try:
                    from app.db.repositories.unknown_repo import UnknownPersonRepository
                    await UnknownPersonRepository.update_session_heartbeat(
                        session=session,
                        event_id=event_id,
                        added_count=added_count,
                        quality_score=quality_score,
                        face_crop=face_crop
                    )
                except Exception as e:
                    logger.debug(f"Heartbeat update failed for event #{event_id}: {e}")

        try:
            if self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(_hb_task(), self.loop)
        except Exception:
            pass

    def _cleanup_expired_presences(self, now: float):
        """Expire presence sessions for persons who have walked away."""
        expired_ids = [
            pid for pid, sess in self.active_presence.items()
            if now - sess.last_seen > self.presence_timeout
        ]
        for pid in expired_ids:
            sess = self.active_presence.pop(pid)
            logger.info(
                f"Presence session ended for {sess.employee_name} on Camera {self.camera_id} "
                f"(left frame for > {self.presence_timeout}s)"
            )

    def _render_hud(self, frame: np.ndarray, orig_shape: Tuple[int, int], now: float) -> np.ndarray:
        """
        Draw sleek biometric HUD overlay with accurate bounding boxes,
        individual FPS telemetry (Stream, Display, AI), and distinct recognition states.
        """
        h, w = frame.shape[:2]
        orig_w, orig_h = orig_shape
        scale_x = w / float(orig_w) if orig_w > 0 else 1.0
        scale_y = h / float(orig_h) if orig_h > 0 else 1.0

        # Top Banner Overlay
        cv2.rectangle(frame, (0, 0), (w, 36), (10, 15, 29), -1)
        cv2.line(frame, (0, 36), (w, 36), (30, 41, 59), 1)

        stream_fps = self._calculate_stream_fps()
        display_fps = self._calculate_display_fps()
        ai_fps = self._calculate_ai_fps()
        avg_inf_ms = self._get_avg_inference_ms()
        avg_lat_ms = self._get_avg_latency_ms()

        now_t = time.time()
        is_live = (stream_fps > 0 and self.last_frame_time is not None and (now_t - self.last_frame_time < 2.5))

        if is_live:
            status_dot_color = (0, 220, 0)
            telemetry_text = (
                f"{self.name.upper()} | {self.mode}  •  "
                f"STR: {stream_fps:.1f} FPS  |  DISP: {display_fps:.1f} FPS  |  AI: {ai_fps:.1f} FPS  |  "
                f"INF: {avg_inf_ms:.0f}ms"
            )
        elif self.status == "connected":
            status_dot_color = (0, 200, 255)
            telemetry_text = f"{self.name.upper()} | {self.mode}  •  CONNECTED (Awaiting frames)"
        elif self.status in ("connecting", "reconnecting"):
            status_dot_color = (0, 165, 255)
            telemetry_text = f"{self.name.upper()} | {self.mode}  •  CONNECTING (Attempt {self.reconnect_attempt})"
        else:
            status_dot_color = (0, 0, 255)
            telemetry_text = f"{self.name.upper()} | {self.mode}  •  OFFLINE"

        cv2.circle(frame, (16, 18), 5, status_dot_color, -1)
        cv2.putText(
            frame,
            telemetry_text,
            (28, 23),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (240, 240, 240),
            1,
            cv2.LINE_AA
        )

        time_str = datetime.now().strftime("%H:%M:%S")
        cv2.putText(
            frame,
            time_str,
            (w - 75, 23),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (148, 163, 184),
            1,
            cv2.LINE_AA
        )

        # Draw Active Tracks from FaceTracker
        tracks = self.tracker.get_active_tracks()

        for track in tracks:
            bbox = track.bbox
            if not bbox or len(bbox) < 4:
                continue

            x1 = int(max(0, bbox[0] * scale_x))
            y1 = int(max(0, bbox[1] * scale_y))
            x2 = int(min(w, (bbox[0] + bbox[2]) * scale_x))
            y2 = int(min(h, (bbox[1] + bbox[3]) * scale_y))

            # Select badge color and label based on state machine
            state = track.state
            if state == "CONFIRMED":
                color = (0, 220, 0)       # Green
                label = f"✓ {track.confirmed_name} ({track.confirmed_score*100:.0f}%)"
            elif state == "MATCHING":
                color = (255, 180, 0)     # Cyan/Blue
                c_name = track.candidate_name or "Face"
                label = f"MATCHING... ({c_name})"
            elif state == "FACE_TOO_SMALL":
                color = (0, 180, 255)     # Amber/Yellow
                label = "FACE TOO SMALL (MOVE CLOSER)"
            elif state == "LOW_QUALITY":
                color = (0, 140, 255)     # Orange
                label = "LOW QUALITY"
            elif state == "UNKNOWN":
                acc_status = (track.access_status or "PENDING").upper()
                if acc_status == "APPROVED":
                    color = (0, 220, 0)       # Green
                    label = "✓ VISITOR (APPROVED)"
                elif acc_status == "DENIED":
                    color = (0, 0, 220)       # Red
                    label = "✕ ACCESS DENIED"
                elif acc_status == "ENROLLED":
                    color = (255, 180, 0)     # Blue
                    label = "✓ ENROLLED VISITOR"
                else:
                    color = (0, 140, 255)     # Amber/Orange
                    label = "⚠ UNKNOWN (PENDING APPROVAL)"
            else:
                color = (148, 163, 184)   # Slate
                label = "DETECTING..."

            # Bounding box with corner accents
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            corner_len = max(8, min(16, (x2 - x1) // 4, (y2 - y1) // 4))
            t = 2
            cv2.line(frame, (x1, y1), (x1 + corner_len, y1), color, t)
            cv2.line(frame, (x1, y1), (x1, y1 + corner_len), color, t)
            cv2.line(frame, (x2, y1), (x2 - corner_len, y1), color, t)
            cv2.line(frame, (x2, y1), (x2, y1 + corner_len), color, t)
            cv2.line(frame, (x1, y2), (x1 + corner_len, y2), color, t)
            cv2.line(frame, (x1, y2), (x1, y2 - corner_len), color, t)
            cv2.line(frame, (x2, y2), (x2 - corner_len, y2), color, t)
            cv2.line(frame, (x2, y2), (x2, y2 - corner_len), color, t)

            # Name label tag above box
            label_y = max(50, y1 - 8)
            tag_w = len(label) * 8 + 12
            cv2.rectangle(frame, (x1, label_y - 18), (x1 + tag_w, label_y + 4), (10, 15, 29), -1)
            cv2.rectangle(frame, (x1, label_y - 18), (x1 + tag_w, label_y + 4), color, 1)
            cv2.putText(
                frame,
                label,
                (x1 + 6, label_y - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                (255, 255, 255),
                1,
                cv2.LINE_AA
            )

            # Action pill below box (e.g. "✓ CHECK-IN (01:20 PM)" or approval badge)
            action = track.action_taken
            if action:
                action_y = min(h - 8, y2 + 22)
                act_text = f"● {action}"
                act_w = len(act_text) * 8 + 12
                cv2.rectangle(frame, (x1, action_y - 16), (x1 + act_w, action_y + 4), (10, 15, 29), -1)
                cv2.rectangle(frame, (x1, action_y - 16), (x1 + act_w, action_y + 4), color, 1)
                cv2.putText(
                    frame,
                    act_text,
                    (x1 + 6, action_y - 3),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.40,
                    color,
                    1,
                    cv2.LINE_AA
                )
            elif state == "UNKNOWN":
                action_y = min(h - 8, y2 + 22)
                acc_status = (track.access_status or "PENDING").upper()
                if acc_status == "APPROVED":
                    act_text = "● ENTRY APPROVED (OWNER)"
                    act_color = (0, 220, 0)
                elif acc_status == "DENIED":
                    act_text = "● ENTRY DENIED (OWNER)"
                    act_color = (0, 0, 220)
                elif acc_status == "ENROLLED":
                    act_text = "● ENROLLED IN SYSTEM"
                    act_color = (255, 180, 0)
                else:
                    act_text = "● AWAITING OWNER REVIEW"
                    act_color = (0, 140, 255)

                act_w = len(act_text) * 8 + 12
                cv2.rectangle(frame, (x1, action_y - 16), (x1 + act_w, action_y + 4), (10, 15, 29), -1)
                cv2.rectangle(frame, (x1, action_y - 16), (x1 + act_w, action_y + 4), act_color, 1)
                cv2.putText(
                    frame,
                    act_text,
                    (x1 + 6, action_y - 3),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.40,
                    act_color,
                    1,
                    cv2.LINE_AA
                )

        return frame

    def get_latest_jpeg_with_seq(self) -> Tuple[bytes, int]:
        """Returns the latest JPEG frame bytes and sequence number for 15 FPS pacing."""
        with self._lock:
            if self.latest_jpeg:
                return self.latest_jpeg, self.latest_jpeg_seq
        return self._get_placeholder_jpeg(), 0

    def _get_placeholder_jpeg(self) -> bytes:
        """Generate sleek placeholder frame reflecting true status and diagnostics."""
        h, w = 360, 640
        placeholder = np.zeros((h, w, 3), dtype=np.uint8)
        placeholder[:] = (10, 15, 29)

        stream_fps = self._calculate_stream_fps()
        if self.status == "connected" and stream_fps > 0:
            status_text = f"{self.mode} LIVE ({stream_fps:.1f} FPS)"
            color = (0, 220, 0)
        elif self.status == "connected":
            status_text = f"{self.mode} CONNECTED (NO FRAMES)"
            color = (0, 200, 255)
        elif self.status == "connecting":
            status_text = f"{self.mode} CONNECTING..."
            color = (0, 200, 255)
        elif self.status == "reconnecting":
            status_text = f"{self.mode} RECONNECTING (Attempt {self.reconnect_attempt})"
            color = (0, 165, 255)
        else:
            status_text = f"{self.mode} DISCONNECTED"
            color = (148, 163, 184)

        sub_text = self.status_message or "Awaiting connection..."
        if len(sub_text) > 65:
            sub_text = sub_text[:62] + "..."

        cv2.putText(placeholder, status_text, (w // 2 - 170, h // 2 - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 2, cv2.LINE_AA)
        cv2.putText(placeholder, sub_text, (w // 2 - 200, h // 2 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (148, 163, 184), 1, cv2.LINE_AA)
        cv2.putText(placeholder, self.name, (w // 2 - 120, h // 2 + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

        ret, jpeg = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return jpeg.tobytes() if ret else b''

    @staticmethod
    def get_static_placeholder_jpeg(message: str = "CAMERA INACTIVE") -> bytes:
        """Generate a static offline placeholder."""
        h, w = 360, 640
        placeholder = np.zeros((h, w, 3), dtype=np.uint8)
        placeholder[:] = (10, 15, 29)
        cv2.putText(placeholder, message, (w // 2 - 110, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 200), 2, cv2.LINE_AA)
        _, enc = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return enc.tobytes()

    def get_status_summary(self) -> Dict[str, Any]:
        """Returns current live health, granular FPS metrics, and full diagnostics of this camera."""
        with self._lock:
            stream_fps = self._calculate_stream_fps()
            display_fps = self._calculate_display_fps()
            ai_fps = self._calculate_ai_fps()
            avg_inf = self._get_avg_inference_ms()
            avg_lat = self._get_avg_latency_ms()

            now = time.time()
            is_receiving_frames = (
                self.status == "connected"
                and stream_fps > 0
                and self.last_frame_time is not None
                and (now - self.last_frame_time < 3.0)
            )
            effective_status = self.status
            effective_msg = self.status_message
            if self.status == "connected" and not is_receiving_frames:
                effective_msg = "Connected over TCP. Waiting for incoming camera frames..."

            parsed_url = urlparse(self.rtsp_url.strip())
            host = parsed_url.hostname or "unknown"
            port = parsed_url.port or (554 if "rtsp" in parsed_url.scheme.lower() else 80)
            path = parsed_url.path or "/live"

            # Track counts
            tracks = self.tracker.get_active_tracks()
            faces_detected = len(tracks)
            faces_recognized = len([t for t in tracks if t.is_confirmed])
            unknown_count = len([t for t in tracks if t.state == "UNKNOWN"])
            too_small_count = len([t for t in tracks if t.state == "FACE_TOO_SMALL"])

            diag = dict(self.last_error_details)
            diag["camera_id"] = self.camera_id
            diag["camera_name"] = self.name
            diag["role"] = self.mode
            diag["redacted_url"] = self.get_redacted_url()
            diag["host"] = diag.get("host") or host
            diag["port"] = diag.get("port") or port
            diag["path"] = diag.get("path") or path
            diag["state"] = effective_status.upper()
            diag["stream_fps"] = round(stream_fps, 1)
            diag["display_fps"] = round(display_fps, 1)
            diag["ai_fps"] = round(ai_fps, 1)
            diag["actual_fps"] = round(stream_fps, 1)
            diag["avg_inference_ms"] = round(avg_inf, 1)
            diag["latency_ms"] = round(avg_lat, 1)
            diag["dropped_frames"] = self.dropped_frames_count
            diag["queue_size"] = 1 if self.latest_raw_frame is not None else 0
            diag["faces_detected"] = faces_detected
            diag["faces_recognized"] = faces_recognized
            diag["unknown_count"] = unknown_count
            diag["too_small_count"] = too_small_count
            diag["last_frame"] = datetime.fromtimestamp(self.last_frame_time).isoformat() if self.last_frame_time else "Never"
            diag["last_connected"] = datetime.fromtimestamp(self.last_connected_time).isoformat() if self.last_connected_time else "Never"
            diag["reconnect_count"] = self.reconnect_attempt
            diag["last_error"] = diag.get("last_error")
            if not diag.get("hint"):
                subnet_hint = self._detect_network_issue(host, port)
                diag["hint"] = subnet_hint or f"Backend host IP is {self._get_local_ip_hint()}. Ensure camera is on same network and port {port} is open."

            return {
                "id": self.camera_id,
                "name": self.name,
                "status": effective_status,
                "status_message": effective_msg,
                "mode": self.mode,
                "location": self.location,
                "rtsp_url": self.get_redacted_url(),
                "stream_fps": round(stream_fps, 1),
                "display_fps": round(display_fps, 1),
                "ai_fps": round(ai_fps, 1),
                "actual_fps": round(stream_fps, 1),
                "avg_inference_ms": round(avg_inf, 1),
                "latency_ms": round(avg_lat, 1),
                "dropped_frames": self.dropped_frames_count,
                "queue_size": 1 if self.latest_raw_frame is not None else 0,
                "target_fps": self.TARGET_FPS,
                "is_receiving_frames": is_receiving_frames,
                "reconnect_attempt": self.reconnect_attempt,
                "last_seen": datetime.fromtimestamp(self.last_seen_time).isoformat() if self.last_seen_time else None,
                "last_frame_time": datetime.fromtimestamp(self.last_frame_time).isoformat() if self.last_frame_time else None,
                "last_connected_time": datetime.fromtimestamp(self.last_connected_time).isoformat() if self.last_connected_time else None,
                "diagnostics": diag,
                "active_persons_count": len(self.active_presence),
                "recent_events": list(self.recent_events),
                "latest_detections": [
                    {
                        "name": d.get("name"),
                        "state": d.get("state"),
                        "similarity": d.get("similarity"),
                        "action_badge": d.get("action_badge"),
                        "checkout_status": d.get("checkout_status"),
                        "is_confirmed": d.get("is_confirmed"),
                        "is_unknown": d.get("is_unknown"),
                        "is_too_small": d.get("is_too_small")
                    }
                    for d in self.latest_detections
                ]
            }


class RTSPManager:
    """
    Central manager for all configured RTSP cameras.
    Controls camera workers, connection tests, and live streams.
    """
    _unknown_access_cache: Dict[int, str] = {}

    @classmethod
    def set_unknown_status(cls, event_id: int, status: str):
        cls._unknown_access_cache[event_id] = status.upper()

    @classmethod
    def get_unknown_status(cls, event_id: Optional[int]) -> Optional[str]:
        if event_id is None:
            return None
        return cls._unknown_access_cache.get(event_id)

    def get_camera_raw_frame(self, camera_id: Optional[int] = None, mode: Optional[str] = None) -> Optional[np.ndarray]:
        """Fetch latest raw frame from active camera worker without opening a duplicate connection."""
        with self._lock:
            if camera_id and camera_id in self.workers:
                return self.workers[camera_id].get_current_raw_frame()
            if mode:
                w = self.get_worker_by_mode(mode)
                if w:
                    return w.get_current_raw_frame()
            for w in self.workers.values():
                if w.running:
                    f = w.get_current_raw_frame()
                    if f is not None:
                        return f
        return None

    def __init__(self, recognition_service, loop: Optional[asyncio.AbstractEventLoop] = None):
        self.recognition_service = recognition_service
        self.loop = loop or asyncio.get_event_loop()
        self.workers: Dict[int, RTSPCameraWorker] = {}
        self._lock = threading.RLock()
        logger.info("RTSPManager initialized (15 FPS Low-Latency Engine with Distance Recognition)")

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        for worker in self.workers.values():
            worker.loop = loop

    async def load_and_start_all(self):
        """Loads all enabled cameras from DB and starts their background workers."""
        try:
            async with AsyncSessionLocal() as session:
                cameras = await RTSPCameraRepository.list_all(session, enabled_only=True)
                logger.info(f"Loaded {len(cameras)} enabled RTSP cameras from database")
                for cam in cameras:
                    self.start_camera(
                        camera_id=cam.id,
                        name=cam.name,
                        rtsp_url=cam.rtsp_url,
                        mode=cam.mode,
                        location=cam.location,
                        username=cam.username,
                        password=cam.password,
                    )
        except Exception as e:
            logger.error(f"Failed to load RTSP cameras on startup: {e}", exc_info=True)

    def start_camera(
        self,
        camera_id: int,
        name: str,
        rtsp_url: str,
        mode: str,
        location: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> RTSPCameraWorker:
        """Start or restart a camera worker."""
        with self._lock:
            if camera_id in self.workers:
                self.workers[camera_id].stop()

            worker = RTSPCameraWorker(
                camera_id=camera_id,
                name=name,
                rtsp_url=rtsp_url,
                mode=mode,
                location=location,
                username=username,
                password=password,
                recognition_service=self.recognition_service,
                loop=self.loop,
            )
            worker.start()
            self.workers[camera_id] = worker
            return worker

    def stop_camera(self, camera_id: int):
        """Stop and remove a camera worker."""
        with self._lock:
            if camera_id in self.workers:
                worker = self.workers.pop(camera_id)
                worker.stop()

    def get_worker(self, camera_id: int) -> Optional[RTSPCameraWorker]:
        with self._lock:
            return self.workers.get(camera_id)

    def connect_camera(self, camera_id: int) -> bool:
        """Manually connect or reconnect a camera worker."""
        with self._lock:
            worker = self.workers.get(camera_id)
            if worker:
                worker.manual_connect()
                return True
            return False

    def disconnect_camera(self, camera_id: int) -> bool:
        """Manually disconnect a camera worker."""
        with self._lock:
            worker = self.workers.get(camera_id)
            if worker:
                worker.manual_disconnect()
                return True
            return False

    def reconnect_camera(self, camera_id: int) -> bool:
        """
        Manually trigger immediate, clean reconnection for a camera.
        Stops the existing worker, releases all OpenCV/FFmpeg handles, and restarts
        fresh worker threads immediately without requiring manual disable/enable toggle.
        """
        with self._lock:
            worker = self.workers.get(camera_id)
            if worker:
                name = worker.name
                rtsp_url = worker.rtsp_url
                mode = worker.mode
                location = worker.location
                username = worker.username
                password = worker.password

                # Stop existing worker and release all handles cleanly
                worker.stop()

                # Start fresh worker
                new_worker = RTSPCameraWorker(
                    camera_id=camera_id,
                    name=name,
                    rtsp_url=rtsp_url,
                    mode=mode,
                    location=location,
                    username=username,
                    password=password,
                    recognition_service=self.recognition_service,
                    loop=self.loop,
                )
                new_worker.start()
                self.workers[camera_id] = new_worker
                logger.info(f"RTSP Camera {camera_id} ('{name}') cleanly reconnected by RTSPManager")
                return True
            return False

    def ensure_camera_running(self, camera) -> Optional[RTSPCameraWorker]:
        """
        Ensures that an enabled camera has an active running worker.
        Does not restart if already running or if user manually disconnected it.
        """
        if not getattr(camera, 'enabled', False):
            return None
        with self._lock:
            worker = self.workers.get(camera.id)
            if worker is None:
                logger.info(f"Auto-starting worker for enabled camera {camera.id} ('{camera.name}')")
                return self.start_camera(
                    camera_id=camera.id,
                    name=camera.name,
                    rtsp_url=camera.rtsp_url,
                    mode=camera.mode,
                    location=camera.location,
                    username=camera.username,
                    password=camera.password
                )
            elif not worker.running and not worker.manual_disconnected:
                logger.info(f"Resuming dormant worker for camera {camera.id} ('{camera.name}')")
                worker.start()
                return worker
            return worker

    def get_worker_by_mode(self, mode: str) -> Optional[RTSPCameraWorker]:
        """Returns the first active running worker matching mode, or any worker matching mode."""
        with self._lock:
            # 1. Prefer running worker with exact mode
            for w in self.workers.values():
                if w.mode.upper() == mode.upper() and w.running:
                    return w
            # 2. Any worker with exact mode
            for w in self.workers.values():
                if w.mode.upper() == mode.upper():
                    return w
            return None

    def shutdown(self):
        """Cleanly shutdown all running camera workers."""
        with self._lock:
            for cid, worker in list(self.workers.items()):
                try:
                    worker.stop()
                except Exception as e:
                    logger.warning(f"Error stopping RTSP worker {cid}: {e}")
            self.workers.clear()
            logger.info("RTSPManager cleanly stopped all camera workers.")

    def test_rtsp_connection(
        self,
        rtsp_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout_seconds: float = 5.0
    ) -> Dict[str, Any]:
        """Test reachability and frame grab of an RTSP stream before saving."""
        url = rtsp_url.strip()
        if not url:
            return {"success": False, "error": "RTSP URL cannot be empty", "message": "URL required"}

        if username and password and "@" not in url:
            try:
                parsed = urlparse(url)
                if parsed.scheme.lower() in ("rtsp", "rtsps", "http", "https"):
                    user_enc = quote_plus(username)
                    pass_enc = quote_plus(password)
                    netloc = f"{user_enc}:{pass_enc}@{parsed.hostname}"
                    if parsed.port:
                        netloc += f":{parsed.port}"
                    url = urlunparse(parsed._replace(netloc=netloc))
            except Exception:
                pass

        reachable, reason = RTSPCameraWorker._check_reachability(url, timeout=min(2.0, timeout_seconds))
        if not reachable:
            return {
                "success": False,
                "error": f"Network reachability check failed: {reason}",
                "message": reason
            }

        t_start = time.time()
        cap = None
        try:
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                return {
                    "success": False,
                    "error": "Failed to open RTSP stream with OpenCV FFmpeg backend",
                    "message": "Stream handshake failed"
                }

            ret, frame = cap.read()
            elapsed_ms = round((time.time() - t_start) * 1000, 1)
            if not ret or frame is None or frame.size == 0:
                return {
                    "success": False,
                    "error": "Opened stream but failed to read initial video frame",
                    "latency_ms": elapsed_ms,
                    "message": "No frame read"
                }

            h, w = frame.shape[:2]
            return {
                "success": True,
                "message": f"Successfully connected ({w}x{h})",
                "resolution": f"{w}x{h}",
                "latency_ms": elapsed_ms,
                "fps": 15.0
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Connection test failed: {str(e)}"
            }
        finally:
            if cap is not None:
                cap.release()

