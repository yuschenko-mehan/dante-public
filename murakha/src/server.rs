//! Server module implementing the task queue and coordinator server.
//! Модуль сервера, що реалізує чергу завдань та сервер координатора.

use std::collections::HashMap;
use std::io::{self, BufRead, BufReader, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use crate::protocol::{AntMessage, CoordMessage, hex_decode};

/// Task result structure.
/// Структура результату завдання.
#[derive(Clone, Debug)]
pub struct TaskResult {
    pub task_id: String,
    pub ant_id: String,
    pub exit_code: i32,
    pub output: String,
}

/// Internal task representation.
/// Внутрішнє представлення завдання.
#[derive(Clone, Debug)]
struct Task {
    id: String,
    command: String,
    timeout_s: u64,
}

/// Inner state of the TaskQueue.
/// Внутрішній стан черги завдань.
struct TaskQueueInner {
    tasks: Vec<Task>,
    results: Vec<TaskResult>,
    ants: HashMap<String, InstantPlaceholder>, // ant_id -> placeholder
    active_tasks: HashMap<String, (String, Task)>, // ant_id -> (task_id, task)
    next_id: usize,
}

/// Placeholder struct for ant tracking.
/// Структура-заповнювач для відстеження мурах.
#[derive(Clone, Debug)]
struct InstantPlaceholder {}

/// Shared thread-safe TaskQueue handle.
/// Спільний потокобезпечний дескриптор TaskQueue.
#[derive(Clone)]
pub struct TaskQueue {
    inner: Arc<Mutex<TaskQueueInner>>,
}

impl TaskQueue {
    /// Push a new task to the queue and return its unique ID.
    /// Додати нове завдання до черги та повернути його унікальний ID.
    pub fn push(&self, command: &str, timeout_s: u64) -> String {
        let mut inner = self.inner.lock().unwrap();
        inner.next_id += 1;
        let id = format!("t{}", inner.next_id);
        inner.tasks.push(Task {
            id: id.clone(),
            command: command.to_string(),
            timeout_s,
        });
        id
    }

    /// Return number of pending tasks.
    /// Повернути кількість очікуючих завдань.
    pub fn pending(&self) -> usize {
        let inner = self.inner.lock().unwrap();
        inner.tasks.len()
    }

    /// Return all stored results.
    /// Повернути всі збережені результати.
    pub fn results(&self) -> Vec<TaskResult> {
        let inner = self.inner.lock().unwrap();
        inner.results.clone()
    }

    /// Return IDs of ants that said HELLO.
    /// Повернути ID мурах, які сказали HELLO.
    pub fn ants(&self) -> Vec<String> {
        let inner = self.inner.lock().unwrap();
        let mut ants: Vec<String> = inner.ants.keys().cloned().collect();
        ants.sort();
        ants
    }
}

/// Server struct for handling connections.
/// Структура сервера для обробки з'єднань.
pub struct Server {
    listener: TcpListener,
    queue: TaskQueue,
}

impl Server {
    /// Bind server to an address.
    /// Прив'язати сервер до адреси.
    pub fn bind(addr: &str) -> io::Result<Server> {
        let listener = TcpListener::bind(addr)?;
        let queue = TaskQueue {
            inner: Arc::new(Mutex::new(TaskQueueInner {
                tasks: Vec::new(),
                results: Vec::new(),
                ants: HashMap::new(),
                active_tasks: HashMap::new(),
                next_id: 0,
            })),
        };
        Ok(Server { listener, queue })
    }

    /// Return local address of the server.
    /// Повернути локальну адресу сервера.
    pub fn local_addr(&self) -> SocketAddr {
        self.listener.local_addr().unwrap()
    }

    /// Return a clone of the task queue.
    /// Повернути копію черги завдань.
    pub fn queue(&self) -> TaskQueue {
        self.queue.clone()
    }

    /// Spawn the accept loop in a background thread.
    /// Запустити цикл прийняття з'єднань у фоновому потоці.
    pub fn spawn(self) -> JoinHandle<()> {
        let listener = self.listener;
        let queue = self.queue;
        thread::spawn(move || {
            for stream in listener.incoming() {
                match stream {
                    Ok(stream) => {
                        let q = queue.clone();
                        thread::spawn(move || {
                            if let Err(e) = handle_connection(stream, q) {
                                let _ = e; // Ignore connection errors / Ігнорувати помилки з'єднання
                            }
                        });
                    }
                    Err(_) => {
                        break;
                    }
                }
            }
        })
    }
}

/// Handle an individual ant connection session.
/// Обробити окрему сесію з'єднання з мурахою.
fn handle_connection(stream: TcpStream, queue: TaskQueue) -> io::Result<()> {
    stream.set_read_timeout(Some(Duration::from_secs(10)))?;
    stream.set_write_timeout(Some(Duration::from_secs(10)))?;

    let mut reader = BufReader::new(stream.try_clone()?);
    let mut writer = stream;

    let mut current_ant_id: Option<String> = None;
    let mut line_buf = Vec::new();

    loop {
        line_buf.clear();
        // Read raw bytes until newline to handle invalid UTF-8 gracefully
        // Читаємо сирі байти до нового рядка, щоб коректно обробляти недійсний UTF-8
        match reader.read_until(b'\n', &mut line_buf) {
            Ok(0) => break, // EOF / Кінець файлу
            Ok(_) => {
                // Try to convert to string, skip line if invalid UTF-8
                // Спробуємо перетворити на рядок, пропускаємо рядок якщо недійсний UTF-8
                let line_str = match std::str::from_utf8(&line_buf) {
                    Ok(s) => s.trim_end_matches(['\r', '\n']),
                    Err(_) => continue, // Ignore broken lines / Ігнорувати зламані рядки
                };
                if line_str.is_empty() {
                    continue;
                }
                match AntMessage::parse(line_str) {
                    Ok(AntMessage::Hello { id, .. }) => {
                        current_ant_id = Some(id.clone());
                        let mut inner = queue.inner.lock().unwrap();
                        inner.ants.insert(id, InstantPlaceholder {});
                    }
                    Ok(AntMessage::Ask { id }) => {
                        if current_ant_id.is_none() {
                            current_ant_id = Some(id.clone());
                        }
                        let mut inner = queue.inner.lock().unwrap();
                        inner.ants.entry(id.clone()).or_insert(InstantPlaceholder {});

                        if let Some(task) = inner.tasks.pop() {
                            let task_id = task.id.clone();
                            let timeout_s = task.timeout_s;
                            let command = task.command.clone();
                            inner.active_tasks.insert(id.clone(), (task_id.clone(), task));
                            let msg = CoordMessage::Task {
                                task_id,
                                timeout_s,
                                command,
                            };
                            let _ = writeln!(writer, "{}", msg.to_line());
                        } else {
                            let msg = CoordMessage::Wait { seconds: 5 };
                            let _ = writeln!(writer, "{}", msg.to_line());
                        }
                    }
                    Ok(AntMessage::Result { id, task_id, exit_code, output }) => {
                        let decoded_bytes = hex_decode(&output).unwrap_or_default();
                        let decoded_text = String::from_utf8_lossy(&decoded_bytes).to_string();

                        let mut inner = queue.inner.lock().unwrap();
                        inner.ants.entry(id.clone()).or_insert(InstantPlaceholder {});
                        inner.active_tasks.remove(&id);

                        inner.results.push(TaskResult {
                            task_id,
                            ant_id: id,
                            exit_code,
                            output: decoded_text,
                        });
                    }
                    Ok(AntMessage::Beat { id }) => {
                        let mut inner = queue.inner.lock().unwrap();
                        inner.ants.entry(id).or_insert(InstantPlaceholder {});
                    }
                    Err(_) => {
                        // Broken or unknown line - ignore, never panic / Зламаний або невідомий рядок — ігнорувати, ніколи не панікувати
                    }
                }
            }
            Err(_) => break,
        }
    }

    // If ant disconnects without a RESULT, put its active task back to the queue
    // Якщо мураха від'єднується без RESULT, повернути її активне завдання назад до черги
    if let Some(ref ant_id) = current_ant_id {
        let mut inner = queue.inner.lock().unwrap();
        if let Some((_, task)) = inner.active_tasks.remove(ant_id) {
            inner.tasks.push(task);
        }
    }

    Ok(())
}

