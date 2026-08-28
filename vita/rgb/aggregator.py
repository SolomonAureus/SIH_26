"""Robust N-frame aggregation for one RGB acquisition window."""

from datetime import datetime, timezone
from typing import Mapping
import numpy as np


class FeatureAggregator:
    def __init__(self, target_frames: int) -> None:
        if target_frames <= 0:
            raise ValueError("target_frames must be positive")
        self.target_frames = target_frames
        self._observations: list[dict[str, float]] = []

    @property
    def count(self) -> int:
        return len(self._observations)

    @property
    def complete(self) -> bool:
        return self.count >= self.target_frames

    def add(self, features: Mapping[str, float]) -> None:
        if self.complete:
            raise RuntimeError("Acquisition already complete")
        numeric = {key: float(value) for key, value in features.items()}
        if not numeric:
            raise ValueError("At least one feature is required")
        if self._observations and numeric.keys() != self._observations[0].keys():
            raise ValueError("Feature schemas must match")
        self._observations.append(numeric)

    def aggregate(self) -> dict[str, float | int | str]:
        if not self._observations:
            raise ValueError("No accepted observations")
        result: dict[str, float | int | str] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "accepted_frames": self.count,
        }
        for key in self._observations[0]:
            values = np.asarray([sample[key] for sample in self._observations])
            result[f"{key}_median"] = float(np.median(values))
            result[f"{key}_std"] = float(np.std(values))
        return result

