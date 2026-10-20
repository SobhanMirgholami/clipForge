"""Render one clip from start to finish.

For each clip ClipForge:

1. writes the clip's own SRT (trimmed and retimed captions), if captions were given,
2. measures the clip's loudness (loudnorm pass 1),
3. runs one ffmpeg command that cuts, reframes, burns in captions,
   normalizes audio (loudnorm pass 2) and encodes H.264 + AAC,
4. makes the contact sheet from the finished clip.

**Frame-accurate cuts:** ``-ss`` goes *before* ``-i`` and we re-encode.
ffmpeg jumps to the nearest keyframe before the start, then decodes and
throws away frames until it reaches the exact start time. Stream copy
(``-c copy``) can only cut on keyframes, which is why we don't use it.
"""

import logging
import struct
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from . import audio
from .clips import Clip
from .contact_sheet import make_contact_sheet
from .framing import OUT_H, OUT_W, build_framing
from .probe import VideoInfo
from .runner import require_tool, run
from .srt import Caption, captions_for_clip, write_srt
from .timecode import ms_to_seconds

log = logging.getLogger("clipforge")


@dataclass(frozen=True)
class RenderOptions:
    framing: str = "crop"
    offset: float = 0.0
    font: Path | None = None
    font_size: int = 64
    caption_y: float = 0.75  # bottom of the caption, as a fraction of the height
    lufs: float = -14.0
    dry_run: bool = False


@dataclass(frozen=True)
class RenderResult:
    video: Path
    contact_sheet: Path
    srt: Path | None


# ---------- escaping for ffmpeg filter graphs ----------

def filter_path(path: Path | str) -> str:
    """Turn a file path into the form ffmpeg filters expect.

    Windows backslashes become forward slashes (``C:\\Users`` -> ``C:/Users``),
    which ffmpeg understands on every system. The ``:`` after the drive
    letter is handled by :func:`escape_filter_value`.
    """
    text = str(path)
    if "\\" in text:
        text = PureWindowsPath(text).as_posix()
    return text


def escape_filter_value(value: str) -> str:
    """Escape a value so it is safe inside an ffmpeg filter graph.

    ffmpeg reads a filter graph in two steps, and each step has its own
    special characters, so we escape twice:

    1. inside a filter's options ``:`` separates options, so ``\\``, ``'``
       and ``:`` get a backslash in front;
    2. the whole graph treats ``[ ] , ;`` as structure, so we wrap the value
       in single quotes. A quote inside is written as ``'\\''`` (close,
       escaped quote, reopen).

    ``C:/Users/Me/clip.srt`` becomes ``'C\\:/Users/Me/clip.srt'``.
    """
    level1 = value.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    return "'" + level1.replace("'", "'\\''") + "'"


# ---------- fonts ----------

def font_family(font_file: Path) -> str | None:
    """Read the family name (e.g. "Montserrat") from a .ttf or .otf file.

    The subtitles filter picks fonts by family name, not by file, so we
    look inside the font's "name" table for it. Returns None if the file
    can't be read.
    """
    try:
        data = Path(font_file).read_bytes()
        num_tables = struct.unpack(">H", data[4:6])[0]
        for i in range(num_tables):
            tag, _, offset, _ = struct.unpack(">4sIII", data[12 + 16 * i: 28 + 16 * i])
            if tag != b"name":
                continue
            _, count, strings = struct.unpack(">HHH", data[offset: offset + 6])
            found = {}
            for j in range(count):
                rec = offset + 6 + 12 * j
                platform, _, _, name_id, length, str_off = struct.unpack(">HHHHHH", data[rec: rec + 12])
                if name_id != 1:  # 1 = font family name
                    continue
                raw = data[offset + strings + str_off: offset + strings + str_off + length]
                # Platform 3 (Windows) and 0 (Unicode) store UTF-16, platform 1 (Mac) is plain bytes.
                found[platform] = raw.decode("utf-16-be" if platform in (0, 3) else "latin-1")
            for platform in (3, 0, 1):
                if found.get(platform):
                    return found[platform]
    except (OSError, struct.error, UnicodeDecodeError):
        pass
    return None


