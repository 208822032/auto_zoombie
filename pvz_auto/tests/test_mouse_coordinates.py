import ctypes
from types import SimpleNamespace

import pytest

from pvz_auto.config import (
    WindowGeometry,
    client_to_screen,
    normalized_to_screen,
    refresh_window_geometry,
    screen_to_client,
    validate_click_bounds,
)
from pvz_auto.capture.window_capture import rectangles_overlap
import pvz_auto.control.mouse as mouse_module
from pvz_auto.control.mouse import (
    MouseController,
    click_event_flags,
    require_foreground_window,
    require_target_hwnd,
)


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


def test_live_window_origin_refreshes_and_resize_fails_closed():
    calibrated = WindowGeometry(10, 20, 800, 600)
    assert refresh_window_geometry(calibrated, 50, 70, 800, 600) == WindowGeometry(50, 70, 800, 600)
    with pytest.raises(ValueError, match="size changed"):
        refresh_window_geometry(calibrated, 50, 70, 1024, 600)


def test_click_move_and_down_flags_are_batched_without_losing_virtual_desktop():
    move_flags, down_flags = click_event_flags()
    assert move_flags == (0x0001 | 0x8000 | 0x4000)
    assert down_flags == 0x0002


def test_click_submits_move_and_down_in_one_sendinput_batch(monkeypatch):
    batches = []
    user32 = SimpleNamespace()

    def get_client_rect(_hwnd, rect_ptr):
        rect = ctypes.cast(rect_ptr, ctypes.POINTER(ctypes.wintypes.RECT)).contents
        rect.left, rect.top, rect.right, rect.bottom = 0, 0, 800, 600
        return 1

    def client_to_screen(_hwnd, point_ptr):
        point = ctypes.cast(point_ptr, ctypes.POINTER(ctypes.wintypes.POINT)).contents
        point.x, point.y = 100, 50
        return 1

    def send_input(count, events, _size):
        flags = tuple(events[i].union.mi.dwFlags for i in range(count)) if count == 2 else ()
        batches.append((count, flags))
        return count

    user32.GetForegroundWindow = lambda: 123
    user32.GetClientRect = get_client_rect
    user32.ClientToScreen = client_to_screen
    user32.GetSystemMetrics = lambda index: {76: 0, 77: 0, 78: 2000, 79: 1200}[index]
    user32.SendInput = send_input
    monkeypatch.setattr(mouse_module.sys, "platform", "win32")
    monkeypatch.setattr(mouse_module, "ensure_per_monitor_dpi_awareness", lambda: None)
    monkeypatch.setattr(mouse_module.ctypes, "windll", SimpleNamespace(user32=user32), raising=False)

    mouse_module.MouseController(
        WindowGeometry(1, 2, 800, 600), hwnd=123, emergency_hotkey=False
    ).click(5, 6)
    assert batches[0] == (2, (0xC001, 0x0002))
    assert batches[1][0] == 1  # guaranteed left-button release


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
