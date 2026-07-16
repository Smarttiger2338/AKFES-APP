from __future__ import annotations

import os

import server as core
from server_boundary import install_server_boundary


# Register the closed API boundary before importing the attestation layer so
# malformed or unexpected requests are rejected before any protected handler.
install_server_boundary(core.app, core)

import hardened_server  # noqa: E402,F401  Registers device/session attestation hooks.

app = core.app


def main() -> None:
    from waitress import serve

    host = os.environ.get("SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("SERVER_PORT", "5000"))
    threads = max(2, min(int(os.environ.get("SERVER_THREADS", "4")), 32))

    serve(
        app,
        host=host,
        port=port,
        threads=threads,
        clear_untrusted_proxy_headers=True,
        expose_tracebacks=False,
        ident="AKFES",
    )


if __name__ == "__main__":
    main()
