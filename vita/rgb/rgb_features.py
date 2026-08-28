"""Small feature vector derived only from wound-mask pixels."""

import math
import cv2
import numpy as np


class EmptyMaskError(ValueError):
    pass


def extract_rgb_features(frame: np.ndarray, mask: np.ndarray) -> dict[str, float]:
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame must be a BGR image")
    if mask is None or mask.ndim != 2 or mask.shape != frame.shape[:2]:
        raise ValueError("mask must match frame dimensions")
    binary = (mask > 0).astype(np.uint8)
    area = int(cv2.countNonZero(binary))
    if area == 0:
        raise EmptyMaskError("Cannot extract features from an empty wound mask")
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        raise EmptyMaskError("Mask contains no contour")
    contour = max(contours, key=cv2.contourArea)
    perimeter = float(cv2.arcLength(contour, True))
    _, _, width, height = cv2.boundingRect(contour)
    circularity = float(np.clip(4 * math.pi * area / (perimeter**2 + 1e-8), 0, 1))
    pixels = frame[binary.astype(bool)].astype(np.float64)
    mean_b, mean_g, mean_r = np.mean(pixels, axis=0)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    roi_gray = gray[binary.astype(bool)].astype(np.float64)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)[binary.astype(bool)]
    return {
        "wound_area_px": float(area), "wound_perimeter_px": perimeter,
        "bounding_box_width": float(width), "bounding_box_height": float(height),
        "circularity": circularity, "mean_R": float(mean_r),
        "mean_G": float(mean_g), "mean_B": float(mean_b),
        "normalized_red_ratio": float(mean_r / (mean_r + mean_g + mean_b + 1e-8)),
        "grayscale_std": float(np.std(roi_gray)),
        "laplacian_variance": float(np.var(laplacian)),
    }

