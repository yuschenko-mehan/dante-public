/// Ant module handling network connection with coordinator, task execution, and backoff.
/// Модуль мурахи, що обробляє мережеве з'єднання з координатором, виконання завдань та повторні спроби.

use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::path::Path;
use std::time::Duration;

use crate::protocol::{AntMessage, CoordMessage, hex_decode, hex_encode};
use crate::worker::run_command_code;

/// Maximum backoff duration for ant reconnection.
/// Максимальна тривалість затримки для перепідключення мурахи.
pub const MAX_BACKOFF: Duration = Duration::from_secs(30);

/// IO timeout for TCP stream operations.
/// Таймаут вводу-виводу для операцій з TCP-потоком.
pub const IO_TIMEOUT: Duration = Duration::from_secs(30);

/// Generate a non-zero random seed for an ant mixing its id and current time in nanoseconds.
/// Згенерувати ненульове випадкове зерно для мурахи, змішуючи її ідентифікатор та поточний час у наносекундах.
pub fn seed_for(ant_id: &str) -> u64 {
    // Get current time in nanoseconds / Отримати поточний час у наносекундах
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .subsec_nanos() as u64;

    // Hash ant_id bytes / Хешувати байти ant_id
    let mut hash: u64 = 0xcbf29ce484222325; // FNV offset basis / Початкове значення FNV
    for byte in ant_id.bytes() {
        hash ^= byte as u64;
        hash = hash.wrapping_mul(0x100000001b3); // FNV prime / Просте число FNV
    }

    // Mix with nanoseconds / Змішати з наносекундами
    let mut seed = hash ^ nanos.wrapping_mul(0x9e3779b97f4a7c15);

    // Ensure seed is non-zero / Забезпечити, щоб зерно було ненульовим
    if seed == 0 {
        seed = 0x123456789abcdef0;
    }

    seed
}

/// Calculate next delay with exponential backoff and random jitter using xorshift rng.
/// Обчислити наступну затримку з експоненційним зворотним відсвітом та випадковим тремтінням за допомогою xorshift rng.
pub fn next_delay(current: Duration, rng: &mut u64) -> Duration {
    // If rng state is zero, fix it to a non-zero value per specification / Якщо стан rng дорівнює нулю, виправити його на ненульове значення згідно зі специфікацією
    if *rng == 0 {
        *rng = 0x123456789abcdef0;
    }
    // Xorshift64 step / Крок xorshift64
    *rng ^= *rng << 13;
    *rng ^= *rng >> 7;
    *rng ^= *rng << 17;

    let base = std::cmp::min(current * 2, MAX_BACKOFF);
    let base_millis = base.as_millis() as u64;
    let jitter_max = base_millis / 2;
    let jitter_millis = if jitter_max > 0 {
        *rng % (jitter_max + 1)
    } else {
        0
    };

    Duration::from_millis(base_millis + jitter_millis)
}

/// Generate a unique ant identifier based on hostname and a random suffix.
/// Генерувати унікальний ідентифікатор мурахи на основі імені хоста та випадкового суфікса.
pub fn generate_ant_id() -> String {
    // Get hostname or fallback / Отримати ім'я хоста або використати резервне значення
    let hostname = match std::env::var("HOSTNAME") {
        Ok(h) => h,
        Err(_) => match std::env::var("COMPUTERNAME") {
            Ok(h) => h,
            Err(_) => "antbox".to_string(),
        },
    };
    
    // Simple pseudo-random suffix using current time nanoseconds / Простий псевдовипадковий суфікс на основі наносекунд поточного часу
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .subsec_nanos();
    
    format!("{}-{:06x}", hostname, nanos % 0x1000000)
}

