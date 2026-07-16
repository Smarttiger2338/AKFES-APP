from __future__ import annotations

import json
import os
import time
from pathlib import Path

from device_identity import protect_bytes, unprotect_bytes


_SESSION_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AKFES"
_SESSION_PATH = _SESSION_DIR / "session.bin"


def install_session_vault(main_module) -> None:
    def _load_session(self):
        try:
            raw = unprotect_bytes(_SESSION_PATH.read_bytes())
            data = json.loads(raw.decode("utf-8"))
            expires_at = data.get("license_expires_at")
            if expires_at and int(expires_at) <= int(time.time()):
                raise ValueError("expired session")
            token = str(data.get("token", ""))
            if not token.startswith("HCS1."):
                raise ValueError("invalid session token")
            return main_module.SessionState(token=token, license_expires_at=expires_at)
        except Exception:
            return main_module.SessionState()

    def _save_session(self) -> None:
        _SESSION_DIR.mkdir(parents=True, exist_ok=True)
        try:
            legacy = getattr(main_module, "SESSION_FILE", None)
            if legacy and Path(legacy).exists():
                Path(legacy).unlink(missing_ok=True)
        except Exception:
            pass

        if not self.session.token:
            _SESSION_PATH.unlink(missing_ok=True)
            return

        payload = json.dumps(self.session.__dict__, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        protected = protect_bytes(payload)
        temporary = _SESSION_PATH.with_suffix(".tmp")
        temporary.write_bytes(protected)
        os.replace(temporary, _SESSION_PATH)

    original_failure = main_module.AKFESWindow._process_failure

    def _process_failure(self, message: str) -> None:
        self.password = ""
        try:
            self.password_label.setText("키패드 입력 대기 중")
        except Exception:
            pass
        original_failure(self, message)

    main_module.AKFESWindow._load_session = _load_session
    main_module.AKFESWindow._save_session = _save_session
    main_module.AKFESWindow._process_failure = _process_failure
