"""Fail-closed Windows mouse input with an explicit emergency stop."""

from __future__ import annotations

import ctypes
import sys
import threading

from pvz_auto.config import WindowGeometry, client_to_screen


class MouseController:
    """Send client-relative clicks; emergency_stop permanently disables input."""

    def __init__(self, window: WindowGeometry) -> None:
        self.window = window
        self._stopped = threading.Event()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def emergency_stop(self) -> None:
        """Immediately prevent this controller from issuing further events."""
        self._stopped.set()

    def click(self, x: float, y: float) -> None:
        if self.stopped:
            raise RuntimeError("mouse controller is emergency-stopped")
        if sys.platform != "win32":
            raise OSError("Mouse input is available only on Windows")
        sx, sy = client_to_screen(x, y, self.window)
        user32 = ctypes.windll.user32
        # Absolute SendInput coordinates span the virtual desktop, including monitors.
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)  # SM_X/YVIRTUALSCREEN
        vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        if vw <= 1 or vh <= 1:
            raise OSError("Windows reported invalid virtual desktop dimensions")
        ax = round((sx - vx) * 65535 / (vw - 1))
        ay = round((sy - vy) * 65535 / (vh - 1))
        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_void_p)]
        class INPUTUNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]
        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("union", INPUTUNION)]
        inp = INPUT(0, INPUTUNION(MOUSEINPUT(ax, ay, 0, 0x8001, 0, None)))  # MOVE | ABSOLUTE
        if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
            raise OSError("SendInput failed to move cursor")
        down = INPUT(0, INPUTUNION(MOUSEINPUT(0, 0, 0, 0x0002, 0, None)))
        up = INPUT(0, INPUTUNION(MOUSEINPUT(0, 0, 0, 0x0004, 0, None)))
        if user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT)) != 1:
            raise OSError("SendInput failed to press mouse button")
        user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
