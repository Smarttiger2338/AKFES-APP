use serde::Serialize;
use serialport::SerialPortType;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SerialPortInfo {
    name: String,
    port_type: String,
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![list_serial_ports])
        .run(tauri::generate_context!())
        .expect("AKFES 데스크톱 애플리케이션을 실행하지 못했습니다.");
}
