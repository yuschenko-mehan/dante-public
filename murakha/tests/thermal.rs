// Spec: temperature guard of the Knyaz.
// Специфікація: контроль температури Князя.
use murakha::thermal::{combine, cpu_share, parse_linux_thermal, parse_nvidia_smi, ThermalGuard, Throttle};

#[test]
fn pause_at_limit_resume_after_cooling() {
    // limit 80 C, hysteresis 10 C: pause at >=80, resume only at <=70
    // межа 80 °C, гістерезис 10 °C: пауза від 80, продовження лише при <=70
    let mut g = ThermalGuard::new(80.0, 10.0);
    assert_eq!(g.update(Some(60.0)), Throttle::Run);
    assert_eq!(g.update(Some(79.9)), Throttle::Run);
    assert_eq!(g.update(Some(80.0)), Throttle::Pause);
    assert!(g.is_paused());
    assert_eq!(g.update(Some(75.0)), Throttle::Pause);
    assert_eq!(g.update(Some(70.1)), Throttle::Pause);
    assert_eq!(g.update(Some(70.0)), Throttle::Run);
    assert!(!g.is_paused());
}

#[test]
fn unknown_temperature_is_careful() {
    // No sensor -> careful (half power); while paused stays paused
    // Немає датчика -> обережно (пів потужності); під час паузи — пауза
    let mut g = ThermalGuard::new(80.0, 10.0);
    assert_eq!(g.update(None), Throttle::Careful);
    g.update(Some(90.0));
    assert_eq!(g.update(None), Throttle::Pause);
}

#[test]
fn nvidia_smi_output() {
    assert_eq!(parse_nvidia_smi("65\n"), Some(65.0));
    assert_eq!(parse_nvidia_smi("61\r\n73\r\n"), Some(73.0), "hottest of several GPUs");
    assert_eq!(parse_nvidia_smi("[N/A]\n58\n"), Some(58.0));
    assert_eq!(parse_nvidia_smi(""), None);
    assert_eq!(parse_nvidia_smi("NVIDIA-SMI has failed"), None);
}

#[test]
fn linux_thermal_zone() {
    assert_eq!(parse_linux_thermal("45000\n"), Some(45.0));
    assert_eq!(parse_linux_thermal("87500"), Some(87.5));
    assert_eq!(parse_linux_thermal("-1000"), None);
    assert_eq!(parse_linux_thermal("999999"), None);
    assert_eq!(parse_linux_thermal("abc"), None);
}

#[test]
fn worst_wins_and_cpu_share() {
    assert_eq!(combine(Throttle::Run, Throttle::Pause), Throttle::Pause);
    assert_eq!(combine(Throttle::Careful, Throttle::Run), Throttle::Careful);
    assert_eq!(combine(Throttle::Run, Throttle::Run), Throttle::Run);
    assert_eq!(cpu_share(50, Throttle::Run), 50);
    assert_eq!(cpu_share(50, Throttle::Careful), 25);
    assert_eq!(cpu_share(1, Throttle::Careful), 1);
    assert_eq!(cpu_share(80, Throttle::Pause), 0);
}
