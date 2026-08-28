"""Publish the latest RGB inference result for the local BUERLYPH dashboard."""

import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from .quality import QualityResult
from .wound_model import SegmentationResult


class DashboardPublisher:
    """Atomically replace the dashboard preview and status files."""

    def __init__(self, output_directory: str | Path) -> None:
        self.output_directory = Path(output_directory)
        self.camera_path = self.output_directory / "live_camera.jpg"
        self.preview_path = self.output_directory / "live_preview.jpg"
        self.status_path = self.output_directory / "live_status.json"

    def publish_camera(self, frame: np.ndarray) -> None:
        """Publish a fast, unannotated camera frame independently of inference."""
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self._write_jpeg(frame, self.camera_path, "live_camera.tmp.jpg", quality=76)

    def publish(
        self,
        frame: np.ndarray,
        status: str,
        accepted_frames: int,
        target_frames: int,
        quality: QualityResult,
        segmentation: SegmentationResult | None = None,
        features: dict[str, float] | None = None,
        inference_fps: float = 0.0,
    ) -> None:
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self._write_jpeg(frame, self.preview_path, "live_preview.tmp.jpg", quality=88)

        features = features or {}
        bounding_box = None
        confidence = None
        if segmentation is not None and segmentation.detected:
            bounding_box = list(segmentation.bounding_box or ())
            confidence = float(segmentation.confidence)

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "accepted_frames": accepted_frames,
            "target_frames": target_frames,
            "complete": accepted_frames >= target_frames,
            "wound_area_px": self._number(features.get("wound_area_px")),
            "confidence": confidence,
            "bounding_box": bounding_box,
            "mean_R": self._number(features.get("mean_R")),
            "mean_G": self._number(features.get("mean_G")),
            "mean_B": self._number(features.get("mean_B")),
            "normalized_red_ratio": self._number(features.get("normalized_red_ratio")),
            "grayscale_std": self._number(features.get("grayscale_std")),
            "blur_score": float(quality.blur_score),
            "brightness_mean": float(quality.brightness_mean),
            "inference_fps": float(inference_fps),
        }
        status_temp = self.output_directory / "live_status.tmp.json"
        status_temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        status_temp.replace(self.status_path)

    @staticmethod
    def _number(value: object) -> float | None:
        return float(value) if value is not None else None

    def _write_jpeg(
        self, frame: np.ndarray, destination: Path, temporary_name: str, quality: int,
    ) -> None:
        encoded, image = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not encoded:
            raise RuntimeError("Could not encode dashboard preview frame")
        temporary = self.output_directory / temporary_name
        temporary.write_bytes(image.tobytes())
        temporary.replace(destination)
