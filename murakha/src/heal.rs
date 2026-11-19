/// Self-healing module for swarm coordinator and ants.
/// Модуль самовідновлення для координатора рою та мурах.

use std::io;
use std::path::PathBuf;
use std::thread;
use std::time::Duration;

use crate::{scout, serve, survive};

/// Snapshot structure representing the swarm state.
/// Структура Snapshot, що представляє стан рою.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Snapshot {
    pub swarm: String,
    pub peers: Vec<(String, String)>,
    pub tasks: Vec<String>,
}

/// Encode a snapshot into bytes.
/// Закодувати знімок у байти.
pub fn encode(s: &Snapshot) -> Vec<u8> {
    let mut lines = Vec::new();
    lines.push(format!("SWARM\t{}", s.swarm));
    for (id, addr) in &s.peers {
        lines.push(format!("PEER\t{}\t{}", id, addr));
    }
    for task in &s.tasks {
        lines.push(format!("TASK\t{}", task));
    }
    lines.join("\n").into_bytes()
}

/// Decode a snapshot from bytes.
/// Декодувати знімок з байтів.
pub fn decode(data: &[u8]) -> Option<Snapshot> {
    let text = std::str::from_utf8(data).ok()?;
    let mut swarm = None;
    let mut peers = Vec::new();
    let mut tasks = Vec::new();

    for line in text.lines() {
        if line.is_empty() {
            continue;
        }
        let mut parts = line.splitn(2, '\t');
        let prefix = parts.next()?;
        let rest = parts.next().unwrap_or("");

        match prefix {
            "SWARM" => {
                if swarm.is_none() {
                    swarm = Some(rest.to_string());
                }
            }
            "PEER" => {
                let mut peer_parts = rest.splitn(2, '\t');
                if let Some(id) = peer_parts.next() {
                    let addr = peer_parts.next().unwrap_or("");
                    // Skip if address is empty / Пропустити, якщо адреса порожня
                    if !addr.is_empty() {
                        peers.push((id.to_string(), addr.to_string()));
                    }
                }
            }
            "TASK" => {
                tasks.push(rest.to_string());
            }
            _ => {
                // Unknown or broken lines are skipped / Невідомі або пошкоджені рядки пропускаються
            }
        }
    }

    let swarm = swarm?;
    Some(Snapshot { swarm, peers, tasks })
}

/// Choice for the ant during healing rounds.
/// Вибір для мурахи під час раундів самовідновлення.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Choice {
    Follow(String),
    TakeOver,
    Wait,
}

/// Choose action based on node status and answered peers.
/// Вибрати дію на основі статусу вузла та відповідей від учасників.
pub fn choose(me: &str, peers: &[(String, String)], answering: &[bool], round: u32) -> Choice {
    // The first peer that is not me and answered -> Follow(its addr)
    // Перший учасник, який не є мною та відповів -> Follow(його адреса)
    for (i, (id, addr)) in peers.iter().enumerate() {
        if id != me {
            let answered = answering.get(i).copied().unwrap_or(false);
            if answered {
                return Choice::Follow(addr.clone());
            }
        }
    }

    // Else, if me is not in peers -> Wait
    // Інакше, якщо мене немає в списку учасників -> Wait
    let my_rank = peers.iter().position(|(id, _)| id == me);
    let rank = match my_rank {
        Some(r) => r as u32,
        None => return Choice::Wait,
    };

    // Else rank = my index in peers: round >= rank -> TakeOver, otherwise Wait
    // Інакше rank = мій індекс в учасниках: round >= rank -> TakeOver, інакше Wait
    if round >= rank {
        Choice::TakeOver
    } else {
        Choice::Wait
    }
}

/// Configuration for healing.
/// Конфігурація для самовідновлення.
pub struct HealCfg {
    pub me: String,
    pub snap_dir: PathBuf,
    pub probe_timeout: Duration,
    pub round_pause: Duration,
    pub max_rounds: u32,
}

/// Result of the healing process.
/// Результат процесу самовідновлення.
pub enum Healed {
    Follow(String),
    Leader(serve::Serving),
    GaveUp,
}

/// Run the self-healing routine.
/// Запустити процедуру самовідновлення.
pub fn heal(cfg: &HealCfg) -> io::Result<Healed> {
    let snap_bytes = match survive::latest(&cfg.snap_dir) {
        Some(b) => b,
        None => return Ok(Healed::GaveUp),
    };

    let snapshot = match decode(&snap_bytes) {
        Some(s) => s,
        None => return Ok(Healed::GaveUp),
    };

    for round in 0..cfg.max_rounds {
        let mut answering = Vec::with_capacity(snapshot.peers.len());
        let mut my_addr = None;

        for (id, addr) in &snapshot.peers {
            if id == &cfg.me {
                my_addr = Some(addr.clone());
                answering.push(false);
            } else {
                let ans = scout::tcp_probe(addr, cfg.probe_timeout);
                answering.push(ans);
            }
        }

        let choice = choose(&cfg.me, &snapshot.peers, &answering, round);
        match choice {
            Choice::Follow(a) => {
                return Ok(Healed::Follow(a));
            }
            Choice::TakeOver => {
                let addr_str = match my_addr {
                    Some(a) => a,
                    None => return Ok(Healed::GaveUp),
                };
                let serving = serve::start(&addr_str, &snapshot.swarm, &snapshot.tasks, None)?;
                return Ok(Healed::Leader(serving));
            }
            Choice::Wait => {
                thread::sleep(cfg.round_pause);
            }
        }
    }

    Ok(Healed::GaveUp)
}


