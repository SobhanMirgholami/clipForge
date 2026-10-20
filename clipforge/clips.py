"""Load and check the clips JSON file.

The file is a list of clips::

    [
      {"name": "hook", "start": "00:01:05.200", "end": "00:01:35.000"},
      {"name": "best moment", "start": "00:12:00.000", "end": "00:12:45.500"}
    ]

A top-level object with a ``"clips"`` list is accepted too. Every
problem is collected and reported together, so you can fix the whole
file in one go instead of one error at a time.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .timecode import TimecodeError, format_timecode, parse_timecode


class ClipsError(ValueError):
    """Raised when the clips file is missing or invalid."""


@dataclass(frozen=True)
class Clip:
    name: str
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def file_stem(self) -> str:
        """A safe file name made from the clip name, e.g. "Best moment!" -> "Best_moment"."""
        stem = re.sub(r"[^\w\-]+", "_", self.name, flags=re.UNICODE).strip("_")
        return stem or "clip"


def parse_clips(data, video_duration_ms: int | None = None) -> list[Clip]:
    """Check already-loaded JSON data and turn it into Clip objects."""
    if isinstance(data, dict) and "clips" in data:
        data = data["clips"]
    if not isinstance(data, list) or not data:
        raise ClipsError('the clips file must be a non-empty list of {"name", "start", "end"} objects')

    clips: list[Clip] = []
    problems: list[str] = []
    seen_stems: set[str] = set()

    for number, item in enumerate(data, start=1):
        where = f"clip {number}"
        if not isinstance(item, dict):
            problems.append(f"{where}: must be an object with name, start and end")
            continue
        missing = [k for k in ("name", "start", "end") if k not in item]
        if missing:
            problems.append(f"{where}: missing {', '.join(missing)}")
            continue

        name = item["name"]
        if not isinstance(name, str) or not name.strip():
            problems.append(f"{where}: name must be non-empty text")
            continue
        where = f"clip {number} ({name!r})"

        try:
            start = parse_timecode(item["start"])
            end = parse_timecode(item["end"])
        except TimecodeError as exc:
            problems.append(f"{where}: {exc}")
            continue

        if start >= end:
            problems.append(f"{where}: start ({item['start']}) must be before end ({item['end']})")
            continue
        if video_duration_ms is not None and end > video_duration_ms:
            problems.append(
                f"{where}: ends at {item['end']} but the video is only "
                f"{format_timecode(video_duration_ms)} long"
            )
            continue

        clip = Clip(name=name.strip(), start_ms=start, end_ms=end)
        if clip.file_stem in seen_stems:
            problems.append(f"{where}: another clip already uses the file name {clip.file_stem!r}")
            continue
        seen_stems.add(clip.file_stem)
        clips.append(clip)

    if problems:
        raise ClipsError("problems in the clips file:\n  - " + "\n  - ".join(problems))
    return clips


def load_clips(path: Path, video_duration_ms: int | None = None) -> list[Clip]:
    """Read and check a clips JSON file."""
    path = Path(path)
    if not path.is_file():
        raise ClipsError(f"clips file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ClipsError(f"{path.name} is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}") from exc
    return parse_clips(data, video_duration_ms)
