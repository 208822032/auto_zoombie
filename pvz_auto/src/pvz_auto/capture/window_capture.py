"""Windows client-area capture using MSS.

The backend is deliberately small and replaceable. It captures the client area
of a selected top-level window; it does not infer gameplay state.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    user32 = ctypes.windll.user32
    wintypes = ctypes.wintypes
    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [enum_proc_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
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
    """Capture a window's client area as an OpenCV-compatible BGR array."""

    def capture(self, window: WindowInfo) -> Any:
        if sys.platform != "win32":
            raise OSError("Window capture is available only on Windows")
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

        image = WindowCapture().capture(matches[0])
        if not cv2.imwrite(str(args.output), image):
            raise OSError(f"Could not write screenshot: {args.output}")
        print(f"Saved {args.output}; inspect this image on the target Windows display before calibrating clicks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
