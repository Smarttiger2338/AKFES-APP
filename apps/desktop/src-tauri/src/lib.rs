use serde::Serialize;
use serialport::SerialPortType;
use std::io::{ErrorKind, Read, Write};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::time::Duration;
use tauri::{AppHandle, Emitter, State};

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SerialPortInfo {
    name: String,
    port_type: String,
}

#[derive(Clone, Default)]
struct SerialConnection {
    port: Arc<Mutex<Option<Box<dyn serialport::SerialPort>>>>,
    stop_signal: Arc<Mutex<Option<mpsc::Sender<()>>>>,
    generation: Arc<AtomicU64>,
}

fn describe_port_type(port_type: &SerialPortType) -> String {
    match port_type {
        SerialPortType::UsbPort(info) => {
            let product = info.product.as_deref().unwrap_or("USB 장치");
            format!("{} · {:04X}:{:04X}", product, info.vid, info.pid)
        }
        SerialPortType::BluetoothPort => "Bluetooth".to_string(),
        SerialPortType::PciPort => "PCI".to_string(),
        SerialPortType::Unknown => "알 수 없는 장치".to_string(),
    }
}

fn close_connection(connection: &SerialConnection) -> Result<(), String> {
    if let Some(sender) = connection
        .stop_signal
        .lock()
        .map_err(|_| "시리얼 종료 신호 잠금이 손상되었습니다.".to_string())?
        .take()
    {
        let _ = sender.send(());
    }

    connection
        .port
        .lock()
        .map_err(|_| "시리얼 포트 잠금이 손상되었습니다.".to_string())?
        .take();

    Ok(())
}

fn emit_line(app: &AppHandle, line: &[u8]) {
    let text = String::from_utf8_lossy(line).trim().to_string();
    if !text.is_empty() {
        let _ = app.emit("serial-line", text);
    }
}

fn safe_filename(filename: &str) -> String {
    let base = Path::new(filename.trim())
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("akfes-result.bin");
    let sanitized: String = base
        .chars()
        .map(|character| match character {
            '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*' => '_',
            character if character.is_control() => '_',
            character => character,
        })
        .collect();
    let trimmed = sanitized.trim().trim_end_matches(['.', ' ']);
    if trimmed.is_empty() {
        "akfes-result.bin".to_string()
    } else {
        trimmed.chars().take(240).collect()
    }
}

#[tauri::command]
fn save_processed_file(filename: String, bytes: Vec<u8>) -> Result<Option<String>, String> {
    if bytes.is_empty() {
        return Err("저장할 파일 데이터가 없습니다.".to_string());
    }
    let filename = safe_filename(&filename);
    let selected = rfd::FileDialog::new().set_file_name(&filename).save_file();
    let Some(path) = selected else {
        return Ok(None);
    };
    std::fs::write(&path, bytes)
        .map_err(|error| format!("결과 파일을 저장하지 못했습니다: {error}"))?;
    Ok(Some(path.to_string_lossy().into_owned()))
}

#[tauri::command]
fn list_serial_ports() -> Result<Vec<SerialPortInfo>, String> {
    let ports = serialport::available_ports()
        .map_err(|error| format!("시리얼 포트를 검색하지 못했습니다: {error}"))?;

    Ok(ports
        .into_iter()
        .map(|port| SerialPortInfo {
            name: port.port_name,
            port_type: describe_port_type(&port.port_type),
        })
        .collect())
}

