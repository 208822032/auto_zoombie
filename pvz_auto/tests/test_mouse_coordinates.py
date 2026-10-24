import pytest

from pvz_auto.config import WindowGeometry, client_to_screen, normalized_to_screen, screen_to_client
from pvz_auto.control.mouse import MouseController


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


def test_emergency_stop_is_sticky_and_blocks_click():
    mouse = MouseController(WindowGeometry(0, 0, 10, 10))
    mouse.emergency_stop()
    assert mouse.stopped
    with pytest.raises(RuntimeError, match="emergency-stopped"):
        mouse.click(2, 3)
