/// UDP discovery module for finding coordinators in the local network.
/// Модуль UDP-виявлення для пошуку координаторів у локальній мережі.

use std::io;
use std::net::{SocketAddr, UdpSocket};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

/// Discovery port used across the network.
/// Порт виявлення, який використовується в мережі.
pub const DISCOVERY_PORT: u16 = 47900;

/// Check if IO error is retryable during discovery receive.
/// Перевірити, чи є помилка введення-виведення повторюваною під час прийому виявлення.
pub fn is_retryable(e: &io::Error) -> bool {
    // Check for WouldBlock, TimedOut, ConnectionReset, Interrupted / Перевірити на WouldBlock, TimedOut, ConnectionReset, Interrupted
    matches!(
        e.kind(),
        io::ErrorKind::WouldBlock
            | io::ErrorKind::TimedOut
            | io::ErrorKind::ConnectionReset
            | io::ErrorKind::Interrupted
    )
}

/// Return default target addresses for discovery.
/// Повернути цільові адреси за замовчуванням для виявлення.
pub fn default_targets() -> Vec<SocketAddr> {
    // Return broadcast address with discovery port / Повернути широкомовну адресу з портом виявлення
    vec![SocketAddr::from(([255, 255, 255, 255], DISCOVERY_PORT))]
}

/// Make discovery request message.
/// Створити повідомлення запиту виявлення.
pub fn make_request(swarm_id: &str) -> Vec<u8> {
    // Format request as b"DANTE-WHO\t<swarm_id>\n" / Відформатувати запит як b"DANTE-WHO\t<swarm_id>\n"
    format!("DANTE-WHO\t{}\n", swarm_id).into_bytes()
}

/// Make discovery reply message.
/// Створити повідомлення відповіді виявлення.
pub fn make_reply(swarm_id: &str, tcp_port: u16) -> Vec<u8> {
    // Format reply as b"DANTE-HERE\t<swarm_id>\t<tcp_port>\n" / Відформатувати відповідь як b"DANTE-HERE\t<swarm_id>\t<tcp_port>\n"
    format!("DANTE-HERE\t{}\t{}\n", swarm_id, tcp_port).into_bytes()
}

/// Parse discovery reply datagram, returning TCP port if valid.
/// Розібрати датаграму відповіді виявлення, повертаючи TCP-порт, якщо вона дійсна.
pub fn parse_reply(datagram: &[u8], swarm_id: &str) -> Option<u16> {
    // Convert datagram to text / Перетворити датаграму на текст
    let text = std::str::from_utf8(datagram).ok()?;
    // Trim trailing newline if present / Обрізати завершальний новий рядок, якщо він є
    let text = text.strip_suffix('\n').unwrap_or(text);
    // Split by tab / Розділити за табуляцією
    let parts: Vec<&str> = text.split('\t').collect();
    if parts.len() != 3 {
        return None;
    }
    if parts[0] != "DANTE-HERE" {
        return None;
    }
    if parts[1] != swarm_id {
        return None;
    }
    // Parse tcp_port / Розібрати tcp_port
    let port = parts[2].parse::<u16>().ok()?;
    if port == 0 {
        return None;
    }
    Some(port)
}

/// Spawn a coordinator responder thread.
/// Запустити потік відповідача координатора.
pub fn spawn_responder(bind: &str, swarm_id: &str, tcp_port: u16) -> io::Result<(SocketAddr, JoinHandle<()>)> {
    // Bind UDP socket / Прив'язати UDP-сокет
    let socket = UdpSocket::bind(bind)?;
    socket.set_read_timeout(Some(Duration::from_millis(500)))?;
    let local_addr = socket.local_addr()?;
    let swarm_id = swarm_id.to_string();
    let reply_bytes = make_reply(&swarm_id, tcp_port);

    // Spawn responder thread / Запустити потік відповідача
    let handle = thread::spawn(move || {
        let mut buf = [0u8; 1024];
        loop {
            match socket.recv_from(&mut buf) {
                Ok((amt, src)) => {
                    let datagram = &buf[..amt];
                    // Check if datagram is a valid request for our swarm / Перевірити, чи є датаграма дійсним запитом для нашого рою
                    if let Ok(text) = std::str::from_utf8(datagram) {
                        let text = text.strip_suffix('\n').unwrap_or(text);
                        let parts: Vec<&str> = text.split('\t').collect();
                        if parts.len() == 2 && parts[0] == "DANTE-WHO" && parts[1] == swarm_id {
                            let _ = socket.send_to(&reply_bytes, src);
                        }
                    }
                }
                Err(e) => {
                    // Ignore retryable errors / Ігнорувати повторювані помилки
                    if is_retryable(&e) {
                        continue;
                    }
                    // For other errors, just continue to keep responder alive / Для інших помилок продовжувати роботу
                }
            }
        }
    });

    Ok((local_addr, handle))
}

/// Discover coordinator in the local network.
/// Знайти координатора в локальній мережі.
pub fn discover(swarm_id: &str, targets: &[SocketAddr], timeout: Duration) -> io::Result<Option<SocketAddr>> {
    // Create UDP socket / Створити UDP-сокет
    let socket = UdpSocket::bind("0.0.0.0:0")?;
    socket.set_broadcast(true)?;
    socket.set_read_timeout(Some(Duration::from_millis(100)))?;

    let request_bytes = make_request(swarm_id);
    let start_time = Instant::now();

    // Initial pause is 0.1 s, doubling each time / Початкова пауза становить 0.1 с, подвоюючись щоразу
    let mut current_pause = Duration::from_millis(100);
    let mut next_send = start_time;

    while start_time.elapsed() < timeout {
        // Send request to all targets if it is time / Надіслати запит на всі цілі, якщо настав час
        let now = Instant::now();
        if now >= next_send {
            for target in targets {
                let _ = socket.send_to(&request_bytes, target);
            }
            next_send = now + current_pause;
            // Double the pause, but keep it bounded or growing / Подвоїти паузу, але тримати її зростаючою
            current_pause *= 2;
        }

        // Calculate remaining time until timeout or next send / Обчислити час, що залишився до тайм-ауту або наступного надсилання
        let remaining_total = timeout.saturating_sub(start_time.elapsed());
        let remaining_until_send = next_send.saturating_duration_since(Instant::now());
        let wait_duration = remaining_total.min(remaining_until_send).min(Duration::from_millis(100));

        if wait_duration > Duration::ZERO {
            let _ = socket.set_read_timeout(Some(wait_duration));
        }

        let mut buf = [0u8; 1024];
        match socket.recv_from(&mut buf) {
            Ok((amt, src)) => {
                if let Some(tcp_port) = parse_reply(&buf[..amt], swarm_id) {
                    return Ok(Some(SocketAddr::new(src.ip(), tcp_port)));
                }
            }
            Err(e) => {
                if is_retryable(&e) {
                    continue;
                }
                return Err(e);
            }
        }
    }

    Ok(None)
}
