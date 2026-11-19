/// Mailbag implementation for persistent results and checkpoints.
/// Реалізація торби для збережених результатів та контрольних точок.

use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

/// Generate a safe identifier keeping only ASCII letters, digits, '-' and '_'.
/// Генерувати безпечний ідентифікатор, залишаючи лише ASCII-літери, цифри, '-' та '_'.
pub fn safe_id(task_id: &str) -> String {
    // Check if task_id is empty / Перевірити, чи task_id порожній
    if task_id.is_empty() {
        return "_".to_string();
    }
    let mut result = String::with_capacity(task_id.len());
    for c in task_id.chars() {
        if c.is_ascii_alphanumeric() || c == '-' || c == '_' {
            result.push(c);
        } else {
            result.push('_');
        }
    }
    // If result ended up empty, return "_" / Якщо результат вийшов порожнім, повернути "_"
    if result.is_empty() {
        "_".to_string()
    } else {
        result
    }
}

/// Put result data into directory atomically using .tmp and rename.
/// Записати дані результату в директорію атомарно, використовуючи .tmp та перейменування.
pub fn put(dir: &Path, task_id: &str, data: &[u8]) -> io::Result<PathBuf> {
    // Ensure parent directory exists / Переконатися, що батьківська директорія існує
    fs::create_dir_all(dir)?;
    let s_id = safe_id(task_id);
    let final_path = dir.join(format!("{}.res", s_id));
    let tmp_path = dir.join(format!("{}.tmp", s_id));

    // Write to temporary file atomically / Записати у тимчасовий файл атомарно
    {
        let mut file = fs::File::create(&tmp_path)?;
        file.write_all(data)?;
        file.sync_all()?;
    }

    // Rename temporary file to final path / Перейменувати тимчасовий файл на кінцевий шлях
    fs::rename(&tmp_path, &final_path)?;
    Ok(final_path)
}

/// Get sorted vector of safe IDs of all pending .res files.
/// Отримати відсортований вектор безпечних ідентифікаторів усіх очікуваних .res файлів.
pub fn pending(dir: &Path) -> Vec<String> {
    let mut ids = Vec::new();
    let entries = match fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return ids,
    };

    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() {
            if let Some(ext) = path.extension() {
                if ext == "res" {
                    if let Some(stem) = path.file_stem() {
                        if let Some(s) = stem.to_str() {
                            ids.push(s.to_string());
                        }
                    }
                }
            }
        }
    }

    ids.sort();
    ids
}

/// Get result data for a task ID.
/// Отримати дані результату для ідентифікатора завдання.
pub fn get(dir: &Path, task_id: &str) -> io::Result<Vec<u8>> {
    let s_id = safe_id(task_id);
    let final_path = dir.join(format!("{}.res", s_id));
    fs::read(final_path)
}

/// Remove result file for a task ID, succeeding if already missing.
/// Видалити файл результату для ідентифікатора завдання, повертаючи успіх, якщо він уже відсутній.
pub fn done(dir: &Path, task_id: &str) -> io::Result<()> {
    let s_id = safe_id(task_id);
    let final_path = dir.join(format!("{}.res", s_id));
    match fs::remove_file(final_path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e),
    }
}

/// Save checkpoint data atomically as "<safe_id>.ckpt".
/// Зберегти дані контрольної точки атомарно як "<safe_id>.ckpt".
pub fn save_checkpoint(dir: &Path, task_id: &str, data: &[u8]) -> io::Result<()> {
    // Ensure directory exists / Переконатися, що директорія існує
    fs::create_dir_all(dir)?;
    let s_id = safe_id(task_id);
    let final_path = dir.join(format!("{}.ckpt", s_id));
    let tmp_path = dir.join(format!("{}.ckpt.tmp", s_id));

    // Write to temp file / Записати у тимчасовий файл
    {
        let mut file = fs::File::create(&tmp_path)?;
        file.write_all(data)?;
        file.sync_all()?;
    }

    // Rename to final path / Перейменувати на кінцевий шлях
    fs::rename(&tmp_path, &final_path)?;
    Ok(())
}

/// Load checkpoint data if it exists.
/// Завантажити дані контрольної точки, якщо вони існують.
pub fn load_checkpoint(dir: &Path, task_id: &str) -> Option<Vec<u8>> {
    let s_id = safe_id(task_id);
    let final_path = dir.join(format!("{}.ckpt", s_id));
    fs::read(final_path).ok()
}

/// Drop checkpoint data without failing or panicking.
/// Видалити дані контрольної точки без збоїв чи паніки.
pub fn drop_checkpoint(dir: &Path, task_id: &str) {
    let s_id = safe_id(task_id);
    let final_path = dir.join(format!("{}.ckpt", s_id));
    let _ = fs::remove_file(final_path);
}
