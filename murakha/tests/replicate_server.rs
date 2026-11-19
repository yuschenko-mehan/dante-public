//! Specification: the coordinator sends the swarm snapshot to new ants (version 0.3 and newer).
//! The snapshot = coordinator + ants in the order they first came + all unfinished tasks.
//! Специфікація: координатор надсилає знімок рою новим мурахам (версії 0.3 і новіші).
//! Знімок = координатор + мурахи в порядку появи + усі незавершені завдання.
//! (Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/server.rs, add:
//!   pub fn wants_snapshots(version: &str) -> bool
//!       true if the leading "major.minor" numbers are >= 0.3 ("0.3.0", "0.10.2", "1.0" -> true;
//!       "0.2.9", "0.1.0", "", "abc" -> false).
//!   impl TaskQueue:
//!     pub fn set_swarm(&self, swarm: &str)        // default "dante"
//!     pub fn set_ant_port(&self, port: u16)       // default 47901: the port an ant would serve on if it takes over
//!     pub fn snapshot_for(&self, coord_addr: &str) -> crate::heal::Snapshot
//!         swarm; peers = ("coord", coord_addr) first, then every ant that sent HELLO, in first-HELLO order,
//!         as (ant id, "<ant's IP as seen by the server>:<ant_port>"); tasks = commands of every unfinished task
//!         (waiting ones and ones given to an ant but without RESULT yet).
//!   Connection rule: an ant whose HELLO version wants_snapshots gets, instead of a task, the line
//!   CoordMessage::Snap { data: hex(heal::encode(&queue.snapshot_for(<this connection's local address>))) }
//!   as the answer to its 1st ASK on that connection, and again to every 20th ASK after it (21st, 41st, ...).
//!   Old ants (or no HELLO) get exactly the old behaviour.
//!   Also: tasks are handed out in the order they were pushed (first pushed = first given).
use murakha::heal;
use murakha::protocol::{hex_decode, CoordMessage};
use murakha::server::{self as srv, Server};
use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::time::Duration;

struct Client { w: TcpStream, r: BufReader<TcpStream> }
impl Client {
    fn new(addr: &str, id: &str, version: &str) -> Client {
        let s = TcpStream::connect(addr).unwrap();
        s.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
        let mut w = s.try_clone().unwrap();
        writeln!(w, "HELLO\t{id}\t4\t{version}").unwrap();
        Client { w, r: BufReader::new(s) }
    }
    fn ask(&mut self, id: &str) -> CoordMessage {
        writeln!(self.w, "ASK\t{id}").unwrap();
        let mut line = String::new();
        self.r.read_line(&mut line).unwrap();
        CoordMessage::parse(&line).unwrap()
    }
}

fn snap_of(m: CoordMessage) -> heal::Snapshot {
    match m { CoordMessage::Snap { data } => heal::decode(&hex_decode(&data).unwrap()).unwrap(), other => panic!("expected SNAP, got {other:?}") }
}

#[test]
fn versions() {
    for v in ["0.3.0", "0.10.2", "1.0", "0.3"] { assert!(srv::wants_snapshots(v), "{v}"); }
    for v in ["0.2.9", "0.1.0", "", "abc", "0"] { assert!(!srv::wants_snapshots(v), "{v}"); }
}

#[test]
fn new_ants_get_the_swarm_snapshot() {
    let server = Server::bind("127.0.0.1:0").unwrap();
    let addr = server.local_addr().to_string();
    let q = server.queue();
    q.set_swarm("kyiv");
    q.set_ant_port(47999);
    q.push("echo one", 60);
    q.push("echo two", 60);
    server.spawn();

    // an old ant: no SNAP, tasks in push order / стара мураха: без SNAP, завдання по черзі
    let mut old = Client::new(&addr, "old-ant", "0.1.0");
    match old.ask("old-ant") { CoordMessage::Task { command, .. } => assert_eq!(command, "echo one"), o => panic!("{o:?}") }

    // a new ant: first answer is the snapshot / нова мураха: першою отримує знімок
    let mut new = Client::new(&addr, "new-ant", "0.3.0");
    let s = snap_of(new.ask("new-ant"));
    assert_eq!(s.swarm, "kyiv");
    assert_eq!(s.peers[0], ("coord".to_string(), addr.clone()));
    assert_eq!(&s.peers[1..], &[("old-ant".to_string(), "127.0.0.1:47999".to_string()), ("new-ant".to_string(), "127.0.0.1:47999".to_string())]);
    let mut tasks = s.tasks.clone();
    tasks.sort();
    assert_eq!(tasks, vec!["echo one".to_string(), "echo two".to_string()]); // "echo one" is given but unfinished / видане, але не завершене
    match new.ask("new-ant") { CoordMessage::Task { command, .. } => assert_eq!(command, "echo two"), o => panic!("{o:?}") }
    // 2nd..20th ASK: no snapshot; 21st: snapshot again / з 2-го по 20-й — без знімка; 21-й — знову знімок
    for _ in 3..=20 { assert!(matches!(new.ask("new-ant"), CoordMessage::Wait { .. })); }
    let again = snap_of(new.ask("new-ant"));
    assert_eq!(again.swarm, "kyiv");
    assert_eq!(q.snapshot_for("1.2.3.4:5").peers[0], ("coord".to_string(), "1.2.3.4:5".to_string()));
}
