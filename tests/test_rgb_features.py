import numpy as np
import pytest
from vita.rgb.rgb_features import EmptyMaskError, extract_rgb_features


def test_extracts_masked_features():
    frame = np.zeros((60, 80, 3), np.uint8)
    frame[10:30, 20:40] = (10, 20, 200)
    mask = np.zeros((60, 80), np.uint8)
    mask[10:30, 20:40] = 1
    features = extract_rgb_features(frame, mask)
    assert features["wound_area_px"] == 400
    assert features["mean_R"] == pytest.approx(200)
    assert features["normalized_red_ratio"] == pytest.approx(200 / 230)


def test_empty_mask_is_rejected():
    with pytest.raises(EmptyMaskError):
        extract_rgb_features(np.zeros((20, 20, 3), np.uint8), np.zeros((20, 20), np.uint8))

