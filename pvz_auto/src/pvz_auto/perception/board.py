"""Pure conversions between client pixels and configurable lawn-grid units.

``LawnRect`` uses client-relative ``left``, ``top``, ``width``, and ``height``.
Cell lookup treats its right and bottom edges as exclusive. Continuous board-x
conversion includes both horizontal edges, mapping them to 0 and
``grid.columns`` respectively, matching the state model's board-x range.
"""

from dataclasses import dataclass
import math
from numbers import Real

from pvz_auto.state import GridDimensions


def _finite_number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError(f"{name} must be finite") from error
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


@dataclass(frozen=True, slots=True)
class LawnRect:
    """Explicit client-relative lawn bounds, represented by origin and size."""

    left: float
    top: float
    width: float
    height: float

    def __post_init__(self) -> None:
        for name in ("left", "top", "width", "height"):
            _finite_number(getattr(self, name), name)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("lawn width and height must be positive")
        if not math.isfinite(self.left + self.width) or not math.isfinite(self.top + self.height):
            raise ValueError("lawn far edges must be finite")


def _check_inputs(lawn: LawnRect, grid: GridDimensions) -> None:
    if not isinstance(lawn, LawnRect):
        raise ValueError("lawn must be a LawnRect")
    if not isinstance(grid, GridDimensions):
        raise ValueError("grid must be GridDimensions")


def pixel_to_cell(x: float, y: float, lawn: LawnRect,
                  grid: GridDimensions) -> tuple[int, int] | None:
    """Return ``(row, column)`` for a client point, or ``None`` outside lawn.

    The lawn's left/top edges are included and its right/bottom edges excluded.
    """
    _check_inputs(lawn, grid)
    px = _finite_number(x, "x")
    py = _finite_number(y, "y")
    right, bottom = lawn.left + lawn.width, lawn.top + lawn.height
    if not (lawn.left <= px < right and lawn.top <= py < bottom):
        return None
    column = min(int((px - lawn.left) * grid.columns / lawn.width), grid.columns - 1)
    row = min(int((py - lawn.top) * grid.rows / lawn.height), grid.rows - 1)
    return row, column


def cell_center(row: int, column: int, lawn: LawnRect,
                grid: GridDimensions) -> tuple[float, float]:
    """Return the client-relative pixel center of a valid zero-based cell."""
    _check_inputs(lawn, grid)
    if (isinstance(row, bool) or not isinstance(row, int) or row < 0
            or row >= grid.rows):
        raise ValueError("row is outside the grid")
    if (isinstance(column, bool) or not isinstance(column, int) or column < 0
            or column >= grid.columns):
        raise ValueError("column is outside the grid")
    return (lawn.left + (column + 0.5) * lawn.width / grid.columns,
            lawn.top + (row + 0.5) * lawn.height / grid.rows)


def client_x_to_board_x(x: float, lawn: LawnRect,
                        grid: GridDimensions) -> float:
    """Convert client x to continuous board units in ``[0, columns]``.

    Both horizontal lawn edges are valid; coordinates outside them raise
    ``ValueError``. The right edge maps exactly to ``grid.columns``.
    """
    _check_inputs(lawn, grid)
    px = _finite_number(x, "x")
    right = lawn.left + lawn.width
    if not lawn.left <= px <= right:
        raise ValueError("x is outside the lawn bounds")
    return (px - lawn.left) * grid.columns / lawn.width
