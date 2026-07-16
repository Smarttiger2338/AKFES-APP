from __future__ import annotations

import ctypes
import os
import random
import sys
import threading
import time
from pathlib import Path


class SecurityViolation(RuntimeError):
    pass


_EXECUTABLE_SNAPSHOT: tuple[int, int] | None = None


def _development_bypass_allowed() -> bool:
    try:
        from release_public_key import RELEASE_PUBLIC_KEY_B64
        return not RELEASE_PUBLIC_KEY_B64 and os.getenv("AKFES_ALLOW_DEBUG") == "1"
    except Exception:
        return False


def _nt_debugger_attached() -> bool:
    if os.name != "nt":
        return False
    try:
        ntdll = ctypes.windll.ntdll
        kernel32 = ctypes.windll.kernel32
        process = kernel32.GetCurrentProcess()

        debug_port = ctypes.c_void_p()
        status = ntdll.NtQueryInformationProcess(
            process, 7, ctypes.byref(debug_port), ctypes.sizeof(debug_port), None
        )
        if status >= 0 and debug_port.value:
            return True

        debug_object = ctypes.c_void_p()
        status = ntdll.NtQueryInformationProcess(
            process, 30, ctypes.byref(debug_object), ctypes.sizeof(debug_object), None
        )
        if status >= 0 and debug_object.value:
            return True

        debug_flags = ctypes.c_ulong(0)
        status = ntdll.NtQueryInformationProcess(
            process, 31, ctypes.byref(debug_flags), ctypes.sizeof(debug_flags), None
        )
        if status >= 0 and debug_flags.value == 0:
            return True
    except Exception:
        return False
    return False


def _debugger_attached() -> bool:
    if _development_bypass_allowed():
        return False
    if sys.gettrace() is not None:
        return True
    if os.name != "nt":
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        if kernel32.IsDebuggerPresent():
            return True
        remote = ctypes.c_bool(False)
        process = kernel32.GetCurrentProcess()
        if kernel32.CheckRemoteDebuggerPresent(process, ctypes.byref(remote)) and remote.value:
            return True
    except Exception:
        pass
    return _nt_debugger_attached()


def _harden_windows_process() -> None:
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
        kernel32.SetDllDirectoryW("")
        kernel32.SetDefaultDllDirectories(0x00000800 | 0x00000400)
        kernel32.SetProcessDEPPolicy(0x1)

        class _POLICY(ctypes.Structure):
            _fields_ = [("flags", ctypes.c_ulong)]

        extension_points = _POLICY(0x1)
        kernel32.SetProcessMitigationPolicy(6, ctypes.byref(extension_points), ctypes.sizeof(extension_points))

        image_load = _POLICY(0x1 | 0x2 | 0x4)
        kernel32.SetProcessMitigationPolicy(10, ctypes.byref(image_load), ctypes.sizeof(image_load))
    except Exception:
        pass


def _capture_executable_snapshot() -> None:
    global _EXECUTABLE_SNAPSHOT
    try:
        stat = Path(sys.executable).resolve().stat()
        _EXECUTABLE_SNAPSHOT = (stat.st_size, stat.st_mtime_ns)
    except Exception:
        _EXECUTABLE_SNAPSHOT = None


def _executable_changed() -> bool:
    if _EXECUTABLE_SNAPSHOT is None:
        return False
    try:
        stat = Path(sys.executable).resolve().stat()
        return (stat.st_size, stat.st_mtime_ns) != _EXECUTABLE_SNAPSHOT
    except Exception:
        return True


def _verify_signed_release() -> None:
    from release_verify import verify_release_integrity
    verify_release_integrity()


def _show_block_message() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            "AKFES 무결성 또는 실행 환경 검증에 실패했습니다. 프로그램을 종료합니다.",
            "AKFES 보호 기능",
            0x10,
        )
    except Exception:
        pass


def verify_startup_environment() -> None:
    _harden_windows_process()
    _capture_executable_snapshot()
    if _debugger_attached():
        raise SecurityViolation("debugger detected")
    try:
        _verify_signed_release()
    except Exception as exc:
        raise SecurityViolation("release integrity failed") from exc


def start_runtime_guard() -> None:
    def guard_loop() -> None:
        last_full_integrity_check = time.monotonic()
        while True:
            time.sleep(random.uniform(0.9, 1.8))
            if _debugger_attached() or _executable_changed():
                _show_block_message()
                os._exit(70)

            now = time.monotonic()
            if now - last_full_integrity_check >= 45:
                try:
                    _verify_signed_release()
                except Exception:
                    _show_block_message()
                    os._exit(71)
                last_full_integrity_check = now

    thread = threading.Thread(target=guard_loop, name="AKFES-RuntimeGuard", daemon=True)
    thread.start()
