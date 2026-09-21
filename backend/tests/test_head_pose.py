import pytest
from app.services.head_pose import HeadPoseEstimator

@pytest.fixture
def estimator():
    # HeadPoseEstimator takes no arguments in __init__
    return HeadPoseEstimator()

def test_get_label_frontal(estimator):
    label = estimator.get_label(0.0, 0.0)
    assert label == 'frontal'

def test_get_label_left(estimator):
    label = estimator.get_label(-25.0, 0.0)
    assert label == 'left'

def test_get_label_right(estimator):
    label = estimator.get_label(25.0, 0.0)
    assert label == 'right'

def test_get_label_up(estimator):
    label = estimator.get_label(0.0, -20.0)
    assert label == 'up'

def test_get_label_down(estimator):
    label = estimator.get_label(0.0, 20.0)
    assert label == 'down'

def test_is_within_recognition_range_frontal(estimator):
    assert estimator.is_within_recognition_range(5.0, 3.0) is True

def test_is_within_recognition_range_extreme(estimator):
    assert estimator.is_within_recognition_range(60.0, 0.0) is False
    assert estimator.is_within_recognition_range(0.0, 45.0) is False

def test_is_within_recognition_range_boundary(estimator):
    # Threshold 45.0 for yaw and 30.0 for pitch
    assert estimator.is_within_recognition_range(44.9, 0.0) is True
    assert estimator.is_within_recognition_range(45.1, 0.0) is False
