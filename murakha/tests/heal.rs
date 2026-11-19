//! Specification: self-healing swarm. Every ant keeps a snapshot of the swarm (peers in priority order + tasks).
//! If the coordinator is gone (missile, power cut), the next ant in priority becomes the coordinator
//! from the snapshot, and the other ants find it and follow it. Never two leaders: a peer that answers always wins.
//! Специфікація: самовідновний мурашник. Кожна мураха тримає знімок рою (учасники за пріоритетом + завдання).
//! Якщо координатора не стало (ракета, світло), наступна за пріоритетом мураха стає координатором зі знімка,
//! а інші її знаходять і йдуть за нею. Ніколи двох ватажків: той, хто відповідає, завжди перемагає.
//! (Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/heal.rs (std only; uses crate::survive, crate::scout, crate::serve):
//!   #[derive(Debug, Clone, PartialEq, Eq)]
//!   pub struct Snapshot { pub swarm: String, pub peers: Vec<(String, String)>, pub tasks: Vec<String> }
//!       peers = (id, "host:port") in priority order (the old coordinator usually first).
//!   pub fn encode(s: &Snapshot) -> Vec<u8>
//!       UTF-8 lines joined by '\n': "SWARM\t<swarm>", then "PEER\t<id>\t<addr>" for each peer, then "TASK\t<command>" for each task.
//!   pub fn decode(data: &[u8]) -> Option<Snapshot>
//!       the inverse. Invalid UTF-8 or no SWARM line -> None. Unknown or broken lines are skipped.
//!       A TASK command is everything after the first TAB (it may contain TABs itself).
//!   #[derive(Debug, Clone, PartialEq, Eq)] pub enum Choice { Follow(String), TakeOver, Wait }
//!   pub fn choose(me: &str, peers: &[(String, String)], answering: &[bool], round: u32) -> Choice
//!       answering[i] = did peers[i] answer (missing entries = false). The first peer that is not me and answered
//!       -> Follow(its addr). Else, if me is not in peers -> Wait. Else rank = my index in peers:
//!       round >= rank -> TakeOver, otherwise Wait (higher-priority peers get time to come back first).
//!   pub struct HealCfg { pub me: String, pub snap_dir: PathBuf, pub probe_timeout: Duration, pub round_pause: Duration, pub max_rounds: u32 }
//!   pub enum Healed { Follow(String), Leader(crate::serve::Serving), GaveUp }
//!   pub fn heal(cfg: &HealCfg) -> io::Result<Healed>
//!       snapshot = survive::latest(snap_dir) decoded; missing or broken -> Ok(GaveUp).
//!       For round in 0..max_rounds: probe every peer addr with scout::tcp_probe(addr, probe_timeout)
//!       (my own entry is not probed, it counts as false); then choose():
//!         Follow(a) -> Ok(Follow(a)); TakeOver -> serve::start(my addr, swarm, tasks, None) -> Ok(Leader(serving));
//!         Wait -> sleep round_pause. After max_rounds -> Ok(GaveUp).
use murakha::heal::{self as h, Choice, HealCfg, Healed, Snapshot};
use murakha::{ant, survive};
use std::net::TcpListener;
use std::time::Duration;

fn free_addr() -> String {
    let l = TcpListener::bind("127.0.0.1:0").unwrap();
    l.local_addr().unwrap().to_string()
}
fn p(x: &[(&str, &str)]) -> Vec<(String, String)> { x.iter().map(|(a, b)| (a.to_string(), b.to_string())).collect() }

