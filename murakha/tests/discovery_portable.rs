//! Review of DANTE's discovery (Claude, 19.11.2026): must work on Linux/Android too, and must not flood the network.
//! Рецензія пошуку Данте: має працювати й на Linux/Android і не засмічувати мережу.
//!   pub fn discovery::is_retryable(e: &io::Error) -> bool
//!       true for WouldBlock (Linux/Android timeout), TimedOut (Windows timeout), ConnectionReset, Interrupted; else false
//!   discover() sends the request to each target with growing pauses (e.g. 0.1 s, 0.2 s, 0.4 s, ... doubling),
//!   so in 1.5 s at most 6 requests reach one target.
use std::io;
use std::net::UdpSocket;
use std::time::Duration;

use murakha::discovery as d;

#[test]
fn timeouts_of_every_system_are_retryable() {
    for k in [io::ErrorKind::WouldBlock, io::ErrorKind::TimedOut, io::ErrorKind::ConnectionReset, io::ErrorKind::Interrupted] {
        assert!(d::is_retryable(&io::Error::from(k)), "{:?}", k);
    }
    for k in [io::ErrorKind::PermissionDenied, io::ErrorKind::AddrInUse, io::ErrorKind::InvalidInput] {
        assert!(!d::is_retryable(&io::Error::from(k)), "{:?}", k);
    }
}

#[test]
fn does_not_flood_a_silent_target() {
    let silent = UdpSocket::bind("127.0.0.1:0").unwrap(); // listens, never answers / слухає, але мовчить
    silent.set_read_timeout(Some(Duration::from_millis(50))).unwrap();
    let addr = silent.local_addr().unwrap();
    let h = std::thread::spawn(move || d::discover("sw1", &[addr], Duration::from_millis(1500)));
    let mut count = 0;
    let mut buf = [0u8; 256];
    let end = std::time::Instant::now() + Duration::from_millis(1800);
    while std::time::Instant::now() < end {
        if let Ok((n, _)) = silent.recv_from(&mut buf) {
            if buf[..n].starts_with(b"DANTE-WHO") { count += 1; }
        }
    }
    assert_eq!(h.join().unwrap().unwrap(), None);
    assert!(count >= 1 && count <= 6, "requests sent: {}", count);
}
