"""Two-pass loudness normalization with ffmpeg's ``loudnorm`` filter.

Platforms like YouTube and TikTok play audio at about **-14 LUFS**
(LUFS = how loud it *sounds*, not just peak level). To hit that exactly:

1. **Pass 1 (measure):** run ``loudnorm`` over the clip's audio, output
   nothing, and read the loudness numbers it prints as JSON.
2. **Pass 2 (apply):** run ``loudnorm`` again with those measured numbers.
   Now it knows the whole clip in advance, so it can apply one smooth,
   even gain ("linear" mode) instead of guessing as it goes.
"""

import json
import logging
import math
import re
from pathlib import Path

from .runner import FFmpegError, require_tool, run
from .timecode import ms_to_seconds

log = logging.getLogger("clipforge")

TRUE_PEAK = -1.5  # dBTP: keep peaks a little under 0 dB so nothing clips
LOUDNESS_RANGE = 11  # LU: how much loud/quiet variation to allow
SAMPLE_RATE = 48000  # loudnorm works at 192 kHz inside, so we resample after

# The keys pass 2 needs from pass 1.
_MEASURED_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")


def _targets(lufs: float) -> str:
    return f"I={lufs:g}:TP={TRUE_PEAK}:LRA={LOUDNESS_RANGE}"


def measure_command(input_path: Path, start_ms: int, end_ms: int, lufs: float,
                    ffmpeg: str = "ffmpeg") -> list[str]:
    """Pass 1: the ffmpeg command that measures one clip's loudness."""
    return [
        ffmpeg, "-hide_banner", "-nostats",
        "-ss", ms_to_seconds(start_ms),
        "-i", str(input_path),
        "-t", ms_to_seconds(end_ms - start_ms),
        "-vn",  # skip the video, we only need sound
        "-af", f"loudnorm={_targets(lufs)}:print_format=json",
        "-f", "null", "-",  # throw the output away
    ]


def parse_measurement(stderr: str) -> dict[str, str]:
    """Pull the JSON block that loudnorm prints at the end of pass 1."""
    # The JSON is the last {...} in ffmpeg's log output.
    blocks = re.findall(r"\{[^{}]*\}", stderr)
    if not blocks:
        raise FFmpegError("loudnorm did not print any measurement")
    data = json.loads(blocks[-1])
    missing = [k for k in _MEASURED_KEYS if k not in data]
    if missing:
        raise FFmpegError(f"loudnorm measurement is missing {', '.join(missing)}")
    return {k: data[k] for k in _MEASURED_KEYS}


def is_silent(measured: dict[str, str]) -> bool:
    """Silent audio measures as -inf LUFS and can't be normalized."""
    try:
        return not math.isfinite(float(measured["input_i"]))
    except ValueError:
        return True


def apply_filter(measured: dict[str, str] | None, lufs: float) -> str:
    """Pass 2: the audio filter that applies the measured correction.

    With ``measured=None`` (used by --dry-run) the values are shown as
    placeholders, because pass 1 hasn't really run.
    """
    if measured is None:
        values = {k: f"<{k} from pass 1>" for k in _MEASURED_KEYS}
    elif is_silent(measured):
        # Nothing to normalize. Just keep the audio format consistent.
        return f"aresample={SAMPLE_RATE}"
    else:
        values = measured
    return (
        f"loudnorm={_targets(lufs)}"
        f":measured_I={values['input_i']}"
        f":measured_TP={values['input_tp']}"
        f":measured_LRA={values['input_lra']}"
        f":measured_thresh={values['input_thresh']}"
        f":offset={values['target_offset']}"
        ":linear=true:print_format=summary,"
        f"aresample={SAMPLE_RATE}"
    )


def measure(input_path: Path, start_ms: int, end_ms: int, lufs: float) -> dict[str, str]:
    """Run pass 1 and return the measured values."""
    result = run(measure_command(input_path, start_ms, end_ms, lufs, require_tool("ffmpeg")))
    measured = parse_measurement(result.stderr)
    log.debug("measured loudness: %s", measured)
    if is_silent(measured):
        log.warning("clip audio is silent, skipping loudness normalization")
    return measured
