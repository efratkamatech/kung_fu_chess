"""Img: a thin OpenCV wrapper for loading, compositing, drawing, and showing images.

This class is the graphics layer's *single* point of contact with OpenCV and numpy —
every other graphics module talks to images through ``Img``, never to ``cv2``
directly. Keeping the dependency in one place means the rest of the code reads in
game terms ("draw this sprite on the canvas") instead of array slicing, and if the
image backend ever changes only this file does.

Conventions (all inherited from OpenCV, so they are worth stating once):

- An image is a numpy array indexed ``[y, x]`` — **row first, then column**.
- Pixel positions passed to methods are ``(x, y)`` — **column first, then row** —
  matching ``cv2``'s own coordinate order.
- Colours are ``(B, G, R)`` or ``(B, G, R, A)`` tuples (blue first, not red).
- A 4th channel is *alpha*: 0 = fully transparent, 255 = fully opaque. Sprites are
  loaded with their alpha intact, and ``draw_on`` blends by it so transparent pixels
  of a piece let the board show through.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

import cv2
import numpy as np

# A colour is a B,G,R or B,G,R,A tuple; a path may be a str or a Path.
Color = Sequence[int]
PathLike = Union[str, Path]


class Img:
    """One image (a numpy array) plus the operations the graphics layer needs.

    Construct an empty ``Img()`` and fill it with :meth:`read` or :meth:`blank`, or
    wrap an existing array with ``Img(array)``. Every mutating method returns
    ``self`` so calls can be chained: ``Img().read(path, size=(100, 100)).draw_on(...)``.
    """

    __slots__ = ("img",)

    def __init__(self, img: Optional[np.ndarray] = None) -> None:
        self.img = img

    # --- construction --------------------------------------------------------

    @classmethod
    def blank(
        cls, width: int, height: int, channels: int = 3, color: Color = (0, 0, 0)
    ) -> "Img":
        """A fresh ``height x width`` image filled with ``color`` — the drawing canvas.

        ``channels`` is 3 (BGR) or 4 (BGRA). ``color`` is applied to as many channels
        as it provides; any remaining channels stay 0.
        """
        canvas = np.zeros((height, width, channels), dtype=np.uint8)
        canvas[:, :] = _fit_color(color, channels)
        return cls(canvas)

    def read(
        self,
        path: PathLike,
        size: Optional[Tuple[int, int]] = None,
        keep_aspect: bool = False,
        interpolation: int = cv2.INTER_AREA,
    ) -> "Img":
        """Load an image file (PNG/JPEG) into this ``Img``, keeping any alpha channel.

        ``size`` is an optional ``(width, height)`` to resize to; ``keep_aspect``
        fits the image inside that box without distorting it. A grayscale file is
        promoted to BGR so every image the layer handles has at least 3 channels.
        """
        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise FileNotFoundError(f"could not read image: {path}")
        if img.ndim == 2:  # grayscale -> BGR, so downstream code sees uniform channels
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        self.img = img
        if size is not None:
            self.resize(size[0], size[1], interpolation, keep_aspect)
        return self

    def copy(self) -> "Img":
        """An independent copy — mutating the copy never touches the original array."""
        return Img(None if self.img is None else self.img.copy())

    # --- properties ----------------------------------------------------------

    @property
    def width(self) -> int:
        """Width in pixels (columns)."""
        return self._require().shape[1]

    @property
    def height(self) -> int:
        """Height in pixels (rows)."""
        return self._require().shape[0]

    @property
    def channels(self) -> int:
        """Number of channels: 3 for BGR, 4 for BGRA."""
        return self._require().shape[2]

    # --- operations ----------------------------------------------------------

    def resize(
        self,
        width: int,
        height: int,
        interpolation: int = cv2.INTER_AREA,
        keep_aspect: bool = False,
    ) -> "Img":
        """Resize in place to ``width x height``.

        With ``keep_aspect`` the image is scaled to fit *inside* that box while
        preserving its proportions, so the result may be smaller than the box in one
        dimension (no padding is added).
        """
        img = self._require()
        if keep_aspect:
            h, w = img.shape[:2]
            scale = min(width / w, height / h)
            width, height = max(1, round(w * scale)), max(1, round(h * scale))
        self.img = cv2.resize(img, (int(width), int(height)), interpolation=interpolation)
        return self

    def draw_on(self, target: "Img", x: int, y: int) -> "Img":
        """Composite this image onto ``target`` with its top-left corner at ``(x, y)``.

        If this image has an alpha channel, it is blended over ``target`` by that
        alpha (transparent pixels leave ``target`` untouched); otherwise it is copied
        opaquely. The paste is clipped to ``target``'s bounds, so a piece drawn partly
        off the canvas simply shows the part that fits. Returns ``target`` for chaining.
        """
        src = self._require()
        dst = target._require()
        dst_h, dst_w = dst.shape[:2]
        src_h, src_w = src.shape[:2]
        x, y = int(x), int(y)

        # Overlap rectangle in target coordinates, then the matching slice of source.
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(dst_w, x + src_w), min(dst_h, y + src_h)
        if x0 >= x1 or y0 >= y1:
            return target  # entirely off the canvas: nothing to draw
        src_x0, src_y0 = x0 - x, y0 - y
        src_region = src[src_y0 : src_y0 + (y1 - y0), src_x0 : src_x0 + (x1 - x0)]
        dst_region = dst[y0:y1, x0:x1]

        if src_region.shape[2] == 4:
            alpha = src_region[:, :, 3:4].astype(np.float32) / 255.0
            blended = (
                src_region[:, :, :3].astype(np.float32) * alpha
                + dst_region[:, :, :3].astype(np.float32) * (1.0 - alpha)
            )
            dst_region[:, :, :3] = blended.astype(np.uint8)
        else:
            dst_region[:, :, :3] = src_region[:, :, :3]
        return target

    def draw_rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        color: Color = (0, 255, 0),
        thickness: int = 3,
    ) -> "Img":
        """Draw a rectangle outline with its top-left at ``(x, y)`` (for highlights)."""
        cv2.rectangle(
            self._require(),
            (int(x), int(y)),
            (int(x + width), int(y + height)),
            _fit_color(color, self.channels),
            thickness,
        )
        return self

    def fill_rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        color: Color,
        alpha: float = 1.0,
    ) -> "Img":
        """Blend a filled rectangle over the image (``alpha`` 0..1), clipped to bounds.

        Used for the translucent cooldown gauge so the piece shows through the fill.
        """
        dst = self._require()
        dst_h, dst_w = dst.shape[:2]
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(dst_w, int(x + width)), min(dst_h, int(y + height))
        if x0 >= x1 or y0 >= y1:
            return self
        region = dst[y0:y1, x0:x1, :3].astype(np.float32)
        fill = np.array(_fit_color(color, 3), dtype=np.float32)
        dst[y0:y1, x0:x1, :3] = (region * (1.0 - alpha) + fill * alpha).astype(np.uint8)
        return self

    def put_text(
        self,
        text: str,
        x: int,
        y: int,
        font_scale: float = 1.0,
        color: Color = (255, 255, 255, 255),
        thickness: int = 2,
        font: int = cv2.FONT_HERSHEY_SIMPLEX,
    ) -> "Img":
        """Draw ``text`` with its baseline-left at pixel ``(x, y)``.

        ``color`` is trimmed to this image's channel count, so the same BGRA colour
        works whether the target is a 3- or 4-channel image.
        """
        cv2.putText(
            self._require(),
            text,
            (int(x), int(y)),
            font,
            font_scale,
            _fit_color(color, self.channels),
            thickness,
            cv2.LINE_AA,
        )
        return self

    def put_text_centered(
        self,
        text: str,
        center_x: int,
        y: int,
        font_scale: float = 1.0,
        color: Color = (255, 255, 255, 255),
        thickness: int = 2,
        font: int = cv2.FONT_HERSHEY_SIMPLEX,
    ) -> "Img":
        """Draw ``text`` horizontally centred on ``center_x`` at baseline ``y``."""
        (text_w, _text_h), _ = cv2.getTextSize(text, font, font_scale, thickness)
        return self.put_text(
            text, int(center_x - text_w / 2), y, font_scale, color, thickness, font
        )

    # --- output --------------------------------------------------------------

    def save(self, path: PathLike) -> "Img":
        """Write the image to ``path`` as a file (used for headless visual checks)."""
        cv2.imwrite(str(path), self._require())
        return self

    # --- screen / window / mouse I/O ------------------------------------------
    # These talk to the actual OpenCV window and screen; they have no return value
    # to assert and need a live display, so they are excluded from coverage. The
    # logic that *decides* to call them lives elsewhere and is unit-tested.

    def show(  # pragma: no cover
        self, window_name: str = "KungFu Chess", wait_ms: int = 0
    ) -> int:
        """Display the image in a window and return the key pressed within ``wait_ms``.

        ``wait_ms == 0`` blocks until a key is pressed; the frame loop passes a small
        value to show a frame and move on. Returns the ``cv2.waitKey`` code (``-1`` if
        no key was pressed).
        """
        cv2.imshow(window_name, self._require())
        return cv2.waitKey(wait_ms)

    @staticmethod
    def is_window_closed(window_name: str) -> bool:  # pragma: no cover
        """True once the window has been closed (e.g. the user clicked its X button).

        Also true before the window exists, so the frame loop must show at least one
        frame (which creates the window) before it starts checking this.
        """
        return cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1

    @staticmethod
    def destroy_windows() -> None:  # pragma: no cover
        """Close every OpenCV window (called once when the frame loop ends)."""
        cv2.destroyAllWindows()

    # Mouse-event codes the input layer compares against, re-exported so no other
    # module has to import cv2.
    MOUSE_LEFT_DOWN = cv2.EVENT_LBUTTONDOWN
    MOUSE_RIGHT_DOWN = cv2.EVENT_RBUTTONDOWN

    @staticmethod
    def create_window(window_name: str, resizable: bool = True) -> None:  # pragma: no cover
        """Create a named window ahead of showing frames.

        A ``resizable`` window (``WINDOW_NORMAL``) lets the user drag it to any size —
        which is why clicks must be scaled from window pixels back to board pixels.
        """
        flag = cv2.WINDOW_NORMAL if resizable else cv2.WINDOW_AUTOSIZE
        cv2.namedWindow(window_name, flag)

    @staticmethod
    def set_mouse_callback(window_name: str, callback) -> None:  # pragma: no cover
        """Register ``callback(event, x, y, flags, param)`` for mouse events on a window."""
        cv2.setMouseCallback(window_name, callback)

    @staticmethod
    def window_image_size(window_name: str) -> Tuple[int, int]:  # pragma: no cover
        """The current on-screen size ``(width, height)`` of the window's image area.

        Used to scale mouse coordinates: when the window is resized this differs from
        the board's pixel size. Returns ``(0, 0)`` if the window has no size yet.
        """
        _x, _y, width, height = cv2.getWindowImageRect(window_name)
        return max(0, width), max(0, height)

    # --- internals -----------------------------------------------------------

    def _require(self) -> np.ndarray:
        """Return the backing array, or fail loudly if this ``Img`` is still empty."""
        if self.img is None:
            raise ValueError("Img has no image loaded (call read() or blank() first)")
        return self.img


def _fit_color(color: Color, channels: int) -> Tuple[int, ...]:
    """Trim or zero-pad ``color`` to exactly ``channels`` integer components."""
    values = [int(c) for c in color][:channels]
    values += [0] * (channels - len(values))
    return tuple(values)
