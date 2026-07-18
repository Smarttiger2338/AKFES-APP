use serde::{Deserialize, Serialize};
use std::fs;
use std::io::Write;
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager, RunEvent, State};

const MAX_PIN_ATTEMPTS: u32 = 5;
const PIN_LOCK_SECONDS: u64 = 300;

#[derive(Deserialize, Serialize)]
struct RuntimeConfig {
    license_secret: String,
    admin_token: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    created_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    admin_token_rotated_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    admin_pin_salt: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    admin_pin_hash: Option<String>,
    #[serde(default)]
    admin_pin_failed_attempts: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    admin_pin_locked_until: Option<String>,
}

#[derive(Deserialize, Serialize)]
struct ProtectedRuntimeConfig {
    version: u8,
    protected: bool,
    protection: String,
    payload: String,
}

#[derive(Serialize)]
struct AdminSecurityStatus {
    pin_set: bool,
    config_protected: bool,
    failed_attempts: u32,
    locked_until: Option<String>,
}

#[derive(Serialize)]
struct LocalServerStatus {
    running: bool,
    owned_by_admin_app: bool,
    port: u16,
    server_url: String,
    config_protected: bool,
    config_path: String,
    database_path: String,
    backup_count: usize,
    latest_backup_path: Option<String>,
    startup_error: Option<String>,
}

#[derive(Serialize)]
struct BackupResult {
    path: String,
}

#[derive(Deserialize, Serialize)]
struct LocalAuditEntry {
    action: String,
    created_at: String,
    detail: String,
}

#[derive(Deserialize)]
struct GithubRelease {
    tag_name: Option<String>,
    name: Option<String>,
    html_url: Option<String>,
    published_at: Option<String>,
}

#[derive(Serialize)]
struct UpdateStatus {
    current_version: String,
    latest_version: Option<String>,
    update_available: bool,
    release_name: Option<String>,
    release_url: Option<String>,
    published_at: Option<String>,
    error: Option<String>,
}

#[derive(Default)]
struct ServerSidecar {
    child: Mutex<Option<Child>>,
    startup_error: Mutex<Option<String>>,
    port: Mutex<Option<u16>>,
}

fn app_data_directory() -> Result<PathBuf, String> {
    let base = std::env::var_os("LOCALAPPDATA")
        .or_else(|| std::env::var_os("APPDATA"))
        .ok_or_else(|| "Windows app data path was not found.".to_string())?;
    Ok(PathBuf::from(base).join("AKFES"))
}

fn runtime_config_path() -> Result<PathBuf, String> {
    Ok(app_data_directory()?.join("server-runtime.json"))
}

fn database_path() -> Result<PathBuf, String> {
    Ok(app_data_directory()?.join("akfes.sqlite3"))
}

fn backup_directory() -> Result<PathBuf, String> {
    Ok(app_data_directory()?.join("backups"))
}

fn local_audit_path() -> Result<PathBuf, String> {
    Ok(app_data_directory()?.join("admin-audit.jsonl"))
}

fn now_unix_string() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_else(|_| Duration::from_secs(0))
        .as_secs()
        .to_string()
}

fn now_unix_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_else(|_| Duration::from_secs(0))
        .as_secs()
}

fn append_local_audit(action: &str, detail: &str) {
    let Ok(path) = local_audit_path() else {
        return;
    };
    if let Some(directory) = path.parent() {
        let _ = fs::create_dir_all(directory);
    }
    let entry = LocalAuditEntry {
        action: action.to_string(),
        created_at: now_unix_string(),
        detail: detail.to_string(),
    };
    if let Ok(mut line) = serde_json::to_string(&entry) {
        line.push('\n');
        let _ = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .and_then(|mut file| file.write_all(line.as_bytes()));
    }
}

fn find_available_port() -> Result<u16, String> {
    for port in 8000..8050 {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return Ok(port);
        }
    }
    Err("No available local server port was found.".to_string())
}

fn sidecar_port(sidecar: &ServerSidecar) -> u16 {
    sidecar
        .port
        .lock()
        .ok()
        .and_then(|guard| *guard)
        .unwrap_or(8000)
}

