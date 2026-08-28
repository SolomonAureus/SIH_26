"""End-to-end live RGB acquisition orchestration."""

import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from .aggregator import FeatureAggregator
from .camera import OpenCVCamera
from .config import RGBConfig
from .dashboard_bridge import DashboardPublisher
from .quality import FrameQualityFilter, QualityResult
from .rgb_features import EmptyMaskError, extract_rgb_features
from .wound_model import SegmentationResult, WoundSegmenter


class NoWoundTimeoutError(TimeoutError):
    pass


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    features: dict[str, float | int | str]
    json_path: Path
    csv_path: Path | None
    inference_fps: float


class RGBPipeline:
    def __init__(self, config: RGBConfig, segmenter: WoundSegmenter) -> None:
        config.validate()
        self.config, self.segmenter = config, segmenter
        self.quality = FrameQualityFilter(config.quality)
        self.aggregator = FeatureAggregator(config.target_good_frames)
        self.inference_times: list[float] = []
        self.dashboard = DashboardPublisher(config.output_directory) if config.publish_dashboard else None
        self._last_camera_publish = 0.0

    @property
    def inference_fps(self) -> float:
        return 0.0 if not self.inference_times else float(1 / np.mean(self.inference_times))

    def run(self) -> AcquisitionResult | None:
        print("VITA RGB Acquisition")
        print(f"Device: {self.segmenter.device_name}\nCamera: {self.config.camera_index}")
        print(f"Target samples: {self.config.target_good_frames}\n")
        last_accepted = time.monotonic()
        cancelled = False
        camera = OpenCVCamera(
            self.config.camera_index, self.config.camera_width,
            self.config.camera_height, self.config.sampling_fps,
            self._publish_camera_frame if self.dashboard is not None else None,
        )
        try:
            with camera:
                for captured in camera.sampled_frames():
                    frame = captured.image
                    quality = self.quality.evaluate(frame)
                    if not quality.is_good:
                        reason = quality.reason.value if quality.reason else "quality"
                        print(f"[-] REJECT {reason}")
                        cancelled = self._display_and_publish(
                            frame, None, quality, f"REJECTED: {reason.upper()}"
                        )
                        self._timeout(last_accepted)
                        if cancelled:
                            break
                        continue
                    started = time.perf_counter()
                    try:
                        segmentation = self.segmenter.segment(frame)
                    except Exception as exc:
                        print(f"[-] MODEL ERROR {exc}")
                        cancelled = self._display_and_publish(frame, None, quality, "MODEL ERROR")
                        self._timeout(last_accepted)
                        if cancelled:
                            break
                        continue
                    self.inference_times.append(time.perf_counter() - started)
                    if not segmentation.detected:
                        print("[-] NO WOUND")
                        cancelled = self._display_and_publish(
                            frame, segmentation, quality, "NO WOUND DETECTED"
                        )
                        self._timeout(last_accepted)
                        if cancelled:
                            break
                        continue
                    try:
                        features = extract_rgb_features(frame, segmentation.mask)
                    except EmptyMaskError:
                        continue
                    self.aggregator.add(features)
                    last_accepted = time.monotonic()
                    print(f"[{self.aggregator.count}/{self.config.target_good_frames}] GOOD area={int(features['wound_area_px'])}")
                    cancelled = self._display_and_publish(
                        frame, segmentation, quality, "GOOD", features
                    )
                    if cancelled or self.aggregator.complete:
                        break
        finally:
            if self.config.preview:
                cv2.destroyAllWindows()
        if cancelled or not self.aggregator.complete:
            return None
        result = self.aggregator.aggregate()
        result["model_device"] = self.segmenter.device_name
        result["model_inference_fps"] = self.inference_fps
        json_path, csv_path = self._save(result)
        print(f"\nAcquisition complete.\nSaved -> {json_path}")
        return AcquisitionResult(result, json_path, csv_path, self.inference_fps)

    def _publish_camera_frame(self, frame: np.ndarray) -> None:
        """Keep the dashboard camera fluid while model inference runs separately."""
        now = time.monotonic()
        if now - self._last_camera_publish < 0.1:
            return
        self._last_camera_publish = now
        if self.dashboard is not None:
            self.dashboard.publish_camera(frame)

    def _timeout(self, last_accepted: float) -> None:
        if time.monotonic() - last_accepted >= self.config.no_wound_timeout_seconds:
            raise NoWoundTimeoutError(
                f"No usable wound observation for {self.config.no_wound_timeout_seconds:.0f} seconds"
            )

    def _display_and_publish(
        self, frame: np.ndarray, segmentation: SegmentationResult | None,
        quality: QualityResult, status: str,
        features: dict[str, float] | None = None,
    ) -> bool:
        display = self._annotate(frame, segmentation, quality, status)
        if self.dashboard is not None:
            self.dashboard.publish(
                display, status, self.aggregator.count,
                self.config.target_good_frames, quality, segmentation,
                features, self.inference_fps,
            )
        if not self.config.preview:
            return False
        cv2.imshow("VITA RGB wound localization - q to quit", display)
        return (cv2.waitKey(1) & 0xFF) == ord("q")

    def _annotate(
        self, frame: np.ndarray, segmentation: SegmentationResult | None,
        quality: QualityResult, status: str,
    ) -> np.ndarray:
        display = frame.copy()
        if segmentation and segmentation.detected:
            overlay = np.zeros_like(display)
            overlay[segmentation.mask > 0] = (40, 40, 255)
            display = cv2.addWeighted(display, 1.0, overlay, 0.42, 0)
            x, y, width, height = segmentation.bounding_box
            cv2.rectangle(display, (x, y), (x + width, y + height), (255, 255, 255), 2)
            cv2.putText(display, f"area={int(segmentation.mask.sum())} conf={segmentation.confidence:.2f}",
                        (x, max(22, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 2)
        colour = (60, 220, 60) if status == "GOOD" else (50, 170, 255)
        cv2.rectangle(display, (0, 0), (display.shape[1], 70), (15, 15, 15), -1)
        cv2.putText(display, status, (14, 28), cv2.FONT_HERSHEY_SIMPLEX, .72, colour, 2)
        cv2.putText(display, f"accepted {self.aggregator.count}/{self.config.target_good_frames}  blur {quality.blur_score:.0f}  light {quality.brightness_mean:.0f}",
                    (14, 55), cv2.FONT_HERSHEY_SIMPLEX, .5, (235, 235, 235), 1)
        return display

    def _save(self, result: dict[str, float | int | str]) -> tuple[Path, Path | None]:
        output = self.config.output_directory
        output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_path = output / f"rgb_assessment_{stamp}.json"
        json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        csv_path = None
        if self.config.append_csv:
            csv_path = output / "rgb_assessments.csv"
            exists = csv_path.exists() and csv_path.stat().st_size > 0
            with csv_path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(result.keys()))
                if not exists:
                    writer.writeheader()
                writer.writerow(result)
        return json_path, csv_path
