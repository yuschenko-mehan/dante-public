//! Specification: the scout ant. When the coordinator is lost, it walks known routes for a limited time,
//! with growing pauses (weak internet, power cuts), until someone answers.
//! Специфікація: мураха-пошуковець. Коли координатор зник, обходить відомі маршрути обмежений час,
//! зі зростаючими паузами (слабкий інтернет, вимкнення світла), доки хтось не відповість.
//! (Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/scout.rs (std only):
//!   pub fn routes(last: Option<&str>, peers: &[String], lan: &[String]) -> Vec<String>
//!       last, then peers, then lan; skips empty strings; removes duplicates keeping the first.
//!   pub fn pause_s(round: u32, base_s: u64, max_s: u64) -> u64
//!       base_s * 2^round, never above max_s, never panics (saturating).
//!   pub fn patrol<P: FnMut(&str) -> bool, W: FnMut(u64)>(routes: &[String], budget_s: u64, base_s: u64, max_s: u64, probe: P, wait: W) -> Option<String>
//!       round = 0, spent = 0. Loop: probe every route in order; the first that answers true is returned.
//!       Empty routes -> None at once. Otherwise p = pause_s(round, base_s, max_s);
//!       if p == 0 or spent + p > budget_s -> None; else wait(p), spent += p, round += 1, repeat.
//!   pub fn tcp_probe(addr: &str, timeout: std::time::Duration) -> bool
//!       true if a TCP connection to any resolved address of `addr` succeeds within timeout; bad address -> false.
use murakha::scout as s;
use std::net::TcpListener;
use std::time::Duration;

fn v(x: &[&str]) -> Vec<String> { x.iter().map(|s| s.to_string()).collect() }

#[test]
fn routes_order_and_dedup() {
    assert_eq!(s::routes(Some("a:1"), &v(&["b:2", "a:1", ""]), &v(&["c:3", "b:2"])), v(&["a:1", "b:2", "c:3"]));
    assert_eq!(s::routes(None, &[], &[]), Vec::<String>::new());
    assert_eq!(s::routes(Some(""), &v(&["x:1"]), &[]), v(&["x:1"]));
}

#[test]
fn pauses_grow_and_cap() {
    assert_eq!(s::pause_s(0, 30, 3600), 30);
    assert_eq!(s::pause_s(3, 30, 3600), 240);
    assert_eq!(s::pause_s(10, 30, 3600), 3600);
    assert_eq!(s::pause_s(200, u64::MAX, 7), 7);
}

#[test]
fn patrol_finds_late_answer_within_budget() {
    let r = v(&["dead:1", "late:2"]);
    let mut calls = 0;
    let mut waits = Vec::new();
    let got = s::patrol(&r, 1000, 10, 100, |a| { calls += 1; a == "late:2" && calls > 4 }, |p| waits.push(p));
    assert_eq!(got, Some("late:2".to_string()));
    assert_eq!(waits, vec![10, 20]);
}

#[test]
fn patrol_gives_up_when_budget_is_spent() {
    let mut waits = Vec::new();
    let got = s::patrol(&v(&["dead:1"]), 100, 10, 1000, |_| false, |p| waits.push(p));
    assert_eq!(got, None);
    assert_eq!(waits, vec![10, 20, 40]); // next 80 would exceed 100 / наступні 80 перевищили б 100
    let mut n = 0;
    assert_eq!(s::patrol(&v(&["x:1"]), 100, 0, 10, |_| { n += 1; false }, |_| panic!("no wait")), None);
    assert_eq!(n, 1);
    assert_eq!(s::patrol(&[], 100, 10, 10, |_| true, |_| {}), None);
}

#[test]
fn tcp_probe_real() {
    let l = TcpListener::bind("127.0.0.1:0").unwrap();
    let live = l.local_addr().unwrap().to_string();
    assert!(s::tcp_probe(&live, Duration::from_millis(500)));
    let dead = { let d = TcpListener::bind("127.0.0.1:0").unwrap(); d.local_addr().unwrap().to_string() };
    assert!(!s::tcp_probe(&dead, Duration::from_millis(300)));
    assert!(!s::tcp_probe("not an address", Duration::from_millis(300)));
}
