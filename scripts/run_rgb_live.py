#!/usr/bin/env python3
"""Run one VITA live RGB wound-feature acquisition window."""

import argparse
import sys
from pathlib import Path

from vita.rgb.camera import CameraUnavailableError
from vita.rgb.config import RGBConfig
from vita.rgb.pipeline import NoWoundTimeoutError, RGBPipeline
from vita.rgb.wound_model import FUSegNetSegmenter, ModelConfigurationError


def build_parser() -> argparse.ArgumentParser:
    defaults = RGBConfig()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--sampling-fps", type=float, default=5)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--checkpoint", type=Path, default=defaults.checkpoint_path)
    parser.add_argument("--model-repo", type=Path, default=defaults.model_repo_path)
    parser.add_argument("--mask-threshold", type=float, default=.5)
    parser.add_argument("--minimum-wound-area", type=int, default=500)
    parser.add_argument("--blur-threshold", type=float, default=75)
    parser.add_argument("--min-brightness", type=float, default=35)
    parser.add_argument("--max-brightness", type=float, default=225)
    parser.add_argument("--no-wound-timeout", type=float, default=30)
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--no-csv", action="store_true")
    parser.add_argument(
        "--no-dashboard", action="store_true",
        help="Do not publish the live camera, detection preview, and status files",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = RGBConfig(
        camera_index=args.camera, camera_width=args.width, camera_height=args.height,
        sampling_fps=args.sampling_fps, target_good_frames=args.samples,
        preview=not args.no_preview, model_repo_path=args.model_repo,
        checkpoint_path=args.checkpoint, mask_threshold=args.mask_threshold,
        minimum_wound_area=args.minimum_wound_area, device=args.device,
        no_wound_timeout_seconds=args.no_wound_timeout, append_csv=not args.no_csv,
        publish_dashboard=not args.no_dashboard,
    )
    config.quality.blur_threshold = args.blur_threshold
    config.quality.min_brightness = args.min_brightness
    config.quality.max_brightness = args.max_brightness
    try:
        segmenter = FUSegNetSegmenter(
            config.checkpoint_path, config.model_repo_path, config.device,
            config.model_input_size, config.mask_threshold, config.minimum_wound_area,
        )
        return 0 if RGBPipeline(config, segmenter).run() else 130
    except (ModelConfigurationError, CameraUnavailableError, NoWoundTimeoutError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
