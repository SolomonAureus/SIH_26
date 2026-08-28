"""Live RGB wound-localization and feature-extraction pipeline."""

from .aggregator import FeatureAggregator
from .config import RGBConfig
from .pipeline import RGBPipeline
from .rgb_features import extract_rgb_features
from .wound_model import FUSegNetSegmenter, SegmentationResult, WoundSegmenter

__all__ = [
    "FeatureAggregator", "FUSegNetSegmenter", "RGBConfig", "RGBPipeline",
    "SegmentationResult", "WoundSegmenter", "extract_rgb_features",
]

