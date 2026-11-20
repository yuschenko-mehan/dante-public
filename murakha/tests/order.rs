// Spec: signed orders Archant -> Knyaz (AdDante).
// Специфікація: підписані накази Архант -> Князь (АдДанте).
use murakha::order::{sign_order, ArchantKey, Obedience, Order, OrderError};

const NOW: u64 = 1_800_000_000;

#[test]
fn keys_are_hex_and_restorable() {
    // Seed and public key are 64 hex chars; seed restores the same key
    // Сід і відкритий ключ — 64 hex-символи; сід відновлює той самий ключ
    let k = ArchantKey::generate();
    assert_eq!(k.public_hex().len(), 64);
    assert_eq!(k.seed_hex().len(), 64);
    let k2 = ArchantKey::from_seed_hex(&k.seed_hex()).unwrap();
    assert_eq!(k.public_hex(), k2.public_hex());
    assert_ne!(k.public_hex(), ArchantKey::generate().public_hex());
    assert!(ArchantKey::from_seed_hex("abcd").is_err());
}

#[test]
fn order_line_format() {
    // ORDER<TAB>seq<TAB>expires<TAB>hex(body)<TAB>sig(128 hex), one line
    // ORDER<TAB>номер<TAB>термін<TAB>hex(тіло)<TAB>підпис(128 hex), один рядок
    let k = ArchantKey::generate();
    let line = sign_order(&k, 7, NOW + 60, "cargo test\nрядок 2\twith tab");
    assert!(!line.contains('\n'));
    let p: Vec<&str> = line.split('\t').collect();
    assert_eq!(p.len(), 5);
    assert_eq!(p[0], "ORDER");
    assert_eq!(p[1], "7");
    assert_eq!(p[2], (NOW + 60).to_string());
    assert_eq!(p[4].len(), 128);
}

#[test]
fn knyaz_obeys_only_archant() {
    let k = ArchantKey::generate();
    let mut o = Obedience::new(&k.public_hex()).unwrap();
    let body = "build: cargo build --release\nУкраїнський текст";
    let got = o.accept(&sign_order(&k, 1, NOW + 60, body), NOW).unwrap();
    assert_eq!(got, Order { seq: 1, expires: NOW + 60, body: body.to_string() });
    assert_eq!(o.last_seq(), 1);
    // Another key (even the Knyaz's own) cannot command
    // Інший ключ (навіть власний ключ Князя) не може наказувати
    let stranger = ArchantKey::generate();
    assert_eq!(o.accept(&sign_order(&stranger, 2, NOW + 60, "rm -rf"), NOW), Err(OrderError::BadSignature));
    assert_eq!(o.last_seq(), 1, "refused order must not move seq");
}

#[test]
fn tampering_is_detected() {
    let k = ArchantKey::generate();
    let mut o = Obedience::new(&k.public_hex()).unwrap();
    let line = sign_order(&k, 5, NOW + 60, "echo hi");
    let mut p: Vec<String> = line.split('\t').map(String::from).collect();
    // changed body / змінене тіло
    let mut a = p.clone();
    a[3] = murakha::protocol::hex_encode(b"echo bye");
    assert_eq!(o.accept(&a.join("\t"), NOW), Err(OrderError::BadSignature));
    // changed seq / змінений номер
    let mut b = p.clone();
    b[1] = "6".into();
    assert_eq!(o.accept(&b.join("\t"), NOW), Err(OrderError::BadSignature));
    // changed expiry / змінений термін
    p[2] = (NOW + 999_999).to_string();
    assert_eq!(o.accept(&p.join("\t"), NOW), Err(OrderError::BadSignature));
}

#[test]
fn expired_and_replayed_orders_refused() {
    let k = ArchantKey::generate();
    let mut o = Obedience::new(&k.public_hex()).unwrap();
    assert_eq!(o.accept(&sign_order(&k, 1, NOW - 1, "old"), NOW), Err(OrderError::Expired));
    let l3 = sign_order(&k, 3, NOW + 60, "three");
    assert!(o.accept(&l3, NOW).is_ok());
    assert_eq!(o.accept(&l3, NOW), Err(OrderError::Replay));
    assert_eq!(o.accept(&sign_order(&k, 2, NOW + 60, "two"), NOW), Err(OrderError::Replay));
    assert!(o.accept(&sign_order(&k, 4, NOW + 60, "four"), NOW).is_ok());
    // exactly at expiry is still valid / рівно в момент терміну ще дійсний
    assert!(o.accept(&sign_order(&k, 5, NOW, "edge"), NOW).is_ok());
}

#[test]
fn malformed_lines_refused() {
    let k = ArchantKey::generate();
    let mut o = Obedience::new(&k.public_hex()).unwrap();
    for bad in ["", "ORDER", "HELLO\t1\t2\t00\t00", "ORDER\tx\t2\t00\t00", "ORDER\t1\t2\tzz\t00", "ORDER\t1\t2\t00\t00"] {
        assert_eq!(o.accept(bad, NOW), Err(OrderError::Malformed), "line: {bad:?}");
    }
    assert!(Obedience::new("1234").is_err());
}

#[test]
fn last_seq_survives_restart() {
    // After a restart an old order must still be refused
    // Після перезапуску старий наказ усе одно відхиляється
    let k = ArchantKey::generate();
    let mut o = Obedience::new(&k.public_hex()).unwrap();
    let l9 = sign_order(&k, 9, NOW + 60, "nine");
    o.accept(&l9, NOW).unwrap();
    let dir = std::env::temp_dir().join(format!("knyaz-order-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let f = dir.join("obey.txt");
    o.save(&f).unwrap();
    let mut o2 = Obedience::load(&f).unwrap();
    assert_eq!(o2.last_seq(), 9);
    assert_eq!(o2.accept(&l9, NOW), Err(OrderError::Replay));
    assert!(o2.accept(&sign_order(&k, 10, NOW + 60, "ten"), NOW).is_ok());
    let _ = std::fs::remove_dir_all(&dir);
}
