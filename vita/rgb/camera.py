"""OpenCV camera lifecycle and sampled-frame capture."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Iterator

import cv2
import numpy as np


class CameraUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    image: np.ndarray
    captured_at: float
    sequence: int


class OpenCVCamera:
    def __init__(
        self, index: int, width: int, height: int, sampling_fps: float,
        frame_callback: Callable[[np.ndarray], None] | None = None,
    ) -> None:
        self.index, self.width, self.height = index, width, height
        self.sampling_fps = sampling_fps
        self.frame_callback = frame_callback
        self.capture: cv2.VideoCapture | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._frame_ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest_frame: np.ndarray | None = None
        self._captured_at = 0.0
        self._sequence = 0
        self._error: CameraUnavailableError | None = None

    def open(self) -> "OpenCVCamera":
        self.capture = cv2.VideoCapture(self.index)
        if not self.capture.isOpened():
            self.release()
            raise CameraUnavailableError(f"Unable to open camera index {self.index}")
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._stop.clear()
        self._frame_ready.clear()
        self._latest_frame = None
        self._sequence = 0
        self._error = None
        self._thread = threading.Thread(target=self._capture_loop, name="vita-camera", daemon=True)
        self._thread.start()
        return self

    def _capture_loop(self) -> None:
        failures = 0
        while not self._stop.is_set():
            capture = self.capture
            if capture is None:
                break
            ok, frame = capture.read()
            now = time.monotonic()
            if not ok or frame is None or frame.size == 0:
                failures += 1
                if failures >= 10 and not self._stop.is_set():
                    self._error = CameraUnavailableError("Camera returned 10 malformed frames")
                    self._frame_ready.set()
                    break
                continue
            failures = 0
            with self._lock:
                self._latest_frame = frame
                self._captured_at = now
                self._sequence += 1
            self._frame_ready.set()
            if self.frame_callback is not None:
                try:
                    self.frame_callback(frame)
                except Exception:
                    # Dashboard publishing must never stop data capture.
                    pass

    def sampled_frames(self) -> Iterator[CapturedFrame]:
        if self.capture is None or not self.capture.isOpened():
            raise CameraUnavailableError("Camera must be opened before reading frames")
        interval, next_sample, last_sequence = 1 / self.sampling_fps, 0.0, -1
        while True:
            self._frame_ready.wait(timeout=1.0)
            if self._error is not None:
                raise self._error
            now = time.monotonic()
            if now < next_sample:
                time.sleep(min(next_sample - now, 0.01))
                continue
            with self._lock:
                sequence = self._sequence
                captured_at = self._captured_at
                frame = None if self._latest_frame is None else self._latest_frame.copy()
            if frame is None or sequence == last_sequence:
                time.sleep(0.002)
                continue
            next_sample, last_sequence = now + interval, sequence
            yield CapturedFrame(frame, captured_at, sequence)

    def release(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=0.5)
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.5)
        self._thread = None

    def __enter__(self) -> "OpenCVCamera":
        return self.open()

    def __exit__(self, *_: Any) -> None:
        self.release()
