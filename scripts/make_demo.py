"""Make a synthetic demo video, run ClipForge on it, and build the README images.

Run it from the project folder:

    python scripts/make_demo.py

It creates (all ignored by git, except assets/):

* ``demo/source.mp4``: a 30 second 16:9 test video with a beep
* ``demo/out/``: the vertical clips ClipForge made from it
* ``assets/contact_sheet.jpg`` and ``assets/before_after.jpg`` for the README
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clipforge import cli  # noqa: E402
from clipforge.framing import build_framing  # noqa: E402
from clipforge.render import escape_filter_value, filter_path  # noqa: E402


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def make_source(path: Path) -> None:
    """A 30 s, 1920x1080, 30 fps test pattern with a 440 Hz tone."""
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", "30",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(path),
    )


def label(text: str, font: Path | None) -> str:
    """A drawtext filter that writes a label at the top of a panel."""
    if font is None:
        return "null"
    return (
        f"drawtext=fontfile={escape_filter_value(filter_path(font))}:text={escape_filter_value(text)}"
        ":fontcolor=white:fontsize=34:box=1:boxcolor=black@0.6:boxborderw=12:x=(w-tw)/2:y=24"
    )


def make_before_after(source: Path, output: Path, font: Path | None, at: str = "4") -> None:
    """Original 16:9 frame | crop | fill, side by side, all 640 px tall."""
    crop = build_framing("crop", 1920, 1080, in_label="c", out_label="crop")
    fill = build_framing("fill", 1920, 1080, in_label="f", out_label="fill")
    graph = ";".join([
        "[0:v]split=3[o][c][f]",
        crop,
        fill,
        f"[o]scale=-2:640,{label('Original 16:9', font)},pad=iw+12:ih+12:6:6:color=0x111111[po]",
        f"[crop]scale=-2:640,{label('crop', font)},pad=iw+12:ih+12:6:6:color=0x111111[pc]",
        f"[fill]scale=-2:640,{label('fill', font)},pad=iw+12:ih+12:6:6:color=0x111111[pf]",
        "[po][pc][pf]hstack=inputs=3[out]",
    ])
    ffmpeg("-ss", at, "-i", str(source), "-filter_complex", graph,
           "-map", "[out]", "-frames:v", "1", "-q:v", "2", str(output))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", type=Path, help="font for captions and image labels (.ttf/.otf)")
    args = parser.parse_args()

    demo = ROOT / "demo"
    out = demo / "out"
    assets = ROOT / "assets"
    demo.mkdir(exist_ok=True)
    assets.mkdir(exist_ok=True)

    source = demo / "source.mp4"
    print("1/3 making the synthetic source video...")
    make_source(source)

    print("2/3 running ClipForge on it...")
    cli_args = [
        "--input", str(source),
        "--clips", str(ROOT / "examples" / "clips.json"),
        "--srt", str(ROOT / "examples" / "captions.srt"),
        "--out-dir", str(out),
        "--framing", "fill",
    ]
    if args.font:
        cli_args += ["--font", str(args.font)]
    code = cli.main(cli_args)
    if code != 0:
        return code

    print("3/3 building the README images...")
    (assets / "contact_sheet.jpg").write_bytes((out / "hook_contact_sheet.jpg").read_bytes())
    make_before_after(source, assets / "before_after.jpg", args.font)
    print(f"done: see {out} and {assets}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
