import pytest
from app.services.authorization import AuthorizationService

@pytest.fixture
def auth_service(settings):
    return AuthorizationService(settings)

def test_authorize_valid_person(auth_service):
    # Dummy mock of Person and RecognitionResult
    person_status = "active"
    result = auth_service.check(
        person_id=1,
        person_status=person_status,
        confidence=0.8,
        quality_score=0.9,
        liveness_score=0.9,
        pose_within_range=True
    )
    assert result.granted is True
    assert result.reason == "authorized"

def test_deny_unknown_person(auth_service):
    result = auth_service.check(
        person_id=None,
        person_status=None,
        confidence=0.8,
        quality_score=0.9,
        liveness_score=0.9,
        pose_within_range=True
    )
    assert result.granted is False
    assert result.reason == "unknown_person"

def test_deny_low_confidence(auth_service):
    result = auth_service.check(
        person_id=1,
        person_status="active",
        confidence=0.3,
        quality_score=0.9,
        liveness_score=0.9,
        pose_within_range=True
    )
    assert result.granted is False
    assert result.reason == "low_confidence"

def test_deny_inactive_person(auth_service):
    result = auth_service.check(
        person_id=1,
        person_status="disabled",
        confidence=0.8,
        quality_score=0.9,
        liveness_score=0.9,
        pose_within_range=True
    )
    assert result.granted is False
    assert result.reason == "person_inactive"

def test_deny_poor_quality(auth_service):
    result = auth_service.check(
        person_id=1,
        person_status="active",
        confidence=0.8,
        quality_score=0.3,
        liveness_score=0.9,
        pose_within_range=True
    )
    assert result.granted is False
    assert result.reason == "poor_quality"

def test_deny_liveness_failed(auth_service):
    result = auth_service.check(
        person_id=1,
        person_status="active",
        confidence=0.8,
        quality_score=0.9,
        liveness_score=0.4,
        pose_within_range=True
    )
    assert result.granted is False
    assert result.reason == "liveness_failed"

def test_deny_bad_pose(auth_service):
    result = auth_service.check(
        person_id=1,
        person_status="active",
        confidence=0.8,
        quality_score=0.9,
        liveness_score=0.9,
        pose_within_range=False
    )
    assert result.granted is False
    assert result.reason == "bad_pose"

def test_deny_multiple_failures(auth_service):
    # Liveness and confidence both low, should return first checked reason
    result = auth_service.check(
        person_id=1,
        person_status="active",
        confidence=0.3,  # fails
        quality_score=0.9,
        liveness_score=0.4, # fails
        pose_within_range=True
    )
    assert result.granted is False
    # Depending on order of checks, usually confidence or liveness.
    # Fail-closed means any failure results in deny.
    assert result.reason in ["low_confidence", "liveness_failed", "poor_quality", "bad_pose", "inactive_person"]

def test_boundary_threshold(auth_service, settings):
    # confidence exactly at threshold (0.45)
    result_granted = auth_service.check(
        person_id=1, person_status="active", confidence=settings.RECOGNITION_THRESHOLD,
        quality_score=0.9, liveness_score=0.9, pose_within_range=True
    )
    assert result_granted.granted is True
    
    result_denied = auth_service.check(
        person_id=1, person_status="active", confidence=settings.RECOGNITION_THRESHOLD - 0.001,
        quality_score=0.9, liveness_score=0.9, pose_within_range=True
    )
    assert result_denied.granted is False

def test_default_is_deny(auth_service):
    # If something unexpected happens or missing data, should default to deny
    result = auth_service.check(
        person_id=1,
        person_status="active",
        confidence=0.8,
        quality_score=None, # Missing data
        liveness_score=0.9,
        pose_within_range=True
    )
    assert result.granted is False
