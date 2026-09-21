import logging
import cv2
import hashlib
import threading
from dataclasses import dataclass, field
import numpy as np

try:
    from insightface.app import FaceAnalysis
except (ImportError, Exception):
    FaceAnalysis = None

logger = logging.getLogger(__name__)

@dataclass
class DetectedFace:
    """Represents a detected face with its attributes."""
    bbox: list[int]  # x, y, w, h
    confidence: float
    landmarks: np.ndarray  # 5-point landmarks
    embedding: np.ndarray | None = None  # 512-d, filled on request
    pose: list[float] = field(default_factory=list)  # [pitch, yaw, roll]
    age: int | None = None
    gender: str | None = None
    raw_face: object = None

class FaceDetector:
    """Wrapper for InsightFace detector and embedding extractor with OpenCV/Haar Cascade fallback."""
    def __init__(self, model_name: str = 'buffalo_sc'):
        """Initialize the FaceDetector."""
        self.app = None
        if FaceAnalysis is not None:
            try:
                self.app = FaceAnalysis(name=model_name, providers=['CPUExecutionProvider'])
                self.app.prepare(ctx_id=-1, det_size=(640, 640), det_thresh=0.40)
                logger.info(f"InsightFace detector initialized with model {model_name} (det_thresh=0.40 for distance detection)")
            except Exception as e:
                logger.warning(f"Failed to load InsightFace ({e}); fallback detector will be active.")
                self.app = None

        # Load built-in OpenCV Haar Cascade as an ultra-fast, robust fallback
        self._cascade_lock = threading.Lock()
        try:
            import os
            assets_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "haarcascade_frontalface_default.xml"))
            if os.path.exists(assets_path):
                self.cascade = cv2.CascadeClassifier(assets_path)
            else:
                self.cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        except Exception as e:
            logger.error(f"Failed to load Haar Cascade: {e}")
            self.cascade = None

    def _generate_fallback_embedding(self, face_crop: np.ndarray) -> np.ndarray:
        """Generates a consistent, deterministic 512-d normalized facial feature vector from face patch."""
        try:
            resized = cv2.resize(face_crop, (112, 112))
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY) if len(resized.shape) == 3 else resized
            
            # Extract multiple statistical and frequency features across patches
            blocks = []
            for r in range(4):
                for c in range(4):
                    block = gray[r*28:(r+1)*28, c*28:(c+1)*28]
                    blocks.extend([
                        np.mean(block),
                        np.std(block),
                        float(np.median(block)),
                        float(np.percentile(block, 25)),
                        float(np.percentile(block, 75)),
                        float(np.min(block)),
                        float(np.max(block)),
                        float(np.var(block))
                    ])
            
            # Compute 2D DCT / gradient descriptors
            grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
            grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
            mag, _ = cv2.cartToPolar(grad_x, grad_y)
            hist = cv2.calcHist([mag], [0], None, [64], [0, 256]).flatten()
            
            # Combine to 512 values
            combined = np.concatenate([np.array(blocks, dtype=np.float32), hist])
            if len(combined) < 512:
                combined = np.pad(combined, (0, 512 - len(combined)), mode='reflect')
            else:
                combined = combined[:512]
                
            norm = np.linalg.norm(combined)
            if norm > 0:
                combined = combined / norm
            return combined.astype(np.float32)
        except Exception as e:
            logger.error(f"Fallback embedding error: {e}")
            vec = np.zeros(512, dtype=np.float32)
            vec[0] = 1.0
            return vec

    @staticmethod
    def is_valid_face_candidate(
        bbox: list[int],
        landmarks: np.ndarray | None = None,
        confidence: float = 0.0,
        min_dim: int = 32
    ) -> bool:
        """
        Validates human face geometry to reject non-human objects (fans, chairs, walls, doors, etc.).
        """
        if len(bbox) < 4:
            return False
        x, y, w, h = bbox[:4]
        if w < min_dim or h < min_dim:
            return False

        # Aspect ratio check: Human faces in surveillance feeds have w/h between 0.55 and 1.40
        aspect_ratio = float(w) / float(h) if h > 0 else 0.0
        if not (0.55 <= aspect_ratio <= 1.40):
            return False

        # Detection confidence threshold: reject low-confidence noise textures
        if confidence < 0.45:
            return False

        # Landmark verification: if 5-point landmarks are provided, check geometry
        if landmarks is not None and isinstance(landmarks, np.ndarray) and landmarks.shape == (5, 2):
            if np.any(landmarks):
                # Landmark 0: left eye, Landmark 1: right eye
                eye_dist = float(np.linalg.norm(landmarks[0] - landmarks[1]))
                if eye_dist < 8.0:
                    return False
                # Verify points lie roughly within or near the bounding box
                for pt in landmarks:
                    if pt[0] < x - w * 0.4 or pt[0] > x + w * 1.4 or pt[1] < y - h * 0.4 or pt[1] > y + h * 1.4:
                        return False

        return True

    def detect(self, frame: np.ndarray) -> list[DetectedFace]:
        """Detect faces in a given frame, filtering out non-human objects."""
        if self.app is not None and frame is not None:
            try:
                faces = self.app.get(frame)
                results = []
                for face in faces:
                    x1, y1, x2, y2 = face.bbox
                    x, y, w, h = int(x1), int(y1), int(x2 - x1), int(y2 - y1)
                    confidence = float(getattr(face, 'det_score', 0.95))
                    landmarks = getattr(face, 'kps', np.zeros((5, 2)))

                    # Reject non-human geometry or noise
                    if not self.is_valid_face_candidate([x, y, w, h], landmarks, confidence):
                        continue

                    pose = list(face.pose) if getattr(face, 'pose', None) is not None else []
                    det_face = DetectedFace(
                        bbox=[x, y, w, h],
                        confidence=confidence,
                        landmarks=landmarks,
                        pose=pose,
                        age=getattr(face, 'age', None),
                        gender=getattr(face, 'gender', None),
                        raw_face=face
                    )
                    results.append(det_face)
                return results
            except Exception as e:
                logger.warning(f"InsightFace detection failed: {e}")

        # Fallback to OpenCV Cascade with stricter parameters
        if self.cascade is not None and frame is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
            with self._cascade_lock:
                faces = self.cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=7, minSize=(36, 36))
            results = []
            for (x, y, w, h) in faces:
                if self.is_valid_face_candidate([int(x), int(y), int(w), int(h)], None, 0.60):
                    results.append(DetectedFace(
                        bbox=[int(x), int(y), int(w), int(h)],
                        confidence=0.60,
                        landmarks=np.zeros((5, 2)),
                        pose=[0.0, 0.0, 0.0]
                    ))
            return results
        return []

    def detect_faces(self, frame: np.ndarray) -> list[DetectedFace]:
        """Alias for detect() for API consistency."""
        return self.detect(frame)

    def extract_embedding(self, frame: np.ndarray, face_data=None) -> np.ndarray | None:
        """Extract a 512-d normalized ArcFace embedding for a face. Never returns fake vectors for unknown logging."""
        if face_data is not None:
            if hasattr(face_data, 'normed_embedding') and face_data.normed_embedding is not None:
                return np.array(face_data.normed_embedding, dtype=np.float32)
            if hasattr(face_data, 'raw_face') and getattr(face_data.raw_face, 'normed_embedding', None) is not None:
                return np.array(face_data.raw_face.normed_embedding, dtype=np.float32)
            if hasattr(face_data, 'embedding') and face_data.embedding is not None:
                return np.array(face_data.embedding, dtype=np.float32)

        if self.app is not None and frame is not None:
            try:
                faces = self.app.get(frame)
                if faces and getattr(faces[0], 'normed_embedding', None) is not None:
                    return np.array(faces[0].normed_embedding, dtype=np.float32)
            except Exception as e:
                logger.warning(f"InsightFace extraction error: {e}")

        return None

    def detect_and_embed(self, frame: np.ndarray) -> list[DetectedFace]:
        """Detect faces and extract genuine ArcFace embeddings. Rejects non-face objects."""
        if self.app is not None and frame is not None:
            try:
                faces = self.app.get(frame)
                results = []
                for face in faces:
                    x1, y1, x2, y2 = face.bbox
                    x, y, w, h = int(x1), int(y1), int(x2 - x1), int(y2 - y1)
                    confidence = float(getattr(face, 'det_score', 0.95))
                    landmarks = getattr(face, 'kps', np.zeros((5, 2)))

                    if not self.is_valid_face_candidate([x, y, w, h], landmarks, confidence):
                        continue

                    pose = list(face.pose) if getattr(face, 'pose', None) is not None else []
                    emb = getattr(face, 'normed_embedding', None)
                    if emb is not None:
                        emb = np.array(emb, dtype=np.float32)

                    results.append(DetectedFace(
                        bbox=[x, y, w, h],
                        confidence=confidence,
                        landmarks=landmarks,
                        embedding=emb,
                        pose=pose,
                        age=getattr(face, 'age', None),
                        gender=getattr(face, 'gender', None),
                        raw_face=face
                    ))
                return results
            except Exception as e:
                logger.warning(f"InsightFace detect_and_embed failed: {e}")

        # Fallback via Cascade (without fake embeddings)
        faces = self.detect(frame)
        for face in faces:
            face.embedding = None
        return faces
