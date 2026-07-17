use std::fs;
use std::path::Path;

const PLACEHOLDER_ICON: &[u8] = &[
    137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1, 0, 0,
    0, 1, 8, 6, 0, 0, 0, 31, 21, 196, 137, 0, 0, 0, 11, 73, 68, 65, 84, 120, 156,
    99, 96, 0, 2, 0, 0, 5, 0, 1, 122, 94, 171, 63, 0, 0, 0, 0, 73, 69, 78, 68, 174,
    66, 96, 130,
];

const PLACEHOLDER_ICO: &[u8] = &[
    0, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 32, 0, 70, 0, 0, 0, 22, 0, 0, 0, 40, 0,
    0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 1, 0, 32, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
];

fn write_if_missing(path: &Path, bytes: &[u8]) {
    if path.exists() {
        return;
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).expect("failed to create build resource directory");
    }
    fs::write(path, bytes).expect("failed to write build resource");
}

fn main() {
    write_if_missing(Path::new("icons/icon.png"), PLACEHOLDER_ICON);
    write_if_missing(Path::new("icons/icon.ico"), PLACEHOLDER_ICO);
    tauri_build::build()
}
