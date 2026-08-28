"""Fast image-quality checks performed before wound inference."""

from dataclasses import dataclass
from enum import Enum

import cv2
import numpy as np

from .config import QualityConfig


class QualityStatus(str, Enum):
    GOOD = "GOOD"
    REJECTED = "REJECTED"


class RejectionReason(str, Enum):
    MALFORMED = "malformed frame"
    UNDEREXPOSED = "underexposed"
    OVEREXPOSED = "overexposed"
    BLUR = "blur"
    MOTION = "motion"


@dataclass(frozen=True, slots=True)
class QualityResult:
    status: QualityStatus
    reason: RejectionReason | None
    blur_score: float
    brightness_mean: float
    motion_score: float | None = None

    @property
    def is_good(self) -> bool:
        return self.status is QualityStatus.GOOD


class FrameQualityFilter:
    def __init__(self, config: QualityConfig) -> None:
        self.config = config
        self._previous_gray: np.ndarray | None = None

    def evaluate(self, frame: np.ndarray) -> QualityResult:
        if frame is None or frame.ndim != 3 or frame.shape[2] != 3 or frame.size == 0:
            return QualityResult(QualityStatus.REJECTED, RejectionReason.MALFORMED, 0, 0)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(gray))
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        dark = float(np.mean(gray <= self.config.dark_pixel_value))
        bright = float(np.mean(gray >= self.config.bright_pixel_value))
        motion = None
        if self._previous_gray is not None and self.config.motion_threshold is not None:
            previous = cv2.resize(self._previous_gray, (gray.shape[1], gray.shape[0]))
            motion = float(np.mean(cv2.absdiff(gray, previous)))
        self._previous_gray = gray
        reason = None
        if brightness < self.config.min_brightness or dark > self.config.max_dark_fraction:
            reason = RejectionReason.UNDEREXPOSED
        elif brightness > self.config.max_brightness or bright > self.config.max_bright_fraction:
            reason = RejectionReason.OVEREXPOSED
        elif blur < self.config.blur_threshold:
            reason = RejectionReason.BLUR
        elif motion is not None and motion > (self.config.motion_threshold or float("inf")):
            reason = RejectionReason.MOTION
        if reason:
            return QualityResult(QualityStatus.REJECTED, reason, blur, brightness, motion)
        return QualityResult(QualityStatus.GOOD, None, blur, brightness, motion)

