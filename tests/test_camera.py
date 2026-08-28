import threading

import numpy as np

from vita.rgb.camera import OpenCVCamera


class FakeCapture:
    def __init__(self):
        self.opened = True
        self.released = False
        self.sequence = 0

    def isOpened(self):
        return self.opened

    def set(self, *_):
        return True

    def read(self):
        self.sequence += 1
        frame = np.full((8, 10, 3), self.sequence % 255, dtype=np.uint8)
        return True, frame

    def release(self):
        self.opened = False
        self.released = True


def test_camera_capture_advances_independently_of_sample_consumer(monkeypatch):
    capture = FakeCapture()
    callback_count = 0
    captured_five = threading.Event()

    def on_frame(_frame):
        nonlocal callback_count
        callback_count += 1
        if callback_count >= 5:
            captured_five.set()

    monkeypatch.setattr("vita.rgb.camera.cv2.VideoCapture", lambda _index: capture)
    camera = OpenCVCamera(0, 10, 8, sampling_fps=30, frame_callback=on_frame)
    with camera:
        assert captured_five.wait(timeout=1)
        sampled = next(camera.sampled_frames())
        assert sampled.sequence >= 5

    assert capture.released