fn server_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}")
}

fn powershell_stdout(script: &str, args: &[&str]) -> Result<String, String> {
    let output = Command::new("powershell")
        .args(["-NoProfile", "-Command", script])
        .args(args)
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .output()
        .map_err(|error| format!("Could not start PowerShell helper: {error}"))?;

    if !output.status.success() {
        return Err("PowerShell helper failed.".to_string());
    }

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn powershell_stdout_with_stdin(script: &str, stdin_payload: &str) -> Result<String, String> {
    let mut child = Command::new("powershell")
        .args(["-NoProfile", "-Command", script])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("Could not start PowerShell helper: {error}"))?;

    {
        let stdin = child
            .stdin
            .as_mut()
            .ok_or_else(|| "PowerShell helper input was not available.".to_string())?;
        stdin
            .write_all(stdin_payload.as_bytes())
            .map_err(|error| format!("Could not send data to PowerShell helper: {error}"))?;
    }
    drop(child.stdin.take());

    let output = child
        .wait_with_output()
        .map_err(|error| format!("PowerShell helper did not finish: {error}"))?;

    if !output.status.success() {
        return Err("PowerShell helper failed.".to_string());
    }

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn generate_secret() -> Result<String, String> {
    let script = "$bytes = New-Object byte[] 48; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes); [Convert]::ToBase64String($bytes) -replace '\\+','-' -replace '/','_' -replace '=',''";
    let token = powershell_stdout(script, &[])?;
    if token.len() < 32 {
        return Err("Generated secret is too short.".to_string());
    }
    Ok(token)
}

fn hash_pin(pin: &str, salt: &str) -> Result<String, String> {
    let input = serde_json::json!({ "pin": pin, "salt": salt }).to_string();
    let script = "$json=[Console]::In.ReadToEnd() | ConvertFrom-Json; $sha=[Security.Cryptography.SHA256]::Create(); $bytes=[Text.Encoding]::UTF8.GetBytes($json.salt + ':' + $json.pin); [Convert]::ToBase64String($sha.ComputeHash($bytes))";
    let hash = powershell_stdout_with_stdin(script, &input)?;
    if hash.len() < 32 {
        return Err("PIN hash generation failed.".to_string());
    }
    Ok(hash)
}

fn unprotect_payload(payload: &str) -> Result<String, String> {
    let script = "Add-Type -AssemblyName System.Security; $bytes=[Convert]::FromBase64String($args[0]); $plain=[Security.Cryptography.ProtectedData]::Unprotect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser); [Text.Encoding]::UTF8.GetString($plain)";
    powershell_stdout(script, &[payload])
        .map_err(|_| "Local server config could not be decrypted by this Windows user.".to_string())
}

fn protect_payload(content: &str) -> Result<String, String> {
    let script = "$json=[Console]::In.ReadToEnd(); Add-Type -AssemblyName System.Security; $bytes=[Text.Encoding]::UTF8.GetBytes($json); $cipher=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser); [Convert]::ToBase64String($cipher)";
    let payload = powershell_stdout_with_stdin(script, content)?;
    if payload.len() < 32 {
        return Err("Local server config encryption returned an invalid payload.".to_string());
    }
    Ok(payload)
}

fn validate_runtime_config(config: RuntimeConfig) -> Result<RuntimeConfig, String> {
    if config.license_secret.len() < 32 || config.admin_token.len() < 32 {
        return Err("Local server config secrets are invalid.".to_string());
    }
    Ok(config)
}

fn read_runtime_config_file() -> Result<(RuntimeConfig, bool), String> {
    let path = runtime_config_path()?;
    let content = fs::read_to_string(&path)
        .map_err(|error| format!("Could not read local server config: {error}"))?;

    if let Ok(envelope) = serde_json::from_str::<ProtectedRuntimeConfig>(&content) {
        if envelope.version == 2 && envelope.protected && !envelope.payload.is_empty() {
            let plaintext = unprotect_payload(&envelope.payload)?;
            let config: RuntimeConfig = serde_json::from_str(&plaintext)
                .map_err(|_| "Local server config payload is damaged.".to_string())?;
            return Ok((validate_runtime_config(config)?, true));
        }
    }

    let config: RuntimeConfig = serde_json::from_str(&content)
        .map_err(|_| "Local server config is damaged.".to_string())?;
    Ok((validate_runtime_config(config)?, false))
}

fn read_runtime_config() -> Result<RuntimeConfig, String> {
    read_runtime_config_file().map(|(config, _)| config)
}

fn write_runtime_config(config: &RuntimeConfig) -> Result<(), String> {
    let path = runtime_config_path()?;
    let directory = path
        .parent()
        .ok_or_else(|| "Local server config path is invalid.".to_string())?;
    fs::create_dir_all(directory)
        .map_err(|error| format!("Could not create local server config directory: {error}"))?;
    let plaintext = serde_json::to_string(config)
        .map_err(|error| format!("Could not serialize local server config: {error}"))?;
    let envelope = ProtectedRuntimeConfig {
        version: 2,
        protected: true,
        protection: "windows-dpapi-current-user".to_string(),
        payload: protect_payload(&plaintext)?,
    };
    let content = serde_json::to_string_pretty(&envelope)
        .map_err(|error| format!("Could not serialize protected local server config: {error}"))?;
    let temporary = path.with_extension("tmp");
    fs::write(&temporary, content)
        .map_err(|error| format!("Could not write temporary local server config: {error}"))?;
    if path.exists() {
        fs::remove_file(&path)
            .map_err(|error| format!("Could not replace local server config: {error}"))?;
    }
    fs::rename(&temporary, &path)
        .map_err(|error| format!("Could not save local server config: {error}"))?;
    Ok(())
}

fn server_is_running(port: u16) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    TcpStream::connect_timeout(&address, Duration::from_millis(300)).is_ok()
}

