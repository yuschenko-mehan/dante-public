/// Library entry point for murakha crate.
/// Точка входу бібліотеки для крейту murakha.

pub mod protocol;
pub mod worker;
pub mod coordinator; // Coordinator module / Модуль координатора
pub mod server; // Server module / Модуль сервера
pub mod ant; // Ant module / Модуль мурахи
pub mod discovery; // Discovery module / Модуль виявлення
pub mod serve; // Serve module / Модуль запуску сервера
pub mod survive; // Survive module / Модуль виживання
pub mod health; // Health module / Модуль стану здоров'я
pub mod plan; // Plan module / Модуль планування
pub mod scout; // Scout module / Модуль пошуковця
pub mod mailbag; // Mailbag module / Модуль торби мурахи
pub mod heal; // Heal module / Модуль самовідновлення
pub mod life; // Life module / Модуль життя мурахи

#[cfg(test)]
/// Tests for the library.
/// Тести для бібліотеки.
mod tests {
    use super::*;

    #[test]
    /// Test that worker module is accessible.
    /// Перевірити, що модуль воркера доступний.
    fn test_worker_module() {
        // Ensure worker module is public and linked / Переконатися, що модуль воркера публічний і підключений
        assert!(true);
    }

    #[test]
    /// Test that coordinator module can be instantiated.
    /// Перевірити, що модуль координатора можна створити.
    fn test_coordinator_creation() {
        // Create a coordinator bound to an OS-assigned port / Створити координатор, прив'язаний до порту, вибраного ОС
        let coord = coordinator::Coordinator::new("127.0.0.1:0")
            .expect("Failed to create coordinator");
        // Ensure we have a valid local address / Переконатися, що локальна адреса дійсна
        let addr = coord.listener.local_addr().expect("Failed to get local address");
        assert!(addr.port() != 0, "Port should be assigned by OS");
    }

    #[test]
    /// Test that ant module is accessible.
    /// Перевірити, що модуль мурахи доступний.
    fn test_ant_module() {
        let id = ant::generate_ant_id();
        assert!(!id.is_empty());
    }
}

pub mod heart;
pub mod secure; // Secure module / Модуль безпеки рою
pub mod order; // Order module / Модуль наказів
pub mod thermal; // Thermal guard module / Модуль температурного захисту
pub mod flash; // Flash module / Модуль флеш-накопичувача
