import base64
import logging
import cv2
import numpy as np

logger = logging.getLogger(__name__)

def encode_frame_to_jpeg(frame: np.ndarray, quality: int = 80) -> bytes:
    """Encode a numpy frame to JPEG bytes."""
    try:
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        success, encoded_image = cv2.imencode('.jpg', frame, encode_param)
        if success:
            return encoded_image.tobytes()
        return b""
    except Exception as e:
        logger.error(f"Error encoding frame to JPEG: {e}")
        return b""

def decode_frame_from_bytes(data: bytes) -> np.ndarray | None:
    """Decode JPEG/PNG bytes to numpy frame."""
    try:
        np_arr = np.frombuffer(data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        return frame
    except Exception as e:
        logger.error(f"Error decoding frame from bytes: {e}")
        return None

def decode_base64_frame(b64_string: str) -> np.ndarray | None:
    """Decode a base64 encoded string to a numpy frame."""
    try:
        if "," in b64_string:
            b64_string = b64_string.split(",")[1]
        img_data = base64.b64decode(b64_string)
        return decode_frame_from_bytes(img_data)
    except Exception as e:
        logger.error(f"Error decoding base64 frame: {e}")
        return None

def crop_face(frame: np.ndarray, bbox: list[int], margin: float = 0.2) -> np.ndarray:
    """Crop the face from a frame with an optional margin."""
    try:
        x, y, w, h = bbox
        
        margin_x = int(w * margin)
        margin_y = int(h * margin)
        
        start_x = max(0, x - margin_x)
        start_y = max(0, y - margin_y)
        end_x = min(frame.shape[1], x + w + margin_x)
        end_y = min(frame.shape[0], y + h + margin_y)
        
        return frame[start_y:end_y, start_x:end_x]
    except Exception as e:
        logger.error(f"Error cropping face: {e}")
        return np.zeros((1, 1, 3), dtype=np.uint8)

def resize_frame(frame: np.ndarray, max_width: int = 640) -> np.ndarray:
    """Resize a frame while maintaining aspect ratio."""
    try:
        h, w = frame.shape[:2]
        if w <= max_width:
            return frame
            
        ratio = max_width / float(w)
        new_h = int(h * ratio)
        return cv2.resize(frame, (max_width, new_h), interpolation=cv2.INTER_AREA)
    except Exception as e:
        logger.error(f"Error resizing frame: {e}")
        return frame

def draw_face_overlay(frame: np.ndarray, bbox: list[int], name: str | None, status: str, confidence: float, color: tuple) -> np.ndarray:
    """Draw a bounding box and overlay information on the face."""
    try:
        result = frame.copy()
        x, y, w, h = bbox
        
        cv2.rectangle(result, (x, y), (x + w, y + h), color, 2)
        
        text = f"{name or 'Unknown'} ({confidence:.2f})"
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        thickness = 1
        
        (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
        
        cv2.rectangle(result, (x, max(0, y - text_h - 10)), (x + text_w, y), color, cv2.FILLED)
        
        cv2.putText(result, text, (x, y - 5), font, font_scale, (255, 255, 255), thickness)
        
        return result
    except Exception as e:
        logger.error(f"Error drawing face overlay: {e}")
        return frame
