// Flash drive keys management / Управління ключами на флешці
use argon2::{Algorithm, Argon2, Params, Version};
use chacha20poly1305::{
    aead::{Aead, KeyInit, Payload},
    ChaCha20Poly1305, Nonce,
};

/// Magic bytes for the flash file format
/// Магічні байти для формату файлу флешки
pub const MAGIC: &[u8] = b"DANTE-FLASH-1\n";

/// Errors that can occur during flash file operations
/// Помилки, які можуть виникнути під час операцій з файлом флешки
#[derive(Debug, PartialEq, Eq)]
pub enum FlashError {
    NotFlash,
    WrongPassOrDamaged,
}

/// KDF parameters for Argon2id
/// Параметри KDF для Argon2id
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct KdfParams {
    pub m_kib: u32,
    pub t: u32,
    pub p: u32,
}

impl KdfParams {
    /// Strong KDF parameters for production
    /// Сильні параметри KDF для продакшну
    pub fn strong() -> Self {
        Self {
            m_kib: 65536,
            t: 3,
            p: 1,
        }
    }

    /// Fast KDF parameters for testing
    /// Швидкі параметри KDF для тестування
    pub fn fast() -> Self {
        Self {
            m_kib: 64,
            t: 1,
            p: 1,
        }
    }
}

/// Check if the passphrase meets strength requirements: at least 10 chars, not all the same.
/// Перевірити, чи відповідає парольна фраза вимогам міцності: щонайменше 10 символів, не всі однакові.
pub fn check_pass(pass: &str) -> Result<(), ()> {
    let chars: Vec<char> = pass.chars().collect();
    if chars.len() < 10 {
        return Err(());
    }
    let first = chars[0];
    if chars.iter().all(|&c| c == first) {
        return Err(());
    }
    Ok(())
}

/// Extract key names from content: key=value lines, skipping blanks, comments, empty names.
/// Витягти назви ключів із вмісту: рядки key=value, пропускаючи порожні, коментарі та порожні назви.
pub fn key_names(content: &str) -> Vec<String> {
    let mut names = Vec::new();
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        if let Some(idx) = trimmed.find('=') {
            let name = trimmed[..idx].trim();
            if !name.is_empty() {
                names.push(name.to_string());
            }
        }
    }
    names
}

/// Merge incoming keys into existing keys, keeping order and comments, ending with newline.
/// Об'єднати вхідні ключі з існуючими, зберігаючи порядок та коментарі, завершуючи новим рядком.
pub fn merge_keys(existing: &str, incoming: &str) -> String {
    let incoming_map: Vec<(String, String)> = incoming
        .lines()
        .filter_map(|line| {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') {
                return None;
            }
            if let Some(idx) = trimmed.find('=') {
                let name = trimmed[..idx].trim();
                let val = trimmed[idx + 1..].trim();
                if !name.is_empty() {
                    return Some((name.to_string(), val.to_string()));
                }
            }
            None
        })
        .collect();

    let mut result_lines = Vec::new();
    // Track updated key names as &str to avoid Borrow issues / Відстежувати назви ключів як &str, щоб уникнути проблем з Borrow
    let mut updated_keys: std::collections::HashSet<&str> = std::collections::HashSet::new();

    for line in existing.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            result_lines.push(line.to_string());
            continue;
        }
        if let Some(idx) = trimmed.find('=') {
            let name = trimmed[..idx].trim();
            if !name.is_empty() {
                let mut replaced = false;
                for (inc_name, inc_val) in &incoming_map {
                    if inc_name == name {
                        result_lines.push(format!("{}={}", name, inc_val));
                        updated_keys.insert(name);
                        replaced = true;
                        break;
                    }
                }
                if !replaced {
                    result_lines.push(line.to_string());
                }
            } else {
                result_lines.push(line.to_string());
            }
        } else {
            result_lines.push(line.to_string());
        }
    }

    for (inc_name, inc_val) in &incoming_map {
        if !updated_keys.contains(inc_name.as_str()) {
            result_lines.push(format!("{}={}", inc_name, inc_val));
        }
    }

    let mut final_str = result_lines.join("\n");
    if !final_str.is_empty() {
        final_str.push('\n');
    }
    final_str
}

/// Seal data with passphrase and KdfParams into a flash blob.
/// Запечатати дані за допомогою парольної фрази та KdfParams у блiб флешки.
pub fn seal(pass: &str, data: &[u8], params: KdfParams) -> Vec<u8> {
    let mut salt = [0u8; 16];
    getrandom::getrandom(&mut salt).expect("Failed to generate salt");
    let mut nonce_bytes = [0u8; 12];
    getrandom::getrandom(&mut nonce_bytes).expect("Failed to generate nonce");

    let mut header = Vec::new();
    header.extend_from_slice(MAGIC);
    header.extend_from_slice(&params.m_kib.to_le_bytes());
    header.extend_from_slice(&params.t.to_le_bytes());
    header.extend_from_slice(&params.p.to_le_bytes());
    header.extend_from_slice(&salt);
    header.extend_from_slice(&nonce_bytes);

    let argon2_params = Params::new(params.m_kib, params.t, params.p, Some(32))
        .expect("Invalid Argon2 params");
    let argon2 = Argon2::new(Algorithm::Argon2id, Version::V0x13, argon2_params);
    let mut key = [0u8; 32];
    argon2
        .hash_password_into(pass.as_bytes(), &salt, &mut key)
        .expect("Argon2 hashing failed");

    let cipher = ChaCha20Poly1305::new(&key.into());
    let nonce = Nonce::from_slice(&nonce_bytes);
    let ciphertext = cipher
        .encrypt(nonce, Payload { msg: data, aad: &header })
        .expect("Encryption failed");

    let mut blob = header;
    blob.extend_from_slice(&ciphertext);
    blob
}

/// Open and decrypt a flash blob with the passphrase.
/// Відкрити та розшифрувати блiб флешки за допомогою парольної фрази.
pub fn open(pass: &str, blob: &[u8]) -> Result<Vec<u8>, FlashError> {
    if blob.len() < 54 {
        return Err(FlashError::NotFlash);
    }
    if &blob[..14] != MAGIC {
        return Err(FlashError::NotFlash);
    }

    let m_kib = u32::from_le_bytes([blob[14], blob[15], blob[16], blob[17]]);
    let t = u32::from_le_bytes([blob[18], blob[19], blob[20], blob[21]]);
    let p = u32::from_le_bytes([blob[22], blob[23], blob[24], blob[25]]);

    if m_kib > 2_097_152 || t > 64 || p == 0 || p > 16 {
        return Err(FlashError::NotFlash);
    }

    let salt = &blob[26..42];
    let nonce_bytes = &blob[42..54];
    let header = &blob[..54];
    let ciphertext = &blob[54..];

    let argon2_params = Params::new(m_kib, t, p, Some(32)).map_err(|_| FlashError::NotFlash)?;
    let argon2 = Argon2::new(Algorithm::Argon2id, Version::V0x13, argon2_params);
    let mut key = [0u8; 32];
    argon2
        .hash_password_into(pass.as_bytes(), salt, &mut key)
        .map_err(|_| FlashError::WrongPassOrDamaged)?;

    let cipher = ChaCha20Poly1305::new(&key.into());
    let nonce = Nonce::from_slice(nonce_bytes);
    cipher
        .decrypt(nonce, Payload { msg: ciphertext, aad: header })
        .map_err(|_| FlashError::WrongPassOrDamaged)
}
