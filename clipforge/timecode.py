"""Parse and format timestamps.

Inside ClipForge every time is stored as a whole number of **milliseconds**
(an ``int``). Floats like 65.2 can turn into 65.19999 and cause off-by-one
frame errors, while integers are always exact.

Two text formats are supported:

* Clip JSON files use ``HH:MM:SS.mmm``, for example ``00:01:05.200``.
* SRT files use a comma instead of a dot: ``00:01:05,200``.
"""

import re

# HH:MM:SS, then an optional "." or "," with 1 to 3 digits of fraction.
# Hours can have more than two digits so very long videos still work.
_TIMECODE_RE = re.compile(r"^(\d{1,}):([0-5]\d):([0-5]\d)(?:[.,](\d{1,3}))?$")


class TimecodeError(ValueError):
    """Raised when a timestamp string is not in a valid format."""


def parse_timecode(text: str) -> int:
    """Turn ``"HH:MM:SS.mmm"`` (or ``"HH:MM:SS,mmm"``) into milliseconds.

    >>> parse_timecode("00:01:05.200")
    65200
    """
    if not isinstance(text, str):
        raise TimecodeError(f"timestamp must be text like 00:01:05.200, got {text!r}")

    match = _TIMECODE_RE.match(text.strip())
    if match is None:
        raise TimecodeError(
            f"invalid timestamp {text!r}: expected HH:MM:SS.mmm, e.g. 00:01:05.200"
        )

    hours, minutes, seconds, fraction = match.groups()
    # "2" means 200 ms and "25" means 250 ms, so pad the fraction to 3 digits.
    millis = int((fraction or "0").ljust(3, "0"))
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + millis


def format_timecode(ms: int, separator: str = ".") -> str:
    """Turn milliseconds into ``"HH:MM:SS.mmm"``.

    Pass ``separator=","`` to get the SRT style ``"HH:MM:SS,mmm"``.

    >>> format_timecode(65200)
    '00:01:05.200'
    """
    if ms < 0:
        raise ValueError(f"time cannot be negative: {ms} ms")
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"


def ms_to_seconds(ms: int) -> str:
    """Turn milliseconds into a seconds string for ffmpeg, e.g. ``"65.200"``.

    We return text (not a float) so the value ffmpeg receives is exact.
    """
    if ms < 0:
        raise ValueError(f"time cannot be negative: {ms} ms")
    return f"{ms // 1000}.{ms % 1000:03d}"
