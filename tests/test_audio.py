import pytest

from clipforge.audio import apply_filter, is_silent, measure_command, parse_measurement
from clipforge.runner import FFmpegError

STDERR = """[Parsed_loudnorm_0 @ 0x55]
{
	"input_i" : "-20.31",
	"input_tp" : "-17.00",
	"input_lra" : "0.00",
	"input_thresh" : "-30.31",
	"output_i" : "-14.02",
	"output_tp" : "-10.70",
	"output_lra" : "0.00",
	"output_thresh" : "-24.02",
	"normalization_type" : "dynamic",
	"target_offset" : "0.02"
}
"""


def test_measure_command_is_a_list_with_seek_and_duration():
    cmd = measure_command("my video.mp4", 65200, 75200, -14)
    assert cmd[cmd.index("-ss") + 1] == "65.200"
    assert cmd[cmd.index("-t") + 1] == "10.000"
    assert "my video.mp4" in cmd  # path stays one argument, spaces and all
    assert "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json" in cmd


def test_parse_measurement():
    m = parse_measurement("lots of log lines\n" + STDERR)
    assert m == {
        "input_i": "-20.31",
        "input_tp": "-17.00",
        "input_lra": "0.00",
        "input_thresh": "-30.31",
        "target_offset": "0.02",
    }


def test_parse_measurement_missing():
    with pytest.raises(FFmpegError):
        parse_measurement("no json here")


def test_apply_filter_uses_measured_values():
    f = apply_filter(parse_measurement(STDERR), -14)
    assert f.startswith("loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=-20.31:")
    assert "offset=0.02" in f
    assert "linear=true" in f
    assert f.endswith("aresample=48000")


def test_apply_filter_custom_target():
    assert apply_filter(parse_measurement(STDERR), -16).startswith("loudnorm=I=-16:")


def test_silent_audio_is_not_normalized():
    m = parse_measurement(STDERR.replace('"-20.31"', '"-inf"'))
    assert is_silent(m)
    assert apply_filter(m, -14) == "aresample=48000"


def test_dry_run_placeholders():
    assert "<input_i from pass 1>" in apply_filter(None, -14)
