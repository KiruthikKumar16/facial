"""Facial recognition module for surveillance system."""

from .detector import InsightFaceDetector
from .recognizer import Recognizer
from .logger import DetectionLogger
from .pending import PendingSaver
from .capture import CameraCapture

__all__ = [
    'InsightFaceDetector',
    'Recognizer', 
    'DetectionLogger',
    'PendingSaver',
    'CameraCapture',
]
