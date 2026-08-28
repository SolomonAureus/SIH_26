import numpy as np
from vita.rgb.wound_model import FUSegNetSegmenter


def bare_segmenter(minimum=5):
    segmenter = FUSegNetSegmenter.__new__(FUSegNetSegmenter)
    segmenter.minimum_wound_area = minimum
    return segmenter


def test_empty_prediction_returns_no_detection():
    result = bare_segmenter()._largest_region(np.zeros((30, 30), np.uint8), np.zeros((30, 30), np.float32))
    assert not result.detected and result.bounding_box is None


def test_largest_region_is_selected():
    binary = np.zeros((40, 50), np.uint8)
    binary[2:5, 2:5] = 1
    binary[15:30, 20:40] = 1
    result = bare_segmenter()._largest_region(binary, binary.astype(np.float32) * .8)
    assert result.bounding_box == (20, 15, 20, 15)
    assert int(result.mask.sum()) == 300