/// Perform a single exchange session with the coordinator with snapshot support and specified timeout.
/// Виконати один сеанс обміну з координатором із підтримкою знімків та зазначеним таймаутом.
pub fn run_session_snap(coordinator_addr: &str, ant_id: &str, once: bool, io_timeout: Duration, snap_dir: Option<&Path>) -> std::io::Result<()> {
    // Connect to coordinator / Підключитися до координатора
    let stream = TcpStream::connect(coordinator_addr)?;
    stream.set_nodelay(true)?;
    stream.set_read_timeout(Some(io_timeout))?;
    stream.set_write_timeout(Some(io_timeout))?;

    let mut write_stream = stream.try_clone()?;
    let cpus = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(1);

    // Determine version based on snapshot directory presence / Визначити версію на основі наявності каталогу знімків
    let version = if snap_dir.is_some() {
        "0.3.0"
    } else {
        "0.1.0"
    };

    // Send HELLO message / Надіслати повідомлення HELLO
    let hello = AntMessage::Hello {
        id: ant_id.to_string(),
        cpus,
        version: version.to_string(),
    };
    write_stream.write_all(format!("{}\n", hello.to_line()).as_bytes())?;

    let mut reader = BufReader::new(stream);

    loop {
        // Send ASK message / Надіслати повідомлення ASK
        let ask = AntMessage::Ask {
            id: ant_id.to_string(),
        };
        write_stream.write_all(format!("{}\n", ask.to_line()).as_bytes())?;

        // Read response line / Прочитати рядок відповіді
        let mut line = String::new();
        let bytes_read = reader.read_line(&mut line)?;
        if bytes_read == 0 {
            break; // Connection closed / З'єднання закрито
        }

        let coord_msg = match CoordMessage::parse(&line) {
            Ok(m) => m,
            Err(_) => continue,
        };

        match coord_msg {
            CoordMessage::Task { task_id, timeout_s, command } => {
                // Execute command using worker / Виконати команду за допомогою воркера
                let timeout = Duration::from_secs(timeout_s);
                let (exit_code, output_hex) = match run_command_code(&command, timeout) {
                    Ok((code, out)) => (code, hex_encode(out.as_bytes())),
                    Err(err) => (-1, hex_encode(err.as_bytes())),
                };

                // Send RESULT message / Надіслати повідомлення RESULT
                let result_msg = AntMessage::Result {
                    id: ant_id.to_string(),
                    task_id,
                    exit_code,
                    output: output_hex,
                };
                write_stream.write_all(format!("{}\n", result_msg.to_line()).as_bytes())?;

                if once {
                    break;
                }
            }
            CoordMessage::Wait { seconds } => {
                std::thread::sleep(Duration::from_secs(seconds));
                if once {
                    break;
                }
            }
            CoordMessage::Snap { data } => {
                if let Some(dir) = snap_dir {
                    if let Ok(bytes) = hex_decode(&data) {
                        let _ = crate::survive::store(dir, &bytes, 5);
                    }
                }
                // After SNAP the ant just asks again / Після SNAP мураха просто питає знову
            }
            CoordMessage::Bye => {
                break;
            }
        }
    }

    Ok(())
}

/// Perform a single exchange session with the coordinator with specified timeout: connect, HELLO, loop asking for tasks/waiting.
/// Виконати один сеанс обміну з координатором із зазначеним таймаутом: підключення, HELLO, цикл запиту завдань / очікування.
pub fn run_session_timeout(coordinator_addr: &str, ant_id: &str, once: bool, io_timeout: Duration) -> std::io::Result<()> {
    run_session_snap(coordinator_addr, ant_id, once, io_timeout, None)
}

/// Perform a single exchange session with the coordinator using default IO_TIMEOUT.
/// Виконати один сеанс обміну з координатором, використовуючи стандартний IO_TIMEOUT.
pub fn run_session(coordinator_addr: &str, ant_id: &str, once: bool) -> std::io::Result<()> {
    run_session_timeout(coordinator_addr, ant_id, once, IO_TIMEOUT)
}

/// Run the ant loop with exponential backoff and random jitter upon network failures.
/// Запустити цикл мурахи з експоненційним зворотним відсвітом та випадковим тремтінням при збоях мережі.
pub fn run_ant_loop(coordinator_addr: &str, once: bool) {
    let ant_id = generate_ant_id();
    let mut backoff = Duration::from_millis(500);
    let mut rng = seed_for(&ant_id);

    loop {
        match run_session(coordinator_addr, &ant_id, once) {
            Ok(_) => {
                if once {
                    break;
                }
                // Reset backoff on successful session end / Скинути затримку при успішному завершенні сеансу
                backoff = Duration::from_millis(500);
            }
            Err(e) => {
                eprintln!("Ant connection error: {}. Reconnecting...", e);
                if once {
                    break;
                }
            }
        }

        // Sleep with backoff / Спати з урахуванням затримки
        std::thread::sleep(backoff);
        // Exponential increase with jitter / Експоненційне збільшення з тремтінням
        backoff = next_delay(backoff, &mut rng);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    /// Test ant id generation.
    /// Перевірити генерацію ідентифікатора мурахи.
    fn test_generate_ant_id() {
        let id1 = generate_ant_id();
        let id2 = generate_ant_id();
        assert!(!id1.is_empty());
        assert!(!id2.is_empty());
    }
}
