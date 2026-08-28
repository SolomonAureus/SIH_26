import numpy as np
from vita.rgb.config import QualityConfig
from vita.rgb.quality import FrameQualityFilter, QualityStatus, RejectionReason


def test_rejects_underexposed_frame():
    result = FrameQualityFilter(QualityConfig(blur_threshold=0)).evaluate(np.full((80, 80, 3), 5, np.uint8))
    assert result.reason is RejectionReason.UNDEREXPOSED


def test_rejects_overexposed_frame():
    result = FrameQualityFilter(QualityConfig(blur_threshold=0)).evaluate(np.full((80, 80, 3), 250, np.uint8))
    assert result.reason is RejectionReason.OVEREXPOSED


def test_rejects_blurred_frame():
    config = QualityConfig(blur_threshold=10, min_brightness=0, max_brightness=255)
    assert FrameQualityFilter(config).evaluate(np.full((80, 80, 3), 120, np.uint8)).reason is RejectionReason.BLUR


def test_accepts_detailed_frame():
    frame = np.random.default_rng(42).integers(55, 205, (100, 100, 3), dtype=np.uint8)
    assert FrameQualityFilter(QualityConfig(blur_threshold=10)).evaluate(frame).status is QualityStatus.GOOD

