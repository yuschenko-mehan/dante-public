//! Specification: swarm security. Only ants and coordinators that share the swarm key can talk; every line is signed,
//! numbered and checked, so a stranger in the network cannot command the ants, change or replay messages.
//! Специфікація: безпека рою. Говорити можуть лише мурахи й координатори зі спільним ключем рою; кожен рядок
//! підписаний, пронумерований і перевірений, тож чужий у мережі не може наказувати мурахам, підмінити чи повторити.
//! (Claude, 20.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! Cargo.toml [dependencies]: hmac = "0.12", sha2 = "0.10", getrandom = "0.2"   (vetted RustCrypto crates —
//! never write your own crypto / перевірені бібліотеки — власної криптографії не писати)
//! src/secure.rs:
//!   pub fn hmac_raw(key: &[u8], parts: &[&str]) -> Vec<u8>   // HMAC-SHA256 over the parts joined by "\n"
//!   pub fn hmac_hex(key: &[u8], parts: &[&str]) -> String    // the same, 64 lower-case hex chars
//!   pub fn new_key() -> String          // 32 random bytes (getrandom) as 64 hex chars
//!   pub fn nonce() -> String            // 16 random bytes as 32 hex chars
//!   pub fn save_key(path: &Path, hex: &str) -> io::Result<()>
//!   pub fn load_key(path: &Path) -> io::Result<Vec<u8>>  // trimmed hex; not exactly 32 bytes -> Err(InvalidData)
//!   pub fn eq_ct(a: &str, b: &str) -> bool               // constant-time compare (different length -> false)
//!   pub fn ant_proof(key: &[u8], nonce_c: &str, nonce_a: &str, ant_id: &str) -> String
//!       = hmac_hex(key, &["ant", nonce_c, nonce_a, ant_id])
//!   pub fn coord_proof(key: &[u8], nonce_c: &str, nonce_a: &str) -> String = hmac_hex(key, &["coord", nonce_a, nonce_c])
//!   pub fn session_key(key: &[u8], nonce_c: &str, nonce_a: &str) -> Vec<u8> = hmac_raw(key, &["session", nonce_c, nonce_a])
//!   pub struct Channel  — one side of a session
//!     pub fn new(session_key: Vec<u8>, is_ant: bool) -> Channel   // ant sends direction "a", coordinator "c"
//!     pub fn seal(&mut self, line: &str) -> String
//!         format "<line>\t#<seq>\t<mac>", seq = 0,1,2.. for this sender, mac = first 32 hex chars of
//!         hmac_hex(session_key, &[my direction, seq as text, line])
//!     pub fn open(&mut self, wire: &str) -> Result<String, String>
//!         trailing "\r\n" ignored; the last two TAB fields are "#<seq>" and mac; seq must equal the next expected seq
//!         from the OTHER side (starting at 0); mac checked with eq_ct for the other side's direction;
//!         any problem -> Err (and the expected seq does not move); Ok(line) -> expected seq + 1.
use murakha::secure::{self as s, Channel};

#[test]
fn hmac_sha256_rfc4231_vector() {
    // RFC 4231 test case 2: key "Jefe", data "what do ya want for nothing?"
    assert_eq!(s::hmac_hex(b"Jefe", &["what do ya want for nothing?"]),
               "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843");
    assert_eq!(s::hmac_hex(b"k", &["a", "b"]), s::hmac_hex(b"k", &["a\nb"]));
    assert_eq!(s::hmac_raw(b"k", &["x"]).len(), 32);
}

#[test]
fn keys_and_nonces() {
    let k = s::new_key();
    assert_eq!(k.len(), 64);
    assert!(k.chars().all(|c| c.is_ascii_hexdigit()));
    assert_ne!(k, s::new_key());
    assert_eq!(s::nonce().len(), 32);
    let dir = std::env::temp_dir().join(format!("murakha-secure-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let p = dir.join("swarm.key");
    s::save_key(&p, &k).unwrap();
    assert_eq!(s::load_key(&p).unwrap().len(), 32);
    std::fs::write(&p, "abcd\n").unwrap();
    assert!(s::load_key(&p).is_err());
    std::fs::write(&p, "zz".repeat(32)).unwrap();
    assert!(s::load_key(&p).is_err());
    assert!(s::eq_ct("abc", "abc") && !s::eq_ct("abc", "abd") && !s::eq_ct("abc", "ab"));
}

#[test]
fn handshake_proofs() {
    let key = [7u8; 32];
    let (nc, na) = (s::nonce(), s::nonce());
    let p = s::ant_proof(&key, &nc, &na, "ant-1");
    assert_eq!(p, s::hmac_hex(&key, &["ant", &nc, &na, "ant-1"]));
    assert_ne!(p, s::ant_proof(&[8u8; 32], &nc, &na, "ant-1"), "a stranger's key gives another proof / чужий ключ");
    assert_ne!(s::coord_proof(&key, &nc, &na), s::ant_proof(&key, &nc, &na, ""));
    assert_eq!(s::session_key(&key, &nc, &na), s::hmac_raw(&key, &["session", &nc, &na]));
}

#[test]
fn channel_signs_numbers_and_rejects_tricks() {
    let sk = s::session_key(&[1u8; 32], "c", "a");
    let mut ant = Channel::new(sk.clone(), true);
    let mut coord = Channel::new(sk.clone(), false);
    let w0 = ant.seal("ASK\tant-1");
    assert!(w0.starts_with("ASK\tant-1\t#0\t"));
    assert_eq!(w0.rsplit('\t').next().unwrap().len(), 32);
    assert_eq!(coord.open(&(w0.clone() + "\r\n")), Ok("ASK\tant-1".to_string()));
    assert!(coord.open(&w0).is_err(), "replay / повтор");
    let w1 = ant.seal("ASK\tant-1");
    let forged = w1.replacen("ASK", "BYE", 1);
    assert!(coord.open(&forged).is_err(), "changed text / змінений текст");
    assert_eq!(coord.open(&w1), Ok("ASK\tant-1".to_string()), "a rejected line does not move the counter");
    let t = coord.seal("TASK\tt1\t60\techo hi");
    assert!(ant.open(&t).is_ok());
    let mut ant2 = Channel::new(sk.clone(), true);
    let own = ant2.seal("RESULT");
    assert!(Channel::new(sk.clone(), true).open(&own).is_err(), "own direction / свій напрямок");
    let mut stranger = Channel::new(s::session_key(&[2u8; 32], "c", "a"), false);
    assert!(stranger.open(&ant.seal("ASK\tant-1")).is_err(), "wrong key / чужий ключ");
    assert!(coord.open("no tabs here").is_err());
    assert!(coord.open("x\t#zz\tabc").is_err());
}
