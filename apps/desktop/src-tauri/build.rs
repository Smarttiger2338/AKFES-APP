use std::fs;
use std::path::Path;

const PLACEHOLDER_ICON: &[u8] = &[
    137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1, 0, 0,
    0, 1, 8, 4, 0, 0, 0, 181, 28, 12, 2, 0, 0, 0, 11, 73, 68, 65, 84, 120, 218, 99,
    100, 248, 15, 0, 1, 5, 1, 1, 39, 24, 227, 102, 0, 0, 0, 0, 73, 69, 78, 68, 174,
    66, 96, 130,
];

fn ensure_placeholder_icon() {
    let icon_path = Path::new("icons/icon.png");
    if icon_path.exists() {
        return;
    }

    if let Some(parent) = icon_path.parent() {
        fs::create_dir_all(parent).expect("failed to create Tauri icon directory");
    }
    fs::write(icon_path, PLACEHOLDER_ICON).expect("failed to write placeholder Tauri icon");
}

fn main() {
    ensure_placeholder_icon();
    tauri_build::build()
}
