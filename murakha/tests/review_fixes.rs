//! Specification after Claude's review (19.11.2026). Do not edit — DANTE makes it pass.
//! Специфікація після рецензії Claude (19.11.2026). Не змінювати — Данте має її пройти.
//!
//! Required API / Потрібний інтерфейс:
//!   ant::MAX_BACKOFF: Duration = 30 s
//!   ant::next_delay(current: Duration, rng: &mut u64) -> Duration
//!       base = min(current * 2, MAX_BACKOFF); result = base + jitter, jitter in [0, base / 2];
//!       rng is a xorshift state, changed by every call (a zero state must still work)
//!   ant::IO_TIMEOUT: Duration (read/write timeout of the TCP stream, at least 30 s)
//!   ant::run_session_timeout(addr, ant_id, once, io_timeout) -> io::Result<()>
//!       same as run_session, with set_read_timeout/set_write_timeout = io_timeout;
//!       run_session(addr, id, once) == run_session_timeout(addr, id, once, IO_TIMEOUT)
//!   worker::run_command_code(cmd, timeout) -> Result<(i32, String), String>
//!       real exit code + output; the timeout works even if the command prints nothing
//!   RESULT sent by the ant carries the real exit code.
use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::thread;
use std::time::{Duration, Instant};

use murakha::{ant, worker};

#[test]
fn delay_doubles_with_jitter_and_cap() {
    assert_eq!(ant::MAX_BACKOFF, Duration::from_secs(30));
    for seed in 0..50u64 {
        let mut rng = seed;
        let d = ant::next_delay(Duration::from_secs(1), &mut rng);
        assert!(d >= Duration::from_secs(2) && d <= Duration::from_secs(3), "{:?}", d);
        let mut rng = seed;
        let d = ant::next_delay(Duration::from_secs(40), &mut rng);
        assert!(d >= Duration::from_secs(30) && d <= Duration::from_secs(45), "{:?}", d);
    }
}

#[test]
fn delay_varies_and_rng_moves() {
    let mut rng = 12345u64;
    let mut seen = std::collections::HashSet::new();
    for _ in 0..50 {
        let before = rng;
        seen.insert(ant::next_delay(Duration::from_secs(4), &mut rng));
        assert_ne!(before, rng, "rng state must change");
    }
    assert!(seen.len() >= 5, "jitter must vary, got {} distinct values", seen.len());
}

#[test]
fn session_times_out_on_silent_coordinator() {
    assert!(ant::IO_TIMEOUT >= Duration::from_secs(30));
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = listener.local_addr().unwrap().to_string();
    let _silent = thread::spawn(move || {
        let (s, _) = listener.accept().unwrap();
        thread::sleep(Duration::from_secs(4)); // accepts, never answers / приймає, але мовчить
        drop(s);
    });
    let t = Instant::now();
    let r = ant::run_session_timeout(&addr, "ant-t", true, Duration::from_millis(300));
    assert!(r.is_err(), "silent coordinator must give an error, not hang");
    assert!(t.elapsed() < Duration::from_secs(3), "took {:?}", t.elapsed());
}

#[test]
fn real_exit_code() {
    let (code, _) = worker::run_command_code("exit 3", Duration::from_secs(10)).unwrap();
    assert_eq!(code, 3);
    let (code, out) = worker::run_command_code("echo hello", Duration::from_secs(10)).unwrap();
    assert_eq!(code, 0);
    assert!(out.contains("hello"));
}

#[test]
fn timeout_works_for_silent_command() {
    #[cfg(windows)]
    let cmd = "ping -n 30 127.0.0.1 >nul";
    #[cfg(not(windows))]
    let cmd = "sleep 30";
    let t = Instant::now();
    assert!(worker::run_command_code(cmd, Duration::from_secs(1)).is_err());
    assert!(t.elapsed() < Duration::from_secs(5), "took {:?}", t.elapsed());
}

#[test]
fn ant_reports_real_exit_code() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = listener.local_addr().unwrap().to_string();
    let coord = thread::spawn(move || -> String {
        let (s, _) = listener.accept().unwrap();
        s.set_read_timeout(Some(Duration::from_secs(10))).unwrap();
        let mut w = s.try_clone().unwrap();
        let mut r = BufReader::new(s);
        let mut line = String::new();
        loop {
            line.clear();
            if r.read_line(&mut line).unwrap_or(0) == 0 {
                return String::new();
            }
            if line.starts_with("ASK") {
                w.write_all(b"TASK\tt1\t10\texit 3\n").unwrap();
            } else if line.starts_with("RESULT") {
                return line.trim_end_matches(['\r', '\n']).to_string();
            }
        }
    });
    let _ = ant::run_session_timeout(&addr, "ant-x", true, Duration::from_secs(10));
    let result = coord.join().unwrap();
    let fields: Vec<&str> = result.split('\t').collect();
    assert!(fields.len() >= 5, "bad RESULT line: {:?}", result);
    assert_eq!(fields[2], "t1");
    assert_eq!(fields[3], "3", "RESULT must carry the real exit code: {:?}", result);
}
