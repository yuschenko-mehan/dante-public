// Spec: one-time consent of the Knyaz (friend) with limits.
// Специфікація: разова згода Князя (друга) з обмеженнями.
use murakha::consent::{self, confirm_answer, Consent};

const PUB: &str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

#[test]
fn only_explicit_yes_counts() {
    for ok in ["так", "ТАК", " Так \n", "yes", "YES"] { assert!(confirm_answer(ok), "{ok:?}"); }
    for no in ["", "ні", "no", "y", "та", "так!", "maybe", "taк"] { assert!(!confirm_answer(no), "{no:?}"); }
}

#[test]
fn safe_defaults() {
    // Defaults: FULL CPU but only when idle (temperature guard limits it), CPU 80 C, GPU 78 C, all hours
    // Типово: ПОВНИЙ процесор, але лише в простої (обмежує контроль температури), CPU 80 °C, GPU 78 °C, будь-які години
    let c = Consent::default_for(PUB, 1000);
    assert_eq!(c.archant_public, PUB);
    assert_eq!(c.max_cpu_percent, 100);
    assert_eq!(c.max_cpu_temp_c, 80);
    assert_eq!(c.max_gpu_temp_c, 78);
    assert!(c.idle_only);
    assert_eq!(c.hours, None);
    assert_eq!(c.granted_unix, 1000);
}

#[test]
fn text_round_trip() {
    let mut c = Consent::default_for(PUB, 42);
    c.hours = Some((22, 7));
    c.max_cpu_percent = 75;
    c.idle_only = false;
    let t = c.to_text();
    assert!(t.starts_with("DANTE-KNYAZ-CONSENT-1\n"));
    assert_eq!(Consent::parse(&t).unwrap(), c);
}

#[test]
fn invalid_consent_is_rejected() {
    let good = Consent::default_for(PUB, 1).to_text();
    assert!(Consent::parse(&good).is_ok());
    let bad = [
        good.replace("DANTE-KNYAZ-CONSENT-1", "OTHER"),
        good.replace(PUB, "1234"),
        good.replace("max_cpu_percent=100", "max_cpu_percent=0"),
        good.replace("max_cpu_percent=100", "max_cpu_percent=101"),
        good.replace("max_gpu_temp_c=78", "max_gpu_temp_c=120"),
        good.replace("max_cpu_temp_c=80", "max_cpu_temp_c=30"),
        good.replace("idle_only=yes", "idle_only=maybe"),
        good.replace("hours=all", "hours=25-3"),
        good.replace("granted_unix=1\n", ""),
    ];
    for b in bad.iter() { assert!(Consent::parse(b).is_err(), "should fail:\n{b}"); }
}

#[test]
fn working_window() {
    let mut c = Consent::default_for(PUB, 1);
    assert!(c.allows_now(12, true));
    assert!(!c.allows_now(12, false), "idle_only: busy PC must not work");
    c.idle_only = false;
    assert!(c.allows_now(12, false));
    c.hours = Some((9, 18));
    assert!(c.allows_now(9, true) && c.allows_now(17, true));
    assert!(!c.allows_now(18, true) && !c.allows_now(3, true));
    // over midnight / через північ
    c.hours = Some((22, 7));
    assert!(c.allows_now(23, true) && c.allows_now(0, true) && c.allows_now(6, true));
    assert!(!c.allows_now(7, true) && !c.allows_now(12, true));
    c.hours = Some((5, 5));
    assert!(c.allows_now(0, true) && c.allows_now(23, true));
}

#[test]
fn save_load_revoke() {
    let dir = std::env::temp_dir().join(format!("knyaz-consent-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let f = dir.join("consent.txt");
    assert!(consent::load(&f).is_none(), "no file = no consent");
    let c = Consent::default_for(PUB, 7);
    consent::save(&c, &f).unwrap();
    assert_eq!(consent::load(&f), Some(c));
    std::fs::write(&f, "garbage").unwrap();
    assert!(consent::load(&f).is_none(), "broken file = no consent");
    consent::revoke(&f).unwrap();
    assert!(!f.exists());
    consent::revoke(&f).unwrap(); // already gone is fine / уже немає — це нормально
    let _ = std::fs::remove_dir_all(&dir);
}
