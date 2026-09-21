import logging
from dataclasses import dataclass
from typing import Optional
from .head_pose import PoseResult
from .face_quality import QualityResult

logger = logging.getLogger(__name__)

@dataclass
class GuidanceResult:
    """Contains actionable feedback for the user to achieve optimal face positioning."""
    face_detected: bool
    position_ok: bool
    message: str
    severity: str  # 'good', 'warning', 'error'
    status_color: str  # 'green', 'yellow', 'red'
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    quality_score: float = 0.0
    suggested_action: str = "none"  # move_up, move_down, move_left, move_right, move_closer, move_back, hold_still, none
    face_count: int = 0

class CameraGuidanceService:
    """Analyzes face position, distance, count, and head pose to generate real-time dynamic guidance."""

    def assess(
        self,
        pose: Optional[PoseResult] = None,
        quality: Optional[QualityResult] = None,
        face_detected: bool = False,
        face_count: int = 1,
        bbox: Optional[list[int]] = None,
        frame_shape: Optional[tuple[int, int]] = None,
        is_mirrored: bool = True
    ) -> GuidanceResult:
        """Evaluate the current frame state and return actionable guidance based on exact geometry."""
        # 1. Check if face is detected
        if not face_detected or face_count == 0 or bbox is None:
            return GuidanceResult(
                face_detected=False,
                position_ok=False,
                message="FACE NOT DETECTED",
                severity="error",
                status_color="red",
                yaw=0.0,
                pitch=0.0,
                roll=0.0,
                quality_score=0.0,
                suggested_action="none",
                face_count=0
            )

        # 2. Reject multiple faces
        if face_count > 1:
            return GuidanceResult(
                face_detected=True,
                position_ok=False,
                message="ONLY ONE PERSON ALLOWED",
                severity="error",
                status_color="red",
                yaw=pose.yaw if pose else 0.0,
                pitch=pose.pitch if pose else 0.0,
                roll=pose.roll if pose else 0.0,
                quality_score=quality.overall_score if quality else 0.0,
                suggested_action="single_person_only",
                face_count=face_count
            )

        q_score = quality.overall_score if quality else 0.85
        cur_yaw = round(float(pose.yaw), 1) if pose else 0.0
        cur_pitch = round(float(pose.pitch), 1) if pose else 0.0
        cur_roll = round(float(pose.roll), 1) if pose else 0.0

        # Frame geometry
        frame_h = frame_shape[0] if frame_shape and len(frame_shape) >= 2 else 480
        frame_w = frame_shape[1] if frame_shape and len(frame_shape) >= 2 else 640

        bx, by, bw, bh = bbox
        face_cx = bx + bw / 2.0
        face_cy = by + bh / 2.0

        # Target zone: center at (50% W, 45% H)
        target_cx = frame_w * 0.50
        target_cy = frame_h * 0.45
        tol_x = frame_w * 0.12  # tolerance ±12%
        tol_y = frame_h * 0.12  # tolerance ±12%

        # 3. Check Position: Y-axis (Up/Down)
        if face_cy < (target_cy - tol_y):
            # Face is too high up in the camera frame
            return GuidanceResult(
                face_detected=True, position_ok=False, message="MOVE DOWN",
                severity="error", status_color="red", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                quality_score=q_score, suggested_action="move_down", face_count=1
            )
        if face_cy > (target_cy + tol_y):
            # Face is too low in the camera frame
            return GuidanceResult(
                face_detected=True, position_ok=False, message="MOVE UP",
                severity="error", status_color="red", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                quality_score=q_score, suggested_action="move_up", face_count=1
            )

        # 4. Check Position: X-axis (Left/Right)
        # In mirrored user webcam:
        # If user is on the left of screen (face_cx < target_cx - tol_x), user must move RIGHT to center
        # If user is on the right of screen (face_cx > target_cx + tol_x), user must move LEFT to center
        if is_mirrored:
            if face_cx < (target_cx - tol_x):
                return GuidanceResult(
                    face_detected=True, position_ok=False, message="MOVE RIGHT",
                    severity="error", status_color="red", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                    quality_score=q_score, suggested_action="move_right", face_count=1
                )
            if face_cx > (target_cx + tol_x):
                return GuidanceResult(
                    face_detected=True, position_ok=False, message="MOVE LEFT",
                    severity="error", status_color="red", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                    quality_score=q_score, suggested_action="move_left", face_count=1
                )
        else:
            if face_cx < (target_cx - tol_x):
                return GuidanceResult(
                    face_detected=True, position_ok=False, message="MOVE LEFT",
                    severity="error", status_color="red", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                    quality_score=q_score, suggested_action="move_left", face_count=1
                )
            if face_cx > (target_cx + tol_x):
                return GuidanceResult(
                    face_detected=True, position_ok=False, message="MOVE RIGHT",
                    severity="error", status_color="red", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                    quality_score=q_score, suggested_action="move_right", face_count=1
                )

        # 5. Check Distance: Face width ratio relative to frame
        w_ratio = bw / max(frame_w, 1.0)
        if w_ratio < 0.22:
            return GuidanceResult(
                face_detected=True, position_ok=False, message="MOVE CLOSER",
                severity="error", status_color="red", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                quality_score=q_score, suggested_action="move_closer", face_count=1
            )
        if w_ratio > 0.52:
            return GuidanceResult(
                face_detected=True, position_ok=False, message="MOVE BACK",
                severity="error", status_color="red", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                quality_score=q_score, suggested_action="move_back", face_count=1
            )

        # 6. Check Head Orientation (Pitch and Yaw)
        # Pitch: positive = looking down, negative = looking up
        if cur_pitch > 14.0:
            return GuidanceResult(
                face_detected=True, position_ok=False, message="MOVE UP",
                severity="error", status_color="red", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                quality_score=q_score, suggested_action="move_up", face_count=1
            )
        if cur_pitch < -14.0:
            return GuidanceResult(
                face_detected=True, position_ok=False, message="MOVE DOWN",
                severity="error", status_color="red", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                quality_score=q_score, suggested_action="move_down", face_count=1
            )

        # Yaw: looking turned away
        if cur_yaw < -15.0:
            # Looking to left -> move head right
            return GuidanceResult(
                face_detected=True, position_ok=False, message="MOVE RIGHT",
                severity="error", status_color="red", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                quality_score=q_score, suggested_action="move_right", face_count=1
            )
        if cur_yaw > 15.0:
            # Looking to right -> move head left
            return GuidanceResult(
                face_detected=True, position_ok=False, message="MOVE LEFT",
                severity="error", status_color="red", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                quality_score=q_score, suggested_action="move_left", face_count=1
            )

        # 7. Check Face Quality (Blur, Lighting)
        if quality:
            if "too_blurry" in quality.issues or quality.blur_score < 0.20:
                return GuidanceResult(
                    face_detected=True, position_ok=False, message="HOLD STILL",
                    severity="warning", status_color="yellow", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                    quality_score=q_score, suggested_action="hold_still", face_count=1
                )
            if "bad_lighting" in quality.issues:
                return GuidanceResult(
                    face_detected=True, position_ok=False, message="IMPROVE LIGHTING",
                    severity="warning", status_color="yellow", yaw=cur_yaw, pitch=cur_pitch, roll=cur_roll,
                    quality_score=q_score, suggested_action="improve_lighting", face_count=1
                )

        # 8. All Valid! Green state: HOLD STILL
        return GuidanceResult(
            face_detected=True,
            position_ok=True,
            message="HOLD STILL",
            severity="good",
            status_color="green",
            yaw=cur_yaw,
            pitch=cur_pitch,
            roll=cur_roll,
            quality_score=q_score,
            suggested_action="hold_still",
            face_count=1
        )