fn record_startup_error(sidecar: &ServerSidecar, message: String) {
    if let Ok(mut guard) = sidecar.startup_error.lock() {
        *guard = Some(message.clone());
    }
    if let Ok(directory) = app_data_directory() {
        let _ = fs::create_dir_all(&directory);
        let _ = fs::write(directory.join("license-manager-startup-error.txt"), message);
    }
}

fn clear_startup_error(sidecar: &ServerSidecar) {
    if let Ok(mut guard) = sidecar.startup_error.lock() {
        *guard = None;
    }
    if let Ok(directory) = app_data_directory() {
        let _ = fs::remove_file(directory.join("license-manager-startup-error.txt"));
    }
}

fn start_server_sidecar(app: &AppHandle, sidecar: &ServerSidecar) {
    #[cfg(target_os = "windows")]
    {
        let result = (|| -> Result<(), String> {
            let port = find_available_port()?;
            let executable = app
                .path()
                .resource_dir()
                .map_err(|error| format!("Could not resolve server resource path: {error}"))?
                .join("akfes-server.exe");
            let metadata = fs::metadata(&executable)
                .map_err(|error| format!("Could not inspect server executable: {error}"))?;
            if metadata.len() == 0 {
                return Err("Installed package does not include a server executable.".to_string());
            }

            let child = Command::new(&executable)
                .env("AKFES_PORT", port.to_string())
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .map_err(|error| format!("Could not start bundled FastAPI server: {error}"))?;
            *sidecar
                .child
                .lock()
                .map_err(|_| "Server process lock was poisoned.".to_string())? = Some(child);
            *sidecar
                .port
                .lock()
                .map_err(|_| "Server port lock was poisoned.".to_string())? = Some(port);
            append_local_audit(
                "server_start",
                &format!("Started local server on port {port}."),
            );
            clear_startup_error(sidecar);
            Ok(())
        })();

        if let Err(error) = result {
            record_startup_error(sidecar, error);
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = (app, sidecar);
    }
}

fn stop_server_sidecar(sidecar: &ServerSidecar) {
    if let Ok(mut guard) = sidecar.child.lock() {
        if let Some(child) = guard.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
        guard.take();
    }
    if let Ok(mut port) = sidecar.port.lock() {
        port.take();
    }
}

fn sidecar_owns_server(sidecar: &ServerSidecar) -> Result<bool, String> {
    Ok(sidecar
        .child
        .lock()
        .map_err(|_| "Server process lock was poisoned.".to_string())?
        .is_some())
}

fn ensure_server_can_restart(sidecar: &ServerSidecar) -> Result<bool, String> {
    let owns_server = sidecar_owns_server(sidecar)?;
    if server_is_running(sidecar_port(sidecar)) && !owns_server {
        return Err(
            "Another AKFES server is already running. Stop it, then try again.".to_string(),
        );
    }
    Ok(owns_server)
}

fn copy_if_exists(from: &Path, to: &Path) -> Result<(), String> {
    if from.exists() {
        fs::copy(from, to).map_err(|error| format!("Could not copy database file: {error}"))?;
    }
    Ok(())
}

fn restore_database_file(from: &Path, to: &Path) -> Result<(), String> {
    if from.exists() {
        fs::copy(from, to).map_err(|error| format!("Could not restore database file: {error}"))?;
    } else if to.exists() {
        fs::remove_file(to)
            .map_err(|error| format!("Could not remove stale database file: {error}"))?;
    }
    Ok(())
}

fn copy_backup_folder(from: &Path, to: &Path) -> Result<(), String> {
    if !from.join("akfes.sqlite3").exists() {
        return Err("Backup folder does not contain akfes.sqlite3.".to_string());
    }
    fs::create_dir_all(to).map_err(|error| format!("Could not create backup folder: {error}"))?;
    copy_if_exists(&from.join("akfes.sqlite3"), &to.join("akfes.sqlite3"))?;
    copy_if_exists(
        &from.join("akfes.sqlite3-wal"),
        &to.join("akfes.sqlite3-wal"),
    )?;
    copy_if_exists(
        &from.join("akfes.sqlite3-shm"),
        &to.join("akfes.sqlite3-shm"),
    )?;
    Ok(())
}

fn create_database_backup(label: &str) -> Result<PathBuf, String> {
    let source = database_path()?;
    if !source.exists() {
        return Err("Local license database does not exist yet.".to_string());
    }

    let backup_root = backup_directory()?;
    fs::create_dir_all(&backup_root)
        .map_err(|error| format!("Could not create backup directory: {error}"))?;
    let destination = backup_root.join(format!("akfes-{label}-{}", now_unix_string()));
    fs::create_dir_all(&destination)
        .map_err(|error| format!("Could not create backup folder: {error}"))?;

    copy_if_exists(&source, &destination.join("akfes.sqlite3"))?;
    copy_if_exists(
        &source.with_extension("sqlite3-wal"),
        &destination.join("akfes.sqlite3-wal"),
    )?;
    copy_if_exists(
        &source.with_extension("sqlite3-shm"),
        &destination.join("akfes.sqlite3-shm"),
    )?;
    Ok(destination)
}

fn latest_backup_path() -> Result<Option<PathBuf>, String> {
    let root = backup_directory()?;
    if !root.exists() {
        return Ok(None);
    }

    let mut folders = fs::read_dir(&root)
        .map_err(|error| format!("Could not read backup directory: {error}"))?
        .filter_map(Result::ok)
        .filter(|entry| entry.path().is_dir())
        .collect::<Vec<_>>();
    folders.sort_by_key(|entry| {
        entry
            .metadata()
            .and_then(|metadata| metadata.modified())
            .unwrap_or(UNIX_EPOCH)
    });
    Ok(folders.pop().map(|entry| entry.path()))
}

fn backup_count() -> usize {
    backup_directory()
        .ok()
        .and_then(|root| fs::read_dir(root).ok())
        .map(|entries| {
            entries
                .filter_map(Result::ok)
                .filter(|entry| entry.path().is_dir())
                .count()
        })
        .unwrap_or(0)
}

fn restart_owned_server(
    app: &AppHandle,
    sidecar: &ServerSidecar,
    was_owned: bool,
) -> Result<(), String> {
    if was_owned {
        start_server_sidecar(app, sidecar);
        if !server_is_running(sidecar_port(sidecar)) {
            return Err("The local server did not restart.".to_string());
        }
    }
    Ok(())
}

#[tauri::command]
fn load_local_admin_token(sidecar: State<'_, ServerSidecar>) -> Result<String, String> {
    let mut last_error = None;

    for _ in 0..30 {
        match read_runtime_config() {
            Ok(config) => return Ok(config.admin_token),
            Err(error) => {
                last_error = Some(error);
                std::thread::sleep(Duration::from_millis(100));
            }
        }
    }

    let startup_error = sidecar
        .startup_error
        .lock()
        .ok()
        .and_then(|guard| guard.clone());
    Err(startup_error.unwrap_or_else(|| {
        format!(
            "Could not load local server config. {}",
            last_error.unwrap_or_else(|| "Unknown error".to_string())
        )
    }))
}

#[tauri::command]
fn get_admin_security_status() -> Result<AdminSecurityStatus, String> {
    let (config, protected) = read_runtime_config_file()?;
    Ok(AdminSecurityStatus {
        pin_set: config.admin_pin_hash.is_some(),
        config_protected: protected,
        failed_attempts: config.admin_pin_failed_attempts,
        locked_until: config.admin_pin_locked_until,
    })
}

#[tauri::command]
fn set_admin_pin(pin: String) -> Result<AdminSecurityStatus, String> {
    if pin.trim().len() < 4 {
        return Err("PIN must be at least 4 characters.".to_string());
    }

    let mut config = read_runtime_config()?;
    let salt = generate_secret()?;
    config.admin_pin_salt = Some(salt.clone());
    config.admin_pin_hash = Some(hash_pin(pin.trim(), &salt)?);
    config.admin_pin_failed_attempts = 0;
    config.admin_pin_locked_until = None;
    write_runtime_config(&config)?;
    append_local_audit("admin_pin_set", "Administrator PIN was set or changed.");
    Ok(AdminSecurityStatus {
        pin_set: true,
        config_protected: true,
        failed_attempts: 0,
        locked_until: None,
    })
}

#[tauri::command]
fn verify_admin_pin(pin: String) -> Result<bool, String> {
    let mut config = read_runtime_config()?;
    let Some(salt) = config.admin_pin_salt.as_deref() else {
        return Ok(true);
    };
    let Some(expected) = config.admin_pin_hash.as_deref() else {
        return Ok(true);
    };

    if let Some(locked_until) = config
        .admin_pin_locked_until
        .as_deref()
        .and_then(|value| value.parse::<u64>().ok())
    {
        if locked_until > now_unix_seconds() {
            append_local_audit(
                "admin_pin_locked",
                "PIN unlock attempt rejected during lockout.",
            );
            return Err(format!("PIN is locked until {locked_until}."));
        }
    }

    let verified = hash_pin(pin.trim(), salt)? == expected;
    if verified {
        config.admin_pin_failed_attempts = 0;
        config.admin_pin_locked_until = None;
        write_runtime_config(&config)?;
        append_local_audit("admin_pin_unlock", "Administrator panel unlocked.");
        return Ok(true);
    }

    config.admin_pin_failed_attempts = config.admin_pin_failed_attempts.saturating_add(1);
    if config.admin_pin_failed_attempts >= MAX_PIN_ATTEMPTS {
        config.admin_pin_locked_until = Some((now_unix_seconds() + PIN_LOCK_SECONDS).to_string());
        append_local_audit("admin_pin_lockout", "Too many failed PIN attempts.");
    } else {
        append_local_audit("admin_pin_failed", "Failed administrator PIN attempt.");
    }
    write_runtime_config(&config)?;
    Ok(false)
}

#[tauri::command]
fn rotate_local_admin_token(
    app: AppHandle,
    sidecar: State<'_, ServerSidecar>,
) -> Result<String, String> {
    ensure_server_can_restart(sidecar.inner())?;

    let mut config = read_runtime_config()?;
    config.admin_token = generate_secret()?;
    config.admin_token_rotated_at = Some(now_unix_string());
    write_runtime_config(&config)?;

    stop_server_sidecar(sidecar.inner());
    start_server_sidecar(&app, sidecar.inner());
    if !server_is_running(sidecar_port(sidecar.inner())) {
        return Err("The token was saved, but the local server did not restart.".to_string());
    }

    append_local_audit("admin_token_rotate", "Administrator token rotated.");
    Ok(config.admin_token)
}

#[tauri::command]
fn get_local_server_status(sidecar: State<'_, ServerSidecar>) -> Result<LocalServerStatus, String> {
    let config_path = runtime_config_path()?;
    let database_path = database_path()?;
    let port = sidecar_port(sidecar.inner());
    let protected = read_runtime_config_file()
        .map(|(_, protected)| protected)
        .unwrap_or(false);
    let latest_backup = latest_backup_path()?;
    let startup_error = sidecar
        .startup_error
        .lock()
        .ok()
        .and_then(|guard| guard.clone());

    Ok(LocalServerStatus {
        running: server_is_running(port),
        owned_by_admin_app: sidecar_owns_server(sidecar.inner())?,
        port,
        server_url: server_url(port),
        config_protected: protected,
        config_path: config_path.display().to_string(),
        database_path: database_path.display().to_string(),
        backup_count: backup_count(),
        latest_backup_path: latest_backup.map(|path| path.display().to_string()),
        startup_error,
    })
}

#[tauri::command]
fn backup_local_database(
    app: AppHandle,
    sidecar: State<'_, ServerSidecar>,
) -> Result<BackupResult, String> {
    let was_owned = ensure_server_can_restart(sidecar.inner())?;
    if was_owned {
        stop_server_sidecar(sidecar.inner());
    }
    let backup = create_database_backup("backup");
    restart_owned_server(&app, sidecar.inner(), was_owned)?;
    let result = BackupResult {
        path: backup?.display().to_string(),
    };
    append_local_audit(
        "database_backup",
        &format!("Created backup at {}.", result.path),
    );
    Ok(result)
}

#[tauri::command]
fn restore_latest_database_backup(
    app: AppHandle,
    sidecar: State<'_, ServerSidecar>,
) -> Result<BackupResult, String> {
    let was_owned = ensure_server_can_restart(sidecar.inner())?;
    if was_owned {
        stop_server_sidecar(sidecar.inner());
    }

    let result = (|| -> Result<BackupResult, String> {
        let backup =
            latest_backup_path()?.ok_or_else(|| "No local backup was found.".to_string())?;
        let source = backup.join("akfes.sqlite3");
        if !source.exists() {
            return Err("Latest backup does not contain a database file.".to_string());
        }

        let _ = create_database_backup("before-restore");
        let destination = database_path()?;
        let app_data = app_data_directory()?;
        fs::create_dir_all(&app_data)
            .map_err(|error| format!("Could not create app data directory: {error}"))?;
        restore_database_file(&source, &destination)?;
        restore_database_file(
            &backup.join("akfes.sqlite3-wal"),
            &destination.with_extension("sqlite3-wal"),
        )?;
        restore_database_file(
            &backup.join("akfes.sqlite3-shm"),
            &destination.with_extension("sqlite3-shm"),
        )?;

        append_local_audit(
            "database_restore",
            &format!("Restored backup from {}.", backup.display()),
        );
        Ok(BackupResult {
            path: backup.display().to_string(),
        })
    })();

    restart_owned_server(&app, sidecar.inner(), was_owned)?;
    result
}

#[tauri::command]
fn export_latest_database_backup(destination_directory: String) -> Result<BackupResult, String> {
    let source = latest_backup_path()?.ok_or_else(|| "No local backup was found.".to_string())?;
    let destination_root = PathBuf::from(destination_directory.trim());
    if destination_root.as_os_str().is_empty() {
        return Err("Destination folder is required.".to_string());
    }
    fs::create_dir_all(&destination_root)
        .map_err(|error| format!("Could not create destination folder: {error}"))?;
    let destination = destination_root.join(
        source
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("akfes-exported-backup"),
    );
    copy_backup_folder(&source, &destination)?;
    append_local_audit(
        "database_backup_export",
        &format!("Exported backup to {}.", destination.display()),
    );
    Ok(BackupResult {
        path: destination.display().to_string(),
    })
}

#[tauri::command]
fn import_database_backup(source_directory: String) -> Result<BackupResult, String> {
    let source = PathBuf::from(source_directory.trim());
    if source.as_os_str().is_empty() {
        return Err("Source backup folder is required.".to_string());
    }
    let backup_root = backup_directory()?;
    fs::create_dir_all(&backup_root)
        .map_err(|error| format!("Could not create backup directory: {error}"))?;
    let destination = backup_root.join(format!("akfes-imported-{}", now_unix_string()));
    copy_backup_folder(&source, &destination)?;
    append_local_audit(
        "database_backup_import",
        &format!("Imported backup from {}.", source.display()),
    );
    Ok(BackupResult {
        path: destination.display().to_string(),
    })
}

#[tauri::command]
fn list_local_admin_audit() -> Result<Vec<LocalAuditEntry>, String> {
    let path = local_audit_path()?;
    if !path.exists() {
        return Ok(Vec::new());
    }
    let content = fs::read_to_string(&path)
        .map_err(|error| format!("Could not read local audit log: {error}"))?;
    let mut entries = content
        .lines()
        .filter_map(|line| serde_json::from_str::<LocalAuditEntry>(line).ok())
        .collect::<Vec<_>>();
    entries.reverse();
    entries.truncate(200);
    Ok(entries)
}

#[tauri::command]
fn check_for_updates() -> UpdateStatus {
    let current_version = env!("CARGO_PKG_VERSION").to_string();
    let script = "$ProgressPreference='SilentlyContinue'; $headers=@{'User-Agent'='AKFES-License-Manager'}; Invoke-RestMethod -Uri 'https://api.github.com/repos/Smarttiger2338/AKFES-APP/releases/latest' -Headers $headers | Select-Object tag_name,name,html_url,published_at | ConvertTo-Json -Compress";

    match powershell_stdout(script, &[]) {
        Ok(content) => match serde_json::from_str::<GithubRelease>(&content) {
            Ok(release) => {
                let latest = release.tag_name.clone();
                let current_normalized = current_version.trim_start_matches('v').to_string();
                let latest_normalized = latest
                    .as_deref()
                    .unwrap_or("")
                    .trim_start_matches('v')
                    .to_string();
                UpdateStatus {
                    current_version,
                    latest_version: latest,
                    update_available: !latest_normalized.is_empty()
                        && latest_normalized != current_normalized,
                    release_name: release.name,
                    release_url: release.html_url,
                    published_at: release.published_at,
                    error: None,
                }
            }
            Err(error) => UpdateStatus {
                current_version,
                latest_version: None,
                update_available: false,
                release_name: None,
                release_url: None,
                published_at: None,
                error: Some(format!("Could not parse update response: {error}")),
            },
        },
        Err(error) => UpdateStatus {
            current_version,
            latest_version: None,
            update_available: false,
            release_name: None,
            release_url: None,
            published_at: None,
            error: Some(error),
        },
    }
}

#[tauri::command]
fn get_startup_error(sidecar: State<'_, ServerSidecar>) -> Option<String> {
    sidecar
        .startup_error
        .lock()
        .ok()
        .and_then(|guard| guard.clone())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(ServerSidecar::default())
        .setup(|app| {
            let sidecar = app.state::<ServerSidecar>();
            start_server_sidecar(app.handle(), sidecar.inner());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            load_local_admin_token,
            get_admin_security_status,
            set_admin_pin,
            verify_admin_pin,
            rotate_local_admin_token,
            get_local_server_status,
            backup_local_database,
            restore_latest_database_backup,
            export_latest_database_backup,
            import_database_backup,
            list_local_admin_audit,
            check_for_updates,
            get_startup_error
        ])
        .build(tauri::generate_context!())
        .expect("failed to build AKFES License Manager");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit) {
            let sidecar = app_handle.state::<ServerSidecar>();
            stop_server_sidecar(sidecar.inner());
        }
    });
}
