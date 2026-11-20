// Temperature guard and thermal monitoring for AdDante.
// Температурний захист та моніторинг для AdDante.

/// Throttle state ordered Run < Careful < Pause.
/// Стан троттлінгу, впорядкований як Run < Careful < Pause.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Throttle {
    Run,
    Careful,
    Pause,
}

/// Combine two throttle states, returning the worse one.
/// Комбінує два стани троттлінгу, повертаючи гірший.
pub fn combine(a: Throttle, b: Throttle) -> Throttle {
    std::cmp::max(a, b)
}

/// Calculate CPU share based on max capacity and throttle state.
/// Розраховує частку CPU на основі максимальної ємності та стану троттлінгу.
pub fn cpu_share(max: usize, throttle: Throttle) -> usize {
    match throttle {
        Throttle::Run => max,
        Throttle::Careful => std::cmp::max(1, max / 2),
        Throttle::Pause => 0,
    }
}

/// Thermal guard with limit and hysteresis.
/// Температурний захист з межею та гістерезисом.
pub struct ThermalGuard {
    limit_c: f64,
    hysteresis_c: f64,
    paused: bool,
}

impl ThermalGuard {
    /// Create a new ThermalGuard with given limit and hysteresis.
    /// Створити новий ThermalGuard із заданою межею та гістерезисом.
    pub fn new(limit_c: f64, hysteresis_c: f64) -> Self {
        Self {
            limit_c,
            hysteresis_c,
            paused: false,
        }
    }

    /// Check if currently paused.
    /// Перевірити, чи поточний стан — пауза.
    pub fn is_paused(&self) -> bool {
        self.paused
    }

    /// Update temperature sensor reading and return throttle state.
    /// Оновити показник датчика температури та повернути стан троттлінгу.
    pub fn update(&mut self, temp: Option<f64>) -> Throttle {
        match temp {
            Some(t) => {
                if self.paused {
                    // While paused, remain paused if t > limit - hysteresis
                    // Поки на паузі, залишатися на паузі, якщо t > limit - hysteresis
                    if t > self.limit_c - self.hysteresis_c {
                        Throttle::Pause
                    } else {
                        self.paused = false;
                        Throttle::Run
                    }
                } else {
                    // Not paused: pause if t >= limit
                    // Не на паузі: пауза, якщо t >= limit
                    if t >= self.limit_c {
                        self.paused = true;
                        Throttle::Pause
                    } else {
                        Throttle::Run
                    }
                }
            }
            None => {
                // No sensor: Pause if paused else Careful
                // Немає датчика: Pause, якщо на паузі, інакше Careful
                if self.paused {
                    Throttle::Pause
                } else {
                    Throttle::Careful
                }
            }
        }
    }
}

/// Parse nvidia-smi CSV output to find the hottest GPU temperature.
/// Розібрати вивод nvidia-smi CSV для пошуку найгарячішої температури GPU.
pub fn parse_nvidia_smi(output: &str) -> Option<f64> {
    let mut hottest: Option<f64> = None;
    for line in output.lines() {
        let trimmed = line.trim();
        if let Ok(val) = trimmed.parse::<f64>() {
            match hottest {
                Some(current) => {
                    if val > current {
                        hottest = Some(val);
                    }
                }
                None => {
                    hottest = Some(val);
                }
            }
        }
    }
    hottest
}

/// Parse Linux thermal zone content in millidegrees to Celsius.
/// Розібрати вміст термічної зони Linux в міліградусах у Цельсії.
pub fn parse_linux_thermal(content: &str) -> Option<f64> {
    let trimmed = content.trim();
    if let Ok(millis) = trimmed.parse::<f64>() {
        let celsius = millis / 1000.0;
        if (0.0..=150.0).contains(&celsius) {
            return Some(celsius);
        }
    }
    None
}
