use serde::{Deserialize, Serialize};
use std::fs;
use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager, RunEvent, State};

#[derive(Deserialize, Serialize)]
struct RuntimeConfig {
    license_secret: String,
    admin_token: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    created_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    admin_token_rotated_at: Option<String>,
}

#[derive(Default)]
struct ServerSidecar {
    child: Mutex<Option<Child>>,
    startup_error: Mutex<Option<String>>,
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

fn now_unix_string() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_else(|_| Duration::from_secs(0))
        .as_secs()
        .to_string()
}

fn generate_admin_token() -> Result<String, String> {
    let output = Command::new("powershell")
        .args([
            "-NoProfile",
            "-Command",
            "$bytes = New-Object byte[] 48; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes); [Convert]::ToBase64String($bytes) -replace '\\+','-' -replace '/','_' -replace '=',''",
        ])
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .output()
        .map_err(|error| format!("Could not start the administrator token generator: {error}"))?;

    if !output.status.success() {
        return Err("Administrator token generation failed.".to_string());
    }

    let token = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if token.len() < 32 {
        return Err("Generated administrator token is too short.".to_string());
    }
    Ok(token)
}

fn read_runtime_config() -> Result<RuntimeConfig, String> {
    let path = runtime_config_path()?;
    let content = fs::read_to_string(&path)
        .map_err(|error| format!("Could not read local server config: {error}"))?;
    let config: RuntimeConfig =
        serde_json::from_str(&content).map_err(|_| "Local server config is damaged.".to_string())?;
    if config.license_secret.len() < 32 || config.admin_token.len() < 32 {
        return Err("Local server config secrets are invalid.".to_string());
    }
    Ok(config)
}

fn write_runtime_config(config: &RuntimeConfig) -> Result<(), String> {
    let path = runtime_config_path()?;
    let directory = path
        .parent()
        .ok_or_else(|| "Local server config path is invalid.".to_string())?;
    fs::create_dir_all(directory)
        .map_err(|error| format!("Could not create local server config directory: {error}"))?;
    let content = serde_json::to_string_pretty(config)
        .map_err(|error| format!("Could not serialize local server config: {error}"))?;
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

fn server_is_running() -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], 8000));
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

fn start_server_sidecar(app: &AppHandle, sidecar: &ServerSidecar) {
    #[cfg(target_os = "windows")]
    {
        if server_is_running() {
            return;
        }

        let result = (|| -> Result<(), String> {
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
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .map_err(|error| format!("Could not start bundled FastAPI server: {error}"))?;
            *sidecar
                .child
                .lock()
                .map_err(|_| "Server process lock was poisoned.".to_string())? = Some(child);
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
fn rotate_local_admin_token(
    app: AppHandle,
    sidecar: State<'_, ServerSidecar>,
) -> Result<String, String> {
    let owns_server = sidecar
        .child
        .lock()
        .map_err(|_| "Server process lock was poisoned.".to_string())?
        .is_some();

    if server_is_running() && !owns_server {
        return Err(
            "Another AKFES server is already running. Stop it, then rotate the token again."
                .to_string(),
        );
    }

    let mut config = read_runtime_config()?;
    config.admin_token = generate_admin_token()?;
    config.admin_token_rotated_at = Some(now_unix_string());
    write_runtime_config(&config)?;

    stop_server_sidecar(sidecar.inner());
    start_server_sidecar(&app, sidecar.inner());
    if !server_is_running() {
        return Err("The token was saved, but the local server did not restart.".to_string());
    }

    Ok(config.admin_token)
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
        .manage(ServerSidecar::default())
        .setup(|app| {
            let sidecar = app.state::<ServerSidecar>();
            start_server_sidecar(app.handle(), sidecar.inner());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            load_local_admin_token,
            rotate_local_admin_token,
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
