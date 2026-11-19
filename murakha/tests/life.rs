//! Specification: the life of a healing ant. It works for the coordinator, keeps every snapshot,
//! and when the coordinator is silent too long it heals the swarm: follows the new leader or becomes it.
//! Специфікація: життя мурахи, що лікує рій. Працює на координатора, зберігає знімки,
//! а коли координатор надто довго мовчить — лікує рій: іде за новим ватажком або сама ним стає.
//! (Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/life.rs (std only; uses crate::ant, crate::heal, crate::serve):
//!   pub fn ant_id_in(dir: &Path) -> String
//!       reads "<dir>/id.txt" (trimmed, non-empty); otherwise creates dir, makes ant::generate_ant_id(),
//!       saves it to id.txt and returns it. The same dir always gives the same id (it survives restarts).
//!   pub struct LifeCfg { pub coordinator: String, pub heal_dir: PathBuf, pub silence: Duration, pub io_timeout: Duration,
//!                        pub probe_timeout: Duration, pub round_pause: Duration, pub max_rounds: u32 }
//!   pub fn live(cfg: &LifeCfg) -> io::Result<crate::serve::Serving>
//!       id = ant_id_in(heal_dir); addr = coordinator; last_ok = now. Loop forever:
//!         ant::run_session_snap(&addr, &id, false, io_timeout, Some(heal_dir)): Ok -> last_ok = now.
//!         If last_ok is older than `silence`: heal::heal(HealCfg { me: id, snap_dir: heal_dir, ... }):
//!             Follow(a) -> addr = a, last_ok = now;  Leader(s) -> return Ok(s);  GaveUp -> last_ok = now.
//!         Otherwise sleep a short pause (at most 200 ms) before trying again.
//!       It only returns when this ant became the coordinator.
use murakha::heal::{self as h, Snapshot};
use murakha::life::{self as l, LifeCfg};
use murakha::protocol::{hex_encode, CoordMessage};
use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::path::PathBuf;
use std::time::{Duration, Instant};

fn free_addr() -> String { TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().to_string() }
fn tmpdir(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("murakha-life-{}-{}", name, std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    d
}

/// A coordinator that lives `life` and then is destroyed: it hands out `snap` and WAITs, then closes everything.
fn doomed_coordinator(snap: Vec<u8>, life: Duration) -> String {
    let l = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = l.local_addr().unwrap().to_string();
    l.set_nonblocking(true).unwrap();
    let end = Instant::now() + life;
    std::thread::spawn(move || {
        let mut handlers = Vec::new();
        while Instant::now() < end {
            match l.accept() {
                Ok((s, _)) => {
                    let snap = snap.clone();
                    handlers.push(std::thread::spawn(move || {
                        s.set_nonblocking(false).unwrap();
                        s.set_read_timeout(Some(Duration::from_millis(100))).unwrap();
                        let mut w = s.try_clone().unwrap();
                        let mut r = BufReader::new(s);
                        let mut sent = false;
                        while Instant::now() < end {
                            let mut line = String::new();
                            match r.read_line(&mut line) {
                                Ok(0) => break,
                                Ok(_) if line.starts_with("ASK") => {
                                    let reply = if !sent { sent = true; CoordMessage::Snap { data: hex_encode(&snap) }.to_line() } else { "WAIT\t0".into() };
                                    if writeln!(w, "{reply}").is_err() { break; }
                                    std::thread::sleep(Duration::from_millis(50));
                                }
                                _ => {}
                            }
                        }
                        let _ = w.shutdown(std::net::Shutdown::Both);
                    }));
                }
                Err(_) => std::thread::sleep(Duration::from_millis(20)),
            }
        }
        drop(l); // destroyed / знищено
        for h in handlers { let _ = h.join(); }
    });
    addr
}

#[test]
fn id_survives_restarts() {
    let d = tmpdir("id");
    let a = l::ant_id_in(&d);
    assert!(!a.is_empty());
    assert_eq!(l::ant_id_in(&d), a);
    std::fs::write(d.join("id.txt"), "fixed-id\n").unwrap();
    assert_eq!(l::ant_id_in(&d), "fixed-id");
    let _ = std::fs::remove_dir_all(&d);
}

#[test]
fn ants_heal_the_swarm_after_the_coordinator_is_destroyed() {
    let (a_addr, b_addr) = (free_addr(), free_addr());
    let coord_placeholder = free_addr();
    // the snapshot the coordinator gives out / знімок, який роздає координатор
    let snap = Snapshot { swarm: "kyiv".into(), peers: vec![("coord".into(), coord_placeholder), ("a".into(), a_addr.clone()), ("b".into(), b_addr)], tasks: vec!["echo healed".into()] };
    let coord = doomed_coordinator(h::encode(&snap), Duration::from_millis(1500));
    let mk = |me: &str| {
        let d = tmpdir(me);
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(d.join("id.txt"), me).unwrap();
        LifeCfg { coordinator: coord.clone(), heal_dir: d, silence: Duration::from_millis(600), io_timeout: Duration::from_secs(5),
                  probe_timeout: Duration::from_millis(200), round_pause: Duration::from_millis(200), max_rounds: 40 }
    };
    let (ca, cb) = (mk("a"), mk("b"));
    let ta = std::thread::spawn(move || l::live(&ca).unwrap());
    std::thread::spawn(move || { let _ = l::live(&cb); }); // b works forever / b працює далі
    let leader = ta.join().unwrap();
    assert_eq!(leader.addr.to_string(), a_addr);
    let t0 = Instant::now();
    while leader.queue.results().is_empty() && t0.elapsed() < Duration::from_secs(15) { std::thread::sleep(Duration::from_millis(100)); }
    let res = leader.queue.results();
    assert!(!res.is_empty(), "ant b must finish the task for the new leader / мураха b має виконати завдання для нового ватажка");
    assert_eq!(res[0].ant_id, "b");
    assert!(res[0].output.contains("healed"));
}
