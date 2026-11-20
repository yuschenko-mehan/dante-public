// Spec: keys on a USB flash drive (encrypted, passphrase typed only by the owner).
// Специфікація: ключі на флешці (зашифровані, пароль вводить лише власник).
use murakha::flash::{check_pass, key_names, merge_keys, open, seal, FlashError, KdfParams, MAGIC};

const PASS: &str = "Довгий пароль 2026";
const KEYS: &str = "# DANTE keys\nGEMINI_API_KEY=AIza-secret-1\nGROQ_API_KEY=gsk_secret_2\n";

#[test]
fn round_trip() {
    let blob = seal(PASS, KEYS.as_bytes(), KdfParams::fast());
    assert!(blob.starts_with(MAGIC));
    assert_eq!(open(PASS, &blob).unwrap(), KEYS.as_bytes());
}

#[test]
fn secret_is_not_visible_on_the_flash() {
    // Nothing of the keys may be readable in the file
    // Жодна частина ключів не повинна читатися у файлі
    let blob = seal(PASS, KEYS.as_bytes(), KdfParams::fast());
    let text = String::from_utf8_lossy(&blob);
    assert!(!text.contains("secret") && !text.contains("GEMINI") && !text.contains("AIza"));
    // fresh salt and nonce every time / щоразу нова сіль і nonce
    assert_ne!(blob, seal(PASS, KEYS.as_bytes(), KdfParams::fast()));
}

#[test]
fn wrong_pass_or_damage_is_refused() {
    let blob = seal(PASS, KEYS.as_bytes(), KdfParams::fast());
    assert_eq!(open("Довгий пароль 2025", &blob), Err(FlashError::WrongPassOrDamaged));
    let mut bad = blob.clone();
    let last = bad.len() - 1;
    bad[last] ^= 1;
    assert_eq!(open(PASS, &bad), Err(FlashError::WrongPassOrDamaged));
    // tampering with the header (salt) is also detected / підміна заголовка теж помітна
    let mut bad2 = blob.clone();
    bad2[30] ^= 1;
    assert_eq!(open(PASS, &bad2), Err(FlashError::WrongPassOrDamaged));
}

#[test]
fn not_a_flash_file() {
    assert_eq!(open(PASS, b""), Err(FlashError::NotFlash));
    assert_eq!(open(PASS, b"GEMINI_API_KEY=x\n"), Err(FlashError::NotFlash));
    let blob = seal(PASS, KEYS.as_bytes(), KdfParams::fast());
    assert_eq!(open(PASS, &blob[..40]), Err(FlashError::NotFlash));
    // absurd KDF memory (memory bomb) must be refused, not attempted
    // абсурдна пам'ять KDF (бомба пам'яті) — відмова, а не спроба
    let mut bomb = blob.clone();
    bomb[14..18].copy_from_slice(&u32::MAX.to_le_bytes());
    assert_eq!(open(PASS, &bomb), Err(FlashError::NotFlash));
}

#[test]
fn strong_params_are_strong() {
    let s = KdfParams::strong();
    assert!(s.m_kib >= 65536 && s.t >= 3);
}

#[test]
fn passphrase_rules() {
    assert!(check_pass(PASS).is_ok());
    assert!(check_pass("короткий").is_err());
    assert!(check_pass("aaaaaaaaaaaa").is_err());
    assert!(check_pass("ключ-флешки").is_ok(), "11 Cyrillic chars count as characters, not bytes");
    assert!(check_pass("абвгд").is_err(), "5 Cyrillic chars = 10 bytes but only 5 characters");
}

#[test]
fn key_names_never_values() {
    assert_eq!(key_names(KEYS), vec!["GEMINI_API_KEY", "GROQ_API_KEY"]);
    assert_eq!(key_names("# only comment\n\n=novalue\n"), Vec::<String>::new());
}

#[test]
fn merge_flash_into_existing_keys() {
    let existing = "# my laptop\nGROQ_API_KEY=old\nLOCAL_ONLY=keep\n";
    let incoming = "GEMINI_API_KEY=new1\nGROQ_API_KEY=new2\n";
    let m = merge_keys(existing, incoming);
    assert_eq!(m, "# my laptop\nGROQ_API_KEY=new2\nLOCAL_ONLY=keep\nGEMINI_API_KEY=new1\n");
    // empty laptop / порожній ноутбук
    assert_eq!(merge_keys("", incoming), "GEMINI_API_KEY=new1\nGROQ_API_KEY=new2\n");
    // merging twice changes nothing / повторне злиття нічого не змінює
    assert_eq!(merge_keys(&m, incoming), m);
}
