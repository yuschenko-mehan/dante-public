// Spec: the crown — moving the Archant role between the owner's devices (home <-> work) and back.
// Специфікація: корона — перенесення ролі Арханта між пристроями власника (дім <-> робота) і назад.
use murakha::crown::{sign_crown, CrownBook, CrownError, CrownEvent, Role};
use murakha::order::ArchantKey;

#[test]
fn first_crown_and_roles() {
    let k = ArchantKey::generate();
    let mut b = CrownBook::new(&k.public_hex()).unwrap();
    assert!(b.current().is_none());
    assert_eq!(b.next_gen(), 1);
    assert_eq!(b.role_of("home-pc"), Role::Reserve, "no crown yet = nobody is the Archant");
    assert_eq!(b.observe(&sign_crown(&k, 1, "home-pc", 100)), Ok(CrownEvent::New));
    assert_eq!(b.role_of("home-pc"), Role::Archant);
    assert_eq!(b.role_of("work-pc"), Role::Reserve);
    assert_eq!(b.current().unwrap().holder, "home-pc");
    assert_eq!(b.next_gen(), 2);
}

#[test]
fn handover_and_rollback() {
    // home -> work -> home: every move is the next generation
    // дім -> робота -> дім: кожне перенесення — наступне покоління
    let k = ArchantKey::generate();
    let mut b = CrownBook::new(&k.public_hex()).unwrap();
    b.observe(&sign_crown(&k, 1, "home-pc", 100)).unwrap();
    assert_eq!(b.observe(&sign_crown(&k, 2, "work-pc", 200)), Ok(CrownEvent::New));
    assert_eq!(b.role_of("work-pc"), Role::Archant);
    assert_eq!(b.role_of("home-pc"), Role::Reserve, "the old Archant steps down by itself");
    assert_eq!(b.observe(&sign_crown(&k, 3, "home-pc", 300)), Ok(CrownEvent::New));
    assert_eq!(b.role_of("home-pc"), Role::Archant);
    // the old crown cannot come back / стара корона не повертається
    assert_eq!(b.observe(&sign_crown(&k, 2, "work-pc", 200)), Err(CrownError::Stale));
    assert_eq!(b.role_of("home-pc"), Role::Archant);
}

#[test]
fn first_claim_wins() {
    // Two flashes claim the same generation: the first wins, the second is refused
    // Дві флешки претендують на те саме покоління: перемагає перша, друга — відмова
    let k = ArchantKey::generate();
    let mut b = CrownBook::new(&k.public_hex()).unwrap();
    b.observe(&sign_crown(&k, 4, "laptop", 400)).unwrap();
    assert_eq!(b.observe(&sign_crown(&k, 4, "work-pc", 401)), Err(CrownError::Conflict));
    assert_eq!(b.role_of("laptop"), Role::Archant);
    // the same crown again is harmless / та сама корона повторно — нешкідливо
    assert_eq!(b.observe(&sign_crown(&k, 4, "laptop", 400)), Ok(CrownEvent::Same));
}

#[test]
fn only_the_owner_key_crowns() {
    let k = ArchantKey::generate();
    let thief = ArchantKey::generate();
    let mut b = CrownBook::new(&k.public_hex()).unwrap();
    b.observe(&sign_crown(&k, 1, "home-pc", 1)).unwrap();
    assert_eq!(b.observe(&sign_crown(&thief, 9, "thief-pc", 9)), Err(CrownError::BadSignature));
    // tampered holder / підмінений власник корони
    let line = sign_crown(&k, 2, "work-pc", 2);
    let mut p: Vec<String> = line.split('\t').map(String::from).collect();
    p[2] = murakha::protocol::hex_encode(b"thief-pc");
    assert_eq!(b.observe(&p.join("\t")), Err(CrownError::BadSignature));
    assert_eq!(b.role_of("home-pc"), Role::Archant);
}

#[test]
fn malformed_crowns() {
    let k = ArchantKey::generate();
    let mut b = CrownBook::new(&k.public_hex()).unwrap();
    for bad in ["", "CROWN", "ORDER\t1\t00\t1\t00", "CROWN\tx\t6869\t1\t00", "CROWN\t1\tzz\t1\t00", "CROWN\t1\t6869\t1\t00"] {
        assert_eq!(b.observe(bad), Err(CrownError::Malformed), "{bad:?}");
    }
    // generation 0 and an empty holder are not allowed / покоління 0 і порожній власник заборонені
    assert_eq!(b.observe(&sign_crown(&k, 0, "home-pc", 1)), Err(CrownError::Malformed));
    assert_eq!(b.observe(&sign_crown(&k, 1, " ", 1)), Err(CrownError::Malformed));
    assert!(CrownBook::new("12").is_err());
}
