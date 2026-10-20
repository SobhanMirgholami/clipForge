"""Read basic facts about a video with ffprobe.

ffprobe can print its findings as JSON, which Python reads with the
``json`` module. We keep only what ClipForge needs: size, frame rate,
duration and whether there is an audio track.
"""

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from .runner import FFmpegError, require_tool, run


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: str  # exact ffmpeg-style fraction, e.g. "30000/1001" or "25/1"
    duration_ms: int
    has_audio: bool

    @property
    def fps_float(self) -> float:
        """Frame rate as a normal number, e.g. 29.97. Good for display and maths."""
        return float(Fraction(self.fps))


def _valid_rate(rate: str | None) -> bool:
    """ffprobe reports "0/0" when it doesn't know a rate."""
    if not rate or "/" not in rate:
        return False
    num, den = rate.split("/", 1)
    return num.isdigit() and den.isdigit() and int(num) > 0 and int(den) > 0


def parse_probe_output(data: dict) -> VideoInfo:
    """Build a VideoInfo from ffprobe's JSON (already loaded into a dict)."""
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise FFmpegError("the input file has no video stream")

    # avg_frame_rate is the real average. r_frame_rate is a fallback.
    fps = video.get("avg_frame_rate")
    if not _valid_rate(fps):
        fps = video.get("r_frame_rate")
    if not _valid_rate(fps):
        raise FFmpegError("could not read the video's frame rate")
    # Reduce e.g. "60/2" to "30/1".
    rate = Fraction(fps)
    fps = f"{rate.numerator}/{rate.denominator}"

    duration = data.get("format", {}).get("duration") or video.get("duration")
    if duration is None:
        raise FFmpegError("could not read the video's duration")

    return VideoInfo(
        width=int(video["width"]),
        height=int(video["height"]),
        fps=fps,
        duration_ms=round(float(duration) * 1000),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )


def probe(path: Path) -> VideoInfo:
    """Run ffprobe on ``path`` and return its VideoInfo."""
    args = [
        require_tool("ffprobe"),
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    result = run(args)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FFmpegError(f"ffprobe returned output that isn't JSON: {exc}") from exc
    return parse_probe_output(data)
