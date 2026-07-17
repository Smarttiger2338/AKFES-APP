use serde::Deserialize;
use std::fs;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Manager, RunEvent, State};

#[derive(Deserialize)]
struct RuntimeConfig {
    admin_token: String,
}

#[derive(Default)]
struct ServerSidecar {
    child: Mutex<Option<Child>>,
}

fn runtime_config_path() -> Result<PathBuf, String> {
    let base = std::env::var_os("LOCALAPPDATA")
        .or_else(|| std::env::var_os("APPDATA"))
        .ok_or_else(|| "Windows 앱 데이터 경로를 찾을 수 없습니다.".to_string())?;
    Ok(PathBuf::from(base).join("AKFES").join("server-runtime.json"))
}

fn start_server_sidecar(app: &AppHandle, sidecar: &ServerSidecar) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        let executable = app
            .path()
            .resource_dir()
            .map_err(|error| format!("서버 리소스 경로를 찾지 못했습니다: {error}"))?
            .join("akfes-server.exe");
        let metadata = fs::metadata(&executable)
            .map_err(|error| format!("서버 실행 파일을 확인하지 못했습니다: {error}"))?;
        if metadata.len() == 0 {
            return Ok(());
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
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = (app, sidecar);
    }
    Ok(())
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
fn load_local_admin_token() -> Result<String, String> {
    let path = runtime_config_path()?;
    let content = fs::read_to_string(&path)
        .map_err(|_| "로컬 서버 설정이 없습니다. 잠시 후 다시 시도하세요.".to_string())?;
    let config: RuntimeConfig = serde_json::from_str(&content)
        .map_err(|_| "로컬 서버 설정 파일이 손상되었습니다.".to_string())?;
    if config.admin_token.len() < 32 {
        return Err("관리자 토큰이 올바르지 않습니다.".to_string());
    }
    Ok(config.admin_token)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .manage(ServerSidecar::default())
        .setup(|app| {
            let sidecar = app.state::<ServerSidecar>();
            start_server_sidecar(app.handle(), sidecar.inner()).map_err(std::io::Error::other)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![load_local_admin_token])
        .build(tauri::generate_context!())
        .expect("failed to build AKFES License Manager");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit) {
            let sidecar = app_handle.state::<ServerSidecar>();
            stop_server_sidecar(sidecar.inner());
        }
    });
}
