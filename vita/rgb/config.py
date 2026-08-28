"""Central configuration for the VITA RGB acquisition pipeline."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class QualityConfig:
    blur_threshold: float = 75.0
    min_brightness: float = 35.0
    max_brightness: float = 225.0
    max_dark_fraction: float = 0.70
    max_bright_fraction: float = 0.70
    dark_pixel_value: int = 20
    bright_pixel_value: int = 235
    motion_threshold: float | None = None


@dataclass(slots=True)
class RGBConfig:
    camera_index: int | str = 0
    camera_width: int = 640
    camera_height: int = 480
    sampling_fps: float = 5.0
    target_good_frames: int = 10
    preview: bool = True
    quality: QualityConfig = field(default_factory=QualityConfig)
    model_repo_path: Path = Path("models/FUSegNet")
    checkpoint_path: Path = Path(
        "models/FUSegNet/checkpoints/"
        "Unet_pscsev1_efficientnet-b7_2023-02-28_10-05-44/best_model.pth"
    )
    model_input_size: int = 224
    mask_threshold: float = 0.50
    minimum_wound_area: int = 500
    device: str = "auto"
    no_wound_timeout_seconds: float = 30.0
    output_directory: Path = Path("outputs")
    append_csv: bool = True
    publish_dashboard: bool = True

    def validate(self) -> None:
        if self.camera_width <= 0 or self.camera_height <= 0:
            raise ValueError("Camera dimensions must be positive")
        if self.sampling_fps <= 0 or self.target_good_frames <= 0:
            raise ValueError("Sampling FPS and target frames must be positive")
        if not 0 < self.mask_threshold < 1:
            raise ValueError("mask_threshold must be between 0 and 1")
        if self.minimum_wound_area <= 0:
            raise ValueError("minimum_wound_area must be positive")
        if self.device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto, cpu, or cuda")
