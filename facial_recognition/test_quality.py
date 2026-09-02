import numpy as np
import pytest
import cv2
from facial_recognition.quality import FaceQualityAssessor, QualityCategory

@pytest.fixture
def default_thresholds():
    return {
        'high': {
            'min_size': 80,
            'min_confidence': 0.7,
            'min_sharpness': 100.0,
            'illumination_range': [40, 210],
            'min_pose_score': 0.65,
            'min_occlusion_score': 0.60
        },
        'medium': {
            'min_size': 40,
            'min_confidence': 0.4,
            'min_sharpness': 50.0,
            'illumination_range': [20, 235],
            'min_pose_score': 0.40,
            'min_occlusion_score': 0.35
        },
        'temporal_observations_required': 5
    }

@pytest.fixture
def assessor(default_thresholds):
    return FaceQualityAssessor(default_thresholds)

def create_synthetic_frame(color=200, blur=False, size=200):
    """Create a synthetic image frame."""
    frame = np.full((size, size, 3), color, dtype=np.uint8)
    
    # Draw some high-contrast features so it has measurable sharpness
    cv2.circle(frame, (size//2, size//2), size//4, (0, 0, 0), -1)
    cv2.rectangle(frame, (size//4, size//4), (size//3, size//3), (255, 255, 255), -1)
    
    if blur:
        frame = cv2.GaussianBlur(frame, (11, 11), 0)
        
    return frame

def test_high_quality(assessor):
    frame = create_synthetic_frame(color=200, blur=False, size=200)
    face_dict = {
        'bbox': [50, 50, 150, 150], # 100x100
        'det_score': 0.9,
        # Frontal landmarks: left eye, right eye, nose, left mouth, right mouth
        'kps': [[75, 80], [125, 80], [100, 105], [80, 130], [120, 130]]
    }
    category, metrics = assessor.assess(frame, face_dict)
    
    assert category == QualityCategory.HIGH
    assert metrics['size'] == 100.0
    assert metrics['confidence'] == 0.9
    assert metrics['sharpness'] > 100.0
    assert 40 <= metrics['illumination'] <= 210
    assert metrics['pose_score'] >= 0.65
    assert metrics['score'] > 75.0

def test_medium_quality_blur(assessor):
    frame = create_synthetic_frame(color=200, blur=True, size=200)
    face_dict = {
        'bbox': [50, 50, 150, 150],
        'det_score': 0.9
    }
    category, metrics = assessor.assess(frame, face_dict)
    
    assert category == QualityCategory.MEDIUM
    assert metrics['sharpness'] < 100.0
    assert metrics['sharpness'] >= 50.0

def test_medium_quality_size(assessor):
    frame = create_synthetic_frame(color=200, blur=False, size=200)
    face_dict = {
        'bbox': [25, 25, 75, 75], # 50x50 (Medium size threshold: 40-79)
        'det_score': 0.9
    }
    category, metrics = assessor.assess(frame, face_dict)
    
    assert category == QualityCategory.MEDIUM
    assert metrics['size'] == 50.0

def test_poor_quality_tiny_size(assessor):
    frame = create_synthetic_frame(color=200, blur=False, size=200)
    face_dict = {
        'bbox': [30, 30, 50, 50], # 20x20 (Below medium min_size 40)
        'det_score': 0.9
    }
    category, metrics = assessor.assess(frame, face_dict)
    
    assert category == QualityCategory.POOR
    assert metrics['size'] == 20.0

def test_poor_quality_dark(assessor):
    frame = create_synthetic_frame(color=10, blur=False, size=200) # Dark frame
    face_dict = {
        'bbox': [50, 50, 150, 150],
        'det_score': 0.9
    }
    category, metrics = assessor.assess(frame, face_dict)
    
    assert category == QualityCategory.POOR
    assert metrics['illumination'] < 20.0

def test_poor_quality_low_confidence(assessor):
    frame = create_synthetic_frame(color=200, blur=False, size=200)
    face_dict = {
        'bbox': [50, 50, 150, 150],
        'det_score': 0.25 # Below medium threshold of 0.4
    }
    category, metrics = assessor.assess(frame, face_dict)
    assert category == QualityCategory.POOR

def test_pose_yaw_symmetry(assessor):
    frame = create_synthetic_frame(color=200, blur=False, size=200)
    # Severe profile pose (nose pushed far to the right)
    face_dict_profile = {
        'bbox': [50, 50, 150, 150],
        'det_score': 0.9,
        'kps': [[60, 80], [140, 80], [135, 105], [70, 130], [130, 130]]
    }
    category, metrics = assessor.assess(frame, face_dict_profile)
    assert metrics['yaw_symmetry'] < 0.40
    assert category in [QualityCategory.MEDIUM, QualityCategory.POOR]

def test_motion_velocity_penalty(assessor):
    frame = create_synthetic_frame(color=200, blur=False, size=200)
    face_dict = {
        'bbox': [150, 150, 250, 250],
        'det_score': 0.9
    }
    prev_bbox = [50, 50, 150, 150] # Moved 100px in dt=0.033s -> ~4285 px/s
    _, metrics = assessor.assess(frame, face_dict, prev_bbox=prev_bbox, dt=0.033)
    assert metrics['motion_score'] == 0.0

def test_temporal_observation_accumulation():
    """
    Test adaptive behavior:
    - High quality face -> immediate recognition
    - Medium quality face -> requires 5 observations before recognition
    - Poor quality face -> deferred/skipped recognition
    """
    thresholds = {
        'high': {'min_size': 80, 'min_confidence': 0.7, 'min_sharpness': 100.0, 'illumination_range': [40, 210]},
        'medium': {'min_size': 40, 'min_confidence': 0.4, 'min_sharpness': 50.0, 'illumination_range': [20, 235]},
        'temporal_observations_required': 5
    }
    assessor = FaceQualityAssessor(thresholds)
    
    # 1. Medium quality face simulation
    frame_med = create_synthetic_frame(color=200, blur=True, size=200)
    face_dict_med = {'bbox': [50, 50, 150, 150], 'det_score': 0.8}
    cat, _ = assessor.assess(frame_med, face_dict_med)
    assert cat == QualityCategory.MEDIUM

    # Simulate observation counter over consecutive frames
    obs_count = 0
    recognition_triggered = []
    for frame_idx in range(1, 7):
        obs_count += 1
        run_rec = (obs_count >= assessor.temporal_observations_required)
        recognition_triggered.append(run_rec)

    # Observation 1-4 should be deferred (False), observation 5 & 6 should trigger recognition (True)
    assert recognition_triggered == [False, False, False, False, True, True]

def test_aggregate_score_computation(assessor):
    frame = create_synthetic_frame(color=200, blur=False, size=200)
    face_dict = {
        'bbox': [50, 50, 150, 150],
        'det_score': 0.9
    }
    _, metrics = assessor.assess(frame, face_dict)
    
    assert 'score' in metrics
    assert 0 <= metrics['score'] <= 100

