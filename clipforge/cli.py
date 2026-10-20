"""The ``clipforge`` command: read the options, check the inputs, render every clip.

Exit codes: 0 = every clip rendered, 1 = at least one clip failed,
2 = the inputs were invalid, so nothing was rendered.
"""

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .clips import ClipsError, load_clips
from .framing import FRAMINGS
from .probe import probe
from .render import RenderOptions, render_clip
from .runner import FFmpegError
from .srt import SrtError, read_srt
from .timecode import format_timecode

log = logging.getLogger("clipforge")


class InputError(Exception):
    """A problem with the user's input that should stop the run."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipforge",
        description="Turn a long 16:9 video into vertical 1080x1920 clips.",
        epilog="Example: clipforge --input talk.mp4 --clips clips.json --srt talk.srt --framing fill",
    )
    parser.add_argument("--input", required=True, type=Path, help="the long source video (MP4)")
    parser.add_argument("--clips", required=True, type=Path, help="JSON file listing the clips to cut")
    parser.add_argument("--srt", type=Path, help="optional SRT captions for the whole video")
    parser.add_argument("--out-dir", type=Path, default=Path("out"), help="where to save the clips (default: out)")
    parser.add_argument("--framing", choices=FRAMINGS, default="crop",
                        help="crop = centre crop, fill = full frame on a blurred background (default: crop)")
    parser.add_argument("--offset", type=float, default=0.0,
                        help="crop only: slide the crop from -1 (left) to 1 (right), default 0 (centre)")
    parser.add_argument("--font", type=Path, help="caption font file (.ttf or .otf)")
    parser.add_argument("--font-size", type=int, default=64, help="caption size in pixels (default: 64)")
    parser.add_argument("--caption-y", type=float, default=0.75,
                        help="where the bottom of the captions sits, 0 = top, 1 = bottom (default: 0.75)")
    parser.add_argument("--lufs", type=float, default=-14.0, help="target loudness in LUFS (default: -14)")
    parser.add_argument("--dry-run", action="store_true", help="print the ffmpeg commands without running them")
    parser.add_argument("--verbose", action="store_true", help="show more detail, including every ffmpeg command")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def check_options(args: argparse.Namespace) -> None:
    """Check the simple options before doing any real work."""
    if not args.input.is_file():
        raise InputError(f"input video not found: {args.input}")
    if args.srt is not None and not args.srt.is_file():
        raise InputError(f"SRT file not found: {args.srt}")
    if args.font is not None and not args.font.is_file():
        raise InputError(f"font file not found: {args.font}")
    if not -1.0 <= args.offset <= 1.0:
        raise InputError("--offset must be between -1 (left) and 1 (right)")
    if args.offset != 0 and args.framing != "crop":
        log.warning("--offset only applies to --framing crop, so it will be ignored")
    if not 8 <= args.font_size <= 400:
        raise InputError("--font-size must be between 8 and 400 pixels")
    if not 0.0 < args.caption_y <= 1.0:
        raise InputError("--caption-y must be above 0 and at most 1")
    if not -70 <= args.lufs <= -5:
        raise InputError("--lufs must be between -70 and -5 (YouTube and TikTok use about -14)")


def setup_logging(verbose: bool) -> None:
    # Emoji in the summary need UTF-8. Old Windows consoles may not use it.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(message)s")


def run(args: argparse.Namespace) -> int:
    check_options(args)

    info = probe(args.input)
    log.info(
        "🎬 %s: %dx%d, %.3f fps, %s, %s",
        args.input.name, info.width, info.height, info.fps_float,
        format_timecode(info.duration_ms), "with audio" if info.has_audio else "no audio",
    )

    clips = load_clips(args.clips, info.duration_ms)
    captions = read_srt(args.srt) if args.srt else None
    if captions is not None:
        log.info("💬 %d caption(s) loaded from %s", len(captions), args.srt.name)

    options = RenderOptions(
        framing=args.framing, offset=args.offset, font=args.font,
        font_size=args.font_size, caption_y=args.caption_y,
        lufs=args.lufs, dry_run=args.dry_run,
    )
    if not args.dry_run:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, str | None]] = []  # (clip name, error or None)
    for number, clip in enumerate(clips, start=1):
        log.info("\n[%d/%d] %s (%s -> %s)", number, len(clips), clip.name,
                 format_timecode(clip.start_ms), format_timecode(clip.end_ms))
        try:
            result = render_clip(args.input, info, clip, args.out_dir, options, captions)
        except (FFmpegError, OSError, ValueError) as exc:
            # One bad clip shouldn't stop the others.
            log.error("  ❌ failed: %s", exc)
            results.append((clip.name, str(exc).splitlines()[0]))
        else:
            if not args.dry_run:
                log.info("  ✅ %s", result.video)
            results.append((clip.name, None))

    print_summary(results, args.dry_run)
    return 0 if all(error is None for _, error in results) else 1


def print_summary(results: list[tuple[str, str | None]], dry_run: bool) -> None:
    title = "Dry run summary (nothing was rendered)" if dry_run else "Summary"
    lines = ["", f"── {title} ──"]
    for name, error in results:
        lines.append(f"  ✅ {name}" if error is None else f"  ❌ {name}: {error}")
    ok = sum(1 for _, error in results if error is None)
    lines.append(f"{ok} of {len(results)} clip(s) done")
    log.info("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    try:
        return run(args)
    except (InputError, ClipsError, SrtError, FFmpegError) as exc:
        # Friendly message instead of a Python traceback.
        log.error("❌ %s", exc)
        return 2
    except KeyboardInterrupt:
        log.error("\nStopped.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
