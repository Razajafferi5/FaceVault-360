import logging
import cv2
import numpy as np
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class QualityResult:
    overall_score: float        # 0.0-1.0 combined
    blur_score: float           # higher = sharper
    brightness_score: float
    contrast_score: float
    face_size_score: float
    landmark_visibility: float
    is_acceptable: bool
    is_valid_face: bool = True  # True if candidate passes human face geometry and landmark checks
    is_too_small: bool = False  # True if face is smaller than minimum recognizable resolution
    min_dimension: int = 0      # min(w, h) in pixels
    issues: list[str] = field(default_factory=list) # e.g., ['face_too_small', 'too_blurry', 'too_dark']
    guidance_message: str = ""  # human-readable guidance

class FaceQualityChecker:
    """Evaluates the quality of a detected face crop with distance-aware metrics."""

    MIN_FACE_PIXELS: int = 36    # Minimum recognizable face width/height in pixels
    OPTIMAL_FACE_PIXELS: int = 64 # Size at which resolution is deemed fully optimal

    def check_blur(self, face_crop: np.ndarray) -> float:
        """Check image sharpness using Laplacian variance normalized for face crop scale."""
        try:
            if face_crop.size == 0:
                return 0.0
            gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY) if len(face_crop.shape) == 3 else face_crop
            variance = cv2.Laplacian(gray, cv2.CV_64F).var()
            # Variance > 150 indicates sharp facial edges even on distance crops
            return min(max(variance / 250.0, 0.0), 1.0)
        except Exception as e:
            logger.error(f"Error checking blur: {e}")
            return 0.0

    def check_brightness(self, face_crop: np.ndarray) -> float:
        """Evaluate average brightness of the face crop."""
        try:
            if face_crop.size == 0:
                return 0.0
            gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY) if len(face_crop.shape) == 3 else face_crop
            mean_val = np.mean(gray)
            if mean_val < 35:
                return max(0.0, mean_val / 35.0)
            elif mean_val > 230:
                return max(0.0, (255 - mean_val) / 25.0)
            return 1.0
        except Exception as e:
            logger.error(f"Error checking brightness: {e}")
            return 0.0

    def check_contrast(self, face_crop: np.ndarray) -> float:
        """Evaluate image contrast via standard deviation."""
        try:
            if face_crop.size == 0:
                return 0.0
            gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY) if len(face_crop.shape) == 3 else face_crop
            std = np.std(gray)
            return min(max(std / 40.0, 0.0), 1.0)
        except Exception as e:
            logger.error(f"Error checking contrast: {e}")
            return 0.0

    def check_face_size(self, bbox: list[int], frame_shape: tuple) -> tuple[float, bool, int]:
        """
        Evaluate face size in absolute pixels for distance-aware recognition.
        Returns: (size_score, is_too_small, min_dimension)
        """
        try:
            x, y, w, h = bbox[:4]
            min_dim = int(min(w, h))

            if min_dim < self.MIN_FACE_PIXELS:
                # Face genuinely too small to extract reliable ArcFace embeddings
                size_score = max(0.0, float(min_dim) / float(self.MIN_FACE_PIXELS) * 0.3)
                return size_score, True, min_dim
            elif min_dim < self.OPTIMAL_FACE_PIXELS:
                # Distance face: perfectly usable, scale smoothly from 0.70 to 1.0
                scale = float(min_dim - self.MIN_FACE_PIXELS) / float(self.OPTIMAL_FACE_PIXELS - self.MIN_FACE_PIXELS)
                size_score = 0.70 + 0.30 * scale
                return min(1.0, size_score), False, min_dim
            else:
                # Optimal face resolution
                return 1.0, False, min_dim
        except Exception as e:
            logger.error(f"Error checking face size: {e}")
            return 0.0, True, 0

    def check_landmark_visibility(self, landmarks: np.ndarray | None, bbox: list[int] | None = None) -> float:
        """Check if 5-point landmarks are present and satisfy realistic human facial geometry."""
        if landmarks is None or len(landmarks) < 5:
            return 0.0
        # Check if landmarks have non-zero coordinates
        if isinstance(landmarks, np.ndarray) and not np.any(landmarks):
            return 0.0

        if bbox and len(bbox) >= 4:
            x, y, w, h = bbox[:4]
            # Verify eye-to-eye distance
            eye_dist = float(np.linalg.norm(landmarks[0] - landmarks[1]))
            if eye_dist < max(8.0, w * 0.12):
                return 0.2

            # Verify landmarks are located inside or near bbox
            for pt in landmarks:
                if pt[0] < x - w * 0.3 or pt[0] > x + w * 1.3 or pt[1] < y - h * 0.3 or pt[1] > y + h * 1.3:
                    return 0.2

        return 1.0

    def assess(self, frame: np.ndarray, bbox: list[int], landmarks: np.ndarray | None = None) -> QualityResult:
        """Assess overall face quality with distance awareness and actionable guidance."""
        issues = []
        try:
            x, y, w, h = bbox[:4]
            x, y = max(0, x), max(0, y)
            w = min(frame.shape[1] - x, w)
            h = min(frame.shape[0] - y, h)

            face_size_score, is_too_small, min_dim = self.check_face_size(bbox, frame.shape)
            if is_too_small:
                issues.append("face_too_small")

            # Aspect ratio check
            aspect_ratio = float(w) / float(h) if h > 0 else 0.0
            if not (0.55 <= aspect_ratio <= 1.45):
                issues.append("invalid_aspect_ratio")

            face_crop = frame[y:y+h, x:x+w]
            if face_crop.size == 0 or w <= 0 or h <= 0:
                return QualityResult(
                    overall_score=0.0,
                    blur_score=0.0,
                    brightness_score=0.0,
                    contrast_score=0.0,
                    face_size_score=0.0,
                    landmark_visibility=0.0,
                    is_acceptable=False,
                    is_valid_face=False,
                    is_too_small=True,
                    min_dimension=0,
                    issues=["invalid_bbox"],
                    guidance_message="NO FACE DETECTED"
                )

            blur_score = self.check_blur(face_crop)
            brightness_score = self.check_brightness(face_crop)
            contrast_score = self.check_contrast(face_crop)
            landmark_score = self.check_landmark_visibility(landmarks, bbox)

            # Balanced quality score across realistic security camera distances
            overall_score = (
                blur_score * 0.35 +
                brightness_score * 0.20 +
                contrast_score * 0.15 +
                face_size_score * 0.20 +
                landmark_score * 0.10
            )

            if blur_score < 0.15:
                issues.append("too_blurry")
            if brightness_score < 0.40:
                issues.append("bad_lighting")
            if landmark_score < 0.50:
                issues.append("missing_landmarks")

            # A candidate is only considered a valid human face if it satisfies landmark & aspect ratio constraints
            is_valid_face = (
                (not is_too_small)
                and (landmark_score >= 0.50)
                and ("invalid_aspect_ratio" not in issues)
                and (blur_score >= 0.12)
            )

            # A face is acceptable for biometric match if quality is sufficient
            is_acceptable = (
                is_valid_face
                and (overall_score >= 0.35)
                and ("too_blurry" not in issues)
                and ("missing_landmarks" not in issues)
            )

            result = QualityResult(
                overall_score=round(float(overall_score), 3),
                blur_score=round(float(blur_score), 3),
                brightness_score=round(float(brightness_score), 3),
                contrast_score=round(float(contrast_score), 3),
                face_size_score=round(float(face_size_score), 3),
                landmark_visibility=round(float(landmark_score), 3),
                is_acceptable=is_acceptable,
                is_valid_face=is_valid_face,
                is_too_small=is_too_small,
                min_dimension=min_dim,
                issues=issues,
                guidance_message=""
            )
            result.guidance_message = self.get_guidance(result)
            return result
        except Exception as e:
            logger.error(f"Error during quality assessment: {e}")
            return QualityResult(
                overall_score=0.0,
                blur_score=0.0,
                brightness_score=0.0,
                contrast_score=0.0,
                face_size_score=0.0,
                landmark_visibility=0.0,
                is_acceptable=False,
                is_too_small=True,
                min_dimension=0,
                issues=["assessment_error"],
                guidance_message="QUALITY CHECK FAILED"
            )

    def get_guidance(self, result: QualityResult) -> str:
        """Provide human-readable guidance based on quality issues."""
        if result.is_too_small:
            return "FACE TOO SMALL (MOVE CLOSER)"
        if "bad_lighting" in result.issues:
            return "IMPROVE LIGHTING"
        if "too_blurry" in result.issues:
            return "HOLD STILL"
        if not result.is_acceptable:
            return "LOW QUALITY"
        return "FACE QUALITY OK"
