from pathlib import Path

import pytest

from clipforge.clips import Clip
from clipforge.probe import VideoInfo
from clipforge.render import (
    RenderOptions,
    escape_filter_value,
    filter_path,
    font_family,
    render_command,
    subtitle_filter,
)

INFO = VideoInfo(width=1920, height=1080, fps="30000/1001", duration_ms=60_000, has_audio=True)
CLIP = Clip("hook", 5000, 15000)


# ---------- escaping ----------

def test_windows_path_uses_forward_slashes():
    assert filter_path(r"C:\Users\Me\clip.srt") == "C:/Users/Me/clip.srt"


def test_posix_path_is_unchanged():
    assert filter_path("/home/me/clip.srt") == "/home/me/clip.srt"


def test_escape_windows_drive_colon():
    assert escape_filter_value("C:/Users/Me/clip.srt") == r"'C\:/Users/Me/clip.srt'"


def test_escape_brackets_commas_and_spaces_are_quoted():
    assert escape_filter_value("/a [b], c; d.srt") == "'/a [b], c; d.srt'"


def test_escape_apostrophe():
    # it's -> level 1: it\'s -> level 2: 'it\'\''s'
    assert escape_filter_value("it's") == "'it\\'\\''s'"


def test_escape_backslash():
    assert escape_filter_value("a\\b") == "'a\\\\b'"


# ---------- subtitles filter ----------

def test_subtitle_filter_style():
    f = subtitle_filter(Path("/tmp/x.srt"), RenderOptions(font_size=80, caption_y=0.75))
    assert f.startswith("subtitles=filename='/tmp/x.srt':force_style='")
    assert "PlayResX=1080,PlayResY=1920" in f
    assert "FontSize=80" in f
    assert "MarginV=480" in f
    assert "PrimaryColour=&H00FFFFFF" in f


def test_subtitle_filter_with_font(tmp_path):
    font = tmp_path / "My Font.ttf"
    font.write_bytes(b"not a real font")
    f = subtitle_filter(Path("/tmp/x.srt"), RenderOptions(font=font))
    assert "FontName=My Font" in f  # falls back to the file name
    assert ":fontsdir='" in f


def test_font_family_reads_real_font():
    fonts = [p for p in Path("/usr/share/fonts").rglob("DejaVuSans.ttf")] if Path("/usr/share/fonts").exists() else []
    if not fonts:
        pytest.skip("DejaVuSans.ttf not installed")
    assert font_family(fonts[0]) == "DejaVu Sans"


def test_font_family_bad_file(tmp_path):
    bad = tmp_path / "bad.ttf"
    bad.write_bytes(b"\x00\x01")
    assert font_family(bad) is None


# ---------- main command ----------

def test_render_command_crop_with_captions_and_audio():
    cmd = render_command(Path("in put.mp4"), INFO, CLIP, Path("out/hook.mp4"),
                         RenderOptions(), Path("out/hook.srt"), "aresample=48000")
    # -ss before -i for an accurate seek, and the path stays one argument.
    assert cmd.index("-ss") < cmd.index("-i")
    assert cmd[cmd.index("-i") + 1] == "in put.mp4"
    assert cmd[cmd.index("-ss") + 1] == "5.000"
    assert cmd[cmd.index("-t") + 1] == "10.000"
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "[framed]subtitles=" in graph
    assert graph.endswith("[0:a:0]aresample=48000[aout]")
    assert cmd[cmd.index("-r") + 1] == "30000/1001"
    assert "libx264" in cmd and "aac" in cmd
    assert "-c" not in cmd  # never stream copy


def test_render_command_without_captions_or_audio():
    cmd = render_command(Path("in.mp4"), INFO, CLIP, Path("o.mp4"), RenderOptions(framing="fill"), None, None)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "subtitles" not in graph
    assert graph.endswith("[vout]")
    assert "[aout]" not in cmd
    assert "aac" not in cmd
