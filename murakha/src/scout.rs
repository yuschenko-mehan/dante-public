/// Scout module implementation.
/// Реалізація модуля пошуковця.

use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

/// Compute routes list from last, peers, and lan.
/// Обчислити список маршрутів з last, peers та lan.
pub fn routes(last: Option<&str>, peers: &[String], lan: &[String]) -> Vec<String> {
    // Result vector / Результуючий вектор
    let mut res = Vec::new();

    // Add last if present and not empty / Додати last, якщо присутній та не порожній
    if let Some(l) = last {
        if !l.is_empty() {
            res.push(l.to_string());
        }
    }

    // Add peers / Додати peers
    for p in peers {
        if !p.is_empty() {
            res.push(p.to_string());
        }
    }

    // Add lan / Додати lan
    for l in lan {
        if !l.is_empty() {
            res.push(l.to_string());
        }
    }

    // Remove duplicates keeping the first / Видалити дублікати, зберігаючи перший
    let mut unique = Vec::new();
    for r in res {
        if !unique.contains(&r) {
            unique.push(r);
        }
    }

    unique
}

/// Compute pause duration in seconds with saturating operations.
/// Обчислити тривалість паузи в секундах з насиченими операціями.
pub fn pause_s(round: u32, base_s: u64, max_s: u64) -> u64 {
    // base_s * 2^round, never above max_s, never panics / base_s * 2^round, ніколи не перевищує max_s, ніколи не панікує
    let mult = if round >= 64 {
        u64::MAX
    } else {
        1u64.checked_shl(round).unwrap_or(u64::MAX)
    };

    let p = base_s.saturating_mul(mult);
    if p > max_s { max_s } else { p }
}

/// Patrol routes within a budget, probing and waiting.
/// Патрулювати маршрути в межах бюджету, перевіряючи та чекаючи.
pub fn patrol<P: FnMut(&str) -> bool, W: FnMut(u64)>(
    routes: &[String],
    budget_s: u64,
    base_s: u64,
    max_s: u64,
    mut probe: P,
    mut wait: W,
) -> Option<String> {
    // Empty routes -> None at once / Порожні маршрути -> одразу None
    if routes.is_empty() {
        return None;
    }

    let mut round: u32 = 0;
    let mut spent: u64 = 0;

    loop {
        // Probe every route in order / Перевірити кожен маршрут по черзі
        for r in routes {
            if probe(r) {
                return Some(r.clone());
            }
        }

        // Calculate pause / Обчислити паузу
        let p = pause_s(round, base_s, max_s);

        // if p == 0 or spent + p > budget_s -> None / якщо p == 0 або spent + p > budget_s -> None
        if p == 0 || spent.checked_add(p).map_or(true, |sum| sum > budget_s) {
            return None;
        }

        wait(p);
        spent += p;
        round += 1;
    }
}

/// Probe a TCP address with a timeout.
/// Перевірити TCP адресу з таймаутом.
pub fn tcp_probe(addr: &str, timeout: Duration) -> bool {
    // true if TCP connection succeeds within timeout; bad address -> false / true, якщо TCP з'єднання вдається в межах таймауту; погана адреса -> false
    match ToSocketAddrs::to_socket_addrs(addr) {
        Ok(addrs) => {
            for a in addrs {
                if TcpStream::connect_timeout(&a, timeout).is_ok() {
                    return true;
                }
            }
            false
        }
        Err(_) => false,
    }
}
