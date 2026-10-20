import json

import pytest

from clipforge.clips import Clip, ClipsError, load_clips, parse_clips


def good():
    return [
        {"name": "hook", "start": "00:00:01.000", "end": "00:00:04.500"},
        {"name": "Best moment!", "start": "00:00:05.000", "end": "00:00:09.000"},
    ]


def test_parse_good_clips():
    clips = parse_clips(good(), video_duration_ms=10_000)
    assert clips[0] == Clip("hook", 1000, 4500)
    assert clips[0].duration_ms == 3500
    assert clips[1].file_stem == "Best_moment"


def test_object_with_clips_key():
    assert len(parse_clips({"clips": good()})) == 2


@pytest.mark.parametrize("data", [[], {}, "text", None, {"other": []}])
def test_not_a_list(data):
    with pytest.raises(ClipsError, match="non-empty list"):
        parse_clips(data)


def test_missing_fields():
    with pytest.raises(ClipsError, match="clip 1: missing start, end"):
        parse_clips([{"name": "x"}])


def test_bad_time_format():
    data = good()
    data[0]["start"] = "1:05"
    with pytest.raises(ClipsError, match="expected HH:MM:SS.mmm"):
        parse_clips(data)


def test_start_after_end():
    data = good()
    data[1]["start"] = "00:00:09.000"
    with pytest.raises(ClipsError, match="must be before end"):
        parse_clips(data)


def test_clip_past_video_end():
    with pytest.raises(ClipsError, match="video is only 00:00:08.000 long"):
        parse_clips(good(), video_duration_ms=8000)


def test_all_problems_reported_together():
    data = good()
    data[0]["end"] = "00:00:00.500"
    data[1]["name"] = ""
    with pytest.raises(ClipsError) as info:
        parse_clips(data)
    assert "clip 1" in str(info.value) and "clip 2" in str(info.value)


def test_duplicate_file_names():
    data = good()
    data[1]["name"] = "hook"
    with pytest.raises(ClipsError, match="already uses the file name"):
        parse_clips(data)


def test_file_stem_fallback():
    assert Clip("!!!", 0, 1).file_stem == "clip"


def test_load_missing_file(tmp_path):
    with pytest.raises(ClipsError, match="not found"):
        load_clips(tmp_path / "nope.json")


def test_load_invalid_json(tmp_path):
    path = tmp_path / "clips.json"
    path.write_text("[{oops}]", encoding="utf-8")
    with pytest.raises(ClipsError, match="not valid JSON"):
        load_clips(path)


def test_load_file(tmp_path):
    path = tmp_path / "clips.json"
    path.write_text(json.dumps(good()), encoding="utf-8")
    assert len(load_clips(path)) == 2
