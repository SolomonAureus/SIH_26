import json

import cv2
import numpy as np

from vita.rgb.dashboard_bridge import DashboardPublisher
from vita.rgb.quality import QualityResult, QualityStatus
from vita.rgb.wound_model import SegmentationResult


def test_dashboard_publisher_writes_preview_and_status(tmp_path):
    frame = np.full((40, 60, 3), 120, dtype=np.uint8)
    mask = np.zeros((40, 60), dtype=np.uint8)
    mask[10:30, 15:45] = 1
    segmentation = SegmentationResult(mask, 0.81, (15, 10, 30, 20))
    quality = QualityResult(QualityStatus.GOOD, None, 101.5, 120.0)

    publisher = DashboardPublisher(tmp_path)
    publisher.publish_camera(frame)
    publisher.publish(
        frame=frame,
        status="GOOD",
        accepted_frames=2,
        target_frames=3,
        quality=quality,
        segmentation=segmentation,
        features={"wound_area_px": 600, "normalized_red_ratio": 0.41},
        inference_fps=0.2,
    )

    preview = cv2.imread(str(tmp_path / "live_preview.jpg"))
    camera = cv2.imread(str(tmp_path / "live_camera.jpg"))
    payload = json.loads((tmp_path / "live_status.json").read_text(encoding="utf-8"))
    assert preview.shape == frame.shape
    assert camera.shape == frame.shape
    assert payload["status"] == "GOOD"
    assert payload["accepted_frames"] == 2
    assert payload["complete"] is False
    assert payload["bounding_box"] == [15, 10, 30, 20]
    assert payload["wound_area_px"] == 600.0
    assert payload["confidence"] == 0.81
