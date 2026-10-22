"""Ball and player detection (Zero-shot YOLO + 3-frame temporal HSV/motion hybrid)."""

from .detector import (
    BallDetection,
    FrameDetections,
    HybridTennisDetector,
    PlayerDetection,
)

__all__ = [
    "BallDetection",
    "FrameDetections",
    "HybridTennisDetector",
    "PlayerDetection",
]
