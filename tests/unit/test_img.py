import cv2
import numpy as np

from kfchess.config import BOARD_IMAGE
from kfchess.graphics.img import Img, _fit_color


def test_blank_has_size_channels_and_fill_color():
    img = Img.blank(4, 3, channels=3, color=(10, 20, 30))
    assert (img.width, img.height, img.channels) == (4, 3, 3)
    assert tuple(img.img[0, 0]) == (10, 20, 30)


def test_read_loads_and_resizes_an_image():
    img = Img().read(BOARD_IMAGE, size=(120, 90))
    assert (img.width, img.height) == (120, 90)
    assert img.channels in (3, 4)


def test_read_missing_file_raises():
    try:
        Img().read("this_file_does_not_exist.png")
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError for a missing image")


def test_read_grayscale_is_promoted_to_bgr_and_keeps_its_size(tmp_path):
    path = tmp_path / "gray.png"
    cv2.imwrite(str(path), np.full((10, 12), 128, dtype=np.uint8))  # 2-D grayscale
    img = Img().read(path)  # no size -> also exercises the "no resize" path
    assert img.channels == 3
    assert (img.width, img.height) == (12, 10)


def test_fill_rect_fully_off_canvas_is_a_no_op():
    canvas = Img.blank(4, 4, 3, (1, 1, 1))
    before = canvas.img.copy()
    canvas.fill_rect(50, 50, 10, 10, (0, 0, 255), 0.5)
    assert np.array_equal(before, canvas.img)


def test_copy_is_independent_of_the_original():
    original = Img.blank(4, 4, 3, (1, 2, 3))
    clone = original.copy()
    clone.resize(2, 2)
    assert (original.width, original.height) == (4, 4)
    assert (clone.width, clone.height) == (2, 2)


def test_resize_keep_aspect_fits_inside_the_box():
    img = Img.blank(40, 20, 3).resize(10, 10, keep_aspect=True)
    assert (img.width, img.height) == (10, 5)  # 2:1 ratio preserved, fit inside 10x10


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


def test_draw_on_opaque_3channel_source_copies_pixels():
    canvas = Img.blank(2, 2, 3, (0, 0, 0))
    sprite = Img(np.full((2, 2, 3), 200, dtype=np.uint8))  # no alpha channel
    sprite.draw_on(canvas, 0, 0)
    assert tuple(canvas.img[0, 0]) == (200, 200, 200)


def test_draw_on_clips_when_partly_off_canvas():
    canvas = Img.blank(2, 2, 3, (0, 0, 0))
    sprite = Img(np.full((2, 2, 4), 255, dtype=np.uint8))
    sprite.draw_on(canvas, 1, 1)  # only the bottom-right pixel overlaps
    assert tuple(canvas.img[1, 1]) == (255, 255, 255)
    assert tuple(canvas.img[0, 0]) == (0, 0, 0)


def test_draw_on_fully_off_canvas_is_a_no_op():
    canvas = Img.blank(2, 2, 3, (5, 5, 5))
    Img(np.full((2, 2, 4), 255, dtype=np.uint8)).draw_on(canvas, 50, 50)
    assert tuple(canvas.img[0, 0]) == (5, 5, 5)


def test_fill_rect_blends_by_alpha():
    canvas = Img.blank(2, 2, 3, (0, 0, 0))
    canvas.fill_rect(0, 0, 2, 2, (0, 255, 255), alpha=0.5)
    assert tuple(canvas.img[0, 0]) == (0, 127, 127)


def test_draw_rect_and_text_mutate_the_image():
    canvas = Img.blank(80, 80, 3, (0, 0, 0))
    before = canvas.img.copy()
    canvas.draw_rect(5, 5, 30, 30, (0, 255, 0), 2)
    canvas.put_text("hi", 5, 60, 0.6, (255, 255, 255), 1)
    canvas.put_text_centered("mid", 40, 70, 0.5, (255, 255, 255), 1)
    assert not np.array_equal(before, canvas.img)


def test_save_writes_a_nonempty_file(tmp_path):
    out = tmp_path / "frame.png"
    Img.blank(8, 8, 3, (9, 9, 9)).save(out)
    assert out.exists() and out.stat().st_size > 0


def test_fit_color_trims_and_pads_to_channels():
    assert _fit_color((1, 2, 3, 4), 3) == (1, 2, 3)
    assert _fit_color((1, 2), 3) == (1, 2, 0)


def test_require_raises_when_empty():
    try:
        _ = Img().width
    except ValueError:
        return
    raise AssertionError("expected ValueError for an empty Img")
