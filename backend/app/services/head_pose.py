import logging
import cv2
import os
import threading
import numpy as np
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class PoseResult:
    """Represents the estimated 3D head pose."""
    yaw: float    # degrees — POSITIVE = user turned RIGHT (face moves LEFT in raw frame)
    pitch: float  # degrees — POSITIVE = user tilted DOWN (chin down)
    roll: float   # degrees
    label: str    # 'frontal', 'left', 'right', 'up', 'down'
    is_frontal: bool
    is_within_recognition_range: bool

class HeadPoseEstimator:
    """Estimates head pose using facial geometry and eye landmarks."""
    
    def __init__(self):
        """Initialize detector cascades for head pose estimation."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        assets_dir = os.path.abspath(os.path.join(current_dir, "..", "assets"))
        
        face_cascade_path = os.path.join(assets_dir, "haarcascade_frontalface_default.xml")
        eye_cascade_path = os.path.join(assets_dir, "haarcascade_eye.xml")
        
        self._cascade_lock = threading.Lock()
        self.face_cascade = cv2.CascadeClassifier(face_cascade_path)
        self.eye_cascade = cv2.CascadeClassifier(eye_cascade_path)

    def estimate(self, frame: np.ndarray) -> list[PoseResult]:
        """Estimate the head pose for all faces in the frame."""
        if frame is None or self.face_cascade.empty():
            return []

        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
            h, w = gray.shape[:2]

            # Fast downscaled face detection (25x speedup: ~30ms vs ~720ms on 1080p/720p)
            if w > 320:
                scale = 320.0 / float(w)
                small_w = 320
                small_h = max(1, int(h * scale))
                small_gray = cv2.resize(gray, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
                inv_scale = float(w) / 320.0

                with self._cascade_lock:
                    faces_small = self.face_cascade.detectMultiScale(
                        small_gray,
                        scaleFactor=1.15,
                        minNeighbors=3,
                        minSize=(20, 20)
                    )
                faces = [
                    (int(fx * inv_scale), int(fy * inv_scale), int(fw * inv_scale), int(fh * inv_scale))
                    for (fx, fy, fw, fh) in faces_small
                ]
            else:
                with self._cascade_lock:
                    faces = self.face_cascade.detectMultiScale(
                        gray,
                        scaleFactor=1.15,
                        minNeighbors=3,
                        minSize=(40, 40)
                    )

            results = []
            for (x, y, w, h) in faces:
                yaw, pitch, roll = self._estimate_pose_from_roi(gray, x, y, w, h)
                label = self.get_label(yaw, pitch)
                is_frontal = abs(yaw) < 15 and abs(pitch) < 15
                is_within = self.is_within_recognition_range(yaw, pitch)

                results.append(PoseResult(
                    yaw=yaw,
                    pitch=pitch,
                    roll=roll,
                    label=label,
                    is_frontal=is_frontal,
                    is_within_recognition_range=is_within
                ))
            return results
        except Exception as e:
            logger.error(f"Error estimating head pose: {e}")
            return []

    def _estimate_pose_from_roi(self, gray: np.ndarray, x: int, y: int, w: int, h: int) -> tuple[float, float, float]:
        """
        Estimate yaw and pitch from a face ROI using a dual-method approach:
        1. Eye geometry (fast, accurate for near-frontal faces)
        2. Facial asymmetry fallback (works when face is turned and eyes aren't detected)

        SIGN CONVENTION (matches POSE_STEPS in enrollment.py):
          YAW:   POSITIVE = user turned RIGHT  (face features shift LEFT in raw frame)
                 NEGATIVE = user turned LEFT   (face features shift RIGHT in raw frame)
          PITCH: POSITIVE = user tilted DOWN   (chin towards chest)
                 NEGATIVE = user tilted UP     (chin away from chest)
        
        NOTE: The frontend captures raw video (no flip) so the raw frame is the
        mirror-image of what the user sees. When the user's head turns to their LEFT,
        in the raw frame the face appears to move to the RIGHT side.
        """
        face_roi = gray[y:y+h, x:x+w]
        yaw = 0.0
        pitch = 0.0
        roll = 0.0

        # --- Method 1: Eye geometry ---
        with self._cascade_lock:
            eyes = self.eye_cascade.detectMultiScale(
                face_roi,
                scaleFactor=1.08,
                minNeighbors=2,
                minSize=(max(10, int(w * 0.10)), max(10, int(h * 0.10)))
            )

        eye_yaw_valid = False
        if isinstance(eyes, (list, tuple, np.ndarray)) and len(eyes) >= 2:
            eye_list = [tuple(e) for e in eyes]
            # Filter to upper 65% of face ROI (eyes should be in upper portion)
            eye_list = [e for e in eye_list if (e[1] + e[3] / 2.0) < h * 0.65]
            if len(eye_list) >= 2:
                eyes_sorted = sorted(eye_list, key=lambda e: e[0])
                e1 = eyes_sorted[0]   # left eye in image (user's right eye in mirror)
                e2 = eyes_sorted[-1]  # right eye in image (user's left eye in mirror)
                e1_cx = float(e1[0]) + float(e1[2]) / 2.0
                e1_cy = float(e1[1]) + float(e1[3]) / 2.0
                e2_cx = float(e2[0]) + float(e2[2]) / 2.0
                e2_cy = float(e2[1]) + float(e2[3]) / 2.0

                # Roll from inter-eye angle
                dy = e2_cy - e1_cy
                dx = e2_cx - e1_cx
                roll = float(np.degrees(np.arctan2(dy, dx))) if dx != 0 else 0.0

                # Yaw: eye midpoint offset relative to face center
                # When user turns RIGHT → face features (eyes) shift LEFT in raw image → mid_x < center → negative offset → yaw POSITIVE (right)
                # When user turns LEFT  → face features (eyes) shift RIGHT in raw image → mid_x > center → positive offset → yaw NEGATIVE (left)
                mid_x = (e1_cx + e2_cx) / 2.0
                offset_x = (mid_x - w / 2.0) / max(w / 2.0, 1.0)  # -1..+1
                # Invert: shift RIGHT in image = face turned LEFT = NEGATIVE yaw
                yaw = float(-offset_x * 55.0)

                # Pitch: eye midpoint vertical position
                mid_y = (e1_cy + e2_cy) / 2.0
                expected_y = float(h) * 0.38
                offset_y = (mid_y - expected_y) / max(float(h) * 0.45, 1.0)
                pitch = float(offset_y * 45.0)

                eye_yaw_valid = True
            elif len(eye_list) == 1:
                # 1 eye detected (common during side head turns)
                e = eye_list[0]
                cx = float(e[0]) + float(e[2]) / 2.0
                cy = float(e[1]) + float(e[3]) / 2.0
                offset_x = (cx - w / 2.0) / max(w / 2.0, 1.0)
                # If eye is to image left (cx < w/2) -> other eye turned away, user turned RIGHT -> positive yaw
                # If eye is to image right (cx > w/2) -> other eye turned away, user turned LEFT -> negative yaw
                yaw = float(-offset_x * 48.0)
                pitch = float((cy - h * 0.38) / max(h * 0.40, 1.0) * 40.0)
                eye_yaw_valid = True
        elif isinstance(eyes, (list, tuple, np.ndarray)) and len(eyes) == 1:
            e = tuple(eyes[0])
            cx = float(e[0]) + float(e[2]) / 2.0
            cy = float(e[1]) + float(e[3]) / 2.0
            offset_x = (cx - w / 2.0) / max(w / 2.0, 1.0)
            yaw = float(-offset_x * 48.0)
            pitch = float((cy - h * 0.38) / max(h * 0.40, 1.0) * 40.0)
            eye_yaw_valid = True

        # --- Method 2: Facial asymmetry fallback (left vs right half brightness) ---
        if not eye_yaw_valid:
            upper_roi = face_roi[int(h * 0.15):int(h * 0.75), :]  # Upper 15%-75% of face
            if upper_roi.size > 0:
                mid_col = upper_roi.shape[1] // 2
                left_half = upper_roi[:, :mid_col]
                right_half = upper_roi[:, mid_col:]
                left_mean = float(np.mean(left_half)) if left_half.size > 0 else 128.0
                right_mean = float(np.mean(right_half)) if right_half.size > 0 else 128.0
                # asymmetry: positive = right side brighter (more face on left = turned RIGHT = positive yaw)
                #            negative = left side brighter (more face on right = turned LEFT = negative yaw)
                denom = max((left_mean + right_mean) / 2.0, 1.0)
                asymmetry = (right_mean - left_mean) / denom
                yaw = float(asymmetry * 50.0)

                # Vertical pitch via top vs bottom brightness
                mid_row = upper_roi.shape[0] // 2
                top_half = upper_roi[:mid_row, :]
                bot_half = upper_roi[mid_row:, :]
                top_mean = float(np.mean(top_half)) if top_half.size > 0 else 128.0
                bot_mean = float(np.mean(bot_half)) if bot_half.size > 0 else 128.0
                # When tilting up, forehead receives more light -> top brighter -> negative pitch
                # When tilting down, chin/nose receives more light -> bottom brighter -> positive pitch
                v_asym = (bot_mean - top_mean) / max((top_mean + bot_mean) / 2.0, 1.0)
                pitch = float(v_asym * 45.0)

        yaw = max(-75.0, min(75.0, yaw))
        pitch = max(-60.0, min(60.0, pitch))
        return round(yaw, 1), round(pitch, 1), round(roll, 1)

    def estimate_from_bbox(self, frame: np.ndarray, bbox: list[int]) -> PoseResult:
        """Estimate 3D head pose directly from an already detected face bounding box."""
        if frame is None or len(bbox) < 4:
            return PoseResult(0.0, 0.0, 0.0, 'frontal', True, True)

        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
            fh, fw = gray.shape[:2]
            bx, by, bw, bh = bbox
            x1 = max(0, int(bx))
            y1 = max(0, int(by))
            x2 = min(fw, int(bx + bw))
            y2 = min(fh, int(by + bh))
            w = max(1, x2 - x1)
            h = max(1, y2 - y1)

            yaw, pitch, roll = self._estimate_pose_from_roi(gray, x1, y1, w, h)

            yaw = max(-75.0, min(75.0, yaw))
            pitch = max(-60.0, min(60.0, pitch))
            label = self.get_label(yaw, pitch)
            is_frontal = abs(yaw) < 14 and abs(pitch) < 14
            is_within = self.is_within_recognition_range(yaw, pitch)

            return PoseResult(
                yaw=round(yaw, 1),
                pitch=round(pitch, 1),
                roll=round(roll, 1),
                label=label,
                is_frontal=is_frontal,
                is_within_recognition_range=is_within
            )
        except Exception as e:
            logger.error(f"Error in estimate_from_bbox: {e}")
            return PoseResult(0.0, 0.0, 0.0, 'frontal', True, True)

    def get_label(self, yaw: float, pitch: float) -> str:
        """Classify the pose direction based on yaw and pitch.
        
        POSITIVE yaw = user turned RIGHT
        NEGATIVE yaw = user turned LEFT
        """
        if abs(yaw) < 14 and abs(pitch) < 14:
            return 'frontal'
        if yaw < -14:
            return 'left'    # user turned left
        if yaw > 14:
            return 'right'   # user turned right
        if pitch < -14:
            return 'up'
        if pitch > 14:
            return 'down'
        return 'frontal'

    def is_within_recognition_range(self, yaw: float, pitch: float, max_yaw: float = 55.0, max_pitch: float = 40.0) -> bool:
        """Check if pose is within valid range for recognition."""
        return abs(yaw) <= max_yaw and abs(pitch) <= max_pitch

    def get_mediapipe_landmarks(self, frame: np.ndarray) -> list[np.ndarray]:
        """Extract synthetic landmarks for faces."""
        poses = self.estimate(frame)
        if not poses:
            return []
        return [np.zeros((478, 3), dtype=np.float32) for _ in poses]

    def close(self) -> None:
        """Clean up resources."""
        pass
