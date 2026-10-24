"""Fail-closed Windows mouse input with an F12 emergency stop."""

from __future__ import annotations

import ctypes
import sys
import threading
import time

from pvz_auto.config import WindowGeometry, client_to_screen

_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_ABSOLUTE = 0x8000
_VK_F12 = 0x7B


class MouseController:
    """Send client-relative clicks; F12 permanently stops input on Windows.

    The global F12 listener starts automatically on Windows when a controller
    is constructed. Set ``emergency_hotkey=False`` to opt out, or call
    :meth:`start_emergency_hotkey` later to enable it. The listener polls
    asynchronously and calls ``emergency_stop`` on key-down.
    """

    def __init__(self, window: WindowGeometry, *, emergency_hotkey: bool = True) -> None:
        self.window = window
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
        sx, sy = client_to_screen(x, y, self.window)
        user32 = ctypes.windll.user32
        # Absolute SendInput coordinates span the virtual desktop, including monitors.
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        if vw <= 1 or vh <= 1:
            raise OSError("Windows reported invalid virtual desktop dimensions")
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

        def send(flags: int) -> None:
            event = INPUT(0, INPUTUNION(MOUSEINPUT(ax if flags & _MOUSEEVENTF_MOVE else 0,
                                                 ay if flags & _MOUSEEVENTF_MOVE else 0,
                                                 0, flags, 0, None)))
            if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
                raise OSError(f"SendInput failed for mouse event 0x{flags:x}")

        with self._state_lock:
            if self.stopped:
                raise RuntimeError("mouse controller is emergency-stopped")
            send(_MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE)
        with self._state_lock:
            if self.stopped:
                raise RuntimeError("mouse controller is emergency-stopped")
            send(_MOUSEEVENTF_LEFTDOWN)
        # Once down succeeds, always release, including if stop or another error
        # occurs. This keeps the button from remaining held across action aborts.
        try:
            if self.stopped:
                raise RuntimeError("mouse controller is emergency-stopped")
            time.sleep(0.005)
            if self.stopped:
                raise RuntimeError("mouse controller is emergency-stopped")
        finally:
            self._send_mouse_event(_MOUSEEVENTF_LEFTUP)
