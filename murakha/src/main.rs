/// Entry point for the murakha CLI.
/// Точка входу для CLI murakha.
use std::env;
use std::process;
use std::time::Duration;
use std::thread;
use std::fs;

use murakha::ant;
use murakha::discovery;
use murakha::serve;

/// Simple command-line argument parser supporting:
///   --coordinator HOST:PORT or auto (required)
///   --swarm ID                      (optional, default "dante")
///   --once                          (optional flag)
///   --serve PORT [--swarm ID] [--tasks FILE] (new mode)
/// Prints usage and exits on error.
/// Простий парсер аргументів командного рядка, що підтримує:
///   --coordinator HOST:PORT або auto (обов'язковий)
///   --swarm ID                      (необов'язковий, за замовчуванням "dante")
///   --once                          (необов'язковий прапорець)
///   --serve PORT [--swarm ID] [--tasks FILE] (новий режим)
///   Виводить інструкції та завершує роботу при помилці.
fn print_usage_and_exit() -> ! {
    eprintln!("Usage: murakha --coordinator HOST|auto [--swarm ID] [--once]");
    eprintln!("       murakha --serve PORT [--swarm ID] [--tasks FILE]");
    eprintln!("Використання: murakha --coordinator HOST|auto [--swarm ID] [--once]");
    eprintln!("            murakha --serve PORT [--swarm ID] [--tasks FILE]");
    process::exit(1);
}

