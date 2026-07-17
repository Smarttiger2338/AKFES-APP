use serde::Deserialize;
use std::fs;
use std::path::PathBuf;

#[derive(Deserialize)]
struct RuntimeConfig {
    admin_token: String,
}

fn runtime_config_path() -> Result<PathBuf, String> {
    let base = std::env::var_os("LOCALAPPDATA")
        .or_else(|| std::env::var_os("APPDATA"))
        .ok_or_else(|| "Windows 앱 데이터 경로를 찾을 수 없습니다.".to_string())?;
    Ok(PathBuf::from(base).join("AKFES").join("server-runtime.json"))
}

#[tauri::command]
fn load_local_admin_token() -> Result<String, String> {
    let path = runtime_config_path()?;
    let content = fs::read_to_string(&path)
        .map_err(|_| "로컬 서버 설정이 없습니다. AKFES 사용자 앱을 먼저 실행하세요.".to_string())?;
    let config: RuntimeConfig = serde_json::from_str(&content)
        .map_err(|_| "로컬 서버 설정 파일이 손상되었습니다.".to_string())?;
    if config.admin_token.len() < 32 {
        return Err("관리자 토큰이 올바르지 않습니다.".to_string());
    }
    Ok(config.admin_token)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![load_local_admin_token])
        .run(tauri::generate_context!())
        .expect("failed to run AKFES License Manager");
}
