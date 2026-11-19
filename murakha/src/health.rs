//! Health analysis module for ant reliability.
//! Модуль аналізу стану здоров'я надійності мурах.

/// Class of ant health reliability.
/// Клас надійності здоров'я мурахи.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Class {
    Stable,
    Flaky,
    Weak,
}

/// Compute sessions from heartbeat times and gap threshold.
/// Обчислити сесії за часом серцебиття та порогом інтервалу.
pub fn sessions(beats: &[u64], gap_s: u64) -> Vec<(u64, u64)> {
    // Check if beats are empty / Перевірити, чи порожнє серцебиття
    if beats.is_empty() {
        return Vec::new();
    }

    // Sort and deduplicate beats / Відсортувати та видалити дублікати серцебиття
    let mut sorted: Vec<u64> = beats.to_vec();
    sorted.sort_unstable();
    sorted.dedup();

    let mut result = Vec::new();
    let mut start = sorted[0];
    let mut last = sorted[0];

    for &b in sorted.iter().skip(1) {
        // If gap between b and last exceeds gap_s, close current session and start new
        // Якщо інтервал між b і last перевищує gap_s, закрити поточну сесію і почати нову
        if b.saturating_sub(last) > gap_s {
            result.push((start, last));
            start = b;
        }
        last = b;
    }
    result.push((start, last));
    result
}

/// Calculate number of outages (sessions minus 1, or 0 if none).
/// Обчислити кількість збоїв (сесії мінус 1, або 0, якщо їх немає).
pub fn outages(beats: &[u64], gap_s: u64) -> usize {
    let s = sessions(beats, gap_s);
    if s.is_empty() {
        0
    } else {
        s.len() - 1
    }
}

/// Calculate integer mean session duration in seconds.
/// Обчислити середню цілочисельну тривалість сесії в секундах.
pub fn mean_session_s(beats: &[u64], gap_s: u64) -> u64 {
    let s = sessions(beats, gap_s);
    if s.is_empty() {
        return 0;
    }
    let total: u64 = s.iter().map(|&(first, last)| last.saturating_sub(first)).sum();
    total / (s.len() as u64)
}

/// Calculate uptime ratio within a given time window.
/// Обчислити коефіцієнт безвідмовної роботи у заданому часовому вікні.
pub fn uptime_ratio(beats: &[u64], gap_s: u64, now_s: u64, window_s: u64) -> f64 {
    if window_s == 0 {
        return 0.0;
    }

    let win_start = now_s.saturating_sub(window_s);
    let s = sessions(beats, gap_s);

    let mut covered_seconds: u64 = 0;

    for &(first, last) in &s {
        let session_end = last.saturating_add(gap_s).min(now_s);
        let session_start = first;

        // Clip session to [win_start, now_s] / Обрізати сесію до [win_start, now_s]
        if session_end <= win_start || session_start >= now_s {
            continue;
        }

        let clipped_start = session_start.max(win_start);
        let clipped_end = session_end.min(now_s);

        if clipped_end > clipped_start {
            covered_seconds = covered_seconds.saturating_add(clipped_end - clipped_start);
        }
    }

    let ratio = (covered_seconds as f64) / (window_s as f64);
    if ratio > 1.0 {
        1.0
    } else {
        ratio
    }
}

/// Classify ant reliability based on uptime, outages, and mean session duration.
/// Класифікувати надійність мурахи на основі часу безвідмовної роботи, збоїв та середньої тривалості сесії.
pub fn classify(beats: &[u64], gap_s: u64, now_s: u64, window_s: u64) -> Class {
    let win_start = now_s.saturating_sub(window_s);

    // Filter beats strictly inside the window / Фільтрувати серцебиття суворо всередині вікна
    let window_beats: Vec<u64> = beats
        .iter()
        .copied()
        .filter(|&b| b >= win_start && b <= now_s)
        .collect();

    let u = uptime_ratio(&window_beats, gap_s, now_s, window_s);
    let o = outages(&window_beats, gap_s);
    let m = mean_session_s(&window_beats, gap_s);

    if u < 0.6 || (o >= 1 && m < 900) {
        Class::Weak
    } else if u >= 0.95 && o <= 1 {
        Class::Stable
    } else {
        Class::Flaky
    }
}