#[test]
fn snapshot_roundtrip() {
    let s = Snapshot { swarm: "dante".into(), peers: p(&[("coord", "10.0.0.1:47901"), ("ant-a", "10.0.0.2:47901")]), tasks: vec!["echo a\tb".into(), "cargo test".into()] };
    let bytes = h::encode(&s);
    assert!(String::from_utf8(bytes.clone()).unwrap().starts_with("SWARM\tdante\n"));
    assert_eq!(h::decode(&bytes), Some(s));
    assert_eq!(h::decode(b"PEER\tx\ty"), None);
    assert_eq!(h::decode(&[0xff, 0xfe]), None);
    let d = h::decode(b"SWARM\tz\nJUNK\nPEER\tonly-id\nTASK\tls").unwrap();
    assert_eq!(d, Snapshot { swarm: "z".into(), peers: vec![], tasks: vec!["ls".into()] });
}

#[test]
fn choose_rules() {
    let peers = p(&[("coord", "c:1"), ("a", "a:1"), ("b", "b:1")]);
    assert_eq!(h::choose("b", &peers, &[false, true, false], 0), Choice::Follow("a:1".into()));
    assert_eq!(h::choose("a", &peers, &[false, true, true], 9), Choice::Follow("b:1".into())); // a returning ant follows b / повернута мураха йде за b
    assert_eq!(h::choose("a", &peers, &[false, false, false], 0), Choice::Wait);
    assert_eq!(h::choose("a", &peers, &[false, false, false], 1), Choice::TakeOver);
    assert_eq!(h::choose("b", &peers, &[], 1), Choice::Wait);
    assert_eq!(h::choose("b", &peers, &[], 2), Choice::TakeOver);
    assert_eq!(h::choose("coord", &peers, &[], 0), Choice::TakeOver);
    assert_eq!(h::choose("stranger", &peers, &[], 99), Choice::Wait);
}

#[test]
fn no_snapshot_gives_up() {
    let d = std::env::temp_dir().join(format!("murakha-heal-none-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    let cfg = HealCfg { me: "a".into(), snap_dir: d, probe_timeout: Duration::from_millis(100), round_pause: Duration::from_millis(10), max_rounds: 3 };
    assert!(matches!(h::heal(&cfg).unwrap(), Healed::GaveUp));
}

#[test]
fn swarm_heals_after_coordinator_is_destroyed() {
    let (dead, a_addr, b_addr) = (free_addr(), free_addr(), free_addr());
    let snap = Snapshot { swarm: "dante".into(), peers: p(&[("coord", &dead), ("a", &a_addr), ("b", &b_addr)]), tasks: vec!["echo healed".into(), "echo again".into()] };
    let base = std::env::temp_dir().join(format!("murakha-heal-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    let mut cfgs = Vec::new();
    for me in ["a", "b"] {
        let dir = base.join(me);
        survive::store(&dir, &h::encode(&snap), 3).unwrap();
        cfgs.push(HealCfg { me: me.into(), snap_dir: dir, probe_timeout: Duration::from_millis(300), round_pause: Duration::from_millis(150), max_rounds: 30 });
    }
    let cb = cfgs.pop().unwrap();
    let ca = cfgs.pop().unwrap();
    let ta = std::thread::spawn(move || h::heal(&ca).unwrap());
    let tb = std::thread::spawn(move || h::heal(&cb).unwrap());
    let leader = match ta.join().unwrap() { Healed::Leader(s) => s, _ => panic!("ant a must become the coordinator / мураха a має стати координатором") };
    assert_eq!(leader.addr.to_string(), a_addr);
    assert_eq!(leader.queue.pending(), 2);
    let follow = match tb.join().unwrap() { Healed::Follow(a) => a, _ => panic!("ant b must follow a / мураха b має йти за a") };
    assert_eq!(follow, a_addr);
    // b really works for the new coordinator / b справді працює на нового координатора
    ant::run_session_timeout(&follow, "b", true, Duration::from_secs(10)).unwrap();
    let t0 = std::time::Instant::now();
    while leader.queue.results().is_empty() && t0.elapsed() < Duration::from_secs(10) { std::thread::sleep(Duration::from_millis(50)); }
    assert!(!leader.queue.results().is_empty(), "a task must be finished / завдання має бути виконане");
    let _ = std::fs::remove_dir_all(&base);
}
