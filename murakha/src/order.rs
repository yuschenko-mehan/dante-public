//! Signed orders Archant -> Knyaz (AdDante) implementation.
//! Реалізація підписаних наказів Архант -> Князь (АдДанте).

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use std::fs;
use std::path::Path;

/// Order error types.
/// Типи помилок наказів.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OrderError {
    Malformed,
    BadSignature,
    Expired,
    Replay,
}

/// Parsed and verified order.
/// Розібраний та перевірений наказ.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Order {
    pub seq: u64,
    pub expires: u64,
    pub body: String,
}

/// Archant key pair wrapper.
/// Обгортка пари ключів Арханта.
pub struct ArchantKey {
    signing_key: SigningKey,
}

impl ArchantKey {
    /// Generate a new random Archant key.
    /// Згенерувати новий випадковий ключ Арханта.
    pub fn generate() -> Self {
        let mut seed = [0u8; 32];
        if let Err(_) = getrandom::getrandom(&mut seed) {
            // Fallback or handle error / Запасний варіант або обробка помилки
        }
        let signing_key = SigningKey::from_bytes(&seed);
        Self { signing_key }
    }

    /// Restore Archant key from seed hex string.
    /// Відновити ключ Арханта з шістнадцяткового рядка сіду.
    pub fn from_seed_hex(hex_str: &str) -> Result<Self, &'static str> {
        let bytes = crate::protocol::hex_decode(hex_str)?;
        if bytes.len() != 32 {
            return Err("Invalid seed length / Не різна довжина сіду");
        }
        let mut seed = [0u8; 32];
        seed.copy_from_slice(&bytes);
        let signing_key = SigningKey::from_bytes(&seed);
        Ok(Self { signing_key })
    }

    /// Get public key as hex string.
    /// Отримати відкритий ключ у вигляді шістнадцяткового рядка.
    pub fn public_hex(&self) -> String {
        crate::protocol::hex_encode(self.signing_key.verifying_key().as_bytes())
    }

    /// Get seed as hex string.
    /// Отримати сід у вигляді шістнадцяткового рядка.
    pub fn seed_hex(&self) -> String {
        crate::protocol::hex_encode(self.signing_key.to_bytes().as_slice())
    }
}

/// Sign an order with Archant's key.
/// Підписати наказ ключем Арханта.
pub fn sign_order(key: &ArchantKey, seq: u64, expires: u64, body: &str) -> String {
    let body_bytes = body.as_bytes();
    let body_hex = crate::protocol::hex_encode(body_bytes);
    let text_to_sign = format!("DANTE-ORDER-1\n{}\n{}\n{}", seq, expires, body);
    let signature: Signature = key.signing_key.sign(text_to_sign.as_bytes());
    let sig_hex = crate::protocol::hex_encode(signature.to_bytes().as_slice());
    format!("ORDER\t{}\t{}\t{}\t{}", seq, expires, body_hex, sig_hex)
}

/// Obedience state machine for Knyaz.
/// Машина стану підкорення для Князя.
pub struct Obedience {
    archant_verifying_key: VerifyingKey,
    last_seq: u64,
}

impl Obedience {
    /// Create a new Obedience instance with Archant's public key hex.
    /// Створити новий екземпляр Obedience з шістнадцятковим відкритим ключем Арханта.
    pub fn new(public_hex: &str) -> Result<Self, OrderError> {
        let bytes = crate::protocol::hex_decode(public_hex).map_err(|_| OrderError::Malformed)?;
        if bytes.len() != 32 {
            return Err(OrderError::Malformed);
        }
        let mut pk_bytes = [0u8; 32];
        pk_bytes.copy_from_slice(&bytes);
        let archant_verifying_key = VerifyingKey::from_bytes(&pk_bytes).map_err(|_| OrderError::Malformed)?;
        Ok(Self {
            archant_verifying_key,
            last_seq: 0,
        })
    }

    /// Get the last accepted sequence number.
    /// Отримати останній прийнятий номер послідовності.
    pub fn last_seq(&self) -> u64 {
        self.last_seq
    }

    /// Accept and verify an order line.
    /// Прийняти та перевірити рядок наказу.
    pub fn accept(&mut self, line: &str, now: u64) -> Result<Order, OrderError> {
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.len() != 5 {
            return Err(OrderError::Malformed);
        }
        if parts[0] != "ORDER" {
            return Err(OrderError::Malformed);
        }
        let seq = parts[1].parse::<u64>().map_err(|_| OrderError::Malformed)?;
        let expires = parts[2].parse::<u64>().map_err(|_| OrderError::Malformed)?;
        let body_bytes = crate::protocol::hex_decode(parts[3]).map_err(|_| OrderError::Malformed)?;
        let body = String::from_utf8(body_bytes).map_err(|_| OrderError::Malformed)?;
        let sig_bytes = crate::protocol::hex_decode(parts[4]).map_err(|_| OrderError::Malformed)?;
        if sig_bytes.len() != 64 {
            return Err(OrderError::Malformed);
        }
        let mut sig_arr = [0u8; 64];
        sig_arr.copy_from_slice(&sig_bytes);
        let signature = Signature::from_bytes(&sig_arr);

        // Check expiration / Перевірити термін дії
        if now > expires {
            return Err(OrderError::Expired);
        }

        // Check replay / Перевірити повтор
        if seq <= self.last_seq {
            return Err(OrderError::Replay);
        }

        // Verify signature / Перевірити підпис
        let text_to_sign = format!("DANTE-ORDER-1\n{}\n{}\n{}", seq, expires, body);
        self.archant_verifying_key
            .verify(text_to_sign.as_bytes(), &signature)
            .map_err(|_| OrderError::BadSignature)?;

        // Only fully accepted order moves last_seq / Лише повністю прийнятий наказ зсуває last_seq
        self.last_seq = seq;

        Ok(Order { seq, expires, body })
    }

    /// Save state to file.
    /// Зберегти стан у файл.
    pub fn save<P: AsRef<Path>>(&self, path: P) -> Result<(), std::io::Error> {
        let pub_hex = crate::protocol::hex_encode(self.archant_verifying_key.as_bytes());
        let content = format!("{}\n{}\n", pub_hex, self.last_seq);
        fs::write(path, content)
    }

    /// Load state from file.
    /// Завантажити стан з файлу.
    pub fn load<P: AsRef<Path>>(path: P) -> Result<Self, OrderError> {
        let content = fs::read_to_string(path).map_err(|_| OrderError::Malformed)?;
        let lines: Vec<&str> = content.lines().collect();
        if lines.len() < 2 {
            return Err(OrderError::Malformed);
        }
        let pub_hex = lines[0].trim();
        let last_seq = lines[1].trim().parse::<u64>().map_err(|_| OrderError::Malformed)?;
        let mut obedience = Self::new(pub_hex)?;
        obedience.last_seq = last_seq;
        Ok(obedience)
    }
}
