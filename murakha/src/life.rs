/// Life module for healing ants.
/// Модуль життя для мурах, що лікують рій.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use crate::ant;
use crate::heal::{self, HealCfg, Healed};
use crate::serve::Serving;

/// Get or create ant id in the specified directory.
/// Отримати або створити ідентифікатор мурахи у вказаному каталозі.
pub fn ant_id_in(dir: &Path) -> String {
    let id_file = dir.join("id.txt");
    if let Ok(content) = fs::read_to_string(&id_file) {
        let trimmed = content.trim();
        if !trimmed.is_empty() {
            return trimmed.to_string();
        }
    }

    let _ = fs::create_dir_all(dir);
    let new_id = ant::generate_ant_id();
    let _ = fs::write(&id_file, &new_id);
    new_id
}

/// Configuration for ant life loop.
/// Конфігурація для життєвого циклу мурахи.
pub struct LifeCfg {
    pub coordinator: String,
    pub heal_dir: PathBuf,
    pub silence: Duration,
    pub io_timeout: Duration,
    pub probe_timeout: Duration,
    pub round_pause: Duration,
    pub max_rounds: u32,
}

/// Run the ant life loop, healing the swarm when necessary.
/// Запустити життєвий цикл мурахи, відновлюючи рій за необхідності.
pub fn live(cfg: &LifeCfg) -> io::Result<Serving> {
    let id = ant_id_in(&cfg.heal_dir);
    let mut addr = cfg.coordinator.clone();
    let mut last_ok = Instant::now();

    loop {
        let now = Instant::now();
        match ant::run_session_snap(&addr, &id, false, cfg.io_timeout, Some(&cfg.heal_dir)) {
            Ok(_) => {
                last_ok = Instant::now();
            }
            Err(_) => {
                // Connection failed or lost, check silence / З'єднання не вдалося або втрачено, перевірити тишу
            }
        }

        if last_ok.elapsed() > cfg.silence {
            let heal_cfg = HealCfg {
                me: id.clone(),
                snap_dir: cfg.heal_dir.clone(),
                probe_timeout: cfg.probe_timeout,
                round_pause: cfg.round_pause,
                max_rounds: cfg.max_rounds,
            };

            match heal::heal(&heal_cfg)? {
                Healed::Follow(new_addr) => {
                    addr = new_addr;
                    last_ok = Instant::now();
                }
                Healed::Leader(serving) => {
                    return Ok(serving);
                }
                Healed::GaveUp => {
                    last_ok = Instant::now();
                }
            }
        } else {
            let elapsed = now.elapsed();
            let pause = if elapsed < Duration::from_millis(200) {
                Duration::from_millis(200) - elapsed
            } else {
                Duration::from_millis(10)
            };
            std::thread::sleep(pause);
        }
    }
}
