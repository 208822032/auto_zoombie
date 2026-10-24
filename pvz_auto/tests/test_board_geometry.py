import math

import pytest

from pvz_auto.perception.board import (
    LawnRect,
    cell_center,
    client_x_to_board_x,
    pixel_to_cell,
)
from pvz_auto.state import GridDimensions


LAWN = LawnRect(100, 50, 900, 500)
GRID = GridDimensions(rows=5, columns=9)


def test_pixel_to_cell_uses_inclusive_top_left_and_exclusive_bottom_right():
    assert pixel_to_cell(100, 50, LAWN, GRID) == (0, 0)
    assert pixel_to_cell(199.999, 149.999, LAWN, GRID) == (0, 0)
    assert pixel_to_cell(200, 150, LAWN, GRID) == (1, 1)
    assert pixel_to_cell(1000, 100, LAWN, GRID) is None
    assert pixel_to_cell(200, 550, LAWN, GRID) is None
    assert pixel_to_cell(99.99, 50, LAWN, GRID) is None


def test_cell_center_round_trips_for_nonstandard_grid_and_rect():
    lawn = LawnRect(-20, 7, 333, 221)
    grid = GridDimensions(rows=3, columns=7)
    for row in range(grid.rows):
        for column in range(grid.columns):
            assert pixel_to_cell(*cell_center(row, column, lawn, grid), lawn, grid) == (row, column)


def test_continuous_board_x_maps_edges_and_interior():
    assert client_x_to_board_x(100, LAWN, GRID) == 0
    assert client_x_to_board_x(550, LAWN, GRID) == 4.5
    assert client_x_to_board_x(1000, LAWN, GRID) == 9
    with pytest.raises(ValueError, match="outside"):
        client_x_to_board_x(1000.01, LAWN, GRID)


@pytest.mark.parametrize("rect", [
    (float("nan"), 0, 1, 1), (0, float("inf"), 1, 1),
    (0, 0, 0, 1), (0, 0, 1, -1), (False, 0, 1, 1),
])
def test_rectangle_requires_finite_origin_and_positive_size(rect):
    with pytest.raises(ValueError):
        LawnRect(*rect)


@pytest.mark.parametrize("point", [
    (float("nan"), 1), (1, float("inf")), (True, 1), (1, "2"), (10**1000, 1),
])
def test_pixel_lookup_rejects_nonfinite_or_non_numeric_points(point):
    with pytest.raises(ValueError):
        pixel_to_cell(*point, LAWN, GRID)


@pytest.mark.parametrize("cell", [(-1, 0), (0, -1), (5, 0), (0, 9), (True, 0), (0, 1.0)])
def test_cell_center_rejects_invalid_indices(cell):
    with pytest.raises(ValueError):
        cell_center(*cell, LAWN, GRID)


def test_lawn_overflow_and_nonfinite_board_x_are_rejected():
    # A finite rectangle can still overflow when its far edge is calculated.
    with pytest.raises(ValueError):
        LawnRect(1e308, 0, 1e308, 1)
    with pytest.raises(ValueError):
        client_x_to_board_x(math.inf, LAWN, GRID)
