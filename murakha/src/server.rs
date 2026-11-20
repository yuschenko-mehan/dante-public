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
    swarm: String,
    ant_port: u16,
    order: Vec<(String, String)>,
    heart: Option<(String, Vec<Vec<u8>>)>,
    swarm_key: Option<Vec<u8>>,
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
    pub fn set_swarm(&self, swarm: &str) { self.inner.lock().unwrap().swarm = swarm.to_string(); }
    pub fn set_swarm_key(&self, key: Vec<u8>) {
        self.inner.lock().unwrap().swarm_key = Some(key);
    }
    pub fn set_heart(&self, version: &str, bundle: &[u8], chunk_size: usize) {
        self.inner.lock().unwrap().heart = Some((version.to_string(), crate::heart::chunks(bundle, chunk_size)));
    }
    pub fn set_ant_port(&self, port: u16) { self.inner.lock().unwrap().ant_port = port; }
    pub fn snapshot_for(&self, coord_addr: &str) -> crate::heal::Snapshot {
        let inner = self.inner.lock().unwrap();
        let mut peers = vec![("coord".to_string(), coord_addr.to_string())];
        for (id, ip) in &inner.order { peers.push((id.clone(), format!("{}:{}", ip, inner.ant_port))); }
        let mut tasks: Vec<String> = inner.tasks.iter().map(|t| t.command.clone()).collect();
        for (_, (_, t)) in &inner.active_tasks { tasks.push(t.command.clone()); }
        crate::heal::Snapshot { swarm: inner.swarm.clone(), peers, tasks }
    }

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
                swarm: "dante".to_string(),
                ant_port: 47901,
                order: Vec::new(),
                heart: None,
                swarm_key: None,
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
pub fn wants_snapshots(version: &str) -> bool {
    let mut it = version.split('.');
    let major = it.next().and_then(|x| x.parse::<u64>().ok());
    let minor = it.next().and_then(|x| x.parse::<u64>().ok());
    match (major, minor) { (Some(a), Some(b)) => (a, b) >= (0, 3), _ => false }
}

fn send_line(w: &mut TcpStream, chan: &mut Option<crate::secure::Channel>, line: &str) {
    // Signed when the swarm key is on / Підписано, коли ключ рою увімкнено
    let out = match chan { Some(c) => c.seal(line), None => line.to_string() };
    let _ = writeln!(w, "{}", out);
}

fn handle_connection(stream: TcpStream, queue: TaskQueue) -> io::Result<()> {
    let key = queue.inner.lock().unwrap().swarm_key.clone();
    let mut chan: Option<crate::secure::Channel> = None;
    let mut nonce_c: Option<String> = None;
    let local = stream.local_addr()?.to_string();
    let peer_ip = stream.peer_addr()?.ip().to_string();
    let mut snaps = false;
    let mut asks: u64 = 0;
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
                let raw = match std::str::from_utf8(&line_buf) {
                    Ok(s) => s.trim_end_matches(['\r', '\n']).to_string(),
                    Err(_) => continue, // Ignore broken lines / Ігнорувати зламані рядки
                };
                if raw.is_empty() {
                    continue;
                }
                let opened;
                let line_str: &str = if let Some(c) = chan.as_mut() {
                    match c.open(&raw) { Ok(l) => { opened = l; &opened } Err(_) => break }
                } else { &raw };
                if let (Some(k), Some(nc)) = (key.as_ref(), nonce_c.as_ref()) {
                    if chan.is_none() {
                        // Waiting for the ant's proof / Чекаємо доказ від мурахи
                        let f: Vec<&str> = line_str.split('\t').collect();
                        let id = current_ant_id.clone().unwrap_or_default();
                        if f.len() == 3 && f[0] == "AUTH" && crate::secure::eq_ct(&crate::secure::ant_proof(k, nc, f[1], &id), f[2]) {
                            let _ = writeln!(writer, "AUTH\t{}", crate::secure::coord_proof(k, nc, f[1]));
                            chan = Some(crate::secure::Channel::new(crate::secure::session_key(k, nc, f[1]), false));
                            continue;
                        }
                        let _ = writeln!(writer, "BYE");
                        break;
                    }
                }
                if key.is_some() && nonce_c.is_none() && !line_str.starts_with("HELLO\t") {
                    let _ = writeln!(writer, "BYE");
                    break;
                }
                match AntMessage::parse(line_str) {
                    Ok(AntMessage::Hello { id, version, .. }) => {
                        current_ant_id = Some(id.clone());
                        snaps = wants_snapshots(&version);
                        let mut inner = queue.inner.lock().unwrap();
                        if !inner.order.iter().any(|(i, _)| i == &id) { inner.order.push((id.clone(), peer_ip.clone())); }
                        inner.ants.insert(id, InstantPlaceholder {});
                        drop(inner);
                        if key.is_some() && nonce_c.is_none() {
                            let nc = crate::secure::nonce();
                            let _ = writeln!(writer, "CHAL\t{}", nc);
                            nonce_c = Some(nc);
                        }
                    }
                    Ok(AntMessage::Ask { id }) => {
                        if current_ant_id.is_none() {
                            current_ant_id = Some(id.clone());
                        }
                        asks += 1;
                        if snaps && asks >= 2 {
                            let chunk = {
                                let inner = queue.inner.lock().unwrap();
                                inner.heart.as_ref().and_then(|(v, parts)| {
                                    let i = (asks - 2) as usize;
                                    parts.get(i).map(|c| CoordMessage::Heart { version: v.clone(), index: i as u32, total: parts.len() as u32, data: crate::protocol::hex_encode(c) })
                                })
                            };
                            if let Some(msg) = chunk {
                                send_line(&mut writer, &mut chan, &msg.to_line());
                                continue;
                            }
                        }
                        if snaps && asks % 20 == 1 {
                            let snap = crate::heal::encode(&queue.snapshot_for(&local));
                            let msg = CoordMessage::Snap { data: crate::protocol::hex_encode(&snap) };
                            send_line(&mut writer, &mut chan, &msg.to_line());
                            continue;
                        }
                        let mut inner = queue.inner.lock().unwrap();
                        inner.ants.entry(id.clone()).or_insert(InstantPlaceholder {});

                        if let Some(task) = if inner.tasks.is_empty() { None } else { Some(inner.tasks.remove(0)) } {
                            let task_id = task.id.clone();
                            let timeout_s = task.timeout_s;
                            let command = task.command.clone();
                            inner.active_tasks.insert(id.clone(), (task_id.clone(), task));
                            let msg = CoordMessage::Task {
                                task_id,
                                timeout_s,
                                command,
                            };
                            send_line(&mut writer, &mut chan, &msg.to_line());
                        } else {
                            let msg = CoordMessage::Wait { seconds: 5 };
                            send_line(&mut writer, &mut chan, &msg.to_line());
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

