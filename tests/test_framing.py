import pytest

from clipforge.framing import build_framing, crop_box, crop_filter, fill_filter


def test_crop_box_center_1080p():
    # 1080 * 9/16 = 607.5 -> 606 (even). Spare = 1314, centred x = 657 -> 656.
    assert crop_box(1920, 1080) == (606, 1080, 656, 0)


def test_crop_box_far_left_and_right():
    w, h, x_left, _ = crop_box(1920, 1080, -1.0)
    _, _, x_right, _ = crop_box(1920, 1080, 1.0)
    assert x_left == 0
    assert x_right + w <= 1920
    assert x_right == 1314


def test_crop_box_4k():
    assert crop_box(3840, 2160) == (1214, 2160, 1312, 0)


def test_crop_box_values_are_even():
    for offset in (-1, -0.37, 0, 0.5, 1):
        assert all(v % 2 == 0 for v in crop_box(1280, 720, offset))


def test_crop_box_tall_source():
    w, h, x, y = crop_box(1080, 2400)
    assert (w, h, x) == (1080, 1920, 0)
    assert y == 240


@pytest.mark.parametrize("bad", [-1.01, 1.5])
def test_crop_offset_out_of_range(bad):
    with pytest.raises(ValueError):
        crop_box(1920, 1080, bad)


def test_crop_filter_text():
    assert crop_filter(1920, 1080) == (
        "[0:v]crop=606:1080:656:0,scale=1080:1920:flags=lanczos,setsar=1[framed]"
    )


def test_fill_filter_has_blur_and_overlay():
    graph = fill_filter()
    assert graph.startswith("[0:v]split=2[bg][fg];")
    assert "boxblur" in graph
    assert "overlay=(W-w)/2:(H-h)/2[framed]" in graph


def test_build_framing_dispatch():
    assert build_framing("crop", 1920, 1080).startswith("[0:v]crop=")
    assert build_framing("fill", 1920, 1080).startswith("[0:v]split")


def test_build_framing_unknown():
    with pytest.raises(ValueError, match="unknown framing"):
        build_framing("zoom", 1920, 1080)
