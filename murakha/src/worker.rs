use std::process::{Command, Stdio};
use std::time::{Duration, Instant};
use std::io::Read;
use std::thread;

/// Maximum output size in bytes (64 KB).
/// Максимальний розмір виводу в байтах (64 КБ).
pub const MAX_OUTPUT_SIZE: usize = 64 * 1024;

/// Run a command with a timeout, capture stdout/stderr, enforce 64 KB limit, and return real exit code.
/// Запустити команду з таймаутом, захопити stdout/stderr, обмежити до 64 КБ та повернути реальний код виходу.
pub fn run_command_code(cmd: &str, timeout: Duration) -> Result<(i32, String), String> {
    let start = Instant::now();

    #[cfg(target_os = "windows")]
    let mut child = Command::new("cmd")
        .args(["/C", cmd])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn: {}", e))?;

    #[cfg(not(target_os = "windows"))]
    let mut child = Command::new("sh")
        .args(["-c", cmd])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn: {}", e))?;

    let stdout = child.stdout.take();
    let stderr = child.stderr.take();

    // Read stdout and stderr in separate threads to work even if command prints nothing
    // Читати stdout та stderr в окремих потоках, щоб працювати навіть якщо команда нічого не друкує
    let stdout_handle = stdout.map(|mut s| {
        thread::spawn(move || {
            let mut buf = Vec::new();
            let mut chunk = [0u8; 1024];
            loop {
                match s.read(&mut chunk) {
                    Ok(0) => break,
                    Ok(n) => {
                        buf.extend_from_slice(&chunk[..n]);
                        if buf.len() > MAX_OUTPUT_SIZE {
                            break;
                        }
                    }
                    Err(_) => break,
                }
            }
            buf
        })
    });

    let stderr_handle = stderr.map(|mut s| {
        thread::spawn(move || {
            let mut buf = Vec::new();
            let mut chunk = [0u8; 1024];
            loop {
                match s.read(&mut chunk) {
                    Ok(0) => break,
                    Ok(n) => {
                        buf.extend_from_slice(&chunk[..n]);
                        if buf.len() > MAX_OUTPUT_SIZE {
                            break;
                        }
                    }
                    Err(_) => break,
                }
            }
            buf
        })
    });

    // Poll try_wait with timeout / Опитувати try_wait з таймаутом
    let exit_status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) => {
                if start.elapsed() > timeout {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err("Timeout exceeded".to_string());
                }
                thread::sleep(Duration::from_millis(10));
            }
            Err(e) => break Err(format!("Error waiting for process: {}", e)),
        }
    };

    let status = exit_status?;

    // Collect output from threads / Зібрати вивід з потоків
    let mut output_bytes = Vec::new();
    if let Some(h) = stdout_handle {
        if let Ok(bytes) = h.join() {
            output_bytes.extend(bytes);
        }
    }
    if let Some(h) = stderr_handle {
        if let Ok(bytes) = h.join() {
            output_bytes.extend(bytes);
        }
    }

    if output_bytes.len() > MAX_OUTPUT_SIZE {
        return Err("Output exceeded 64 KB limit".to_string());
    }

    let code = status.code().unwrap_or(-1);
    let output_str = String::from_utf8(output_bytes).map_err(|_| "Output is not valid UTF-8".to_string())?;

    Ok((code, output_str))
}

/// Run a command with a timeout, capture stdout/stderr, and enforce 64 KB limit (backward compatible wrapper).
/// Запустити команду з таймаутом, захопити stdout/stderr та обмежити до 64 КБ (обгортка для зворотної сумісності).
pub fn run_command(cmd: &str, timeout: Duration) -> Result<String, String> {
    let (code, output) = run_command_code(cmd, timeout)?;
    if code != 0 {
        return Err(format!("Command failed with exit code {}: {}", code, output));
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    /// Test running a simple echo command.
    /// Перевірити виконання простої команди echo.
    fn test_run_command_success() {
        #[cfg(target_os = "windows")]
        let cmd = "echo hello";
        #[cfg(not(target_os = "windows"))]
        let cmd = "echo hello";

        let res = run_command(cmd, Duration::from_secs(5));
        assert!(res.is_ok());
        assert!(res.unwrap().contains("hello"));
    }
}

