import pytest

from clipforge.srt import (
    Caption,
    SrtError,
    captions_for_clip,
    format_srt,
    parse_srt,
    read_srt,
    write_srt,
)

SAMPLE = """1
00:00:01,000 --> 00:00:03,000
First line

2
00:00:04,000 --> 00:00:06,500
Second caption
on two lines

3
00:00:09,000 --> 00:00:12,000
Crosses the clip start

4
00:00:18,000 --> 00:00:22,000
Crosses the clip end
"""


def cap(start, end, text="x", index=1):
    return Caption(index=index, start_ms=start, end_ms=end, text=text)


# ---------- parsing ----------

def test_parse_sample():
    caps = parse_srt(SAMPLE)
    assert len(caps) == 4
    assert caps[0] == Caption(1, 1000, 3000, "First line")
    assert caps[1].text == "Second caption\non two lines"
    assert caps[3].start_ms == 18000 and caps[3].end_ms == 22000


def test_parse_windows_line_endings_and_bom():
    caps = parse_srt("﻿" + SAMPLE.replace("\n", "\r\n"))
    assert len(caps) == 4
    assert caps[1].text == "Second caption\non two lines"


def test_parse_extra_blank_lines():
    text = "\n\n1\n00:00:01,000 --> 00:00:02,000\nHi\n\n\n\n2\n00:00:03,000 --> 00:00:04,000\nBye\n\n"
    assert [c.text for c in parse_srt(text)] == ["Hi", "Bye"]


def test_parse_missing_index_line():
    caps = parse_srt("00:00:01,000 --> 00:00:02,000\nNo index\n")
    assert caps == [Caption(1, 1000, 2000, "No index")]


def test_parse_renumbers():
    caps = parse_srt("7\n00:00:01,000 --> 00:00:02,000\nA\n\n9\n00:00:03,000 --> 00:00:04,000\nB\n")
    assert [c.index for c in caps] == [1, 2]


def test_parse_ignores_position_tags_after_time():
    caps = parse_srt("1\n00:00:01,000 --> 00:00:02,000 X1:0 X2:100\nHi\n")
    assert caps[0].end_ms == 2000


def test_parse_empty_file():
    assert parse_srt("") == []


def test_parse_bad_time():
    with pytest.raises(SrtError, match="block 1"):
        parse_srt("1\n00:00:xx,000 --> 00:00:02,000\nHi\n")


def test_parse_missing_arrow():
    with pytest.raises(SrtError, match="block 2"):
        parse_srt("1\n00:00:01,000 --> 00:00:02,000\nHi\n\n2\njust text\n")


def test_parse_end_before_start():
    with pytest.raises(SrtError, match="end time must be after"):
        parse_srt("1\n00:00:05,000 --> 00:00:02,000\nHi\n")


# ---------- filtering, trimming and retiming ----------

def test_caption_fully_inside_is_retimed():
    out = captions_for_clip([cap(12000, 14000)], 10000, 20000)
    assert (out[0].start_ms, out[0].end_ms) == (2000, 4000)


def test_caption_starting_before_clip_is_trimmed_not_dropped():
    out = captions_for_clip([cap(9000, 12000, "edge")], 10000, 20000)
    assert len(out) == 1
    assert (out[0].start_ms, out[0].end_ms) == (0, 2000)
    assert out[0].text == "edge"


def test_caption_ending_after_clip_is_trimmed_not_dropped():
    out = captions_for_clip([cap(18000, 22000, "edge")], 10000, 20000)
    assert len(out) == 1
    assert (out[0].start_ms, out[0].end_ms) == (8000, 10000)


def test_caption_covering_whole_clip():
    out = captions_for_clip([cap(5000, 25000)], 10000, 20000)
    assert (out[0].start_ms, out[0].end_ms) == (0, 10000)


def test_captions_outside_clip_are_dropped():
    out = captions_for_clip([cap(1000, 3000), cap(21000, 23000)], 10000, 20000)
    assert out == []


def test_caption_touching_edges_is_dropped():
    # Ends exactly at the clip start / starts exactly at the clip end: 0 ms visible.
    out = captions_for_clip([cap(8000, 10000), cap(20000, 21000)], 10000, 20000)
    assert out == []


def test_caption_one_ms_overlap_is_kept():
    out = captions_for_clip([cap(8000, 10001)], 10000, 20000)
    assert (out[0].start_ms, out[0].end_ms) == (0, 1)


def test_clip_results_are_renumbered_from_one():
    caps = parse_srt(SAMPLE)
    out = captions_for_clip(caps, 10000, 20000)
    assert [c.index for c in out] == [1, 2]
    assert [c.text for c in out] == ["Crosses the clip start", "Crosses the clip end"]
    assert [(c.start_ms, c.end_ms) for c in out] == [(0, 2000), (8000, 10000)]


def test_clip_starting_at_zero():
    out = captions_for_clip(parse_srt(SAMPLE), 0, 5000)
    assert [(c.start_ms, c.end_ms) for c in out] == [(1000, 3000), (4000, 5000)]


def test_original_captions_are_not_changed():
    caps = [cap(9000, 12000)]
    captions_for_clip(caps, 10000, 20000)
    assert caps[0].start_ms == 9000


def test_invalid_clip_range():
    with pytest.raises(ValueError):
        captions_for_clip([], 5000, 5000)


# ---------- writing ----------

def test_format_srt():
    text = format_srt([Caption(1, 0, 2000, "Hi"), Caption(2, 61000, 62500, "Two\nlines")])
    assert text == (
        "1\n00:00:00,000 --> 00:00:02,000\nHi\n\n"
        "2\n00:01:01,000 --> 00:01:02,500\nTwo\nlines\n"
    )


def test_write_then_read_round_trip(tmp_path):
    caps = captions_for_clip(parse_srt(SAMPLE), 10000, 20000)
    path = tmp_path / "clip with spaces.srt"
    write_srt(caps, path)
    assert read_srt(path) == caps