#[tauri::command]
fn connect_serial_port(
    app: AppHandle,
    connection: State<'_, SerialConnection>,
    port_name: String,
    baud_rate: Option<u32>,
) -> Result<(), String> {
    let port_name = port_name.trim().to_string();
    if port_name.is_empty() {
        return Err("연결할 시리얼 포트를 선택하세요.".to_string());
    }

    close_connection(connection.inner())?;
    let generation = connection.generation.fetch_add(1, Ordering::SeqCst) + 1;
    let baud_rate = baud_rate.unwrap_or(9_600);

    let port = serialport::new(&port_name, baud_rate)
        .timeout(Duration::from_millis(160))
        .open()
        .map_err(|error| format!("{port_name} 포트를 열지 못했습니다: {error}"))?;

    let mut reader = port
        .try_clone()
        .map_err(|error| format!("시리얼 읽기 채널을 만들지 못했습니다: {error}"))?;

    let (stop_sender, stop_receiver) = mpsc::channel();

    *connection
        .port
        .lock()
        .map_err(|_| "시리얼 포트 잠금이 손상되었습니다.".to_string())? = Some(port);
    *connection
        .stop_signal
        .lock()
        .map_err(|_| "시리얼 종료 신호 잠금이 손상되었습니다.".to_string())? = Some(stop_sender);

    let app_for_thread = app.clone();
    let port_store = Arc::clone(&connection.port);
    let stop_store = Arc::clone(&connection.stop_signal);
    let generation_store = Arc::clone(&connection.generation);
    let thread_port_name = port_name.clone();

    std::thread::spawn(move || {
        let mut buffer = [0_u8; 256];
        let mut line_buffer = Vec::<u8>::with_capacity(128);
        let mut stopped_by_request = false;

        loop {
            if stop_receiver.try_recv().is_ok() {
                stopped_by_request = true;
                break;
            }

            match reader.read(&mut buffer) {
                Ok(0) => {}
                Ok(count) => {
                    for byte in &buffer[..count] {
                        if *byte == b'\n' || *byte == b'\r' {
                            if !line_buffer.is_empty() {
                                emit_line(&app_for_thread, &line_buffer);
                                line_buffer.clear();
                            }
                        } else if line_buffer.len() < 1_024 {
                            line_buffer.push(*byte);
                        } else {
                            line_buffer.clear();
                            let _ = app_for_thread.emit(
                                "serial-error",
                                "시리얼 한 줄이 허용 길이를 초과하여 폐기되었습니다.",
                            );
                        }
                    }
                }
                Err(error) if error.kind() == ErrorKind::TimedOut => {}
                Err(error) => {
                    let _ = app_for_thread.emit(
                        "serial-error",
                        format!("{thread_port_name} 읽기 실패: {error}"),
                    );
                    break;
                }
            }
        }

        if !line_buffer.is_empty() {
            emit_line(&app_for_thread, &line_buffer);
        }

        if generation_store.load(Ordering::SeqCst) == generation {
            if let Ok(mut stored_port) = port_store.lock() {
                stored_port.take();
            }
            if let Ok(mut stored_signal) = stop_store.lock() {
                stored_signal.take();
            }
        }

        if !stopped_by_request {
            let _ = app_for_thread.emit("serial-disconnected", thread_port_name);
        }
    });

    app.emit("serial-opened", port_name)
        .map_err(|error| format!("시리얼 연결 이벤트를 전달하지 못했습니다: {error}"))?;

    Ok(())
}

#[tauri::command]
fn disconnect_serial_port(
    app: AppHandle,
    connection: State<'_, SerialConnection>,
) -> Result<(), String> {
    connection.generation.fetch_add(1, Ordering::SeqCst);
    close_connection(connection.inner())?;
    app.emit("serial-disconnected", "사용자 요청")
        .map_err(|error| format!("시리얼 종료 이벤트를 전달하지 못했습니다: {error}"))?;
    Ok(())
}

#[tauri::command]
fn write_serial_command(
    connection: State<'_, SerialConnection>,
    command: String,
) -> Result<(), String> {
    let command = command.trim();
    if command.is_empty() {
        return Err("빈 시리얼 명령은 전송할 수 없습니다.".to_string());
    }
    if command.len() > 64 {
        return Err("시리얼 명령은 64자를 초과할 수 없습니다.".to_string());
    }

    let mut guard = connection
        .port
        .lock()
        .map_err(|_| "시리얼 포트 잠금이 손상되었습니다.".to_string())?;
    let port = guard
        .as_mut()
        .ok_or_else(|| "연결된 Arduino가 없습니다.".to_string())?;

    let payload = format!("{command}\n");
    port.write_all(payload.as_bytes())
        .map_err(|error| format!("Arduino 명령 전송 실패: {error}"))?;
    port.flush()
        .map_err(|error| format!("Arduino 전송 버퍼 정리 실패: {error}"))?;

    Ok(())
}

#[tauri::command]
fn serial_connection_active(connection: State<'_, SerialConnection>) -> Result<bool, String> {
    Ok(connection
        .port
        .lock()
        .map_err(|_| "시리얼 포트 잠금이 손상되었습니다.".to_string())?
        .is_some())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(SerialConnection::default())
        .invoke_handler(tauri::generate_handler![
            save_processed_file,
            list_serial_ports,
            connect_serial_port,
            disconnect_serial_port,
            write_serial_command,
            serial_connection_active
        ])
        .run(tauri::generate_context!())
        .expect("AKFES 데스크톱 애플리케이션을 실행하지 못했습니다.");
}
