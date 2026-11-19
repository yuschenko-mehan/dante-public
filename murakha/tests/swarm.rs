/// Integration test for the swarm: coordinator + multiple ants.
/// Інтеграційний тест для рою: координатор + кілька мурах.

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use murakha::ant;
use murakha::coordinator;

#[test]
/// Integration test for the swarm with deadline, thread timeout safety, and result content checks.
/// Інтеграційний тест для рою з дедлайном, безпекою таймаутів потоків та перевіркою вмісту результатів.
fn test_swarm() {
    // Create coordinator bound to OS-assigned port / Створити координатор, прив'язаний до порту, вибраного ОС
    let coord = coordinator::Coordinator::new("127.0.0.1:0").expect("Failed to create coordinator");
    let coord_addr = coord.listener.local_addr().expect("Failed to get local address").to_string();

    // Clone shared state / Клонувати спільний стан
    let tasks = Arc::clone(&coord.tasks);
    let results = Arc::clone(&coord.results);

    // Add three tasks to the queue / Додати три завдання до черги
    {
        let mut queue = tasks.lock().unwrap();
        queue.push_back("task1\t10\techo task1".to_string());
        queue.push_back("task2\t10\techo task2".to_string());
        queue.push_back("task3\t10\techo task3".to_string());
    }

    // Start coordinator thread / Запустити потік координатора
    let _coord_thread = thread::spawn(move || {
        let _ = coord.run();
    });

    // Spawn 3 ants in separate threads / Запустити 3 мурахи в окремих потоках
    let mut handles = vec![];
    for i in 0..3 {
        let addr = coord_addr.clone();
        let handle = thread::spawn(move || {
            let _ = ant::run_session(&addr, &format!("ant-{}", i), true);
        });
        handles.push(handle);
    }

    // Join ant threads with a deadline and polling is_finished / Приєднати потоки мурах з дедлайном та опитуванням is_finished
    let deadline = Instant::now() + Duration::from_secs(5);
    for handle in handles {
        loop {
            if handle.is_finished() {
                let _ = handle.join();
                break;
            }
            if Instant::now() >= deadline {
                panic!("Test timed out waiting for ant threads / Тест перевищив таймаут очікування потоків мурах");
            }
            thread::sleep(Duration::from_millis(50));
        }
    }

    // Verify results with deadline / Перевірити результати з дедлайном
    let start_wait = Instant::now();
    loop {
        let count = results.lock().unwrap().len();
        if count >= 3 || start_wait.elapsed() > Duration::from_secs(3) {
            break;
        }
        thread::sleep(Duration::from_millis(50));
    }

    let results_locked = results.lock().unwrap();
    assert!(results_locked.len() >= 3, "Expected at least 3 results, got {} / Очікувалося принаймні 3 результати", results_locked.len());

    // Check that results contain task1, task2 and task3 / Перевірити, що результати містять task1, task2 та task3
    let combined_results = results_locked.join("\n");
    assert!(combined_results.contains("task1"), "Results must contain task1 / Результати повинні містити task1");
    assert!(combined_results.contains("task2"), "Results must contain task2 / Результати повинні містити task2");
    assert!(combined_results.contains("task3"), "Results must contain task3 / Результати повинні містити task3");
}
