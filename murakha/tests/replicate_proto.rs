//! Specification: a new coordinator message SNAP carries the swarm snapshot to every ant.
//! Специфікація: нове повідомлення координатора SNAP несе знімок рою кожній мурасі.
//! (Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)
//!
//! src/protocol.rs: add a variant to CoordMessage:
//!     Snap { data: String }        // data = lowercase hex of the snapshot bytes
//!   to_line -> "SNAP\t<data>";  parse("SNAP\t<data>") -> Snap; wrong field count -> Err. Other messages unchanged.
use murakha::protocol::CoordMessage;

#[test]
fn snap_line_roundtrip() {
    let m = CoordMessage::Snap { data: "4869".into() };
    assert_eq!(m.to_line(), "SNAP\t4869");
    assert_eq!(CoordMessage::parse("SNAP\t4869\r\n"), Ok(m));
    assert!(CoordMessage::parse("SNAP").is_err());
    assert!(CoordMessage::parse("SNAP\ta\tb").is_err());
    assert_eq!(CoordMessage::parse("WAIT\t5"), Ok(CoordMessage::Wait { seconds: 5 }));
}
