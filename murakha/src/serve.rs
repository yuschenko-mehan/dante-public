//! Serve module implementing one-command coordinator launch and task loading.
//! Модуль serve, що реалізує запуск координатора однією командою та завантаження завдань.

use std::io;
use std::net::SocketAddr;

use crate::discovery;
use crate::server::{Server, TaskQueue};

/// Serving structure holding server details and queue.
/// Структура Serving, що містить деталі сервера та чергу.
pub struct Serving {
    pub addr: SocketAddr,
    pub discovery_addr: Option<SocketAddr>,
    pub queue: TaskQueue,
}

/// Load tasks from text content. One command per line, trimmed, empty lines and lines starting with '#' skipped.
/// Завантажити завдання з текстового вмісту. Одна команда на рядок, з обрізаними пробілами; порожні рядки та рядки на '#' пропускаються.
pub fn load_tasks(text: &str) -> Vec<String> {
    let mut tasks = Vec::new();
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        tasks.push(trimmed.to_string());
    }
    tasks
}

/// Start the coordinator server, push tasks, spawn background thread, and optionally start discovery responder.
/// Запустити сервер координатора, додати завдання, запустити фоновий потік та опціонально запустити службу виявлення.
pub fn start(
    bind: &str,
    swarm: &str,
    tasks: &[String],
    discovery_bind: Option<&str>,
) -> io::Result<Serving> {
    // Bind the server (coordinator) to the requested address.
    // Прив'язати сервер (координатор) до вказаної адреси.
    let server = Server::bind(bind)?;
    let addr = server.local_addr();
    let queue = server.queue();
    queue.set_swarm(swarm);

    // Push each task with a timeout of 600 seconds.
    // Додати кожне завдання з тайм-аутом 600 секунд.
    for task in tasks {
        queue.push(task, 600);
    }

    // Run the accept loop in a background thread.
    // Запустити цикл приймання у фоні.
    server.spawn();

    // If discovery is requested, start the responder and obtain its address.
    // Якщо потрібне виявлення, запустити responder і отримати його адресу.
    let discovery_addr = if let Some(d_bind) = discovery_bind {
        // spawn_responder returns (SocketAddr, JoinHandle<()>) / spawn_responder повертає (SocketAddr, JoinHandle<()>)
        let (addr, _handle) = discovery::spawn_responder(d_bind, swarm, addr.port())?;
        Some(addr)
    } else {
        None
    };

    Ok(Serving {
        addr,
        discovery_addr,
        queue,
    })
}

