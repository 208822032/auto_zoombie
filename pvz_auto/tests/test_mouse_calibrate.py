import pytest

from pvz_auto.capture.window_capture import WindowInfo
from pvz_auto.control.mouse_calibrate import calibration_point, confirmation_allowed, select_window


def test_select_window_case_insensitive_and_requires_unique_match():
    first = WindowInfo(1, "Plants vs Zombies", -100, 20, 800, 600)
    assert select_window([first], "PLANTS") is first
    with pytest.raises(ValueError, match="no visible"):
        select_window([first], "minecraft")
    with pytest.raises(ValueError, match="ambiguous"):
        select_window([first, WindowInfo(2, "Plants vs Zombies 2", 0, 0, 800, 600)], "plants")


def test_calibration_point_reports_relative_pixel_as_screen_pixel():
    window = WindowInfo(1, "game", -100, 20, 800, 600)
    geometry, sx, sy = calibration_point(window, 12, 34)
    assert (geometry.left, geometry.top, geometry.width, geometry.height) == (-100, 20, 800, 600)
    assert (sx, sy) == (-88, 54)
    with pytest.raises(ValueError, match="outside"):
        calibration_point(window, 800, 0)


@pytest.mark.parametrize(
    "response,foreground,geometry,unobscured,expected",
    [
        ("CLICK", True, True, True, True),
        ("click", True, True, True, False),
        ("CLICK", False, True, True, False),
        ("CLICK", True, False, True, False),
        ("CLICK", True, True, False, False),
    ],
)
def test_confirmation_requires_exact_opt_in_and_safe_state(response, foreground, geometry, unobscured, expected):
    assert confirmation_allowed(response, foreground=foreground, geometry_unchanged=geometry, unobscured=unobscured) is expected
