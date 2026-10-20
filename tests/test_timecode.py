import pytest

from clipforge.timecode import (
    TimecodeError,
    format_timecode,
    ms_to_seconds,
    parse_timecode,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("00:00:00.000", 0),
        ("00:00:01.000", 1000),
        ("00:01:05.200", 65200),
        ("01:00:00.000", 3_600_000),
        ("00:59:59.999", 3_599_999),
        ("10:00:00.001", 36_000_001),
        ("123:00:00.000", 123 * 3_600_000),  # very long video
    ],
)
def test_parse_valid(text, expected):
    assert parse_timecode(text) == expected


def test_parse_accepts_srt_comma():
    assert parse_timecode("00:01:05,200") == 65200


def test_parse_without_fraction():
    assert parse_timecode("00:00:07") == 7000


@pytest.mark.parametrize("text, expected", [("00:00:01.5", 1500), ("00:00:01.25", 1250)])
def test_parse_short_fraction_is_padded(text, expected):
    assert parse_timecode(text) == expected


def test_parse_strips_whitespace():
    assert parse_timecode("  00:00:02.000 \n") == 2000


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "1:05",
        "00:60:00.000",  # 60 minutes is not valid
        "00:00:60.000",  # 60 seconds is not valid
        "00:00:01.0000",  # too many fraction digits
        "00:00:01:000",
        "-00:00:01.000",
        "aa:bb:cc.ddd",
        "00:1:05.200",  # minutes need two digits
    ],
)
def test_parse_invalid(bad):
    with pytest.raises(TimecodeError):
        parse_timecode(bad)


def test_parse_non_string():
    with pytest.raises(TimecodeError):
        parse_timecode(65.2)


def test_error_message_is_friendly():
    with pytest.raises(TimecodeError, match="expected HH:MM:SS.mmm"):
        parse_timecode("nope")


@pytest.mark.parametrize(
    "ms, expected",
    [
        (0, "00:00:00.000"),
        (65200, "00:01:05.200"),
        (3_599_999, "00:59:59.999"),
        (36_000_001, "10:00:00.001"),
    ],
)
def test_format(ms, expected):
    assert format_timecode(ms) == expected


def test_format_srt_separator():
    assert format_timecode(65200, ",") == "00:01:05,200"


@pytest.mark.parametrize("ms", [0, 1, 999, 1000, 65200, 3_599_999, 36_000_001])
def test_round_trip(ms):
    assert parse_timecode(format_timecode(ms)) == ms
    assert parse_timecode(format_timecode(ms, ",")) == ms


def test_format_negative_raises():
    with pytest.raises(ValueError):
        format_timecode(-1)


@pytest.mark.parametrize("ms, expected", [(0, "0.000"), (65200, "65.200"), (5, "0.005")])
def test_ms_to_seconds(ms, expected):
    assert ms_to_seconds(ms) == expected
