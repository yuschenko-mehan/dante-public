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
    eprintln!("Usage: murakha --coordinator HOST|auto [--swarm ID] [--once] [--heal-dir DIR] [--silence SECONDS]");
    eprintln!("       murakha --serve PORT [--swarm ID] [--tasks FILE] [--ant-port PORT] [--heart-dir DANTE_DIR]");
    eprintln!("       murakha --restore-dante OUT_DIR --heal-dir DIR");
    eprintln!("Використання: murakha --coordinator HOST|auto [--swarm ID] [--once]");
    eprintln!("            murakha --serve PORT [--swarm ID] [--tasks FILE]");
    process::exit(1);
}

fn main() {
    // Collect arguments, skipping the program name.
    // Збираємо аргументи, пропускаючи назву програми.
    let args: Vec<String> = env::args().skip(1).collect();

    // Restore DANTE from the heart kept by this ant / Відновити Данте із серця, яке зберігає ця мураха
    if let Some(pos) = args.iter().position(|a| a == "--restore-dante") {
        let out = args.get(pos + 1).cloned().unwrap_or_else(|| print_usage_and_exit());
        let dir = args.iter().position(|a| a == "--heal-dir").and_then(|i| args.get(i + 1)).cloned()
            .unwrap_or_else(|| print_usage_and_exit());
        let bundle = match murakha::survive::latest(&std::path::Path::new(&dir).join("heart")) {
            Some(b) => b,
            None => { eprintln!("No heart of DANTE here / Тут немає серця Данте: {}", dir); process::exit(1); }
        };
        match murakha::heart::unpack(&bundle, std::path::Path::new(&out)) {
            Ok(n) => {
                println!("DANTE restored: {} files in {} / Данте відновлено: {} файлів у {}", n, out, n, out);
                println!("Next: add your keys (keys.txt), then run Dante.bat / Далі: впишіть ключі (keys.txt) і запустіть Dante.bat");
                process::exit(0);
            }
            Err(e) => { eprintln!("Broken heart / Пошкоджене серце: {}", e); process::exit(1); }
        }
    }

    // Detect the new `--serve` mode early.
    // Виявити новий режим `--serve` на початку.
    if let Some(pos) = args.iter().position(|a| a == "--serve") {
        // Parse `--serve` arguments.
        // Розпарсити аргументи `--serve`.
        let mut port_opt: Option<String> = None;
        let mut swarm_id: Option<String> = None;
        let mut tasks_file: Option<String> = None;
        let mut ant_port: u16 = 47901;
        let mut heart_dir: Option<String> = None;

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
                "--heart-dir" => {
                    heart_dir = args.get(i + 1).cloned();
                    i += 2;
                }
                "--ant-port" => {
                    ant_port = args.get(i + 1).and_then(|x| x.parse::<u16>().ok()).unwrap_or(47901);
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

        serving.queue.set_swarm(&swarm);
        serving.queue.set_ant_port(ant_port);
        if let Some(dir) = heart_dir {
            // Pack the heart of DANTE for every ant (keys are never packed)
            // Запакувати серце Данте для кожної мурахи (ключі ніколи не пакуються)
            match murakha::heart::pack(std::path::Path::new(&dir)) {
                Ok(bundle) => {
                    let version = format!("{:016x}", murakha::survive::checksum(&bundle));
                    let files = murakha::heart::list(&bundle).map(|l| l.len()).unwrap_or(0);
                    serving.queue.set_heart(&version, &bundle, 256 * 1024);
                    println!("Heart of DANTE: {} files, {} KB / Серце Данте: {} файлів, {} КБ", files, bundle.len() / 1024, files, bundle.len() / 1024);
                }
                Err(e) => eprintln!("Cannot pack the heart / Не вдалося запакувати серце: {}", e),
            }
        }
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
    let mut heal_dir: Option<String> = None;
    let mut silence: u64 = 120;

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
            "--heal-dir" => {
                if i + 1 >= args.len() { print_usage_and_exit(); }
                heal_dir = Some(args[i + 1].clone());
                i += 2;
            }
            "--silence" => {
                silence = args.get(i + 1).and_then(|x| x.parse().ok()).unwrap_or(120);
                i += 2;
            }
            "--help" | "-h" => {
                // Show usage and exit successfully.
                // Показати інструкції та успішно завершити.
                println!("murakha --coordinator HOST|auto [--swarm ID] [--once] [--heal-dir DIR] [--silence SECONDS]");
                println!("murakha --serve PORT [--swarm ID] [--tasks FILE] [--ant-port PORT]");
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
    if let Some(dir) = heal_dir {
        let cfg = murakha::life::LifeCfg {
            coordinator: addr, heal_dir: std::path::PathBuf::from(dir), silence: Duration::from_secs(silence),
            io_timeout: Duration::from_secs(60), probe_timeout: Duration::from_secs(2), round_pause: Duration::from_secs(2), max_rounds: 30,
        };
        let serving = match murakha::life::live(&cfg) {
            Ok(s) => s,
            Err(e) => { eprintln!("Heal error: {} / Помилка відновлення: {}", e, e); process::exit(1); }
        };
        let me = serving.addr.to_string();
        println!("This ant is now the coordinator at {} / Ця мураха тепер координатор на {}", me, me);
        thread::spawn(move || ant::run_ant_loop(&me, false));
        let mut printed = 0usize;
        loop {
            let results = serving.queue.results();
            for res in results.iter().skip(printed) { println!("Result: {:?} / Результат: {:?}", res, res); }
            printed = results.len();
            thread::sleep(Duration::from_secs(1));
        }
    }
    ant::run_ant_loop(&addr, once);
}
