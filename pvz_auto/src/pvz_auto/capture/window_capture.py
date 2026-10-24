"""Windows client-area capture using MSS.

The backend is deliberately small and replaceable. It captures the client area
of a selected top-level window; it does not infer gameplay state.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_dpi_lock = threading.Lock()
_dpi_ready = False


def ensure_per_monitor_dpi_awareness() -> None:
    """Set process DPI awareness before any HWND bounds are queried.

    Windows reports ERROR_ACCESS_DENIED if a manifest or earlier call already
    selected a process context. That is accepted only when the current thread
    is already per-monitor aware (awareness value 2).
    """
    global _dpi_ready
    if sys.platform != "win32":
        raise OSError("DPI awareness setup is available only on Windows")
    with _dpi_lock:
        if _dpi_ready:
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_context = user32.SetProcessDpiAwarenessContext
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = ctypes.wintypes.BOOL
        context_per_monitor_v2 = ctypes.c_void_p(ctypes.c_size_t(-4).value)
        if set_context(context_per_monitor_v2):
            _dpi_ready = True
            return
        error = ctypes.get_last_error()
        if error == 5:  # ERROR_ACCESS_DENIED: context already set by manifest/caller.
            thread_context = user32.GetThreadDpiAwarenessContext
            thread_context.argtypes = []
            thread_context.restype = ctypes.c_void_p
            get_awareness = user32.GetAwarenessFromDpiAwarenessContext
            get_awareness.argtypes = [ctypes.c_void_p]
            get_awareness.restype = ctypes.c_int
            if get_awareness(thread_context()) >= 2:
                _dpi_ready = True
                return
            raise OSError("process DPI awareness was already set below per-monitor awareness")
        raise ctypes.WinError(error, "SetProcessDpiAwarenessContext failed")


def _configure_window_api(user32: Any) -> None:
    wintypes = ctypes.wintypes
    user32.EnumWindows.argtypes = [
        ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
        wintypes.LPARAM,
    ]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetTopWindow.argtypes = [wintypes.HWND]
    user32.GetTopWindow.restype = wintypes.HWND
    user32.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
    user32.GetWindow.restype = wintypes.HWND


def rectangles_overlap(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> bool:
    """Return whether two ``(left, top, right, bottom)`` rectangles intersect."""
    return first[0] < second[2] and first[2] > second[0] and first[1] < second[3] and first[3] > second[1]


def _validate_capture_window(user32: Any, window: "WindowInfo") -> None:
    hwnd = window.hwnd
    if user32.IsIconic(hwnd):
        raise RuntimeError(f"capture refused: window is minimized: {window.title}")
    if not user32.IsWindowVisible(hwnd):
        raise RuntimeError(f"capture refused: window is not visible: {window.title}")
    if user32.GetForegroundWindow() != hwnd:
        raise RuntimeError(f"capture refused: game window is not foreground: {window.title}")

    # GetTopWindow/GW_HWNDNEXT enumerate top-level windows in z-order. Fail
    # closed on any visible window above the target that intersects its client.
    game = ctypes.wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(game)):
        raise OSError("GetClientRect failed")
    origin = ctypes.wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise OSError("ClientToScreen failed")
    client_bounds = (
        origin.x + game.left,
        origin.y + game.top,
        origin.x + game.right,
        origin.y + game.bottom,
    )
    if client_bounds != (window.left, window.top, window.left + window.width, window.top + window.height):
        raise RuntimeError("capture refused: game client bounds changed; rediscover the window")

    current = user32.GetTopWindow(None)
    while current:
        if current == hwnd:
            return
        if user32.IsWindowVisible(current):
            rect = ctypes.wintypes.RECT()
            if user32.GetWindowRect(current, ctypes.byref(rect)):
                overlaps = rectangles_overlap(
                    (rect.left, rect.top, rect.right, rect.bottom), client_bounds
                )
                if overlaps:
                    title_length = user32.GetWindowTextLengthW(current)
                    title_buf = ctypes.create_unicode_buffer(title_length + 1)
                    if title_length:
                        user32.GetWindowTextW(current, title_buf, title_length + 1)
                    raise RuntimeError(
                        f"capture refused: top-level window {title_buf.value!r} occludes game client"
                    )
        current = user32.GetWindow(current, 2)  # GW_HWNDNEXT
    raise RuntimeError("capture refused: game window was absent from top-level z-order")


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    left: int
    top: int
    width: int
    height: int


def list_windows() -> list[WindowInfo]:
    """Return visible, titled windows and their client-area screen bounds."""
    if sys.platform != "win32":
        raise OSError("Window discovery is available only on Windows")
    ensure_per_monitor_dpi_awareness()
    user32 = ctypes.windll.user32
    wintypes = ctypes.wintypes
    _configure_window_api(user32)
    enum_proc_type = user32.EnumWindows.argtypes[0]
    results: list[WindowInfo] = []

    def visit(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return True
        origin = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            return True
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width > 0 and height > 0:
            results.append(WindowInfo(int(hwnd), title.value, origin.x, origin.y, width, height))
        return True

    user32.EnumWindows(enum_proc_type(visit), 0)
    return results


class WindowCapture:
    """Capture a visible, foreground, unobscured client area as a BGR array.

    Occlusion detection walks top-level z-order and rejects any visible window
    rectangle intersecting the client area. It is conservative: transparent
    overlays and shaped windows can be rejected even where their visible pixels
    do not cover the game. Child-window overlays are not separately inspected.
    """

    def capture(self, window: WindowInfo) -> Any:
        if sys.platform != "win32":
            raise OSError("Window capture is available only on Windows")
        ensure_per_monitor_dpi_awareness()
        user32 = ctypes.windll.user32
        _configure_window_api(user32)
        _validate_capture_window(user32, window)
        import cv2
        import mss
        import numpy as np

        region = {
            "left": window.left,
            "top": window.top,
            "width": window.width,
            "height": window.height,
        }
        with mss.mss() as session:
            bgra = np.asarray(session.grab(region))
        # Recheck after the desktop read so focus/occlusion changes during the
        # capture do not silently return pixels from a different foreground.
        _validate_capture_window(user32, window)
        return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)


def main() -> int:
    parser = argparse.ArgumentParser(description="List PVZ windows and optionally save a client-area screenshot")
    parser.add_argument("--contains", default="plants vs", help="case-insensitive title substring")
    parser.add_argument("--output", type=Path, help="save the first matching window screenshot to this path")
    args = parser.parse_args()
    try:
        windows = list_windows()
    except OSError as exc:
        parser.error(str(exc))
    matches = [window for window in windows if args.contains.casefold() in window.title.casefold()]
    if not matches:
        print("No matching window found. Visible titled windows:")
        for window in windows:
            print(f"  hwnd={window.hwnd} {window.width}x{window.height} {window.title}")
        return 1
    for window in matches:
        print(f"hwnd={window.hwnd} client={window.width}x{window.height} at ({window.left},{window.top}) {window.title}")
    if args.output:
        import cv2

        try:
            image = WindowCapture().capture(matches[0])
            if not cv2.imwrite(str(args.output), image):
                raise OSError(f"Could not write screenshot: {args.output}")
        except (OSError, RuntimeError, ValueError) as exc:
            parser.error(f"Capture failed: {exc}")
        print(f"Saved {args.output}; inspect this image on the target Windows display before calibrating clicks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
