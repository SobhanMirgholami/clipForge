import pytest

from clipforge.contact_sheet import contact_sheet_command, frame_times


def test_frame_times_evenly_spaced():
    assert frame_times(6000) == [500, 1500, 2500, 3500, 4500, 5500]


def test_frame_times_stay_inside_clip():
    times = frame_times(1234)
    assert len(times) == 6
    assert all(0 <= t < 1234 for t in times)
    assert times == sorted(times)


def test_frame_times_rejects_zero():
    with pytest.raises(ValueError):
        frame_times(0)


def test_command_has_six_inputs_and_a_grid():
    cmd = contact_sheet_command("clip 1.mp4", 6000, "sheet.jpg")
    assert cmd.count("-i") == 6
    assert cmd.count("clip 1.mp4") == 6
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.count("hstack=inputs=3") == 2
    assert "vstack=inputs=2[sheet]" in graph
    assert cmd[-1] == "sheet.jpg"
