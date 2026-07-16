from __future__ import annotations

from security_guard import SecurityViolation, start_runtime_guard, verify_startup_environment
from secure_transport import install_requests_hardening


def run() -> int:
    try:
        verify_startup_environment()
        install_requests_hardening()
    except SecurityViolation:
        return 70
    except Exception:
        return 71

    import main
    from secure_session import install_session_vault

    install_session_vault(main)
    start_runtime_guard()
    return main.main()


if __name__ == "__main__":
    raise SystemExit(run())
