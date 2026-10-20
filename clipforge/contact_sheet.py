"""Make a contact sheet: 6 evenly spaced frames from a clip in one JPG.

It's a quick way to check a clip without playing it, like scrubbing
through a sequence in Premiere. The 6 frames sit in a 3 x 2 grid.

How it works: we open the same video 6 times, each one seeked (``-ss``)
to a different moment, grab one frame from each, then stack them with
``hstack`` (side by side) and ``vstack`` (one row on top of the other).
"""

from pathlib import Path

from .runner import require_tool, run
from .timecode import ms_to_seconds

FRAMES = 6
COLUMNS = 3
TILE_WIDTH = 360  # each frame is scaled to this width
BORDER = 6  # dark gap around every frame, in pixels


def frame_times(duration_ms: int, count: int = FRAMES) -> list[int]:
    """Return ``count`` evenly spaced times (ms), each in the middle of its slice.

    Using the middle of each slice avoids the very first and last frame,
    which are often black or mid-transition.
    """
    if duration_ms <= 0:
        raise ValueError("duration must be positive")
    slice_ms = duration_ms / count
    return [int(slice_ms * i + slice_ms / 2) for i in range(count)]


def contact_sheet_command(video: Path, duration_ms: int, output: Path,
                          ffmpeg: str = "ffmpeg") -> list[str]:
    """Build the ffmpeg command for the contact sheet."""
    times = frame_times(duration_ms)
    args = [ffmpeg, "-hide_banner", "-y"]
    for t in times:
        args += ["-ss", ms_to_seconds(t), "-i", str(video)]

    # Scale each frame and give it a border: [0:v] -> [f0], [1:v] -> [f1] ...
    parts = [
        f"[{i}:v]scale={TILE_WIDTH}:-2,setsar=1,"
        f"pad=iw+{BORDER * 2}:ih+{BORDER * 2}:{BORDER}:{BORDER}:color=0x111111[f{i}]"
        for i in range(len(times))
    ]
    rows = []
    for r in range(len(times) // COLUMNS):
        labels = "".join(f"[f{r * COLUMNS + c}]" for c in range(COLUMNS))
        parts.append(f"{labels}hstack=inputs={COLUMNS}[row{r}]")
        rows.append(f"[row{r}]")
    parts.append(f"{''.join(rows)}vstack=inputs={len(rows)}[sheet]")

    args += [
        "-filter_complex", ";".join(parts),
        "-map", "[sheet]",
        "-frames:v", "1",
        "-q:v", "2",  # JPG quality: 2 is very high (scale is 2 to 31)
        str(output),
    ]
    return args


def make_contact_sheet(video: Path, duration_ms: int, output: Path, dry_run: bool = False) -> None:
    """Create the contact sheet JPG for ``video``."""
    ffmpeg = "ffmpeg" if dry_run else require_tool("ffmpeg")
    run(contact_sheet_command(video, duration_ms, output, ffmpeg), dry_run=dry_run)
