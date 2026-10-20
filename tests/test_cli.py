"""CLI tests that don't need ffmpeg: the ffprobe step is replaced with a fake."""

import json
import logging

import pytest

from clipforge import cli
from clipforge.probe import VideoInfo

INFO = VideoInfo(width=1920, height=1080, fps="30/1", duration_ms=20_000, has_audio=True)


@pytest.fixture
def files(tmp_path, monkeypatch):
    video = tmp_path / "my video.mp4"
    video.write_bytes(b"fake")
    clips = tmp_path / "clips.json"
    clips.write_text(json.dumps([
        {"name": "one", "start": "00:00:01.000", "end": "00:00:05.000"},
        {"name": "two", "start": "00:00:06.000", "end": "00:00:09.000"},
    ]), encoding="utf-8")
    srt = tmp_path / "c.srt"
    srt.write_text("1\n00:00:00,500 --> 00:00:02,000\nHi\n", encoding="utf-8")
    monkeypatch.setattr(cli, "probe", lambda path: INFO)
    return {"video": video, "clips": clips, "srt": srt, "out": tmp_path / "out"}


def base_args(f, *extra):
    return ["--input", str(f["video"]), "--clips", str(f["clips"]), "--out-dir", str(f["out"]), *extra]


def test_dry_run_prints_commands(files, capsys):
    code = cli.main(base_args(files, "--srt", str(files["srt"]), "--dry-run"))
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("loudnorm") >= 4  # measure + apply for each of 2 clips
    assert "subtitles=" in out
    assert "'my video.mp4'" in out or "my video.mp4" in out
    assert not files["out"].exists()  # dry run writes nothing


@pytest.mark.parametrize(
    "extra, message",
    [
        (["--offset", "2"], "--offset must be between"),
        (["--caption-y", "0"], "--caption-y"),
        (["--font-size", "2"], "--font-size"),
        (["--lufs", "3"], "--lufs"),
        (["--font", "missing.ttf"], "font file not found"),
        (["--srt", "missing.srt"], "SRT file not found"),
    ],
)
def test_bad_options_give_friendly_errors(files, caplog, extra, message):
    assert cli.main(base_args(files, *extra)) == 2
    assert message in caplog.text


def test_missing_input(files, caplog):
    args = base_args(files)
    args[1] = "nope.mp4"
    assert cli.main(args) == 2
    assert "input video not found" in caplog.text


def test_clip_longer_than_video(files, caplog):
    files["clips"].write_text(json.dumps([{"name": "x", "start": "00:00:01.000", "end": "00:00:30.000"}]))
    assert cli.main(base_args(files, "--dry-run")) == 2
    assert "video is only 00:00:20.000 long" in caplog.text


def test_one_failing_clip_does_not_stop_the_rest(files, caplog, monkeypatch):
    def fake_render(input_path, info, clip, out_dir, options, captions):
        if clip.name == "one":
            raise cli.FFmpegError("boom")
        return None

    monkeypatch.setattr(cli, "render_clip", fake_render)
    caplog.set_level(logging.INFO)
    assert cli.main(base_args(files, "--dry-run")) == 1
    assert "❌ one: boom" in caplog.text
    assert "✅ two" in caplog.text
    assert "1 of 2 clip(s) done" in caplog.text