def subtitle_filter(srt_path: Path, opts: RenderOptions) -> str:
    """The ``subtitles`` filter: white text, black outline, lower third."""
    family = "Arial"
    extra = ""
    if opts.font is not None:
        family = font_family(opts.font) or Path(opts.font).stem
        # fontsdir tells libass where to find the font file.
        extra = f":fontsdir={escape_filter_value(filter_path(Path(opts.font).parent))}"
    margin_v = round((1 - opts.caption_y) * OUT_H)
    style = ",".join([
        # Lay the captions out on a real 1080x1920 canvas so sizes are in pixels.
        f"PlayResX={OUT_W}", f"PlayResY={OUT_H}",
        f"FontName={family.replace(',', ' ')}",
        f"FontSize={opts.font_size}",
        "PrimaryColour=&H00FFFFFF",  # white (ASS colours are &HAABBGGRR)
        "OutlineColour=&H00000000",  # black
        "BorderStyle=1", f"Outline={max(2, opts.font_size // 16)}", "Shadow=0",
        "Alignment=2",  # bottom centre
        f"MarginV={margin_v}", "MarginL=60", "MarginR=60",
    ])
    return (
        f"subtitles=filename={escape_filter_value(filter_path(srt_path))}"
        f"{extra}:force_style={escape_filter_value(style)}"
    )


# ---------- the render itself ----------

def render_command(input_path: Path, info: VideoInfo, clip: Clip, output: Path,
                   opts: RenderOptions, srt_path: Path | None,
                   audio_filter: str | None, ffmpeg: str = "ffmpeg") -> list[str]:
    """Build the main ffmpeg command for one clip."""
    graph = build_framing(opts.framing, info.width, info.height, opts.offset,
                          out_label="framed" if srt_path else "vout")
    if srt_path is not None:
        graph += f";[framed]{subtitle_filter(srt_path, opts)}[vout]"
    if audio_filter is not None:
        graph += f";[0:a:0]{audio_filter}[aout]"

    args = [
        ffmpeg, "-hide_banner", "-y",
        "-ss", ms_to_seconds(clip.start_ms),
        "-i", str(input_path),
        "-t", ms_to_seconds(clip.duration_ms),
        "-filter_complex", graph,
        "-map", "[vout]",
    ]
    if audio_filter is not None:
        args += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", str(audio.SAMPLE_RATE)]
    args += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",  # plays everywhere, including phones
        "-r", info.fps,  # keep the source frame rate
        "-movflags", "+faststart",  # lets the video start playing before it fully downloads
        str(output),
    ]
    return args


def render_clip(input_path: Path, info: VideoInfo, clip: Clip, out_dir: Path,
                opts: RenderOptions, captions: list[Caption] | None = None) -> RenderResult:
    """Render one clip and its contact sheet. Returns the output paths."""
    out_dir = Path(out_dir)
    video = out_dir / f"{clip.file_stem}.mp4"
    sheet = out_dir / f"{clip.file_stem}_contact_sheet.jpg"
    ffmpeg = "ffmpeg" if opts.dry_run else require_tool("ffmpeg")

    # 1. Captions for this clip only.
    srt_path = None
    if captions is not None:
        clip_caps = captions_for_clip(captions, clip.start_ms, clip.end_ms)
        if clip_caps:
            srt_path = out_dir / f"{clip.file_stem}.srt"
            if not opts.dry_run:
                write_srt(clip_caps, srt_path)
            log.info("  %d caption(s) in this clip", len(clip_caps))
        else:
            log.info("  no captions fall inside this clip")

    # 2. Loudness, pass 1.
    audio_filter = None
    if info.has_audio:
        if opts.dry_run:
            run(audio.measure_command(input_path, clip.start_ms, clip.end_ms, opts.lufs, ffmpeg), dry_run=True)
            audio_filter = audio.apply_filter(None, opts.lufs)
        else:
            measured = audio.measure(input_path, clip.start_ms, clip.end_ms, opts.lufs)
            audio_filter = audio.apply_filter(measured, opts.lufs)
    else:
        log.warning("  the input has no audio track, so the clip will be silent")

    # 3. Cut, reframe, caption, normalize, encode.
    run(render_command(input_path, info, clip, video, opts, srt_path, audio_filter, ffmpeg),
        dry_run=opts.dry_run)

    # 4. Contact sheet from the finished clip.
    make_contact_sheet(video, clip.duration_ms, sheet, dry_run=opts.dry_run)

    return RenderResult(video=video, contact_sheet=sheet, srt=srt_path)
