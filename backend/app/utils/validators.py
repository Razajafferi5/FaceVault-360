import re
import numpy as np

def validate_person_identifier(identifier: str) -> bool:
    """Validate that the identifier matches the required format."""
    if not identifier or not isinstance(identifier, str):
        return False
    pattern = re.compile(r"^[a-zA-Z0-9-]{3,50}$")
    return bool(pattern.match(identifier))

def validate_embedding_dimension(embedding: np.ndarray, expected_dim: int = 512) -> bool:
    """Check if the embedding has the correct dimensions."""
    if not isinstance(embedding, np.ndarray):
        return False
    if embedding.ndim != 1:
        return False
    if embedding.shape[0] != expected_dim:
        return False
    return True

def validate_image_format(data: bytes) -> bool:
    """Check if the bytes correspond to a valid JPEG or PNG signature."""
    if not data or len(data) < 8:
        return False
    
    # JPEG magic bytes
    if data.startswith(b'\xff\xd8\xff'):
        return True
    
    # PNG magic bytes
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return True
        
    return False

def validate_confidence_range(value: float) -> float:
    """Clamp the confidence value between 0.0 and 1.0."""
    try:
        val = float(value)
        return max(0.0, min(1.0, val))
    except (ValueError, TypeError):
        return 0.0
