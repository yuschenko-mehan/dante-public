//! Specification: the swarm key in real connections. A coordinator and ants with the same key prove themselves to
//! each other (challenge-response), then every line is signed and numbered. An ant with a key NEVER runs a command
//! from a coordinator that did not prove itself.
//! Специфікація: ключ рою в справжніх з'єднаннях. Координатор і мурахи зі спільним ключем доводять одне одному, хто
//! вони (виклик-відповідь), далі кожен рядок підписаний і пронумерований. Мураха з ключем НІКОЛИ не виконає команду
//! від координатора, який не довів себе.
//! (Claude, 20.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! Handshake (after the plain HELLO line): coordinator -> "CHAL\t<nonce_c>"; ant -> "AUTH\t<nonce_a>\t<ant_proof>";
//! coordinator checks secure::ant_proof(key, nonce_c, nonce_a, ant_id from HELLO) with eq_ct:
//!   good -> "AUTH\t<coord_proof(key, nonce_c, nonce_a)>", then both sides use secure::Channel with
//!           session_key(key, nonce_c, nonce_a) (ant: is_ant = true) for EVERY following line (seal / open);
//!   bad  -> "BYE" and the connection is closed. A line that fails Channel::open closes the connection.
//! src/server.rs: TaskQueue::set_swarm_key(&self, key: Vec<u8>) — when set, every connection must pass the handshake.
//! src/ant.rs: pub fn run_session_secure(coordinator_addr, ant_id, once, io_timeout, snap_dir: Option<&Path>,
//!     key: Option<&[u8]>) -> io::Result<()>; run_session_snap(..) = run_session_secure(.., None).
//!     With a key: after HELLO the next line must be "CHAL\t.."; anything else -> Err(PermissionDenied) and nothing
//!     is executed; a wrong coordinator proof -> Err(PermissionDenied); a line that fails open -> Err(InvalidData).
//! src/main.rs: `murakha --new-swarm-key FILE` writes secure::new_key() to FILE (exit 0);
//!     serve mode `--key FILE` -> queue.set_swarm_key(secure::load_key(FILE)); ant mode `--key FILE` -> secure sessions.
use murakha::server::Server;
use murakha::{ant, secure};
use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::path::PathBuf;
use std::time::Duration;

fn tmp(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("murakha-snet-{}-{}", name, std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    std::fs::create_dir_all(&d).unwrap();
    d
}
fn touch_cmd(p: &PathBuf) -> String {
    if cfg!(windows) { format!("echo x > \"{}\"", p.display()) } else { format!("echo x > '{}'", p.display()) }
}

#[test]
fn same_key_works() {
    let key = [5u8; 32];
    let server = Server::bind("127.0.0.1:0").unwrap();
    let addr = server.local_addr().to_string();
    let q = server.queue();
    q.set_swarm_key(key.to_vec());
    q.push("echo secure-ok", 30);
    server.spawn();
    ant::run_session_secure(&addr, "ant-k", true, Duration::from_secs(10), None, Some(&key)).unwrap();
    let t0 = std::time::Instant::now();
    while q.results().is_empty() && t0.elapsed() < Duration::from_secs(5) { std::thread::sleep(Duration::from_millis(50)); }
    let r = q.results();
    assert_eq!(r.len(), 1);
    assert!(r[0].output.contains("secure-ok"));
}

#[test]
fn ant_refuses_unproven_coordinator() {
    let dir = tmp("fake");
    let marker = dir.join("pwned.txt");
    let l = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = l.local_addr().unwrap().to_string();
    let cmd = touch_cmd(&marker);
    let h = std::thread::spawn(move || {
        let (s, _) = l.accept().unwrap();
        let mut w = s.try_clone().unwrap();
        let mut r = BufReader::new(s);
        let mut line = String::new();
        r.read_line(&mut line).unwrap(); // HELLO
        let _ = writeln!(w, "TASK\tt1\t10\t{cmd}");
        let _ = r.read_line(&mut line);
    });
    let res = ant::run_session_secure(&addr, "ant-k", true, Duration::from_secs(5), None, Some(&[5u8; 32]));
    assert_eq!(res.unwrap_err().kind(), std::io::ErrorKind::PermissionDenied);
    let _ = h.join();
    assert!(!marker.exists(), "a command from a stranger must never run / команда чужого ніколи не виконується");
}

#[test]
fn wrong_key_or_no_key_gets_no_task() {
    let server = Server::bind("127.0.0.1:0").unwrap();
    let addr = server.local_addr().to_string();
    let q = server.queue();
    q.set_swarm_key(vec![5u8; 32]);
    q.push("echo never", 30);
    server.spawn();
    let res = ant::run_session_secure(&addr, "intruder", true, Duration::from_secs(5), None, Some(&[9u8; 32]));
    assert!(res.is_err());
    let _ = ant::run_session_timeout(&addr, "old-ant", true, Duration::from_secs(3));
    std::thread::sleep(Duration::from_millis(300));
    assert_eq!(q.pending(), 1, "nobody without the key gets work / без ключа роботи немає");
    assert!(q.results().is_empty());
}

#[test]
fn cli_makes_a_swarm_key() {
    let exe = env!("CARGO_BIN_EXE_murakha");
    let f = tmp("cli").join("swarm.key");
    let st = std::process::Command::new(exe).args(["--new-swarm-key", f.to_str().unwrap()])
        .stdout(std::process::Stdio::null()).status().unwrap();
    assert!(st.success());
    assert_eq!(secure::load_key(&f).unwrap().len(), 32);
}
