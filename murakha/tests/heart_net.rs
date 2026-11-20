//! Specification: the coordinator hands the HEART of DANTE to every ant in pieces; one command on any ant's PC
//! brings DANTE back. / Специфікація: координатор частинами роздає СЕРЦЕ Данте кожній мурасі; одна команда
//! на ПК будь-якої мурахи повертає Данте.
//! (Claude, 20.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/protocol.rs: CoordMessage::Heart { version: String, index: u32, total: u32, data: String }  (data = hex)
//!     line "HEART\t<version>\t<index>\t<total>\t<data>"; parse back; wrong field count or bad numbers -> Err.
//! src/server.rs: TaskQueue::set_heart(&self, version: &str, bundle: &[u8], chunk_size: usize)  (heart::chunks)
//!     For an ant that wants snapshots: 1st ASK of a connection -> SNAP (as before); ASKs 2 ..= total+1 of that
//!     connection -> HEART chunks 0 .. total-1 in order; then the old behaviour (task / WAIT, SNAP every 20th).
//!     No heart set or an old ant -> no HEART at all.
//! src/ant.rs: run_session_snap collects HEART chunks (heart::Assembler per version); when complete and
//!     heart::list(&bundle) is Ok it saves the bundle with survive::store(&snap_dir.join("heart"), &bundle, 2).
//!     HEART never ends a `once` session.
//! src/main.rs: serve mode --heart-dir DIR: bundle = heart::pack(DIR), version = 16 hex digits of
//!     survive::checksum(&bundle), queue.set_heart(&version, &bundle, 256 * 1024); prints files and size.
//!   new mode: murakha --restore-dante OUT_DIR --heal-dir DIR
//!     unpack survive::latest(DIR/heart) into OUT_DIR, print the number of files and a bilingual hint, exit 0;
//!     no heart or a broken heart -> message, exit code 1.
use murakha::heart;
use murakha::protocol::{hex_decode, CoordMessage};
use murakha::server::Server;
use murakha::{ant, survive};
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

fn tmp(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("murakha-hnet-{}-{}", name, std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    std::fs::create_dir_all(&d).unwrap();
    d
}
fn fake_dante(name: &str) -> PathBuf {
    let d = tmp(name);
    std::fs::create_dir_all(d.join("dante")).unwrap();
    let big: String = (0..3000).map(|i| format!("x{i} = {i}\n")).collect();
    std::fs::write(d.join("dante/cli.py"), big).unwrap();
    std::fs::write(d.join("lessons.json"), "[]").unwrap();
    std::fs::write(d.join("keys.txt"), "GEMINI_API_KEY=SECRET").unwrap();
    d
}
struct Client { w: TcpStream, r: BufReader<TcpStream> }
impl Client {
    fn new(addr: &str, id: &str, ver: &str) -> Client {
        let s = TcpStream::connect(addr).unwrap();
        s.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
        let mut w = s.try_clone().unwrap();
        writeln!(w, "HELLO\t{id}\t2\t{ver}").unwrap();
        Client { w, r: BufReader::new(s) }
    }
    fn ask(&mut self, id: &str) -> CoordMessage {
        writeln!(self.w, "ASK\t{id}").unwrap();
        let mut l = String::new();
        self.r.read_line(&mut l).unwrap();
        CoordMessage::parse(&l).unwrap()
    }
}

#[test]
fn heart_line_roundtrip() {
    let m = CoordMessage::Heart { version: "abc".into(), index: 2, total: 5, data: "0a0b".into() };
    assert_eq!(m.to_line(), "HEART\tabc\t2\t5\t0a0b");
    assert_eq!(CoordMessage::parse("HEART\tabc\t2\t5\t0a0b\r\n"), Ok(m));
    assert!(CoordMessage::parse("HEART\tabc\tx\t5\t0a").is_err());
    assert!(CoordMessage::parse("HEART\tabc\t1\t5").is_err());
}

#[test]
fn server_hands_out_heart_chunks_in_order() {
    let bundle = heart::pack(&fake_dante("srv")).unwrap();
    let server = Server::bind("127.0.0.1:0").unwrap();
    let addr = server.local_addr().to_string();
    let q = server.queue();
    q.set_heart("v1", &bundle, 10_000);
    let total = heart::chunks(&bundle, 10_000).len();
    assert!(total >= 3);
    server.spawn();
    let mut c = Client::new(&addr, "new", "0.3.0");
    assert!(matches!(c.ask("new"), CoordMessage::Snap { .. }));
    let mut got = Vec::new();
    for i in 0..total {
        match c.ask("new") {
            CoordMessage::Heart { version, index, total: t, data } => {
                assert_eq!((version.as_str(), index as usize, t as usize), ("v1", i, total));
                got.extend(hex_decode(&data).unwrap());
            }
            o => panic!("chunk {i}: {o:?}"),
        }
    }
    assert_eq!(got, bundle);
    assert!(matches!(c.ask("new"), CoordMessage::Wait { .. }));
    let mut old = Client::new(&addr, "old", "0.1.0");
    assert!(matches!(old.ask("old"), CoordMessage::Wait { .. }));
}

#[test]
fn coordinator_process_gives_heart_and_ant_restores_dante() {
    let exe = env!("CARGO_BIN_EXE_murakha");
    let src = fake_dante("proc-src");
    let port = TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
    let mut coord = Command::new(exe)
        .args(["--serve", &port.to_string(), "--swarm", "heart-test", "--heart-dir", src.to_str().unwrap()])
        .stdout(Stdio::null()).stderr(Stdio::null()).spawn().unwrap();
    let heal = tmp("proc-heal");
    let addr = format!("127.0.0.1:{port}");
    let t0 = Instant::now();
    while TcpStream::connect(&addr).is_err() && t0.elapsed() < Duration::from_secs(10) { std::thread::sleep(Duration::from_millis(100)); }
    ant::run_session_snap(&addr, "ant-h", true, Duration::from_secs(10), Some(&heal)).unwrap();
    let _ = coord.kill();
    let _ = coord.wait();
    let saved = survive::latest(&heal.join("heart")).expect("the ant must keep the heart / мураха має зберегти серце");
    assert!(heart::list(&saved).is_ok());

    let out = tmp("proc-out");
    let st = Command::new(exe).args(["--restore-dante", out.to_str().unwrap(), "--heal-dir", heal.to_str().unwrap()])
        .stdout(Stdio::null()).stderr(Stdio::null()).status().unwrap();
    assert!(st.success());
    assert_eq!(std::fs::read(out.join("dante/cli.py")).unwrap(), std::fs::read(src.join("dante/cli.py")).unwrap());
    assert!(out.join("lessons.json").exists());
    assert!(!out.join("keys.txt").exists(), "keys never travel / ключі ніколи не мандрують");

    let empty = tmp("proc-empty");
    let st = Command::new(exe).args(["--restore-dante", tmp("o2").to_str().unwrap(), "--heal-dir", empty.to_str().unwrap()])
        .stdout(Stdio::null()).stderr(Stdio::null()).status().unwrap();
    assert!(!st.success());
}
