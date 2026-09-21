from dataclasses import dataclass
from app.core.config import Settings

@dataclass
class AuthorizationDecision:
    granted: bool
    reason: str
    details: dict

class AuthorizationService:
    """Fail-closed authorization logic."""
    
    def __init__(self, settings: Settings):
        self.settings = settings

    def check(
        self,
        person_id: int | None,
        person_status: str | None,
        confidence: float,
        quality_score: float,
        liveness_score: float,
        pose_within_range: bool
    ) -> AuthorizationDecision:
        """
        Evaluates recognition metrics against thresholds to make a fail-closed access decision.
        """
        details = {
            "person_id": person_id,
            "confidence": confidence,
            "quality_score": quality_score,
            "liveness_score": liveness_score,
            "pose_within_range": pose_within_range
        }
        
        # 1. Unknown person
        if person_id is None:
            return AuthorizationDecision(granted=False, reason="unknown_person", details=details)
            
        # 2. Low confidence
        if confidence < self.settings.RECOGNITION_THRESHOLD:
            return AuthorizationDecision(granted=False, reason="low_confidence", details=details)
            
        # 3. Person inactive
        if person_status != 'active':
            return AuthorizationDecision(granted=False, reason="person_inactive", details=details)
            
        # 4. Poor quality
        if quality_score < self.settings.MIN_FACE_QUALITY:
            return AuthorizationDecision(granted=False, reason="poor_quality", details=details)
            
        # 5. Liveness failed (assume a liveness threshold in settings, fallback to 0.5)
        liveness_threshold = getattr(self.settings, 'LIVENESS_THRESHOLD', 0.5)
        if liveness_score < liveness_threshold:
            return AuthorizationDecision(granted=False, reason="liveness_failed", details=details)
            
        # 6. Bad pose
        if not pose_within_range:
            return AuthorizationDecision(granted=False, reason="bad_pose", details=details)
            
        # 7. All checks pass
        return AuthorizationDecision(granted=True, reason="authorized", details=details)