fn main() {
    // Collect arguments, skipping the program name.
    // Збираємо аргументи, пропускаючи назву програми.
    let args: Vec<String> = env::args().skip(1).collect();

    // Detect the new `--serve` mode early.
    // Виявити новий режим `--serve` на початку.
    if let Some(pos) = args.iter().position(|a| a == "--serve") {
        // Parse `--serve` arguments.
        // Розпарсити аргументи `--serve`.
        let mut port_opt: Option<String> = None;
        let mut swarm_id: Option<String> = None;
        let mut tasks_file: Option<String> = None;

        let mut i = pos + 1;
        while i < args.len() {
            match args[i].as_str() {
                "--swarm" => {
                    if i + 1 >= args.len() {
                        eprintln!("Error: --swarm requires an ID / Помилка: --swarm вимагає ідентифікатор");
                        print_usage_and_exit();
                    }
                    swarm_id = Some(args[i + 1].clone());
                    i += 2;
                }
                "--tasks" => {
                    if i + 1 >= args.len() {
                        eprintln!("Error: --tasks requires a file path / Помилка: --tasks вимагає шлях до файлу");
                        print_usage_and_exit();
                    }
                    tasks_file = Some(args[i + 1].clone());
                    i += 2;
                }
                other => {
                    // Assume the first non-flag after --serve is the port.
                    // Припустити, що перший аргумент без '--' після --serve — це порт.
                    if port_opt.is_none() && !other.starts_with("--") {
                        port_opt = Some(other.to_string());
                        i += 1;
                    } else {
                        eprintln!("Unknown argument: {} / Невідомий аргумент: {}", other, other);
                        print_usage_and_exit();
                    }
                }
            }
        }

        let port = match port_opt {
            Some(p) => p,
            None => {
                eprintln!("Error: PORT is required after --serve / Помилка: після --serve потрібен PORT");
                print_usage_and_exit();
            }
        };

        let swarm = swarm_id.unwrap_or_else(|| "dante".to_string());

        // Load tasks if a file was supplied.
        // Завантажити завдання, якщо вказано файл.
        let tasks: Vec<String> = if let Some(path) = tasks_file {
            match fs::read_to_string(&path) {
                Ok(content) => serve::load_tasks(&content),
                Err(e) => {
                    eprintln!("Failed to read tasks file '{}': {} / Не вдалося прочитати файл завдань '{}': {}", path, e, path, e);
                    print_usage_and_exit();
                }
            }
        } else {
            Vec::new()
        };

        // Start the server.
        // Запустити сервер.
        let bind_addr = format!("0.0.0.0:{}", port);
        let discovery_bind = Some("0.0.0.0:47900");
        let serving = match serve::start(&bind_addr, &swarm, &tasks, discovery_bind) {
            Ok(s) => s,
            Err(e) => {
                eprintln!("Failed to start server: {} / Не вдалося запустити сервер: {}", e, e);
                process::exit(1);
            }
        };

        // Print address and short progress.
        // Вивести адресу та короткий прогрес.
        println!("Server listening on {} / Сервер слухає на {}", serving.addr, serving.addr);
        println!("Swarm ID: {} / Ідентифікатор рою: {}", swarm, swarm);
        println!("Tasks loaded: {} / Завантажено завдань: {}", tasks.len(), tasks.len());

        // Poll results every second and print new ones.
        // Опитувати результати кожну секунду та виводити нові.
        let mut printed = 0usize;
        loop {
            // Retrieve current results.
            // Отримати поточні результати.
            let results = serving.queue.results();
            if printed < results.len() {
                for res in results.iter().skip(printed) {
                    // Use Debug formatting as TaskResult may not implement Display.
                    // Використовуємо форматування Debug, оскільки TaskResult може не мати Display.
                    println!("Result: {:?} / Результат: {:?}", res, res);
                }
                printed = results.len();
            }
            // Sleep for a second.
            // Пауза на секунду.
            thread::sleep(Duration::from_secs(1));
        }
    }

    // Existing ant mode parsing.
    // Існуючий парсер режиму мурахи.
    let mut coordinator_arg: Option<String> = None;
    let mut swarm_id: Option<String> = None;
    let mut once = false;

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--coordinator" => {
                // Need a following argument with the address or auto.
                // Потрібен наступний аргумент з адресою або auto.
                if i + 1 >= args.len() {
                    eprintln!("Error: --coordinator requires an address or 'auto' / Помилка: --coordinator вимагає адресу або 'auto'");
                    print_usage_and_exit();
                }
                coordinator_arg = Some(args[i + 1].clone());
                i += 2;
            }
            "--swarm" => {
                // Need a following argument with the swarm ID.
                // Потрібен наступний аргумент з ідентифікатором рою.
                if i + 1 >= args.len() {
                    eprintln!("Error: --swarm requires an ID / Помилка: --swarm вимагає ідентифікатор");
                    print_usage_and_exit();
                }
                swarm_id = Some(args[i + 1].clone());
                i += 2;
            }
            "--once" => {
                once = true;
                i += 1;
            }
            "--help" | "-h" => {
                // Show usage and exit successfully.
                // Показати інструкції та успішно завершити.
                println!("murakha --coordinator HOST|auto [--swarm ID] [--once]");
                println!("murakha --serve PORT [--swarm ID] [--tasks FILE]");
                return;
            }
            unknown => {
                eprintln!("Unknown argument: {} / Невідомий аргумент: {}", unknown, unknown);
                print_usage_and_exit();
            }
        }
    }

    // Ensure the required coordinator argument was provided.
    // Переконайтеся, що вказано обов'язковий аргумент координатора.
    let coord_val = match coordinator_arg {
        Some(a) => a,
        None => {
            eprintln!("Error: --coordinator argument is required / Помилка: аргумент --coordinator є обов'язковим");
            print_usage_and_exit();
        }
    };

    let swarm = swarm_id.unwrap_or_else(|| "dante".to_string());

    // Resolve coordinator address: if "auto", discover via UDP discovery; otherwise use directly.
    // Визначити адресу координатора: якщо "auto", виконати пошук через UDP-виявлення; інакше використовувати напряму.
    let addr = if coord_val == "auto" {
        eprintln!("Discovering coordinator for swarm '{}'...", swarm);
        eprintln!("Пошук координатора для рою '{}'...", swarm);
        
        let targets = discovery::default_targets();
        match discovery::discover(&swarm, &targets, Duration::from_secs(5)) {
            Ok(Some(socket_addr)) => {
                let resolved = socket_addr.to_string();
                eprintln!("Discovered coordinator at {}", resolved);
                eprintln!("Знайдено координатора на {}", resolved);
                resolved
            }
            Ok(None) => {
                eprintln!("Error: Coordinator not found for swarm '{}'", swarm);
                eprintln!("Помилка: Координатора не знайдено для рою '{}'", swarm);
                process::exit(2);
            }
            Err(e) => {
                eprintln!("Error during coordinator discovery: {}", e);
                eprintln!("Помилка під час пошуку координатора: {}", e);
                process::exit(2);
            }
        }
    } else {
        coord_val
    };

    // Start the ant loop with the resolved parameters.
    // Запускаємо цикл мурахи з отриманими параметрами.
    ant::run_ant_loop(&addr, once);
}
