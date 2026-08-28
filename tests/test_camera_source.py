from scripts.run_rgb_live import parse_camera_source


def test_camera_source_accepts_local_index():
    assert parse_camera_source("0") == 0
    assert parse_camera_source("-1") == -1


def test_camera_source_accepts_phone_stream_url():
    url = "http://192.168.1.25:8080/video"
    assert parse_camera_source(url) == url
