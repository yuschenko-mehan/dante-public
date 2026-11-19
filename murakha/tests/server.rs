//! Specification: the REAL coordinator (Claude, 19.11.2026). Do not edit — DANTE makes it pass.
//! Специфікація: СПРАВЖНІЙ координатор. Не змінювати — Данте має її пройти.
//!
//! src/server.rs, std only, uses crate::protocol for every line / для кожного рядка — crate::protocol:
//!   pub struct TaskResult { pub task_id: String, pub ant_id: String, pub exit_code: i32, pub output: String }
//!       (output = hex-decoded text; Clone + Debug)
//!   #[derive(Clone)] pub struct TaskQueue — shared handle (Arc inside):
//!       push(&self, command: &str, timeout_s: u64) -> String   // new unique task id, e.g. "t1", "t2", ...
//!       pending(&self) -> usize      // tasks waiting to be given out
//!       results(&self) -> Vec<TaskResult>
//!       ants(&self) -> Vec<String>   // ids that said HELLO
//!   pub struct Server; Server::bind(addr: &str) -> io::Result<Server>; local_addr(&self) -> SocketAddr;
//!       queue(&self) -> TaskQueue; spawn(self) -> JoinHandle<()>  (accept loop in a background thread)
//!   Behaviour / Поведінка:
//!     HELLO -> remember the ant; ASK -> "TASK\t<id>\t<timeout>\t<cmd>" if a task waits, else "WAIT\t<seconds>" (1..=10);
//!     RESULT -> store; BEAT -> ok; unknown or broken lines are ignored (never panic, keep the connection);
//!     a task given to an ant that disconnects WITHOUT a RESULT goes back to the queue (not lost);
//!     every connection has read/write timeouts; many ants at the same time must work (one thread per connection is fine).
use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::thread;
use std::time::{Duration, Instant};

use murakha::{ant, server};

fn wait_until(mut f: impl FnMut() -> bool, secs: u64) -> bool {
    let end = Instant::now() + Duration::from_secs(secs);
    while Instant::now() < end {
        if f() { return true; }
        thread::sleep(Duration::from_millis(20));
    }
    f()
}

#[test]
fn three_ants_do_three_tasks() {
    let srv = server::Server::bind("127.0.0.1:0").unwrap();
    let addr = srv.local_addr().to_string();
    let q = srv.queue();
    let ids: Vec<String> = (1..=3).map(|i| q.push(&format!("echo hello{}", i), 10)).collect();
    assert_eq!(q.pending(), 3);
    let ids_set: std::collections::HashSet<_> = ids.iter().cloned().collect();
    assert_eq!(ids_set.len(), 3, "task ids must be unique");
    srv.spawn();
    let hs: Vec<_> = (0..3).map(|i| { let a = addr.clone();
        thread::spawn(move || ant::run_session_timeout(&a, &format!("ant-{}", i), true, Duration::from_secs(10))) }).collect();
    for h in hs { let _ = h.join(); }
    assert!(wait_until(|| q.results().len() == 3, 5), "results: {:?}", q.results());
    let res = q.results();
    for i in 1..=3 {
        assert!(res.iter().any(|r| r.output.contains(&format!("hello{}", i)) && r.exit_code == 0), "{:?}", res);
    }
    assert_eq!(q.pending(), 0);
    assert_eq!(q.ants().len(), 3);
}

#[test]
fn real_exit_code_is_stored() {
    let srv = server::Server::bind("127.0.0.1:0").unwrap();
    let addr = srv.local_addr().to_string();
    let q = srv.queue();
    let id = q.push("exit 4", 10);
    srv.spawn();
    let _ = ant::run_session_timeout(&addr, "ant-e", true, Duration::from_secs(10));
    assert!(wait_until(|| q.results().len() == 1, 5));
    let r = &q.results()[0];
    assert_eq!((r.task_id.as_str(), r.ant_id.as_str(), r.exit_code), (id.as_str(), "ant-e", 4));
}

fn raw(addr: &str) -> (TcpStream, BufReader<TcpStream>) {
    let s = TcpStream::connect(addr).unwrap();
    s.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
    let r = BufReader::new(s.try_clone().unwrap());
    (s, r)
}

#[test]
fn empty_queue_says_wait_and_garbage_is_ignored() {
    let srv = server::Server::bind("127.0.0.1:0").unwrap();
    let addr = srv.local_addr().to_string();
    srv.spawn();
    let (mut s, mut r) = raw(&addr);
    s.write_all(b"\xff\xfe junk\nHELLO\tant-g\t4\t0.1.0\nRESULT\tbroken\nASK\tant-g\n").unwrap();
    let mut line = String::new();
    r.read_line(&mut line).unwrap();
    let parts: Vec<&str> = line.trim_end().split('\t').collect();
    assert_eq!(parts[0], "WAIT", "got {:?}", line);
    let secs: u64 = parts[1].parse().unwrap();
    assert!((1..=10).contains(&secs));
}

#[test]
fn task_of_a_vanished_ant_comes_back() {
    let srv = server::Server::bind("127.0.0.1:0").unwrap();
    let addr = srv.local_addr().to_string();
    let q = srv.queue();
    q.push("echo again", 10);
    srv.spawn();
    {
        let (mut s, mut r) = raw(&addr);
        s.write_all(b"HELLO\tant-v\t1\t0.1.0\nASK\tant-v\n").unwrap();
        let mut line = String::new();
        r.read_line(&mut line).unwrap();
        assert!(line.starts_with("TASK"), "{:?}", line);
        assert_eq!(q.pending(), 0);
    } // disconnects without RESULT / зникає без RESULT
    assert!(wait_until(|| q.pending() == 1, 5), "task was lost");
    let _ = ant::run_session_timeout(&addr, "ant-w", true, Duration::from_secs(10));
    assert!(wait_until(|| q.results().len() == 1, 5));
    assert!(q.results()[0].output.contains("again"));
}

#[test]
fn two_hundred_ants_at_once() {
    let srv = server::Server::bind("127.0.0.1:0").unwrap();
    let addr = srv.local_addr().to_string();
    let q = srv.queue();
    for i in 0..200 { q.push(&format!("echo n{}", i), 20); }
    srv.spawn();
    let t = Instant::now();
    let hs: Vec<_> = (0..200).map(|i| { let a = addr.clone();
        thread::spawn(move || ant::run_session_timeout(&a, &format!("ant-{}", i), true, Duration::from_secs(20))) }).collect();
    for h in hs { let _ = h.join(); }
    assert!(wait_until(|| q.results().len() == 200, 10), "only {} results", q.results().len());
    assert!(t.elapsed() < Duration::from_secs(40));
    let mut outs: Vec<String> = q.results().iter().map(|r| r.output.trim().to_string()).collect();
    outs.sort(); outs.dedup();
    assert_eq!(outs.len(), 200, "every task done exactly once");
}
