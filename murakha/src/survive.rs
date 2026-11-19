/// Survive module for snapshots, checksums, and takeover logic.
/// Модуль виживання для зрімків, контрольних сум та логіки підхоплення.

use std::fs;
use std::io::{self, ErrorKind};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

/// Global counter for snapshot file names to ensure uniqueness.
/// Глобальний лічильник для назв файлів знімків для забезпечення унікальності.
static SNAPSHOT_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Calculate FNV-1a 64-bit checksum.
/// Обчислити контрольну суму FNV-1a 64-біт.
pub fn checksum(data: &[u8]) -> u64 {
    // FNV-1a constants / Константи FNV-1a
    let mut hash: u64 = 0xcbf29ce484222325;
    for &byte in data {
        hash ^= byte as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    hash
}

/// Store snapshot data atomically and prune old ones.
/// Зберегти дані знімка атомарно та видалити старі.
pub fn store(dir: &Path, data: &[u8], keep: usize) -> io::Result<PathBuf> {
    fs::create_dir_all(dir)?;

    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let millis_u64 = millis as u64;
    let counter = SNAPSHOT_COUNTER.fetch_add(1, Ordering::SeqCst);

    let name = format!("snapshot-{:015}-{:06}.bin", millis_u64, counter);
    let final_path = dir.join(&name);
    let tmp_path = dir.join(format!("{}.tmp", name));

    // Build file contents: 8 bytes checksum (little-endian) + data /
    // Побудувати вміст файлу: 8 байтів контрольної суми (little-endian) + дані
    let cs = checksum(data);
    let mut file_data = Vec::with_capacity(8 + data.len());
    file_data.extend_from_slice(&cs.to_le_bytes());
    file_data.extend_from_slice(data);

    // Atomic write: write tmp, then rename / Атомарний запис: записати tmp, потім перейменувати
    fs::write(&tmp_path, &file_data)?;
    fs::rename(&tmp_path, &final_path)?;

    // Prune old snapshots / Видалити старі знімки
    let keep_count = if keep == 0 { 1 } else { keep };
    let mut snapshots = list(dir);
    if snapshots.len() > keep_count {
        let to_remove_count = snapshots.len() - keep_count;
        for path in snapshots.drain(..to_remove_count) {
            let _ = fs::remove_file(path);
        }
    }

    Ok(final_path)
}

/// List valid snapshot files in directory, oldest first.
/// Перерахувати дійсні файли знімків у каталозі, від найстаріших до найновіших.
pub fn list(dir: &Path) -> Vec<PathBuf> {
    let mut paths = Vec::new();
    let entries = match fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return paths,
    };

    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() {
            if let Some(file_name) = path.file_name().and_then(|n| n.to_str()) {
                if file_name.starts_with("snapshot-") && file_name.ends_with(".bin") {
                    paths.push(path);
                }
            }
        }
    }

    // Sort by file name (oldest first due to timestamp and counter layout) /
    // Сортувати за назвою файлу (найстаріші першими через мітку часу та лічильник)
    paths.sort();
    paths
}

/// Load and verify snapshot data from path.
/// Завантажити та перевірити дані знімка за шляхом.
pub fn load(path: &Path) -> io::Result<Vec<u8>> {
    let file_data = fs::read(path)?;
    if file_data.len() < 8 {
        return Err(io::Error::new(ErrorKind::InvalidData, "Snapshot too short"));
    }

    let (stored_cs_bytes, data) = file_data.split_at(8);
    let mut arr = [0u8; 8];
    arr.copy_from_slice(stored_cs_bytes);
    let stored_cs = u64::from_le_bytes(arr);

    let calculated_cs = checksum(data);
    if stored_cs != calculated_cs {
        return Err(io::Error::new(ErrorKind::InvalidData, "Checksum mismatch"));
    }

    Ok(data.to_vec())
}

/// Get the data of the newest snapshot that loads correctly.
/// Отримати дані найновішого знімка, який завантажується коректно.
pub fn latest(dir: &Path) -> Option<Vec<u8>> {
    let snapshots = list(dir);
    for path in snapshots.into_iter().rev() {
        if let Ok(data) = load(&path) {
            return Some(data);
        }
    }
    None
}

/// Determine whether a node should take over coordination duties.
/// Визначити, чи повинен вузол взяти на себе обов'язки координатора.
pub fn should_take_over(now_s: u64, last_seen_s: Option<u64>, silence_limit_s: u64) -> bool {
    let last_seen = match last_seen_s {
        Some(t) => t,
        None => return false,
    };

    let diff = now_s.saturating_sub(last_seen);
    diff > silence_limit_s
}

/// Determine the successor ant based on priority list and alive list.
/// Визначити наступну мураху на основі списку пріоритетів та списку живих.
pub fn successor(priority: &[String], alive: &[String]) -> Option<String> {
    // First, check priority list / Спочатку перевірити список пріоритетів
    for p_id in priority {
        if alive.contains(p_id) {
            return Some(p_id.clone());
        }
    }

    // Otherwise, find the alphabetically smallest alive id / В іншому випадку знайти алфавітно найменший живий ідентифікатор
    let mut sorted_alive = alive.to_vec();
    sorted_alive.sort();
    sorted_alive.into_iter().next()
}
