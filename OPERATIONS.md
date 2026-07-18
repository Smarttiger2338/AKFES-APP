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
- a HTTPS endpoint, such as a GitHub Release `latest.json`
- release signing with `TAURI_SIGNING_PRIVATE_KEY`

The License Manager currently checks the latest GitHub Release and reports whether a newer version
exists. Do not add a fake updater public key; generate and publish the real key before enabling
automatic installation.
