import pytest

from clipforge.probe import parse_probe_output
from clipforge.runner import FFmpegError


def sample(video_extra=None, with_audio=True, duration="12.345"):
    video = {"codec_type": "video", "width": 1920, "height": 1080,
             "avg_frame_rate": "30000/1001", "r_frame_rate": "30000/1001"}
    video.update(video_extra or {})
    streams = [video]
    if with_audio:
        streams.append({"codec_type": "audio"})
    return {"streams": streams, "format": {"duration": duration}}


def test_basic_fields():
    info = parse_probe_output(sample())
    assert (info.width, info.height) == (1920, 1080)
    assert info.fps == "30000/1001"
    assert info.fps_float == pytest.approx(29.97, abs=0.01)
    assert info.duration_ms == 12345
    assert info.has_audio is True


def test_no_audio():
    assert parse_probe_output(sample(with_audio=False)).has_audio is False


def test_falls_back_to_r_frame_rate():
    info = parse_probe_output(sample({"avg_frame_rate": "0/0", "r_frame_rate": "25/1"}))
    assert info.fps == "25/1"


def test_rate_is_reduced():
    info = parse_probe_output(sample({"avg_frame_rate": "60/2"}))
    assert info.fps == "30/1"


def test_no_video_stream():
    with pytest.raises(FFmpegError, match="no video stream"):
        parse_probe_output({"streams": [{"codec_type": "audio"}], "format": {}})


def test_unknown_frame_rate():
    with pytest.raises(FFmpegError, match="frame rate"):
        parse_probe_output(sample({"avg_frame_rate": "0/0", "r_frame_rate": "0/0"}))


def test_missing_duration():
    data = sample()
    data["format"] = {}
    with pytest.raises(FFmpegError, match="duration"):
        parse_probe_output(data)
