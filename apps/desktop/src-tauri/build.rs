use std::fs;
use std::path::Path;

const PLACEHOLDER_PNG: &[u8] = &[
    137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1, 0, 0,
    0, 1, 8, 6, 0, 0, 0, 31, 21, 196, 137, 0, 0, 0, 11, 73, 68, 65, 84, 120, 156,
    99, 96, 0, 2, 0, 0, 5, 0, 1, 122, 94, 171, 63, 0, 0, 0, 0, 73, 69, 78, 68, 174,
    66, 96, 130,
];

fn ensure_icon_directory() {
    fs::create_dir_all("icons").expect("failed to create Tauri icon directory");
}

fn ensure_placeholder_png() {
    let path = Path::new("icons/icon.png");
    if !path.exists() {
        fs::write(path, PLACEHOLDER_PNG).expect("failed to write placeholder PNG icon");
    }
}

fn ensure_placeholder_ico() {
    let path = Path::new("icons/icon.ico");
    if path.exists() {
        return;
    }

    let png_size = PLACEHOLDER_PNG.len() as u32;
    let mut ico = Vec::with_capacity(22 + PLACEHOLDER_PNG.len());
    ico.extend_from_slice(&[0, 0, 1, 0, 1, 0]);
    ico.extend_from_slice(&[1, 1, 0, 0]);
    ico.extend_from_slice(&1_u16.to_le_bytes());
    ico.extend_from_slice(&32_u16.to_le_bytes());
    ico.extend_from_slice(&png_size.to_le_bytes());
    ico.extend_from_slice(&22_u32.to_le_bytes());
    ico.extend_from_slice(PLACEHOLDER_PNG);
    fs::write(path, ico).expect("failed to write placeholder ICO icon");
}

fn main() {
    ensure_icon_directory();
    ensure_placeholder_png();
    ensure_placeholder_ico();
    tauri_build::build()
}
