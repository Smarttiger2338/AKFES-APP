use serde::Deserialize;
use std::fs;
use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{AppHandle, Manager, RunEvent, State};

#[derive(Deserialize)]
struct RuntimeConfig {
    admin_token: String,
}

#[derive(Default)]
struct ServerSidecar {
    child: Mutex<Option<Child>>,
    startup_error: Mutex<Option<String>>,
}

fn app_data_directory() -> Result<PathBuf, String> {
    let base = std::env::var_os("LOCALAPPDATA")
        .or_else(|| std::env::var_os("APPDATA"))
        .ok_or_else(|| "Windows 앱 데이터 경로를 찾을 수 없습니다.".to_string())?;
    Ok(PathBuf::from(base).join("AKFES"))
}

fn runtime_config_path() -> Result<PathBuf, String> {
    Ok(app_data_directory()?.join("server-runtime.json"))
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
                .map_err(|error| format!("서버 리소스 경로를 찾지 못했습니다: {error}"))?
                .join("akfes-server.exe");
            let metadata = fs::metadata(&executable)
                .map_err(|error| format!("서버 실행 파일을 확인하지 못했습니다: {error}"))?;
            if metadata.len() == 0 {
                return Err("설치 패키지에 서버 실행 파일이 포함되지 않았습니다.".to_string());
            }

            let child = Command::new(&executable)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .map_err(|error| format!("내장 FastAPI 서버를 시작하지 못했습니다: {error}"))?;
            *sidecar
                .child
                .lock()
                .map_err(|_| "서버 프로세스 잠금이 손상되었습니다.".to_string())? = Some(child);
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
    let path = runtime_config_path()?;
    let mut last_error = None;

    for _ in 0..30 {
        match fs::read_to_string(&path) {
            Ok(content) => {
                let config: RuntimeConfig = serde_json::from_str(&content)
                    .map_err(|_| "로컬 서버 설정 파일이 손상되었습니다.".to_string())?;
                if config.admin_token.len() < 32 {
                    return Err("관리자 토큰이 올바르지 않습니다.".to_string());
                }
                return Ok(config.admin_token);
            }
            Err(error) => {
                last_error = Some(error.to_string());
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
            "로컬 서버 설정을 불러오지 못했습니다. {}",
            last_error.unwrap_or_else(|| "알 수 없는 오류".to_string())
        )
    }))
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
