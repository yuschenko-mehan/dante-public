/// Coordinator module handling ant connections, task queue, and result collection.
/// Модуль координатора, що обробляє підключення мурах, чергу завдань та збір результатів.

use std::collections::VecDeque;
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::{Arc, Mutex};
use std::thread;

/// Public struct representing the coordinator.
/// Публічна структура, що представляє координатор.
pub struct Coordinator {
    /// TCP listener for incoming ant connections.
    /// TCP-слухач для вхідних підключень мурах.
    pub listener: TcpListener,
    /// Queue of tasks to be sent to ants.
    /// Черга завдань, які будуть відправлені мурахам.
    pub tasks: Arc<Mutex<VecDeque<String>>>,
    /// Collected results from ants.
    /// Зібрані результати від мурах.
    pub results: Arc<Mutex<Vec<String>>>,
}

impl Coordinator {
    /// Create a new coordinator bound to the given address.
    /// Створити новий координатор, прив'язаний до вказаної адреси.
    pub fn new(addr: &str) -> std::io::Result<Self> {
        let listener = TcpListener::bind(addr)?;
        let tasks = Arc::new(Mutex::new(VecDeque::new()));
        let results = Arc::new(Mutex::new(Vec::new()));
        Ok(Coordinator {
            listener,
            tasks,
            results,
        })
    }

    /// Start the coordinator loop in the current thread.
    /// Запустити цикл координатора у поточному потоці.
    ///
    /// For each incoming connection, a new thread is spawned to handle the simple
    /// protocol: send a TASK line if available, then read RESULT lines.
    /// Для кожного вхідного підключення створюється новий потік, який обробляє простий
    /// протокол: надсилає рядок TASK, якщо є завдання, потім читає RESULT.
    pub fn run(&self) -> std::io::Result<()> {
        for stream in self.listener.incoming() {
            match stream {
                Ok(stream) => {
                    let tasks = Arc::clone(&self.tasks);
                    let results = Arc::clone(&self.results);
                    thread::spawn(move || {
                        if let Err(e) = handle_connection(stream, tasks, results) {
                            eprintln!("Connection handling error: {}", e);
                        }
                    });
                }
                Err(e) => {
                    eprintln!("Listener error: {}", e);
                }
            }
        }
        Ok(())
    }
}

/// Handle a single ant connection.
/// Обробити одне підключення мурахи.
fn handle_connection(
    mut stream: TcpStream,
    tasks: Arc<Mutex<VecDeque<String>>>,
    results: Arc<Mutex<Vec<String>>>,
) -> std::io::Result<()> {
    // Simple handshake: read a line (e.g., HELLO) and ignore.
    let mut reader = BufReader::new(stream.try_clone()?);
    let mut line = String::new();
    reader.read_line(&mut line)?; // ignore content

    // Send a TASK if any.
    if let Some(task) = tasks.lock().unwrap().pop_front() {
        let task_line = format!("TASK\t{}\n", task);
        stream.write_all(task_line.as_bytes())?;
    } else {
        // No task, send WAIT.
        stream.write_all(b"WAIT\n")?;
    }

    // Read RESULT lines until connection closes.
    loop {
        line.clear();
        let bytes = reader.read_line(&mut line)?;
        if bytes == 0 {
            break; // connection closed
        }
        if line.starts_with("RESULT") {
            results.lock().unwrap().push(line.trim_end().to_string());
        }
    }
    Ok(())
}
