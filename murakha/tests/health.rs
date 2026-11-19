//! Specification: how reliable is an ant? (power cuts, weak internet)
//! Специфікація: наскільки надійна мураха? (вимкнення світла, слабкий інтернет)
//! (Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/health.rs (std only):
//!   #[derive(Debug, Clone, Copy, PartialEq, Eq)] pub enum Class { Stable, Flaky, Weak }
//!   pub fn sessions(beats: &[u64], gap_s: u64) -> Vec<(u64, u64)>
//!       beats = heartbeat times in seconds, any order, duplicates allowed (sort + dedup first).
//!       A new session starts when two neighbouring beats are more than gap_s apart.
//!       Returns (first beat, last beat) of every session in time order; no beats -> [].
//!   pub fn outages(beats: &[u64], gap_s: u64) -> usize        // number of sessions minus 1 (0 if none)
//!   pub fn mean_session_s(beats: &[u64], gap_s: u64) -> u64   // integer mean of (last - first); 0 if none
//!   pub fn uptime_ratio(beats: &[u64], gap_s: u64, now_s: u64, window_s: u64) -> f64
//!       window = [now_s - window_s (saturating), now_s]. Every session covers [first, min(last + gap_s, now_s)].
//!       Result = covered seconds inside the window / window_s, at most 1.0; window_s == 0 -> 0.0.
//!   pub fn classify(beats: &[u64], gap_s: u64, now_s: u64, window_s: u64) -> Class
//!       Only beats inside the window are used. u = uptime_ratio, o = outages, m = mean_session_s.
//!       Weak if u < 0.6, or (o >= 1 and m < 900). Otherwise Stable if u >= 0.95 and o <= 1. Otherwise Flaky.
use murakha::health::{self as h, Class};

fn every(from: u64, to: u64, step: u64) -> Vec<u64> { (from..=to).step_by(step as usize).collect() }

#[test]
fn sessions_split_on_gaps() {
    assert_eq!(h::sessions(&[], 60), vec![]);
    assert_eq!(h::sessions(&[30, 10, 20, 20], 60), vec![(10, 30)]);
    assert_eq!(h::sessions(&[0, 60, 200, 230, 1000], 60), vec![(0, 60), (200, 230), (1000, 1000)]);
    assert_eq!(h::outages(&[0, 60, 200, 230, 1000], 60), 2);
    assert_eq!(h::outages(&[], 60), 0);
    assert_eq!(h::mean_session_s(&[0, 60, 200, 230, 1000], 60), 30); // (60+30+0)/3
    assert_eq!(h::mean_session_s(&[], 60), 0);
}

#[test]
fn uptime_is_clipped_to_window() {
    let beats = every(0, 3600, 60);
    assert!((h::uptime_ratio(&beats, 60, 3600, 3600) - 1.0).abs() < 1e-9);
    // only the second half of the window was alive / жива лише друга половина вікна
    let half = every(1800, 3600, 60);
    let u = h::uptime_ratio(&half, 60, 3600, 3600);
    assert!((u - 0.5).abs() < 1e-9, "{u}");
    assert_eq!(h::uptime_ratio(&beats, 60, 3600, 0), 0.0);
    // early "now": window saturates at 0 / вікно не йде нижче нуля
    assert!(h::uptime_ratio(&every(0, 100, 10), 60, 100, 3600) <= 1.0);
}

#[test]
fn classes() {
    let day = 86_400;
    // always on / завжди увімкнена
    assert_eq!(h::classify(&every(0, day, 60), 120, day, day), Class::Stable);
    // light 4h on / 4h off -> half uptime -> Weak / світло 4 год є, 4 год нема
    let mut cut = Vec::new();
    for k in 0..3 { cut.extend(every(k * 28_800, k * 28_800 + 14_400, 60)); }
    assert_eq!(h::classify(&cut, 120, day, day), Class::Weak);
    // three short drops, long sessions, 90% up -> Flaky / три короткі зникнення
    let mut f = Vec::new();
    f.extend(every(0, 20_000, 60));
    f.extend(every(23_000, 50_000, 60));
    f.extend(every(53_000, 80_000, 60));
    f.extend(every(82_400, day, 60));
    assert_eq!(h::classify(&f, 120, day, day), Class::Flaky);
    // blinking internet: many tiny sessions -> Weak / мерехтливий інтернет
    let mut b = Vec::new();
    let mut t = 0;
    while t < day { b.extend(every(t, t + 300, 60)); t += 330; }
    assert_eq!(h::classify(&b, 20, day, day), Class::Weak);
    // nothing in the window -> Weak / нічого у вікні
    assert_eq!(h::classify(&every(0, 1000, 60), 120, 10 * day, day), Class::Weak);
}
