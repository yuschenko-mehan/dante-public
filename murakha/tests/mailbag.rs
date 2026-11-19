//! Specification: the ant's mail bag. Results and checkpoints are kept on disk, so a power cut or
//! lost internet does not lose work; they are delivered when the link is back.
//! Специфікація: торба мурахи. Результати й контрольні точки лежать на диску, тож вимкнення світла
//! чи втрата інтернету не губить роботу; їх доставлять, коли зв'язок повернеться.
//! (Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/mailbag.rs (std only):
//!   pub fn safe_id(task_id: &str) -> String
//!       keeps ASCII letters, digits, '-' and '_'; every other char becomes '_'; empty -> "_".
//!   pub fn put(dir: &Path, task_id: &str, data: &[u8]) -> io::Result<PathBuf>
//!       creates dir; writes "<safe_id>.res" atomically (write "<name>.tmp", then rename); overwrites; returns the path
//!   pub fn pending(dir: &Path) -> Vec<String>     // safe ids of all *.res files, sorted; missing dir -> []
//!   pub fn get(dir: &Path, task_id: &str) -> io::Result<Vec<u8>>
//!   pub fn done(dir: &Path, task_id: &str) -> io::Result<()>     // removes the result; already missing -> Ok
//!   pub fn save_checkpoint(dir: &Path, task_id: &str, data: &[u8]) -> io::Result<()>   // "<safe_id>.ckpt", atomic
//!   pub fn load_checkpoint(dir: &Path, task_id: &str) -> Option<Vec<u8>>
//!   pub fn drop_checkpoint(dir: &Path, task_id: &str)        // never fails, never panics
use murakha::mailbag as m;
use std::fs;

fn tmpdir(name: &str) -> std::path::PathBuf {
    let d = std::env::temp_dir().join(format!("murakha-mailbag-{}-{}", name, std::process::id()));
    let _ = fs::remove_dir_all(&d);
    d
}

#[test]
fn safe_ids() {
    assert_eq!(m::safe_id("t-1_A"), "t-1_A");
    assert_eq!(m::safe_id("../x y"), "___x_y");
    assert_eq!(m::safe_id(""), "_");
    assert_eq!(m::safe_id("ї"), "_");
}

#[test]
fn results_survive_and_are_delivered_once() {
    let d = tmpdir("res");
    assert_eq!(m::pending(&d), Vec::<String>::new());
    let p = m::put(&d, "t2", b"two").unwrap();
    assert!(p.starts_with(&d) && p.ends_with("t2.res"));
    m::put(&d, "t1", b"one").unwrap();
    m::put(&d, "t1", b"ONE").unwrap();
    assert_eq!(m::pending(&d), vec!["t1".to_string(), "t2".to_string()]);
    assert_eq!(m::get(&d, "t1").unwrap(), b"ONE");
    m::done(&d, "t1").unwrap();
    m::done(&d, "t1").unwrap();
    assert_eq!(m::pending(&d), vec!["t2".to_string()]);
    let leftovers: Vec<_> = fs::read_dir(&d).unwrap().flatten().filter(|e| e.path().extension().map_or(false, |x| x == "tmp")).collect();
    assert!(leftovers.is_empty());
    // no escape from the folder / не виходить за межі теки
    let esc = m::put(&d, "../evil", b"x").unwrap();
    assert!(esc.starts_with(&d));
    let _ = fs::remove_dir_all(&d);
}

#[test]
fn checkpoints() {
    let d = tmpdir("ckpt");
    assert_eq!(m::load_checkpoint(&d, "job"), None);
    m::drop_checkpoint(&d, "job");
    m::save_checkpoint(&d, "job", b"step 1").unwrap();
    m::save_checkpoint(&d, "job", b"step 2").unwrap();
    assert_eq!(m::load_checkpoint(&d, "job"), Some(b"step 2".to_vec()));
    assert_eq!(m::pending(&d), Vec::<String>::new()); // checkpoints are not results / точки — не результати
    m::drop_checkpoint(&d, "job");
    assert_eq!(m::load_checkpoint(&d, "job"), None);
    let _ = fs::remove_dir_all(&d);
}
