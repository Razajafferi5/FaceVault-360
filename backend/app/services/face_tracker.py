import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

@dataclass
class TrackedFace:
    """Represents a temporally tracked face across video frames."""
    track_id: int
    bbox: List[int]                     # [x, y, w, h] in frame coordinates
    first_seen: float                   # Timestamp first detected
    last_seen: float                    # Timestamp most recently observed
    last_ai_time: float                 # Timestamp last AI inference was run on this track
    
    # State: "DETECTING", "FACE_TOO_SMALL", "LOW_QUALITY", "MATCHING", "CONFIRMED", "UNKNOWN"
    state: str = "DETECTING"
    
    # Candidate matching state
    candidate_id: Optional[int] = None
    candidate_name: Optional[str] = None
    candidate_score: float = 0.0
    consecutive_matches: int = 0
    consecutive_unknowns: int = 0
    
    # Confirmed identity state
    confirmed_id: Optional[int] = None
    confirmed_name: Optional[str] = None
    confirmed_score: float = 0.0
    is_confirmed: bool = False
    last_match_time: float = 0.0
    
    # Attendance event state
    action_taken: Optional[str] = None
    action_time_str: Optional[str] = None
    checkout_status: Optional[str] = None
    badge_color: Tuple[int, int, int] = (0, 220, 0)
    attendance_dispatched: bool = False

    # Unknown person access tracking state
    unknown_event_id: Optional[int] = None
    unknown_logged: bool = False
    unknown_cooldown_until: float = 0.0
    access_status: Optional[str] = None  # "PENDING", "APPROVED", "DENIED", "ENROLLED"
    best_face_area: float = 0.0
    is_valid_face: bool = False
    quality_score: float = 0.0
    best_quality_score: float = 0.0
    embedding: Optional[Any] = None
    last_heartbeat_time: float = 0.0
    pending_detections: int = 0

    def get_center(self) -> Tuple[float, float]:
        """Return (cx, cy) centroid of the face."""
        x, y, w, h = self.bbox[:4]
        return (x + w / 2.0, y + h / 2.0)

    def get_area(self) -> float:
        """Return area of the face bounding box."""
        return float(self.bbox[2] * self.bbox[3])


