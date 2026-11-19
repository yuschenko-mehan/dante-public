//! Specification: which task goes to which ant. Urgent work never goes to unreliable ants;
//! long work goes there only if it can resume after a power cut (checkpoints).
//! Специфікація: яке завдання якій мурасі. Термінове — ніколи ненадійним;
//! довге — їм лише якщо вміє продовжитись після вимкнення світла (контрольні точки).
//! (Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/plan.rs (std only; uses crate::health::Class):
//!   #[derive(Debug, Clone, PartialEq, Eq)]
//!   pub struct Job { pub id: String, pub est_s: u64, pub urgent: bool, pub resumable: bool, pub command: String }
//!   pub fn parse_line(id: &str, line: &str) -> Option<Job>
//!       trims the line; empty or starting with '#' -> None.
//!       If it starts with '[', the text up to the first ']' holds tags separated by spaces:
//!         "urgent", "resumable", "est=<n>" (seconds) / "est=<n>m" (minutes) / "est=<n>h" (hours); unknown tags ignored;
//!         the command is the rest after ']' trimmed. No ']' -> the whole line is the command, defaults apply.
//!       Defaults: est_s 60, urgent false, resumable false. Empty command -> None.
//!   pub fn fits(class: Class, mean_session_s: u64, job: &Job) -> bool
//!       Stable -> true
//!       Flaky  -> !urgent && (resumable || est_s * 2 <= mean_session_s)   (saturating multiply)
//!       Weak   -> !urgent && (resumable || est_s * 4 <= mean_session_s)
//!   pub fn pick(queue: &[Job], class: Class, mean_session_s: u64) -> Option<usize>
//!       Stable: index of the first urgent job; if none, the job with the largest est_s (first on ties).
//!       Flaky / Weak: index of the first job that fits. Empty queue or nothing fits -> None.
use murakha::health::Class;
use murakha::plan::{self as p, Job};

fn j(id: &str, est: u64, urgent: bool, resumable: bool) -> Job {
    Job { id: id.into(), est_s: est, urgent, resumable, command: format!("echo {id}") }
}

#[test]
fn parse_tags() {
    assert_eq!(p::parse_line("1", "  echo hi  "), Some(Job { id: "1".into(), est_s: 60, urgent: false, resumable: false, command: "echo hi".into() }));
    assert_eq!(p::parse_line("2", "[urgent est=10m] build all"), Some(Job { id: "2".into(), est_s: 600, urgent: true, resumable: false, command: "build all".into() }));
    assert_eq!(p::parse_line("3", "[resumable est=2h weird] render | sort"), Some(Job { id: "3".into(), est_s: 7200, urgent: false, resumable: true, command: "render | sort".into() }));
    assert_eq!(p::parse_line("4", "[est=45] x"), Some(Job { id: "4".into(), est_s: 45, urgent: false, resumable: false, command: "x".into() }));
    assert_eq!(p::parse_line("5", "[urgent no close bracket"), Some(Job { id: "5".into(), est_s: 60, urgent: false, resumable: false, command: "[urgent no close bracket".into() }));
    assert_eq!(p::parse_line("6", "# comment"), None);
    assert_eq!(p::parse_line("7", "   "), None);
    assert_eq!(p::parse_line("8", "[urgent]   "), None);
}

#[test]
fn fits_rules() {
    assert!(p::fits(Class::Stable, 0, &j("a", 99_999, true, false)));
    assert!(!p::fits(Class::Flaky, 99_999, &j("a", 10, true, true)));     // urgent never / термінове ніколи
    assert!(p::fits(Class::Flaky, 1200, &j("a", 600, false, false)));
    assert!(!p::fits(Class::Flaky, 1199, &j("a", 600, false, false)));
    assert!(p::fits(Class::Weak, 2400, &j("a", 600, false, false)));
    assert!(!p::fits(Class::Weak, 2399, &j("a", 600, false, false)));
    assert!(p::fits(Class::Weak, 0, &j("a", 86_400, false, true)));      // long but resumable / довге, але з точками
    let _ = p::fits(Class::Weak, u64::MAX, &j("a", u64::MAX, false, false)); // must not panic on overflow / без паніки
}

#[test]
fn pick_rules() {
    let q = vec![j("short", 30, false, false), j("long", 5000, false, false), j("hot", 100, true, false), j("long2", 5000, false, true)];
    assert_eq!(p::pick(&q, Class::Stable, 0), Some(2));
    assert_eq!(p::pick(&q[..2], Class::Stable, 0), Some(1));
    assert_eq!(p::pick(&q, Class::Flaky, 100), Some(0));
    assert_eq!(p::pick(&q[1..], Class::Weak, 100), Some(2)); // only the resumable one / лише з точками
    assert_eq!(p::pick(&q[1..3], Class::Weak, 100), None);
    assert_eq!(p::pick(&[], Class::Stable, 0), None);
}
