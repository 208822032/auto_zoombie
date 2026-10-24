"""Pure screen/client coordinate conversions."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class WindowGeometry:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("window dimensions must be positive")


def client_to_screen(x: float, y: float, window: WindowGeometry) -> tuple[int, int]:
    """Convert client pixels to desktop pixels, rounding to nearest integer."""
    return round(window.left + x), round(window.top + y)


def validate_click_bounds(
    x: float,
    y: float,
    window: WindowGeometry,
    virtual_desktop: tuple[int, int, int, int],
) -> tuple[int, int]:
    """Validate client and virtual-desktop bounds, returning screen pixels.

    ``virtual_desktop`` is ``(left, top, width, height)``. Bounds are pixel
    inclusive at the top/left and exclusive at the right/bottom.
    """
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("click coordinates must be finite")
    if not (0 <= x <= window.width - 1 and 0 <= y <= window.height - 1):
        raise ValueError("click coordinates are outside the window client area")
    left, top, width, height = virtual_desktop
    if width <= 0 or height <= 0:
        raise ValueError("virtual desktop dimensions must be positive")
    sx, sy = client_to_screen(x, y, window)
    if not (left <= sx < left + width and top <= sy < top + height):
        raise ValueError("click coordinates are outside the virtual desktop")
    return sx, sy


def normalized_to_screen(x: float, y: float, window: WindowGeometry) -> tuple[int, int]:
    """Convert normalized client coordinates [0, 1] to desktop pixels."""
    if not 0 <= x <= 1 or not 0 <= y <= 1:
        raise ValueError("normalized coordinates must be in [0, 1]")
    return client_to_screen(x * (window.width - 1), y * (window.height - 1), window)


def screen_to_client(x: int, y: int, window: WindowGeometry) -> tuple[int, int]:
    return x - window.left, y - window.top
