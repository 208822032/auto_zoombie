"""Explicit, fail-closed client-relative mouse calibration CLI."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable, Sequence

from pvz_auto.capture.window_capture import WindowCapture, WindowInfo, list_windows
from pvz_auto.config import WindowGeometry, validate_click_bounds
from pvz_auto.control.mouse import MouseController


def select_window(windows: Sequence[WindowInfo], title_substring: str) -> WindowInfo:
    """Select exactly one visible window matching a case-insensitive title."""
    if not title_substring.strip():
        raise ValueError("window title substring cannot be empty")
    matches = [w for w in windows if title_substring.casefold() in w.title.casefold()]
    if not matches:
        raise ValueError(f"no visible window title contains {title_substring!r}")
    if len(matches) != 1:
        choices = "; ".join(f"hwnd={w.hwnd} {w.title!r}" for w in matches)
        raise ValueError(f"title substring is ambiguous; matching windows: {choices}")
    return matches[0]


def calibration_point(window: WindowInfo, x: float, y: float) -> tuple[WindowGeometry, int, int]:
    """Validate client coordinates and return geometry plus desktop point."""
    geometry = WindowGeometry(window.left, window.top, window.width, window.height)
    sx, sy = validate_click_bounds(x, y, geometry, (window.left, window.top, window.width, window.height))
    return geometry, sx, sy


def confirmation_allowed(response: str, *, foreground: bool, geometry_unchanged: bool, unobscured: bool) -> bool:
    return response.strip() == "CLICK" and foreground and geometry_unchanged and unobscured


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate one safe client-relative PVZ mouse point")
    parser.add_argument("--contains", default="plants vs", help="case-insensitive visible window title substring")
    parser.add_argument("--x", type=float, required=True, help="client-relative x pixel")
    parser.add_argument("--y", type=float, required=True, help="client-relative y pixel")
    parser.add_argument("--click", action="store_true", help="opt in to one real click after interactive confirmation")
    args = parser.parse_args(argv)
    try:
        windows = list_windows()
        window = select_window(windows, args.contains)
        geometry, sx, sy = calibration_point(window, args.x, args.y)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Target: hwnd={window.hwnd} {window.title!r}")
    print(f"Client: {geometry.width}x{geometry.height}; origin=({geometry.left},{geometry.top})")
    print(f"Client point: ({args.x:g},{args.y:g}); screen point: ({sx},{sy})")
    if not args.click:
        print("Dry run: no click sent. Pass --click to opt in.")
        return 0
    print("Choose a safe empty lawn location. Confirm only if the game is foreground and unobscured.")
    try:
        response = input("Type CLICK to authorize exactly one click: ")
    except (EOFError, KeyboardInterrupt):
        print("Cancelled.")
        return 1
    if response.strip() != "CLICK":
        print("Cancelled; no click sent.")
        return 1
    controller = MouseController(geometry, hwnd=window.hwnd)
    try:
        if controller.stopped:
            raise RuntimeError("F12 emergency stop is active")
        # A fresh discovery plus capture refuses minimized, background, or
        # occluded windows and ensures the client geometry is still current.
        current = select_window(list_windows(), args.contains)
        if current.hwnd != window.hwnd or (current.left, current.top, current.width, current.height) != (
            geometry.left, geometry.top, geometry.width, geometry.height
        ):
            raise RuntimeError("game window geometry changed; rerun calibration")
        WindowCapture().capture(current)
        for remaining in range(3, 0, -1):
            if controller.stopped:
                raise RuntimeError("F12 emergency stop is active")
            print(f"Clicking in {remaining}... press F12 to cancel", flush=True)
            time.sleep(1)
        if controller.stopped:
            raise RuntimeError("F12 emergency stop is active")
        current = select_window(list_windows(), args.contains)
        if current.hwnd != window.hwnd or (current.left, current.top, current.width, current.height) != (
            geometry.left, geometry.top, geometry.width, geometry.height
        ):
            raise RuntimeError("game window geometry changed; click refused")
        WindowCapture().capture(current)
        controller.click(args.x, args.y)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Click refused: {exc}")
        return 1
    finally:
        controller.stop_emergency_hotkey_listener()
    print("One click sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
