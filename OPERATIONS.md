# AKFES Operations

## Administrator PIN

The License Manager can protect the administrator panel with a local PIN.

- The PIN is stored as a salted hash inside the protected runtime config.
- Five failed attempts lock the panel for five minutes.
- Successful unlock resets the failed-attempt counter.
- PIN setup and failed unlock attempts are recorded in the local admin audit log.

## Local Runtime Config

The local runtime config is stored at:

```text
%LOCALAPPDATA%\AKFES\server-runtime.json
```

The file is protected with the current Windows user account. Opening the file should not reveal
`admin_token` or `license_secret` in plain text.

If Windows can no longer decrypt this file, close AKFES and run:

```text
RESET_LOCAL_CONFIG.bat
```

The helper backs up `server-runtime.json` and creates a new protected local config. It keeps the
SQLite license database, but licenses signed with the old local secret may need to be reissued.

## License Database Backup

The local SQLite database is stored at:

```text
%LOCALAPPDATA%\AKFES\akfes.sqlite3
```

The License Manager supports:

- creating a local backup
- restoring the latest local backup
- exporting the latest backup to another folder
- importing a backup folder from another location

Restore creates a safety backup before replacing the current database.

## Local Admin Audit

Local-only administrator actions are recorded at:

```text
%LOCALAPPDATA%\AKFES\admin-audit.jsonl
```

This complements the server audit log. It records actions such as PIN changes, unlock failures,
token rotation, backup export/import, and restore.

## Port Collision Handling

The bundled server tries ports `8000` through `8049` and starts on the first available local port.
The desktop and administrator apps ask Tauri for the actual local server URL before making API
requests.

## Updates

Both Tauri apps are configured with:

```json
"createUpdaterArtifacts": true
```

This makes release builds produce updater artifacts. According to the Tauri v2 updater guide, full
in-app installation also requires:

- the official updater plugin
- a Tauri updater public key in `plugins.updater.pubkey`
- HTTPS endpoints, such as GitHub Release JSON manifests
- release signing with `TAURI_SIGNING_PRIVATE_KEY`

The public updater key is configured in both Tauri app configs. The release workflow publishes two
static updater manifests:

```text
latest-desktop.json
latest-admin.json
```

Before creating a release tag, add these GitHub Actions secrets:

```text
TAURI_SIGNING_PRIVATE_KEY
TAURI_SIGNING_PRIVATE_KEY_PASSWORD
```

Do not commit the private key. Only the `.pub` public key belongs in source control.
