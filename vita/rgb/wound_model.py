"""Replaceable interface around the frozen pretrained wound segmenter."""

import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np


class ModelConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    mask: np.ndarray
    confidence: float
    bounding_box: tuple[int, int, int, int] | None

    @property
    def detected(self) -> bool:
        return self.bounding_box is not None and bool(np.any(self.mask))


class WoundSegmenter(Protocol):
    device_name: str

    def segment(self, frame: np.ndarray) -> SegmentationResult: ...


class FUSegNetSegmenter:
    """Frozen FUSegNet EfficientNet-B7/pscse checkpoint adapter."""

    def __init__(
        self, checkpoint_path: str | Path, model_repo_path: str | Path,
        device: str = "auto", input_size: int = 224,
        mask_threshold: float = 0.5, minimum_wound_area: int = 500,
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path).expanduser().resolve()
        self.model_repo_path = Path(model_repo_path).expanduser().resolve()
        self.input_size, self.mask_threshold = input_size, mask_threshold
        self.minimum_wound_area = minimum_wound_area
        self.model = self.preprocessing_fn = self._torch = None
        self.device_name = "uninitialized"
        self._load(device)

    def _load(self, requested: str) -> None:
        if not self.model_repo_path.is_dir():
            raise ModelConfigurationError(f"FUSegNet repository not found: {self.model_repo_path}")
        if not self.checkpoint_path.is_file():
            raise ModelConfigurationError(f"FUSegNet checkpoint not found: {self.checkpoint_path}")
        try:
            import torch
        except ImportError as exc:
            raise ModelConfigurationError("PyTorch is not installed; install requirements.txt") from exc
        repo = str(self.model_repo_path)
        if repo not in sys.path:
            sys.path.insert(0, repo)
        try:
            import segmentation_models_pytorch as smp
        except ImportError as exc:
            raise ModelConfigurationError("Could not import the FUSegNet model fork") from exc
        cuda = bool(torch.cuda.is_available())
        if requested == "cuda" and not cuda:
            warnings.warn("CUDA unavailable; falling back to CPU", RuntimeWarning)
        self.device_name = "cuda" if requested != "cpu" and cuda else "cpu"
        self._device = torch.device(self.device_name)
        model = smp.Unet(
            encoder_name="efficientnet-b7", encoder_weights=None, classes=1,
            activation="sigmoid", decoder_attention_type="pscse",
        )
        try:
            checkpoint = torch.load(self.checkpoint_path, map_location=self._device, weights_only=False)
            state = checkpoint.get("state_dict", checkpoint)
            state = {key.removeprefix("module."): value for key, value in state.items()}
            model.load_state_dict(state, strict=True)
        except Exception as exc:
            raise ModelConfigurationError(f"Checkpoint/model incompatibility: {exc}") from exc
        model.to(self._device).eval()
        for parameter in model.parameters():
            parameter.requires_grad_(False)
        self.model, self._torch = model, torch
        self.preprocessing_fn = smp.encoders.get_preprocessing_fn("efficientnet-b7", "imagenet")

    def segment(self, frame: np.ndarray) -> SegmentationResult:
        if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("segment expects a non-empty BGR frame")
        height, width = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (self.input_size, self.input_size), interpolation=cv2.INTER_AREA)
        normalized = self.preprocessing_fn(resized).astype(np.float32)
        tensor = self._torch.from_numpy(normalized.transpose(2, 0, 1)).unsqueeze(0).to(self._device)
        with self._torch.inference_mode():
            prediction = self.model(tensor)
        if isinstance(prediction, (tuple, list)):
            prediction = prediction[0]
        probability = prediction.squeeze().detach().float().cpu().numpy()
        probability = cv2.resize(probability, (width, height), interpolation=cv2.INTER_LINEAR)
        return self._largest_region((probability >= self.mask_threshold).astype(np.uint8), probability)

    def _largest_region(self, binary: np.ndarray, probability: np.ndarray) -> SegmentationResult:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        candidates = [
            label for label in range(1, count)
            if int(stats[label, cv2.CC_STAT_AREA]) >= self.minimum_wound_area
        ]
        if not candidates:
            return SegmentationResult(np.zeros_like(binary), 0.0, None)
        largest = max(candidates, key=lambda label: int(stats[label, cv2.CC_STAT_AREA]))
        mask = (labels == largest).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        bbox = tuple(int(value) for value in cv2.boundingRect(mask))
        confidence = float(np.mean(probability[mask > 0]))
        return SegmentationResult(mask, confidence, bbox)

