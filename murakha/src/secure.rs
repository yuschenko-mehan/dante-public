/// Swarm security implementation: HMAC-SHA256, keys, nonces, proofs, and secure Channel.
/// Реалізація безпеки рою: HMAC-SHA256, ключі, нонси, докази та захищений канал.

use hmac::{Hmac, Mac};
use sha2::Sha256;
use std::io;
use std::path::Path;
use hex; // Hex encoding/decoding utilities / Утиліти для кодування/декодування hex

type HmacSha256 = Hmac<Sha256>;

/// Compute raw HMAC-SHA256 over parts joined by "\n".
/// Обчислити сирий HMAC-SHA256 для частин, об'єднаних через "\n".
pub fn hmac_raw(key: &[u8], parts: &[&str]) -> Vec<u8> {
    let mut mac = HmacSha256::new_from_slice(key).expect("HMAC can take key of any size / HMAC може приймати ключ будь-якого розміру");
    let joined = parts.join("\n");
    mac.update(joined.as_bytes());
    mac.finalize().into_bytes().to_vec()
}

/// Compute HMAC-SHA256 over parts joined by "\n" as 64 lower-case hex chars.
/// Обчислити HMAC-SHA256 для частин, об'єднаних через "\n", у вигляді 64 шістнадцяткових символів у нижньому регістрі.
pub fn hmac_hex(key: &[u8], parts: &[&str]) -> String {
    let bytes = hmac_raw(key, parts);
    hex::encode(bytes)
}

/// Generate 32 random bytes (using getrandom) as 64 hex chars.
/// Згенерувати 32 випадкові байти (використовуючи getrandom) як 64 шістнадцяткові символи.
pub fn new_key() -> String {
    let mut buf = [0u8; 32];
    getrandom::getrandom(&mut buf).unwrap();
    hex::encode(buf)
}

/// Generate 16 random bytes as 32 hex chars.
/// Згенерувати 16 випадкових байтів як 32 шістнадцяткові символи.
pub fn nonce() -> String {
    let mut buf = [0u8; 16];
    getrandom::getrandom(&mut buf).unwrap();
    hex::encode(buf)
}

/// Save swarm key to path as hex string.
/// Зберегти ключ рою за шляхом у вигляді шістнадцяткового рядка.
pub fn save_key(path: &Path, hex: &str) -> io::Result<()> {
    std::fs::write(path, hex)
}

/// Load swarm key from path; trimmed hex; not exactly 32 bytes -> Err(InvalidData).
/// Завантажити ключ рою з шляху; обрізаний шістнадцятковий рядок; якщо не рівно 32 байти -> Err(InvalidData).
pub fn load_key(path: &Path) -> io::Result<Vec<u8>> {
    let content = std::fs::read_to_string(path)?;
    let trimmed = content.trim();
    let bytes = hex::decode(trimmed).map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "Invalid hex"))?;
    if bytes.len() != 32 {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "Key must be 32 bytes"));
    }
    Ok(bytes)
}

/// Constant-time string comparison (different length -> false).
/// Порівняння рядків за постійний час ( різна довжина -> false ).
pub fn eq_ct(a: &str, b: &str) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let a_bytes = a.as_bytes();
    let b_bytes = b.as_bytes();
    let mut diff = 0;
    for (x, y) in a_bytes.iter().zip(b_bytes.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

/// Compute ant proof for handshake.
/// Обчислити доказ мурахи для рукостискання.
pub fn ant_proof(key: &[u8], nonce_c: &str, nonce_a: &str, ant_id: &str) -> String {
    hmac_hex(key, &["ant", nonce_c, nonce_a, ant_id])
}

/// Compute coordinator proof for handshake.
/// Обчислити доказ координатора для рукостискання.
pub fn coord_proof(key: &[u8], nonce_c: &str, nonce_a: &str) -> String {
    hmac_hex(key, &["coord", nonce_a, nonce_c])
}

/// Compute session key from swarm key and nonces.
/// Обчислити сесійний ключ із ключа рою та нонсів.
pub fn session_key(key: &[u8], nonce_c: &str, nonce_a: &str) -> Vec<u8> {
    hmac_raw(key, &["session", nonce_c, nonce_a])
}

/// One side of a session channel.
/// Один бік сесійного каналу.
pub struct Channel {
    session_key: Vec<u8>,
    is_ant: bool,
    send_seq: u64,
    recv_seq: u64,
}

impl Channel {
    /// Create a new channel. Ant sends direction "a", coordinator "c".
    /// Створити новий канал. Мураха надсилає напрямок "a", координатор "c".
    pub fn new(session_key: Vec<u8>, is_ant: bool) -> Channel {
        Channel {
            session_key,
            is_ant,
            send_seq: 0,
            recv_seq: 0,
        }
    }

    /// Seal a line: format "<line>\t#<seq>\t<mac>".
    /// Запечатати рядок: формат "<line>\t#<seq>\t<mac>".
    pub fn seal(&mut self, line: &str) -> String {
        let seq = self.send_seq;
        self.send_seq += 1;
        let direction = if self.is_ant { "a" } else { "c" };
        let seq_str = seq.to_string();
        let mac = hmac_hex(&self.session_key, &[direction, &seq_str, line]);
        let mac_prefix = &mac[..32];
        format!("{}\t#{}\t{}", line, seq, mac_prefix)
    }

    /// Open a wire message: checks sequence, direction, and HMAC.
    /// Відкрити повідомлення в мережі: перевіряє послідовність, напрямок та HMAC.
    pub fn open(&mut self, wire: &str) -> Result<String, String> {
        let wire = wire.strip_suffix("\r\n").unwrap_or(wire);
        let wire = wire.strip_suffix('\n').unwrap_or(wire);

        let parts: Vec<&str> = wire.split('\t').collect();
        if parts.len() < 3 {
            return Err("Too few fields".to_string());
        }

        let mac_str = parts[parts.len() - 1];
        let seq_field = parts[parts.len() - 2];
        let line_parts = &parts[..parts.len() - 2];
        let line = line_parts.join("\t");

        if !seq_field.starts_with('#') {
            return Err("Invalid sequence field format".to_string());
        }
        let seq_num_str = &seq_field[1..];
        let seq: u64 = match seq_num_str.parse() {
            Ok(n) => n,
            Err(_) => return Err("Failed to parse sequence number".to_string()),
        };

        if seq != self.recv_seq {
            return Err("Sequence number mismatch".to_string());
        }

        let other_direction = if self.is_ant { "c" } else { "a" };
        let expected_mac = hmac_hex(&self.session_key, &[other_direction, seq_num_str, &line]);
        let expected_prefix = &expected_mac[..32];

        if !eq_ct(mac_str, expected_prefix) {
            return Err("HMAC verification failed".to_string());
        }

        self.recv_seq += 1;
        Ok(line)
    }
}
