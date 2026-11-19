//! Specification: `murakha --serve` — one command starts a coordinator that ants find by themselves (Claude, 19.11.2026).
//! Специфікація: одна команда запускає координатора, якого Мурахи знаходять самі. Не змінювати — Данте має пройти.
//!
//! src/serve.rs (std only; uses crate::server and crate::discovery):
//!   pub fn load_tasks(text: &str) -> Vec<String>   // one command per line; trimmed; empty lines and lines starting with '#' skipped
//!   pub struct Serving { pub addr: SocketAddr, pub discovery_addr: Option<SocketAddr>, pub queue: crate::server::TaskQueue }
//!   pub fn start(bind: &str, swarm: &str, tasks: &[String], discovery_bind: Option<&str>) -> io::Result<Serving>
//!       binds the coordinator (crate::server::Server) on `bind`, pushes every task (timeout 600 s), spawns it;
//!       if discovery_bind is Some, starts crate::discovery::spawn_responder(discovery_bind, swarm, addr.port());
//!       returns at once (everything runs in background threads)
//! src/main.rs: `murakha --serve PORT [--swarm ID] [--tasks FILE]` -> start("0.0.0.0:PORT", swarm, tasks,
//!       Some("0.0.0.0:47900")), print address and progress (English + Ukrainian), print each result as it arrives, run until closed.
use std::time::{Duration, Instant};

use murakha::{ant, discovery, serve};

#[test]
fn tasks_file_format() {
    let t = "# my tasks\n echo one \n\n#skip\necho two\n   \n";
    assert_eq!(serve::load_tasks(t), vec!["echo one".to_string(), "echo two".to_string()]);
    assert!(serve::load_tasks("").is_empty());
}

#[test]
fn ants_find_and_finish_the_work() {
    let tasks = vec!["echo first".to_string(), "echo second".to_string()];
    let s = serve::start("127.0.0.1:0", "test-swarm", &tasks, Some("127.0.0.1:0")).unwrap();
    let d = s.discovery_addr.expect("discovery must run");
    let found = discovery::discover("test-swarm", &[d], Duration::from_secs(3)).unwrap();
    assert_eq!(found, Some(s.addr), "ants must find the coordinator");
    assert_eq!(discovery::discover("other", &[d], Duration::from_millis(500)).unwrap(), None);
    let a = s.addr.to_string();
    for i in 0..2 {
        let _ = ant::run_session_timeout(&a, &format!("ant-{}", i), true, Duration::from_secs(10));
    }
    let end = Instant::now() + Duration::from_secs(5);
    while s.queue.results().len() < 2 && Instant::now() < end {
        std::thread::sleep(Duration::from_millis(20));
    }
    let outs: Vec<String> = s.queue.results().iter().map(|r| r.output.trim().to_string()).collect();
    assert!(outs.contains(&"first".to_string()) && outs.contains(&"second".to_string()), "{:?}", outs);
}

#[test]
fn without_discovery() {
    let s = serve::start("127.0.0.1:0", "x", &[], None).unwrap();
    assert!(s.discovery_addr.is_none());
    assert_eq!(s.queue.pending(), 0);
}
