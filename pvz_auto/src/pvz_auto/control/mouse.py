"""Fail-closed Windows mouse input with an F12 emergency stop."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import threading
import time

from pvz_auto.config import WindowGeometry, refresh_window_geometry, validate_click_bounds
from pvz_auto.capture.window_capture import ensure_per_monitor_dpi_awareness

_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_ABSOLUTE = 0x8000
_MOUSEEVENTF_VIRTUALDESK = 0x4000
_VK_F12 = 0x7B


def click_event_flags() -> tuple[int, int]:
    """Flags for the single batched cursor-move and left-button-down input."""
    return (
        _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE | _MOUSEEVENTF_VIRTUALDESK,
        _MOUSEEVENTF_LEFTDOWN,
    )


def require_target_hwnd(hwnd: int | None) -> int:
    """Return a usable target HWND or fail closed before input."""
    if hwnd is None or int(hwnd) == 0:
        raise RuntimeError("mouse input requires the target game HWND")
    return int(hwnd)


def require_foreground_window(target_hwnd: int, foreground_hwnd: int | None) -> None:
    """Raise unless the game still owns foreground focus."""
    if foreground_hwnd is None or int(foreground_hwnd) != int(target_hwnd):
        raise RuntimeError("mouse input refused: target game window is not foreground")


class MouseController:
    """Send client-relative clicks; F12 permanently stops input on Windows.

    The global F12 listener starts automatically on Windows when a controller
    is constructed. Set ``emergency_hotkey=False`` to opt out, or call
    :meth:`start_emergency_hotkey` later to enable it. The listener polls
    asynchronously and calls ``emergency_stop`` on key-down.
    """

    def __init__(
        self,
        window: WindowGeometry,
        hwnd: int | None = None,
        *,
        emergency_hotkey: bool = True,
    ) -> None:
        self.window = window
        self.hwnd = hwnd
        self._stopped = threading.Event()
        self._state_lock = threading.Lock()
        self._hotkey_shutdown = threading.Event()
        self._hotkey_thread: threading.Thread | None = None
        if emergency_hotkey and sys.platform == "win32":
            self.start_emergency_hotkey()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def emergency_stop(self) -> None:
        """Stop future actions and inject a release in case a button is held."""
        with self._state_lock:
            self._stopped.set()
        if sys.platform == "win32":
            self._send_mouse_event(_MOUSEEVENTF_LEFTUP)

    def start_emergency_hotkey(self) -> None:
        """Enable the Windows global F12 emergency stop listener."""
        if sys.platform != "win32":
            raise OSError("The F12 emergency hotkey is available only on Windows")
        if self._hotkey_thread and self._hotkey_thread.is_alive():
            return
        self._hotkey_shutdown.clear()

        def listen() -> None:
            user32 = ctypes.windll.user32
            was_down = False
            while not self._hotkey_shutdown.wait(0.02):
                is_down = bool(user32.GetAsyncKeyState(_VK_F12) & 0x8000)
                if is_down and not was_down:
                    self.emergency_stop()
                    return
                was_down = is_down

        self._hotkey_thread = threading.Thread(target=listen, name="pvz-emergency-hotkey", daemon=True)
        self._hotkey_thread.start()

    def stop_emergency_hotkey_listener(self) -> None:
        """Stop polling F12 without re-enabling a stopped controller."""
        self._hotkey_shutdown.set()

    @staticmethod
    def _send_mouse_event(flags: int) -> None:
        if sys.platform != "win32":
            return

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        class INPUTUNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("union", INPUTUNION)]

        user32 = ctypes.windll.user32
        user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        user32.SendInput.restype = ctypes.c_uint
        event = INPUT(0, INPUTUNION(MOUSEINPUT(0, 0, 0, flags, 0, None)))
        if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
            raise OSError("SendInput failed to release mouse button")

    def click(self, x: float, y: float) -> None:
        if self.stopped:
            raise RuntimeError("mouse controller is emergency-stopped")
        if sys.platform != "win32":
            raise OSError("Mouse input is available only on Windows")
        target_hwnd = require_target_hwnd(self.hwnd)
        ensure_per_monitor_dpi_awareness()
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
        user32.GetClientRect.argtypes = [
            ctypes.wintypes.HWND,
            ctypes.POINTER(ctypes.wintypes.RECT),
        ]
        user32.GetClientRect.restype = ctypes.wintypes.BOOL
        user32.ClientToScreen.argtypes = [
            ctypes.wintypes.HWND,
            ctypes.POINTER(ctypes.wintypes.POINT),
        ]
        user32.ClientToScreen.restype = ctypes.wintypes.BOOL

        def check_foreground() -> None:
            require_foreground_window(target_hwnd, user32.GetForegroundWindow())

        client_rect = ctypes.wintypes.RECT()
        if not user32.GetClientRect(target_hwnd, ctypes.byref(client_rect)):
            raise OSError("GetClientRect failed while preparing mouse click")
        origin = ctypes.wintypes.POINT(0, 0)
        if not user32.ClientToScreen(target_hwnd, ctypes.byref(origin)):
            raise OSError("ClientToScreen failed while preparing mouse click")
        current_window = refresh_window_geometry(
            self.window,
            origin.x,
            origin.y,
            client_rect.right - client_rect.left,
            client_rect.bottom - client_rect.top,
        )

        # Absolute SendInput coordinates span the virtual desktop, including monitors.
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        if vw <= 1 or vh <= 1:
            raise OSError("Windows reported invalid virtual desktop dimensions")
        sx, sy = validate_click_bounds(x, y, current_window, (vx, vy, vw, vh))
        ax = round((sx - vx) * 65535 / (vw - 1))
        ay = round((sy - vy) * 65535 / (vh - 1))

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        class INPUTUNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("union", INPUTUNION)]

        user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        user32.SendInput.restype = ctypes.c_uint

        def send_click_batch() -> None:
            move_flags, down_flags = click_event_flags()
            events = (INPUT * 2)(
                INPUT(0, INPUTUNION(MOUSEINPUT(ax, ay, 0, move_flags, 0, None))),
                INPUT(0, INPUTUNION(MOUSEINPUT(0, 0, 0, down_flags, 0, None))),
            )
            sent = user32.SendInput(2, events, ctypes.sizeof(INPUT))
            if sent != 2:
                raise OSError(f"SendInput accepted {sent} of 2 mouse click events")

        # Send an unconditional release around the down sequence. An extra
        # button-up is harmless, and this also covers errors at the SendInput
        # boundary where the caller cannot know whether Windows accepted down.
        try:
            with self._state_lock:
                if self.stopped:
                    raise RuntimeError("mouse controller is emergency-stopped")
                check_foreground()
                send_click_batch()
            if self.stopped:
                raise RuntimeError("mouse controller is emergency-stopped")
            time.sleep(0.005)
            if self.stopped:
                raise RuntimeError("mouse controller is emergency-stopped")
        finally:
            self._send_mouse_event(_MOUSEEVENTF_LEFTUP)
