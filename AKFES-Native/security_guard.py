from __future__ import annotations

import ctypes
import os
import sys
import threading
import time


class SecurityViolation(RuntimeError):
    pass


def _debugger_attached() -> bool:
    if os.getenv("AKFES_ALLOW_DEBUG") == "1":
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
        return False
    return False


def _harden_dll_loading() -> None:
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        load_library_search_system32 = 0x00000800
        load_library_search_user_dirs = 0x00000400
        kernel32.SetDefaultDllDirectories(
            load_library_search_system32 | load_library_search_user_dirs
        )
    except Exception:
        pass


def _show_block_message() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            "디버거 또는 비정상적인 분석 환경이 감지되어 AKFES를 종료합니다.",
            "AKFES 보호 기능",
            0x10,
        )
    except Exception:
        pass


def verify_startup_environment() -> None:
    _harden_dll_loading()
    if _debugger_attached():
        raise SecurityViolation("debugger detected")


def start_runtime_guard(interval_seconds: float = 2.0) -> None:
    def guard_loop() -> None:
        while True:
            time.sleep(interval_seconds)
            if _debugger_attached():
                _show_block_message()
                os._exit(70)

    thread = threading.Thread(target=guard_loop, name="AKFES-RuntimeGuard", daemon=True)
    thread.start()
