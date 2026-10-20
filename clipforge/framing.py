"""Build the ffmpeg filter graphs that turn a 16:9 frame into 9:16.

A *filter graph* is a recipe ffmpeg applies to every frame. Filters are
joined with ``,`` (one after another) and chains with ``;``. Names in
square brackets like ``[bg]`` are labels, like layer names in Premiere.

Two framing modes:

* ``crop``: cut a 9:16 window out of the frame. ``offset`` slides that
  window: -1 is the far left, 0 the centre, 1 the far right.
* ``fill``: shrink the whole frame to fit the width, and put a blurred,
  enlarged copy of it behind, so nothing is cut off.
"""

OUT_W = 1080
OUT_H = 1920
FRAMINGS = ("crop", "fill")


def _even(value: float) -> int:
    """Round down to an even number. H.264 with yuv420p needs even sizes."""
    return int(value) // 2 * 2


def crop_box(src_w: int, src_h: int, offset: float = 0.0) -> tuple[int, int, int, int]:
    """Return (width, height, x, y) of the 9:16 window to cut from the source."""
    if not -1.0 <= offset <= 1.0:
        raise ValueError("offset must be between -1 (left) and 1 (right)")

    if src_w * OUT_H > src_h * OUT_W:
        # Source is wider than 9:16 (the normal case): keep full height.
        h = _even(src_h)
        w = _even(src_h * OUT_W / OUT_H)
        spare = src_w - w  # pixels left over, split between the two sides
        x = _even(spare / 2 + offset * spare / 2)
        y = 0
    else:
        # Source is already tall: keep full width, centre vertically.
        w = _even(src_w)
        h = _even(src_w * OUT_H / OUT_W)
        x = 0
        y = _even((src_h - h) / 2)
    return w, h, x, y


def crop_filter(src_w: int, src_h: int, offset: float = 0.0,
                in_label: str = "0:v", out_label: str = "framed") -> str:
    """Filter graph for the ``crop`` mode."""
    w, h, x, y = crop_box(src_w, src_h, offset)
    return (
        f"[{in_label}]crop={w}:{h}:{x}:{y},"
        f"scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1[{out_label}]"
    )


def fill_filter(in_label: str = "0:v", out_label: str = "framed", blur: int = 20) -> str:
    """Filter graph for the ``fill`` mode (blurred background)."""
    # We blur a small copy (a quarter size) and scale it back up. That is
    # much faster than blurring at 1080x1920 and looks smoother too.
    small_w, small_h = OUT_W // 4, OUT_H // 4
    return (
        f"[{in_label}]split=2[bg][fg];"
        # Background: zoom to cover the whole 9:16 area, crop, blur, enlarge.
        f"[bg]scale={small_w}:{small_h}:force_original_aspect_ratio=increase,"
        f"crop={small_w}:{small_h},boxblur={blur}:2,"
        f"scale={OUT_W}:{OUT_H},setsar=1[bgblur];"
        # Foreground: the full frame, scaled to fit inside 1080x1920.
        f"[fg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease:"
        f"force_divisible_by=2:flags=lanczos,setsar=1[fgfit];"
        # Put the foreground in the middle of the background.
        f"[bgblur][fgfit]overlay=(W-w)/2:(H-h)/2[{out_label}]"
    )


def build_framing(framing: str, src_w: int, src_h: int, offset: float = 0.0,
                  in_label: str = "0:v", out_label: str = "framed") -> str:
    """Return the filter graph for the chosen framing mode."""
    if framing == "crop":
        return crop_filter(src_w, src_h, offset, in_label, out_label)
    if framing == "fill":
        return fill_filter(in_label, out_label)
    raise ValueError(f"unknown framing {framing!r}: choose one of {', '.join(FRAMINGS)}")
