"""End-to-end test with real ffmpeg.

ffmpeg's ``testsrc`` (a moving test pattern) and ``sine`` (a beep) sources
make a short synthetic video, so no real video file is needed in the repo.
"""

import json
import shutil
import subprocess
from fractions import Fraction

import pytest

from clipforge import cli
from clipforge.probe import probe

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                       reason="ffmpeg and ffprobe are needed for the integration test"),
]

FPS = "25/1"


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    # A folder name with a space and an apostrophe checks the path escaping.
    root = tmp_path_factory.mktemp("clip forge") / "it's here"
    root.mkdir()
    video = root / "source video.mp4"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=size=1920x1080:rate={FPS}",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "12",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(video),
        ],
        check=True,
    )
    clips = root / "clips.json"
    clips.write_text(json.dumps([
        {"name": "first clip", "start": "00:00:01.000", "end": "00:00:03.000"},
        {"name": "second clip", "start": "00:00:05.500", "end": "00:00:08.500"},
    ]), encoding="utf-8")
    srt = root / "captions.srt"
    srt.write_text(
        "1\n00:00:00,500 --> 00:00:02,000\nCrosses the first clip's start\n\n"
        "2\n00:00:08,000 --> 00:00:10,000\nCrosses the second clip's end\n",
        encoding="utf-8",
    )
    return {"root": root, "video": video, "clips": clips, "srt": srt}


@pytest.mark.parametrize("framing", ["crop", "fill"])
def test_render_two_clips(workspace, framing):
    out = workspace["root"] / f"out {framing}"
    code = cli.main([
        "--input", str(workspace["video"]),
        "--clips", str(workspace["clips"]),
        "--srt", str(workspace["srt"]),
        "--out-dir", str(out),
        "--framing", framing,
    ])
    assert code == 0

    for stem, seconds in [("first_clip", 2.0), ("second_clip", 3.0)]:
        info = probe(out / f"{stem}.mp4")
        assert (info.width, info.height) == (1080, 1920)
        assert Fraction(info.fps) == Fraction(FPS)
        # Within one frame (40 ms at 25 fps) plus a little audio padding.
        assert info.duration_ms == pytest.approx(seconds * 1000, abs=60)
        assert info.has_audio
        assert (out / f"{stem}_contact_sheet.jpg").stat().st_size > 0
        assert (out / f"{stem}.srt").is_file()

    # The caption crossing the first clip's start was trimmed, not dropped.
    first_srt = (out / "first_clip.srt").read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,000" in first_srt
