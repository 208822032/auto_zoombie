import pytest

from pvz_auto.config import (
    WindowGeometry,
    client_to_screen,
    normalized_to_screen,
    screen_to_client,
    validate_click_bounds,
)
from pvz_auto.capture.window_capture import rectangles_overlap
from pvz_auto.control.mouse import MouseController, require_foreground_window, require_target_hwnd


def test_client_screen_round_trip():
    geometry = WindowGeometry(120, 80, 800, 600)
    screen = client_to_screen(33, 47, geometry)
    assert screen == (153, 127)
    assert screen_to_client(*screen, geometry) == (33, 47)


def test_normalized_coordinates_cover_client_bounds():
    geometry = WindowGeometry(-1920, 40, 1280, 720)
    assert normalized_to_screen(0, 0, geometry) == (-1920, 40)
    assert normalized_to_screen(1, 1, geometry) == (-641, 759)


@pytest.mark.parametrize("point", [(-0.1, 0), (0, 1.1)])
def test_normalized_coordinates_reject_out_of_range(point):
    with pytest.raises(ValueError):
        normalized_to_screen(*point, WindowGeometry(0, 0, 10, 10))


def test_click_bounds_allow_negative_origin_but_reject_outside_client_or_desktop():
    geometry = WindowGeometry(-100, 50, 20, 10)
    assert validate_click_bounds(19, 9, geometry, (-100, 0, 200, 100)) == (-81, 59)
    with pytest.raises(ValueError, match="client area"):
        validate_click_bounds(19.1, 9, geometry, (-100, 0, 200, 100))
    with pytest.raises(ValueError, match="virtual desktop"):
        validate_click_bounds(0, 0, geometry, (-99, 0, 200, 100))


def test_rectangle_overlap_detects_partial_intersection_only():
    assert rectangles_overlap((0, 0, 10, 10), (9, 9, 12, 12))
    assert not rectangles_overlap((0, 0, 10, 10), (10, 2, 12, 8))


def test_emergency_stop_is_sticky_and_blocks_click():
    mouse = MouseController(WindowGeometry(0, 0, 10, 10))
    mouse.emergency_stop()
    assert mouse.stopped
    with pytest.raises(RuntimeError, match="emergency-stopped"):
        mouse.click(2, 3)


def test_target_hwnd_is_required_before_input():
    with pytest.raises(RuntimeError, match="requires the target game HWND"):
        require_target_hwnd(None)
    with pytest.raises(RuntimeError, match="requires the target game HWND"):
        require_target_hwnd(0)
    assert require_target_hwnd(0x12345678) == 0x12345678


def test_foreground_guard_rejects_focus_switch():
    require_foreground_window(0x1234, 0x1234)
    with pytest.raises(RuntimeError, match="not foreground"):
        require_foreground_window(0x1234, 0x5678)
    with pytest.raises(RuntimeError, match="not foreground"):
        require_foreground_window(0x1234, None)
