//! Specification: a piece of DANTE lives in every ant — keeps snapshots and takes over if the coordinator is gone.
//! Специфікація: частинка Данте в кожній Мурасі — зберігає копії й підхоплює роботу, якщо координатора не стало.
//! (Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/survive.rs (std only):
//!   pub fn checksum(data: &[u8]) -> u64             // FNV-1a 64-bit (offset 0xcbf29ce484222325, prime 0x100000001b3)
//!   pub fn store(dir: &Path, data: &[u8], keep: usize) -> io::Result<PathBuf>
//!       creates dir; writes "snapshot-<unix millis, 15 digits zero-padded>-<counter, 6 digits>.bin" atomically
//!       (write "<name>.tmp", then rename); file = 8 bytes checksum (little-endian) + data;
//!       then deletes the oldest snapshots so that at most `keep` remain (keep 0 counts as 1); returns the new path
//!   pub fn list(dir: &Path) -> Vec<PathBuf>       // snapshot-*.bin only, oldest first (by file name); missing dir -> []
//!   pub fn load(path: &Path) -> io::Result<Vec<u8>>  // checks the checksum; wrong or too short -> ErrorKind::InvalidData
//!   pub fn latest(dir: &Path) -> Option<Vec<u8>>  // data of the newest snapshot that loads correctly (skips broken ones)
//!   pub fn should_take_over(now_s: u64, last_seen_s: Option<u64>, silence_limit_s: u64) -> bool
//!       false if the coordinator was never seen (None); true only if now_s - last_seen_s > silence_limit_s
//!   pub fn successor(priority: &[String], alive: &[String]) -> Option<String>
//!       the first id in `priority` that is alive; else the alphabetically smallest alive id; None if nobody is alive
use std::fs;
use murakha::survive as s;

fn tmpdir(name: &str) -> std::path::PathBuf {
    let d = std::env::temp_dir().join(format!("murakha-survive-{}-{}", name, std::process::id()));
    let _ = fs::remove_dir_all(&d);
    d
}

#[test]
fn checksum_is_fnv1a() {
    assert_eq!(s::checksum(b""), 0xcbf29ce484222325);
    assert_eq!(s::checksum(b"a"), 0xaf63dc4c8601ec8c);
    assert_ne!(s::checksum(b"dante"), s::checksum(b"dantf"));
}

#[test]
fn keeps_only_newest_and_restores() {
    let d = tmpdir("keep");
    for i in 0..4u8 {
        s::store(&d.join("snaps"), &[i; 10], 2).unwrap();
    }
    let l = s::list(&d.join("snaps"));
    assert_eq!(l.len(), 2);
    assert_eq!(s::load(&l[1]).unwrap(), vec![3u8; 10]);
    assert_eq!(s::latest(&d.join("snaps")), Some(vec![3u8; 10]));
    assert!(fs::read_dir(d.join("snaps")).unwrap().all(|e| !e.unwrap().file_name().to_string_lossy().ends_with(".tmp")));
    let _ = fs::remove_dir_all(&d);
}

#[test]
fn broken_snapshot_is_detected_and_skipped() {
    let d = tmpdir("broken");
    s::store(&d, b"good old copy", 5).unwrap();
    let newest = s::store(&d, b"newest copy", 5).unwrap();
    let mut bytes = fs::read(&newest).unwrap();
    let last = bytes.len() - 1;
    bytes[last] ^= 0xff;
    fs::write(&newest, &bytes).unwrap();
    assert_eq!(s::load(&newest).unwrap_err().kind(), std::io::ErrorKind::InvalidData);
    assert_eq!(s::latest(&d), Some(b"good old copy".to_vec()));
    fs::write(&newest, b"short").unwrap();
    assert_eq!(s::load(&newest).unwrap_err().kind(), std::io::ErrorKind::InvalidData);
    assert!(s::list(&d.join("missing")).is_empty());
    assert_eq!(s::latest(&d.join("missing")), None);
    let _ = fs::remove_dir_all(&d);
}

#[test]
fn keep_zero_counts_as_one() {
    let d = tmpdir("zero");
    s::store(&d, b"a", 0).unwrap();
    s::store(&d, b"b", 0).unwrap();
    assert_eq!(s::list(&d).len(), 1);
    let _ = fs::remove_dir_all(&d);
}

#[test]
fn take_over_rules() {
    assert!(!s::should_take_over(10_000, None, 600));
    assert!(!s::should_take_over(10_000, Some(9_500), 600));
    assert!(!s::should_take_over(10_000, Some(9_400), 600));
    assert!(s::should_take_over(10_000, Some(9_399), 600));
    assert!(!s::should_take_over(100, Some(200), 600)); // clock went back: never panic
}

#[test]
fn successor_rules() {
    let p = |v: &[&str]| v.iter().map(|x| x.to_string()).collect::<Vec<_>>();
    assert_eq!(s::successor(&p(&["laptop", "phone"]), &p(&["phone", "laptop", "pc2"])), Some("laptop".into()));
    assert_eq!(s::successor(&p(&["laptop", "phone"]), &p(&["phone", "pc2"])), Some("phone".into()));
    assert_eq!(s::successor(&p(&["laptop"]), &p(&["zeta", "alpha"])), Some("alpha".into()));
    assert_eq!(s::successor(&p(&["laptop"]), &[]), None);
}
