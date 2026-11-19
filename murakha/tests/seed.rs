//! Each ant must get its OWN random seed, otherwise 1000 ants pause identically (Claude's review, 19.11.2026).
//! Кожна Мураха має отримати ВЛАСНЕ випадкове зерно, інакше 1000 Мурах чекають однаково (рецензія Claude).
//!   ant::seed_for(ant_id: &str) -> u64 : non-zero, mixes the id with the current time (nanoseconds);
//!   run_ant_loop must start its rng with seed_for(&ant_id).
use murakha::ant;
use std::collections::HashSet;

#[test]
fn different_ants_get_different_seeds() {
    let seeds: HashSet<u64> = (0..200).map(|i| ant::seed_for(&format!("pc-{}", i))).collect();
    assert!(seeds.len() >= 190, "only {} distinct seeds", seeds.len());
    assert!(!seeds.contains(&0));
}

#[test]
fn same_id_later_gets_another_seed() {
    let a = ant::seed_for("pc-1");
    std::thread::sleep(std::time::Duration::from_millis(5));
    assert_ne!(a, ant::seed_for("pc-1"), "time must be mixed in");
}

#[test]
fn delays_of_two_ants_differ() {
    let (mut r1, mut r2) = (ant::seed_for("pc-a"), ant::seed_for("pc-b"));
    let d = std::time::Duration::from_secs(4);
    let same = (0..20).filter(|_| ant::next_delay(d, &mut r1) == ant::next_delay(d, &mut r2)).count();
    assert!(same < 5, "two ants paused identically {} times of 20", same);
}