class FaceTracker:
    """
    Lightweight IoU & Centroid Face Tracker with Temporal Multi-Frame Confirmation.
    
    - Correlates face bounding boxes across 15 FPS display frames.
    - Prevents identity flickering: candidate must be matched over CONFIRMATION_FRAMES.
    - Holds confirmed identity for RECOGNITION_HOLD_TIME during head turns or brief occlusion.
    - Requires UNKNOWN_HOLD_TIME of consistent non-matches before declaring UNKNOWN.
    - Distinguishes FACE_TOO_SMALL without falsely declaring UNKNOWN.
    """

    def __init__(
        self,
        confirmation_frames: int = 2,
        recognition_hold_time: float = 2.5,
        unknown_hold_time: float = 1.2,
        track_expiry_time: float = 3.5,
        min_face_size: int = 36
    ):
        self.confirmation_frames = confirmation_frames
        self.recognition_hold_time = recognition_hold_time
        self.unknown_hold_time = unknown_hold_time
        self.track_expiry_time = track_expiry_time
        self.min_face_size = min_face_size

        self.tracks: Dict[int, TrackedFace] = {}
        self._next_track_id: int = 1

    @staticmethod
    def _compute_iou(bb1: List[int], bb2: List[int]) -> float:
        """Compute Intersection over Union between two [x, y, w, h] boxes."""
        x1_a, y1_a, w_a, h_a = bb1[:4]
        x2_a, y2_a = x1_a + w_a, y1_a + h_a

        x1_b, y1_b, w_b, h_b = bb2[:4]
        x2_b, y2_b = x1_b + w_b, y1_b + h_b

        xi1 = max(x1_a, x1_b)
        yi1 = max(y1_a, y1_b)
        xi2 = min(x2_a, x2_b)
        yi2 = min(y2_a, y2_b)

        inter_w = max(0, xi2 - xi1)
        inter_h = max(0, yi2 - yi1)
        inter_area = inter_w * inter_h

        area_a = max(0, w_a * h_a)
        area_b = max(0, w_b * h_b)
        union_area = area_a + area_b - inter_area

        if union_area <= 0:
            return 0.0
        return float(inter_area) / float(union_area)

    @staticmethod
    def _centroid_distance(bb1: List[int], bb2: List[int]) -> float:
        """Normalized centroid Euclidean distance."""
        cx1, cy1 = bb1[0] + bb1[2] / 2.0, bb1[1] + bb1[3] / 2.0
        cx2, cy2 = bb2[0] + bb2[2] / 2.0, bb2[1] + bb2[3] / 2.0
        return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5

    def update_from_ai_results(self, raw_faces: List[Dict[str, Any]], now: float) -> List[TrackedFace]:
        """
        Updates tracks from new AI recognition results.
        raw_faces: list of face dicts from recognition_service.recognize_frame()
        """
        matched_track_ids = set()

        for face in raw_faces:
            bbox = face.get("bbox")
            if not bbox or len(bbox) < 4:
                continue

            person_id = face.get("person_id")
            name = face.get("name")
            similarity = float(face.get("similarity", 0.0))
            status = face.get("status", "unknown")
            is_unknown = face.get("is_unknown", True)
            is_too_small = face.get("is_too_small", False) or min(bbox[2], bbox[3]) < self.min_face_size

            # Find best existing track by IoU and distance
            best_iou = 0.0
            best_tid = None
            for tid, track in self.tracks.items():
                if tid in matched_track_ids:
                    continue
                iou = self._compute_iou(track.bbox, bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid

            # If IoU is low, check centroid proximity (for fast moving faces)
            if best_tid is None or best_iou < 0.20:
                min_dist = float("inf")
                for tid, track in self.tracks.items():
                    if tid in matched_track_ids:
                        continue
                    dist = self._centroid_distance(track.bbox, bbox)
                    diag = (track.bbox[2] ** 2 + track.bbox[3] ** 2) ** 0.5
                    if dist < max(diag * 0.8, 40.0) and dist < min_dist:
                        min_dist = dist
                        best_tid = tid

            if best_tid is not None and (best_iou >= 0.20 or min_dist < 80.0):
                # Update existing track with smoothed bbox
                track = self.tracks[best_tid]
                matched_track_ids.add(best_tid)
                # Exponential smoothing of bounding box for stability
                alpha = 0.75
                track.bbox = [
                    int(alpha * bbox[0] + (1 - alpha) * track.bbox[0]),
                    int(alpha * bbox[1] + (1 - alpha) * track.bbox[1]),
                    int(alpha * bbox[2] + (1 - alpha) * track.bbox[2]),
                    int(alpha * bbox[3] + (1 - alpha) * track.bbox[3]),
                ]
                track.last_seen = now
                track.last_ai_time = now
            else:
                # Create brand-new track
                best_tid = self._next_track_id
                self._next_track_id += 1
                track = TrackedFace(
                    track_id=best_tid,
                    bbox=list(bbox),
                    first_seen=now,
                    last_seen=now,
                    last_ai_time=now
                )
                self.tracks[best_tid] = track
                matched_track_ids.add(best_tid)

            is_valid_face = face.get("is_valid_face", False)
            quality_score = float(face.get("quality_score", 0.0))
            track.is_valid_face = is_valid_face
            track.quality_score = quality_score

            # Process AI result into track state machine
            if not is_valid_face or status in ("non_face_object", "no_embedding"):
                # Inanimate object, wall, fan, or chair - completely ignore from unknown logs
                track.state = "OBJECT_IGNORED"
                track.consecutive_matches = 0
                track.consecutive_unknowns = 0
                track.badge_color = (100, 100, 100)
            elif is_too_small:
                track.state = "FACE_TOO_SMALL"
                track.consecutive_matches = 0
                track.consecutive_unknowns = 0
                track.badge_color = (0, 165, 255)  # Amber
            elif status == "low_quality":
                track.state = "LOW_QUALITY"
                track.badge_color = (0, 140, 255)  # Orange
            elif not is_unknown and person_id is not None:
                # Valid candidate matched!
                if track.candidate_id == person_id:
                    track.consecutive_matches += 1
                else:
                    track.candidate_id = person_id
                    track.candidate_name = name
                    track.consecutive_matches = 1

                track.candidate_score = similarity
                track.consecutive_unknowns = 0

                # Check if threshold of consecutive frames met
                if track.consecutive_matches >= self.confirmation_frames:
                    track.is_confirmed = True
                    track.confirmed_id = person_id
                    track.confirmed_name = name
                    track.confirmed_score = max(track.confirmed_score, similarity)
                    track.state = "CONFIRMED"
                    track.last_match_time = now
                    track.badge_color = (0, 220, 0)  # Green
                else:
                    if not track.is_confirmed:
                        track.state = "MATCHING"
                        track.badge_color = (255, 180, 0)  # Cyan/Blue
            elif is_valid_face and is_unknown:
                # Frame produced confirmed valid human face that does not match any employee
                track.consecutive_unknowns += 1
                track.consecutive_matches = max(0, track.consecutive_matches - 1)

                # Check if we are in recognition hold window
                if track.is_confirmed and (now - track.last_match_time < self.recognition_hold_time):
                    # Retain confirmed identity through temporary turns/shadows
                    track.state = "CONFIRMED"
                elif (now - track.first_seen >= self.unknown_hold_time) and track.consecutive_unknowns >= 2:
                    track.state = "UNKNOWN"
                    track.is_confirmed = False
                    track.confirmed_id = None
                    track.confirmed_name = None
                    track.badge_color = (0, 0, 220)  # Red
                else:
                    if not track.is_confirmed:
                        track.state = "MATCHING"
                        track.badge_color = (255, 180, 0)
            else:
                track.state = "MATCHING"

        # Cleanup expired tracks
        self.cleanup_expired(now)
        return list(self.tracks.values())

    def cleanup_expired(self, now: float):
        """Remove tracks that have not been observed within expiry window."""
        expired = [tid for tid, t in self.tracks.items() if now - t.last_seen > self.track_expiry_time]
        for tid in expired:
            del self.tracks[tid]

    def get_active_tracks(self) -> List[TrackedFace]:
        """Return all currently active tracks."""
        return list(self.tracks.values())

