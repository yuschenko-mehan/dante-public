//! Specification: the HEART of DANTE — the whole program packed into one checked bundle, so any ant can
//! bring DANTE back if the main PC is destroyed. Secrets (keys) are NEVER packed.
//! Специфікація: СЕРЦЕ Данте — уся програма в одному перевіреному пакеті, щоб будь-яка мураха могла
//! повернути Данте, якщо головний ПК знищено. Секрети (ключі) НІКОЛИ не пакуються.
//! (Claude, 20.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/heart.rs (std only; uses crate::survive::checksum):
//!   pub const MAGIC: &[u8] = b"DANTE-HEART-1\n";
//!   pub const MAX_BYTES: usize = 64 * 1024 * 1024;
//!   pub fn wanted(rel: &str) -> bool        // rel uses '/' separators
//!       false if any path part is ".git", "__pycache__", "audit", "outbox", "inbox", "target", "graphify-out",
//!             "update-backup", "kopiya-roju", "node_modules" or starts with "." (hidden);
//!       false (NEVER packed) if the file name, lower-cased, is "keys.txt", ".env", "credentials.json", "update.json",
//!             or ends with ".key", ".pem" or ".log";
//!       otherwise true only for extensions py, json, toml, md, txt, bat, cmd, ps1, rs, ttf, otf, png (lower-case compare).
//!   pub fn pack(root: &Path) -> io::Result<Vec<u8>>
//!       MAGIC, then for every wanted file under root (sorted by rel path): "F\t<rel>\t<len>\n" + bytes + "\n",
//!       then "END\t<16 lower-case hex digits of survive::checksum(everything before this line)>\n".
//!       Total > MAX_BYTES -> Err(InvalidData).
//!   pub fn list(bundle: &[u8]) -> Result<Vec<(String, usize)>, String>   // checks MAGIC, structure and checksum
//!   pub fn unpack(bundle: &[u8], dest: &Path) -> io::Result<usize>
//!       list() first (any problem -> Err(InvalidData), nothing written); a path that is absolute, has a drive letter
//!       (second char ':'), a backslash, or a ".." part -> Err(InvalidData), nothing written. Writes all files, returns count.
//!   pub fn chunks(bundle: &[u8], size: usize) -> Vec<Vec<u8>>   // size 0 -> one chunk; empty bundle -> one empty chunk
//!   pub struct Assembler   // collects chunks that may arrive in any order
//!     pub fn new(total: usize) -> Assembler
//!     pub fn add(&mut self, index: usize, data: Vec<u8>) -> bool   // index >= total -> ignored, false; true when all present
//!     pub fn finish(&self) -> Option<Vec<u8>>                       // all chunks joined, None if any is missing
use murakha::heart::{self as h, Assembler};
use std::fs;
use std::path::PathBuf;

fn tmp(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("murakha-heart-{}-{}", name, std::process::id()));
    let _ = fs::remove_dir_all(&d);
    fs::create_dir_all(&d).unwrap();
    d
}

fn make_dante(root: &PathBuf) {
    for (p, c) in [
        ("dante/__init__.py", "__build__ = \"x\"\n"), ("dante/cli.py", "print('cli')\n"), ("lessons.json", "[]"),
        ("dante.toml", "max_tokens = 8192\n"), ("Dante.bat", "@echo off\r\n"), ("fonts/a.ttf", "FONT"),
        ("keys.txt", "GEMINI_API_KEY=SECRET"), ("sub/.env", "X=1"), ("outbox/pult.log", "log"), ("audit/a.jsonl", "{}"),
        (".git/config", "[core]"), ("dante/__pycache__/cli.cpython-313.pyc", "bin"), ("big.mp4", "video"),
        ("server.KEY", "k"), ("update.json", "{}"), ("graphify-out/graph.json", "{}"),
    ] {
        let f = root.join(p);
        fs::create_dir_all(f.parent().unwrap()).unwrap();
        fs::write(f, c).unwrap();
    }
}

#[test]
fn wanted_rules() {
    for ok in ["dante/cli.py", "lessons.json", "fonts/a.TTF", "murakha/src/main.rs", "Dante.bat", "docs/README.md"] {
        assert!(h::wanted(ok), "{ok}");
    }
    for no in ["keys.txt", "KEYS.TXT", "a/.env", "credentials.json", "x.pem", "s.key", "outbox/x.txt", "audit/a.json",
               ".git/config", "a/__pycache__/b.py", "target/x.rs", "graphify-out/graph.json", "pult.log", "v.mp4", ".hidden/a.py",
               "update-backup/1/a.py", "kopiya-roju/x.txt", "node_modules/a.json", "update.json"] {
        assert!(!h::wanted(no), "{no}");
    }
}

#[test]
fn pack_list_unpack_roundtrip_without_secrets() {
    let src = tmp("src");
    make_dante(&src);
    let b = h::pack(&src).unwrap();
    assert!(b.starts_with(h::MAGIC));
    let names: Vec<String> = h::list(&b).unwrap().into_iter().map(|(n, _)| n).collect();
    assert_eq!(names, vec!["Dante.bat", "dante.toml", "dante/__init__.py", "dante/cli.py", "fonts/a.ttf", "lessons.json"]);
    let text = String::from_utf8_lossy(&b);
    assert!(!text.contains("SECRET"), "keys must never be packed / ключі ніколи не пакуються");
    let dst = tmp("dst");
    assert_eq!(h::unpack(&b, &dst).unwrap(), 6);
    assert_eq!(fs::read_to_string(dst.join("dante/cli.py")).unwrap(), "print('cli')\n");
    assert_eq!(fs::read(dst.join("Dante.bat")).unwrap(), b"@echo off\r\n");
    assert!(!dst.join("keys.txt").exists());
}

#[test]
fn damaged_or_evil_bundles_write_nothing() {
    let src = tmp("src2");
    make_dante(&src);
    let mut b = h::pack(&src).unwrap();
    let mid = b.len() / 2;
    b[mid] ^= 0x55;
    assert!(h::list(&b).is_err());
    let dst = tmp("dst2");
    assert!(h::unpack(&b, &dst).is_err());
    assert_eq!(fs::read_dir(&dst).unwrap().count(), 0);
    assert!(h::list(b"not a heart").is_err());
    // hand-made bundle with a path escape / пакет з утечею шляху
    for evil in ["../evil.py", "C:/win.py", "/abs.py", "a\\b.py"] {
        let mut body = h::MAGIC.to_vec();
        body.extend_from_slice(format!("F\tok.py\t1\nx\nF\t{evil}\t1\ny\n").as_bytes());
        let sum = murakha::survive::checksum(&body);
        body.extend_from_slice(format!("END\t{:016x}\n", sum).as_bytes());
        assert!(h::unpack(&body, &dst).is_err(), "{evil}");
        assert!(!dst.join("ok.py").exists(), "{evil}");
    }
}

#[test]
fn chunks_and_assembler() {
    let data: Vec<u8> = (0..1000u32).map(|i| (i % 251) as u8).collect();
    let parts = h::chunks(&data, 300);
    assert_eq!(parts.len(), 4);
    assert_eq!(parts[3].len(), 100);
    let mut a = Assembler::new(parts.len());
    assert!(!a.add(9, vec![1]));
    for i in [2usize, 0, 3] { assert!(!a.add(i, parts[i].clone())); }
    assert_eq!(a.finish(), None);
    assert!(a.add(1, parts[1].clone()));
    assert_eq!(a.finish().unwrap(), data);
    assert_eq!(h::chunks(&data, 0).len(), 1);
    assert_eq!(h::chunks(&[], 10), vec![Vec::<u8>::new()]);
}
