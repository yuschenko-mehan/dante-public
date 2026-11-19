//! Specification: the ant keeps every swarm snapshot it receives (SNAP), so it can heal the swarm later.
//! Специфікація: мураха зберігає кожен отриманий знімок рою (SNAP), щоб потім відновити рій.
//! (Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/protocol.rs: CoordMessage gets a new variant  Snap { data: String }  (data = lowercase hex)
//!     to_line -> "SNAP\t<data>"; parse("SNAP\t<data>") -> Snap; wrong field count -> Err. Others unchanged.
//! src/ant.rs: add
//!   pub fn run_session_snap(coordinator_addr: &str, ant_id: &str, once: bool, io_timeout: Duration, snap_dir: Option<&Path>) -> io::Result<()>
//!       Same as run_session_timeout, but HELLO version is "0.3.0" when snap_dir is Some (else "0.1.0").
//!       On SNAP: hex-decode and save with crate::survive::store(dir, &bytes, 5); bad hex or no dir -> ignore it.
//!       After SNAP the ant just asks again (SNAP never ends a `once` session).
//!   run_session_timeout(...) must behave exactly as before = run_session_snap(..., None).
use murakha::protocol::{hex_encode, CoordMessage};
use murakha::{ant, survive};
use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::time::Duration;

/// A fake coordinator: answers the ant's ASKs with `replies` in order, then returns all lines it received.
fn fake(replies: Vec<String>) -> (String, std::thread::JoinHandle<Vec<String>>) {
    let l = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = l.local_addr().unwrap().to_string();
    let h = std::thread::spawn(move || {
        let (s, _) = l.accept().unwrap();
        s.set_read_timeout(Some(Duration::from_secs(10))).unwrap();
        let mut w = s.try_clone().unwrap();
        let mut r = BufReader::new(s);
        let mut got = Vec::new();
        let mut replies = replies.into_iter();
        loop {
            let mut line = String::new();
            if r.read_line(&mut line).unwrap_or(0) == 0 { break; }
            let line = line.trim_end().to_string();
            if line.starts_with("ASK") {
                match replies.next() { Some(x) => { let _ = writeln!(w, "{x}"); } None => { let _ = writeln!(w, "BYE"); } }
            }
            got.push(line);
        }
        got
    });
    (addr, h)
}

fn tmpdir(name: &str) -> std::path::PathBuf {
    let d = std::env::temp_dir().join(format!("murakha-rep-{}-{}", name, std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    d
}

#[test]
fn ant_saves_snapshot_then_works() {
    let d = tmpdir("ok");
    let snap = CoordMessage::Snap { data: hex_encode(b"SWARM\tdante") }.to_line();
    let (addr, h) = fake(vec![snap, "TASK\tt1\t10\techo hi".into()]);
    ant::run_session_snap(&addr, "ant-z", true, Duration::from_secs(10), Some(&d)).unwrap();
    let got = h.join().unwrap();
    assert!(got[0].starts_with("HELLO\tant-z\t") && got[0].ends_with("\t0.3.0"), "{:?}", got[0]);
    assert!(got.iter().any(|l| l.starts_with("RESULT\tant-z\tt1\t0\t")), "{got:?}");
    assert_eq!(survive::latest(&d), Some(b"SWARM\tdante".to_vec()));
    let _ = std::fs::remove_dir_all(&d);
}

#[test]
fn bad_snapshot_is_ignored() {
    let d = tmpdir("bad");
    let (addr, h) = fake(vec!["SNAP\tzz".into(), "TASK\tt2\t10\techo ok".into()]);
    ant::run_session_snap(&addr, "ant-q", true, Duration::from_secs(10), Some(&d)).unwrap();
    let got = h.join().unwrap();
    assert!(got.iter().any(|l| l.starts_with("RESULT\tant-q\tt2\t0\t")), "{got:?}");
    assert_eq!(survive::latest(&d), None);
}

#[test]
fn old_session_says_old_version() {
    let (addr, h) = fake(vec!["TASK\tt3\t10\techo old".into()]);
    ant::run_session_timeout(&addr, "ant-o", true, Duration::from_secs(10)).unwrap();
    let got = h.join().unwrap();
    assert!(got[0].ends_with("\t0.1.0"), "{:?}", got[0]);
    let (addr, h) = fake(vec![CoordMessage::Snap { data: "41".into() }.to_line(), "TASK\tt4\t10\techo x".into()]);
    ant::run_session_snap(&addr, "ant-n", true, Duration::from_secs(10), None).unwrap();
    let got = h.join().unwrap();
    assert!(got[0].ends_with("\t0.1.0") && got.iter().any(|l| l.starts_with("RESULT\tant-n\tt4\t")), "{got:?}");
}
