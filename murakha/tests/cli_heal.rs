//! Specification: murakha.exe heals the swarm by itself. A real coordinator process is killed;
//! the ant process becomes the new coordinator with the same swarm.
//! Специфікація: murakha.exe сама лікує рій. Справжній процес координатора вбивають;
//! процес мурахи стає новим координатором того ж рою.
//! (Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/serve.rs: start() must call queue.set_swarm(swarm) (so a new leader keeps the swarm name).
//! src/main.rs:
//!   serve mode: new option --ant-port PORT (default 47901); after serve::start call
//!       serving.queue.set_swarm(&swarm) and serving.queue.set_ant_port(port).
//!   ant mode: new options --heal-dir DIR and --silence SECONDS (default 120).
//!       With --heal-dir: after the coordinator address is known, call life::live(&LifeCfg {
//!         coordinator, heal_dir: DIR, silence, io_timeout: 60 s, probe_timeout: 2 s, round_pause: 2 s, max_rounds: 30 }).
//!       When it returns the new Serving: print "This ant is now the coordinator at <addr> / Ця мураха тепер координатор на <addr>",
//!       start a thread running ant::run_ant_loop(<that addr>, false) so the ant keeps working too,
//!       and then print new results every second forever (like serve mode).
//!       Without --heal-dir everything works exactly as before. Usage/help text mentions the new options.
use murakha::heal;
use murakha::protocol::{hex_decode, CoordMessage};
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

fn free_port() -> u16 { TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port() }

fn snapshot_from(addr: &str) -> Option<heal::Snapshot> {
    let s = TcpStream::connect_timeout(&addr.parse().ok()?, Duration::from_millis(500)).ok()?;
    s.set_read_timeout(Some(Duration::from_secs(3))).ok()?;
    let mut w = s.try_clone().ok()?;
    writeln!(w, "HELLO\tprobe\t1\t0.3.0").ok()?;
    writeln!(w, "ASK\tprobe").ok()?;
    let mut line = String::new();
    BufReader::new(s).read_line(&mut line).ok()?;
    match CoordMessage::parse(&line).ok()? { CoordMessage::Snap { data } => heal::decode(&hex_decode(&data).ok()?), _ => None }
}

#[test]
fn ant_process_takes_over_when_coordinator_process_dies() {
    let exe = env!("CARGO_BIN_EXE_murakha");
    let (cport, aport) = (free_port(), free_port());
    let dir = std::env::temp_dir().join(format!("murakha-cli-heal-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let long = if cfg!(windows) { "ping -n 8 127.0.0.1 >nul" } else { "sleep 6" };
    std::fs::write(dir.join("tasks.txt"), format!("{long}\necho two\necho three\n")).unwrap();

    let mut coord = Command::new(exe)
        .args(["--serve", &cport.to_string(), "--swarm", "kyiv-test", "--tasks", dir.join("tasks.txt").to_str().unwrap(), "--ant-port", &aport.to_string()])
        .stdout(Stdio::null()).stderr(Stdio::null()).spawn().unwrap();
    std::thread::sleep(Duration::from_millis(800));
    let mut ant = Command::new(exe)
        .args(["--coordinator", &format!("127.0.0.1:{cport}"), "--swarm", "kyiv-test", "--heal-dir", dir.join("ant").to_str().unwrap(), "--silence", "1"])
        .stdout(Stdio::null()).stderr(Stdio::null()).spawn().unwrap();
    std::thread::sleep(Duration::from_millis(2500)); // the ant got the snapshot and is busy / мураха має знімок і працює
    coord.kill().unwrap(); // the coordinator is destroyed / координатора знищено
    let _ = coord.wait();

    let t0 = Instant::now();
    let mut found = None;
    while t0.elapsed() < Duration::from_secs(45) {
        if let Some(s) = snapshot_from(&format!("127.0.0.1:{aport}")) { found = Some(s); break; }
        std::thread::sleep(Duration::from_millis(300));
    }
    let _ = ant.kill();
    let _ = ant.wait();
    let s = found.expect("the ant must become the coordinator / мураха має стати координатором");
    assert_eq!(s.swarm, "kyiv-test");
    let _ = std::fs::remove_dir_all(&dir);
}
