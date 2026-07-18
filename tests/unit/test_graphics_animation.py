from kfchess.graphics.animation import Animation
from kfchess.graphics.img import Img


def frames(n):
    return [Img.blank(1, 1, 3, (i, i, i)) for i in range(n)]


def test_frame_advances_with_fps():
    f = frames(5)
    anim = Animation(f, fps=4, loop=True)  # 4 fps -> a new frame every 250 ms
    assert anim.frame_at(0) is f[0]
    assert anim.frame_at(250) is f[1]
    assert anim.frame_at(500) is f[2]


def test_looping_wraps_around():
    f = frames(5)
    anim = Animation(f, fps=4, loop=True)
    assert anim.frame_at(1250) is f[0]  # 1250 ms * 4 fps = frame 5 -> wraps to 0


def test_non_looping_holds_last_frame():
    f = frames(5)
    anim = Animation(f, fps=10, loop=False)
    assert anim.frame_at(1000) is f[4]  # index 10 clamped to the last frame
    assert anim.frame_at(9999) is f[4]


def test_zero_fps_stays_on_first_frame():
    f = frames(3)
    anim = Animation(f, fps=0, loop=True)
    assert anim.frame_at(5000) is f[0]


def test_negative_elapsed_clamps_to_the_first_frame():
    f = frames(4)
    assert Animation(f, fps=8, loop=True).frame_at(-500) is f[0]


def test_frame_count_reports_the_number_of_frames():
    assert Animation(frames(7), fps=4, loop=True).frame_count == 7


def test_duration_ms_from_frames_and_fps():
    assert Animation(frames(5), fps=10, loop=False).duration_ms == 500


def test_duration_ms_is_zero_when_fps_is_zero():
    assert Animation(frames(5), fps=0, loop=False).duration_ms == 0


def test_empty_frames_rejected():
    try:
        Animation([], fps=4, loop=True)
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty frames")
