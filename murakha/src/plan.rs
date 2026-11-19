//! Job planning and parsing module.
//! Модуль планування та синтаксичного аналізу завдань.

use crate::health::Class;

/// Job structure representing a work item.
/// Структура завдання, що представляє елемент роботи.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Job {
    pub id: String,
    pub est_s: u64,
    pub urgent: bool,
    pub resumable: bool,
    pub command: String,
}

/// Parse a line of job description.
/// Розібрати рядок опису завдання.
pub fn parse_line(id: &str, line: &str) -> Option<Job> {
    let line = line.trim();
    if line.is_empty() || line.starts_with('#') {
        return None;
    }

    let mut est_s = 60u64;
    let mut urgent = false;
    let mut resumable = false;
    let mut command_str = line;

    if line.starts_with('[') {
        if let Some(close_idx) = line.find(']') {
            let tags_part = &line[1..close_idx];
            for tag in tags_part.split_whitespace() {
                if tag == "urgent" {
                    urgent = true;
                } else if tag == "resumable" {
                    resumable = true;
                } else if let Some(val_str) = tag.strip_prefix("est=") {
                    if let Some(parsed_sec) = parse_duration_to_seconds(val_str) {
                        est_s = parsed_sec;
                    }
                }
            }
            command_str = line[close_idx + 1..].trim();
        }
    }

    if command_str.is_empty() {
        return None;
    }

    Some(Job {
        id: id.to_string(),
        est_s,
        urgent,
        resumable,
        command: command_str.to_string(),
    })
}

/// Parse a duration string like "10", "10s", "10m", "2h" into seconds.
/// Розібрати рядок тривалості на кшталт "10", "10s", "10m", "2h" у секунди.
fn parse_duration_to_seconds(s: &str) -> Option<u64> {
    if s.is_empty() {
        return None;
    }
    let (num_part, unit) = if s.ends_with('s') || s.ends_with('m') || s.ends_with('h') {
        let (n, u) = s.split_at(s.len() - 1);
        (n, &u[..1])
    } else {
        (s, "s")
    };

    let val = num_part.parse::<u64>().ok()?;
    match unit {
        "s" => Some(val),
        "m" => val.checked_mul(60),
        "h" => val.checked_mul(3600),
        _ => None,
    }
}

/// Check if a job fits an ant class and mean session duration.
/// Перевірити, чи підходить завдання класу мурахи та середній тривалості сеансу.
pub fn fits(class: Class, mean_session_s: u64, job: &Job) -> bool {
    match class {
        Class::Stable => true,
        Class::Flaky => {
            if job.urgent {
                false
            } else if job.resumable {
                true
            } else {
                let limit = mean_session_s.checked_div(2).unwrap_or(u64::MAX);
                job.est_s <= limit
            }
        }
        Class::Weak => {
            if job.urgent {
                false
            } else if job.resumable {
                true
            } else {
                let limit = mean_session_s.checked_div(4).unwrap_or(u64::MAX);
                job.est_s <= limit
            }
        }
    }
}

/// Pick the best job index from a queue according to ant class and session duration.
/// Вибрати індекс найкращого завдання з черги відповідно до класу мурахи та тривалості сеансу.
pub fn pick(queue: &[Job], class: Class, mean_session_s: u64) -> Option<usize> {
    if queue.is_empty() {
        return None;
    }

    match class {
        Class::Stable => {
            // First, find the first urgent job / Спочатку знайти перше термінове завдання
            if let Some(idx) = queue.iter().position(|j| j.urgent) {
                return Some(idx);
            }
            // If none, the job with the largest est_s (first on ties) / Якщо немає, завдання з найбільшим est_s (перше при збігах)
            let mut best_idx = 0;
            let mut max_est = queue[0].est_s;
            for (i, job) in queue.iter().enumerate().skip(1) {
                if job.est_s > max_est {
                    max_est = job.est_s;
                    best_idx = i;
                }
            }
            Some(best_idx)
        }
        Class::Flaky | Class::Weak => {
            // Index of the first job that fits / Індекс першого завдання, яке підходить
            queue.iter().position(|job| fits(class, mean_session_s, job))
        }
    }
}
