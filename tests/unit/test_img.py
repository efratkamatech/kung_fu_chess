import numpy as np

from kfchess.graphics.img import Img, _fit_color


def test_blank_has_size_channels_and_fill_color():
    img = Img.blank(4, 3, channels=3, color=(10, 20, 30))
    assert (img.width, img.height, img.channels) == (4, 3, 3)
    assert tuple(img.img[0, 0]) == (10, 20, 30)


def test_draw_on_opaque_alpha_replaces_pixels():
    canvas = Img.blank(2, 2, 3, (0, 0, 0))
    sprite = Img(np.zeros((2, 2, 4), dtype=np.uint8))
    sprite.img[:, :, 0] = 255  # blue
    sprite.img[:, :, 3] = 255  # fully opaque
    sprite.draw_on(canvas, 0, 0)
    assert tuple(canvas.img[0, 0]) == (255, 0, 0)


def test_draw_on_transparent_alpha_leaves_canvas_untouched():
    canvas = Img.blank(2, 2, 3, (7, 8, 9))
    sprite = Img(np.zeros((2, 2, 4), dtype=np.uint8))
    sprite.img[:, :, 0] = 255
    sprite.img[:, :, 3] = 0  # fully transparent
    sprite.draw_on(canvas, 0, 0)
    assert tuple(canvas.img[0, 0]) == (7, 8, 9)


def test_draw_on_clips_when_partly_off_canvas():
    canvas = Img.blank(2, 2, 3, (0, 0, 0))
    sprite = Img(np.full((2, 2, 4), 255, dtype=np.uint8))
    sprite.draw_on(canvas, 1, 1)  # only the bottom-right pixel overlaps
    assert tuple(canvas.img[1, 1]) == (255, 255, 255)
    assert tuple(canvas.img[0, 0]) == (0, 0, 0)


def test_fill_rect_blends_by_alpha():
    canvas = Img.blank(2, 2, 3, (0, 0, 0))
    canvas.fill_rect(0, 0, 2, 2, (0, 255, 255), alpha=0.5)
    assert tuple(canvas.img[0, 0]) == (0, 127, 127)


def test_fit_color_trims_and_pads_to_channels():
    assert _fit_color((1, 2, 3, 4), 3) == (1, 2, 3)
    assert _fit_color((1, 2), 3) == (1, 2, 0)


def test_require_raises_when_empty():
    try:
        _ = Img().width
    except ValueError:
        return
    raise AssertionError("expected ValueError for an empty Img")
