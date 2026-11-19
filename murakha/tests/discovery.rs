//! Specification: finding the coordinator in the local network (Wi-Fi or cable — the same) without typing an IP.
//! Специфікація: пошук координатора в локальній мережі (Wi-Fi чи кабель — однаково) без введення IP.
//! (Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має її пройти.)
//!
//! src/discovery.rs, std only / лише стандартна бібліотека:
//!   pub const DISCOVERY_PORT: u16 = 47900;
//!   pub fn default_targets() -> Vec<SocketAddr>            // [255.255.255.255:DISCOVERY_PORT]
//!   pub fn make_request(swarm_id: &str) -> Vec<u8>          // b"DANTE-WHO\t<swarm_id>\n"
//!   pub fn make_reply(swarm_id: &str, tcp_port: u16) -> Vec<u8>   // b"DANTE-HERE\t<swarm_id>\t<tcp_port>\n"
//!   pub fn parse_reply(datagram: &[u8], swarm_id: &str) -> Option<u16>
//!       Some(port) only for a well-formed reply of THIS swarm with port 1..=65535; anything else -> None, never panic
//!   pub fn spawn_responder(bind: &str, swarm_id: &str, tcp_port: u16) -> io::Result<(SocketAddr, JoinHandle<()>)>
//!       coordinator side: a thread answers every valid request of this swarm (from the sender's address);
//!       ignores other swarms and garbage and keeps running
//!   pub fn discover(swarm_id: &str, targets: &[SocketAddr], timeout: Duration) -> io::Result<Option<SocketAddr>>
//!       ant side: UDP socket on 0.0.0.0:0 with broadcast on; send the request to every target; wait up to `timeout`
//!       for a reply of this swarm; return Some(reply's source IP + its tcp_port); Ok(None) after the timeout.
//!       Errors like ConnectionReset (Windows reports a closed port this way) are ignored — keep waiting.
use std::net::{SocketAddr, UdpSocket};
use std::time::{Duration, Instant};

use murakha::discovery as d;

#[test]
fn messages_roundtrip() {
    assert_eq!(d::DISCOVERY_PORT, 47900);
    assert_eq!(d::default_targets(), vec!["255.255.255.255:47900".parse::<SocketAddr>().unwrap()]);
    assert_eq!(d::make_request("sw1"), b"DANTE-WHO\tsw1\n".to_vec());
    assert_eq!(d::make_reply("sw1", 5000), b"DANTE-HERE\tsw1\t5000\n".to_vec());
    assert_eq!(d::parse_reply(&d::make_reply("sw1", 5000), "sw1"), Some(5000));
}

#[test]
fn bad_replies_are_none() {
    for bad in [&b"DANTE-HERE\tother\t5000\n"[..], b"DANTE-HERE\tsw1\t0\n", b"DANTE-HERE\tsw1\t70000\n",
                b"DANTE-HERE\tsw1\tabc\n", b"DANTE-HERE\tsw1\n", b"DANTE-WHO\tsw1\n", b"", b"\xff\xfe\x00", b"hello"] {
        assert_eq!(d::parse_reply(bad, "sw1"), None, "{:?}", bad);
    }
}

#[test]
fn finds_coordinator_on_loopback() {
    let (addr, _h) = d::spawn_responder("127.0.0.1:0", "sw1", 4242).unwrap();
    let found = d::discover("sw1", &[addr], Duration::from_secs(3)).unwrap();
    assert_eq!(found, Some("127.0.0.1:4242".parse().unwrap()));
    // answers again and again / відповідає знову й знову
    assert!(d::discover("sw1", &[addr], Duration::from_secs(3)).unwrap().is_some());
}

#[test]
fn other_swarm_is_not_found() {
    let (addr, _h) = d::spawn_responder("127.0.0.1:0", "other", 4242).unwrap();
    let t = Instant::now();
    assert_eq!(d::discover("sw1", &[addr], Duration::from_millis(700)).unwrap(), None);
    assert!(t.elapsed() < Duration::from_secs(3));
}

#[test]
fn nobody_listening_gives_none_not_error() {
    let closed = UdpSocket::bind("127.0.0.1:0").unwrap().local_addr().unwrap(); // socket dropped: port is closed
    let t = Instant::now();
    assert_eq!(d::discover("sw1", &[closed], Duration::from_millis(700)).unwrap(), None);
    assert!(t.elapsed() < Duration::from_secs(3));
}

#[test]
fn responder_survives_garbage() {
    let (addr, _h) = d::spawn_responder("127.0.0.1:0", "sw1", 4343).unwrap();
    let s = UdpSocket::bind("127.0.0.1:0").unwrap();
    for junk in [&b"\x00\x01\x02"[..], b"DANTE-WHO", b"DANTE-WHO\t\n", b"DANTE-HERE\tsw1\t1\n"] {
        s.send_to(junk, addr).unwrap();
    }
    std::thread::sleep(Duration::from_millis(100));
    assert_eq!(d::discover("sw1", &[addr], Duration::from_secs(3)).unwrap(), Some("127.0.0.1:4343".parse().unwrap()));
}
