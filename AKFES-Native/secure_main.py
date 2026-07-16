from __future__ import annotations

import os

from security_guard import SecurityViolation, start_runtime_guard, verify_startup_environment


def run() -> int:
    try:
        verify_startup_environment()
    except SecurityViolation:
        return 70

    start_runtime_guard()

    import main

    return main.main()


if __name__ == "__main__":
    raise SystemExit(run())
