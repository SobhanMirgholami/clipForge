"""Read, cut and write SRT caption files.

An SRT file is a list of blocks separated by blank lines::

    1
    00:00:01,000 --> 00:00:03,500
    Hello there!

For each clip we:

1. keep only captions that overlap the clip's time range,
2. **trim** captions that cross the clip's start or end (we never drop them),
3. shift every time so the clip starts at 0 (retiming),
4. renumber from 1 and write a new, small SRT for that clip.
"""

import re
from dataclasses import dataclass, replace
from pathlib import Path

from .timecode import TimecodeError, format_timecode, parse_timecode

_ARROW_RE = re.compile(r"^\s*(\S+)\s*-->\s*(\S+)")


class SrtError(ValueError):
    """Raised when an SRT file can't be understood."""


@dataclass(frozen=True)
class Caption:
    index: int
    start_ms: int
    end_ms: int
    text: str


def parse_srt(content: str) -> list[Caption]:
    """Turn the text of an SRT file into a list of Captions."""
    # Remove a UTF-8 "byte order mark" (common in files saved on Windows)
    # and turn Windows line endings (\r\n) into plain \n.
    content = content.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")

    captions: list[Caption] = []
    # Blocks are separated by one or more blank lines.
    blocks = re.split(r"\n\s*\n", content.strip())
    for number, block in enumerate(blocks, start=1):
        if not block.strip():
            continue
        lines = block.split("\n")

        # The first line is normally the index. Some tools leave it out,
        # so we find the line with "-->" instead of assuming its position.
        arrow_line = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if arrow_line is None or arrow_line > 1:
            raise SrtError(f"caption block {number} has no 'start --> end' time line")

        match = _ARROW_RE.match(lines[arrow_line])
        try:
            start = parse_timecode(match.group(1))
            end = parse_timecode(match.group(2))
        except (AttributeError, TimecodeError) as exc:
            raise SrtError(f"caption block {number}: {exc}") from exc
        if end <= start:
            raise SrtError(f"caption block {number}: end time must be after start time")

        text = "\n".join(lines[arrow_line + 1:]).strip()
        captions.append(Caption(index=len(captions) + 1, start_ms=start, end_ms=end, text=text))
    return captions


def read_srt(path: Path) -> list[Caption]:
    """Read and parse an SRT file from disk."""
    # utf-8-sig also handles the byte order mark.
    return parse_srt(Path(path).read_text(encoding="utf-8-sig", errors="replace"))


def captions_for_clip(captions: list[Caption], clip_start_ms: int, clip_end_ms: int) -> list[Caption]:
    """Return the captions inside one clip, trimmed and retimed to start at 0.

    A caption from 00:09 to 00:12 in a clip that runs 00:10 to 00:20
    becomes 00:00 to 00:02: its start is trimmed to the clip start.
    """
    if clip_end_ms <= clip_start_ms:
        raise ValueError("clip end must be after clip start")

    result: list[Caption] = []
    for cap in captions:
        # Two ranges overlap when each one starts before the other ends.
        # Touching edges (a caption ending exactly at the clip start) don't count.
        if cap.start_ms >= clip_end_ms or cap.end_ms <= clip_start_ms:
            continue

        start = max(cap.start_ms, clip_start_ms) - clip_start_ms
        end = min(cap.end_ms, clip_end_ms) - clip_start_ms
        result.append(replace(cap, index=len(result) + 1, start_ms=start, end_ms=end))
    return result


def format_srt(captions: list[Caption]) -> str:
    """Turn Captions back into SRT text."""
    blocks = []
    for cap in captions:
        blocks.append(
            f"{cap.index}\n"
            f"{format_timecode(cap.start_ms, ',')} --> {format_timecode(cap.end_ms, ',')}\n"
            f"{cap.text}\n"
        )
    return "\n".join(blocks)


def write_srt(captions: list[Caption], path: Path) -> None:
    """Write Captions to an SRT file."""
    Path(path).write_text(format_srt(captions), encoding="utf-8")
