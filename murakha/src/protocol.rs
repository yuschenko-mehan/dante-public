//! Protocol implementation for murakha swarm.
//! Реалізація протоколу для рою мураха.

// Helper function to encode bytes to lowercase hex / Допоміжна функція для кодування байтів у шістнадцятковий формат у нижньому регістрі
pub fn hex_encode(bytes: &[u8]) -> String {
    // Check input bounds or length / Перевірити вхідні межі або довжину
    let mut s = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        use std::fmt::Write;
        let _ = write!(&mut s, "{:02x}", b);
    }
    s
}

// Helper function to decode lowercase hex to bytes / Допоміжна функція для декодування шістнадцяткового формату у байти
pub fn hex_decode(s: &str) -> Result<Vec<u8>, &'static str> {
    // Validate hex string length / Перевірити довжину шістнадцяткового рядка
    if s.len() % 2 != 0 {
        return Err("Invalid hex length / Недійсна довжина шістнадцяткового рядка");
    }
    let mut bytes = Vec::with_capacity(s.len() / 2);
    let bytes_in = s.as_bytes();
    let mut i = 0;
    while i < bytes_in.len() {
        let high = char_to_nibble(bytes_in[i])?;
        let low = char_to_nibble(bytes_in[i + 1])?;
        bytes.push((high << 4) | low);
        i += 2;
    }
    Ok(bytes)
}

// Convert ASCII hex char to nibble / Перетворити шістнадцятковий символ ASCII на півбайт
fn char_to_nibble(c: u8) -> Result<u8, &'static str> {
    match c {
        b'0'..=b'9' => Ok(c - b'0'),
        b'a'..=b'f' => Ok(c - b'a' + 10),
        b'A'..=b'F' => Ok(c - b'A' + 10), // Accept uppercase just in case, though output is lowercase / Приймати верхній регістр на всяк випадок, хоча вихід нижній
        _ => Err("Invalid hex character / Недійсний шістнадцятковий символ"),
    }
}

// Messages sent from Ant to Coordinator / Повідомлення, що надсилаються від Мурахи до Координатора
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AntMessage {
    Hello {
        id: String,
        cpus: usize,
        version: String,
    },
    Ask {
        id: String,
    },
    Result {
        id: String,
        task_id: String,
        exit_code: i32,
        output: String, // lowercase hex / шістнадцятковий формат у нижньому регістрі
    },
    Beat {
        id: String,
    },
}

// Messages sent from Coordinator to Ant / Повідомлення, що надсилаються від Координатора до Мурахи
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CoordMessage {
    Task {
        task_id: String,
        timeout_s: u64,
        command: String,
    },
    Wait {
        seconds: u64,
    },
    Snap {
        data: String,
    },
    Heart {
        version: String,
        index: u32,
        total: u32,
        data: String,
    },
    Bye,
}

impl AntMessage {
    // Format ant message to line / Заформатувати повідомлення мурахи в рядок
    pub fn to_line(&self) -> String {
        match self {
            AntMessage::Hello { id, cpus, version } => {
                format!("HELLO\t{}\t{}\t{}", id, cpus, version)
            }
            AntMessage::Ask { id } => {
                format!("ASK\t{}", id)
            }
            AntMessage::Result { id, task_id, exit_code, output } => {
                format!("RESULT\t{}\t{}\t{}\t{}", id, task_id, exit_code, output)
            }
            AntMessage::Beat { id } => {
                format!("BEAT\t{}", id)
            }
        }
    }

    // Parse ant message from line / Розпарсити повідомлення мурахи з рядка
    pub fn parse(line: &str) -> Result<Self, &'static str> {
        // Strip trailing newline/carriage return if any / Видалити кінцеві символи нового рядка, якщо є
        let line = line.trim_end_matches(['\r', '\n']);
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.is_empty() {
            return Err("Empty message / Порожнє повідомлення");
        }
        match parts[0] {
            "HELLO" => {
                if parts.len() != 4 {
                    return Err("Invalid HELLO fields count / Невірна кількість полів HELLO");
                }
                let cpus = parts[2].parse().map_err(|_| "Invalid cpus / Недійсні cpus")?;
                Ok(AntMessage::Hello {
                    id: parts[1].to_string(),
                    cpus,
                    version: parts[3].to_string(),
                })
            }
            "ASK" => {
                if parts.len() != 2 {
                    return Err("Invalid ASK fields count / Невірна кількість полів ASK");
                }
                Ok(AntMessage::Ask {
                    id: parts[1].to_string(),
                })
            }
            "RESULT" => {
                if parts.len() != 5 {
                    return Err("Invalid RESULT fields count / Невірна кількість полів RESULT");
                }
                let exit_code = parts[3].parse().map_err(|_| "Invalid exit_code / Недійсний exit_code")?;
                Ok(AntMessage::Result {
                    id: parts[1].to_string(),
                    task_id: parts[2].to_string(),
                    exit_code,
                    output: parts[4].to_string(),
                })
            }
            "BEAT" => {
                if parts.len() != 2 {
                    return Err("Invalid BEAT fields count / Невірна кількість полів BEAT");
                }
                Ok(AntMessage::Beat {
                    id: parts[1].to_string(),
                })
            }
            _ => Err("Unknown ant message type / Невідомий тип повідомлення мурахи"),
        }
    }
}

impl CoordMessage {
    // Format coordinator message to line / Заформатувати повідомлення координатора в рядок
    pub fn to_line(&self) -> String {
        match self {
            CoordMessage::Task { task_id, timeout_s, command } => {
                format!("TASK\t{}\t{}\t{}", task_id, timeout_s, command)
            }
            CoordMessage::Wait { seconds } => {
                format!("WAIT\t{}", seconds)
            }
            CoordMessage::Snap { data } => {
                format!("SNAP\t{}", data)
            }
            CoordMessage::Heart { version, index, total, data } => {
                format!("HEART\t{}\t{}\t{}\t{}", version, index, total, data)
            }
            CoordMessage::Bye => {
                "BYE".to_string()
            }
        }
    }

    // Parse coordinator message from line / Розпарсити повідомлення координатора з рядка
    pub fn parse(line: &str) -> Result<Self, &'static str> {
        // Strip trailing newline/carriage return if any / Видалити кінцеві символи нового рядка, якщо є
        let line = line.trim_end_matches(['\r', '\n']);
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.is_empty() {
            return Err("Empty message / Порожнє повідомлення");
        }
        match parts[0] {
            "TASK" => {
                if parts.len() != 4 {
                    return Err("Invalid TASK fields count / Невірна кількість полів TASK");
                }
                let timeout_s = parts[2].parse().map_err(|_| "Invalid timeout_s / Недійсний timeout_s")?;
                Ok(CoordMessage::Task {
                    task_id: parts[1].to_string(),
                    timeout_s,
                    command: parts[3].to_string(),
                })
            }
            "WAIT" => {
                if parts.len() != 2 {
                    return Err("Invalid WAIT fields count / Невірна кількість полів WAIT");
                }
                let seconds = parts[1].parse().map_err(|_| "Invalid seconds / Недійсні секунди")?;
                Ok(CoordMessage::Wait { seconds })
            }
            "SNAP" => {
                if parts.len() != 2 {
                    return Err("Invalid SNAP fields count / Невірна кількість полів SNAP");
                }
                Ok(CoordMessage::Snap {
                    data: parts[1].to_string(),
                })
            }
            "HEART" => {
                if parts.len() != 5 {
                    return Err("Invalid HEART fields count / Невірна кількість полів HEART");
                }
                let index = parts[2].parse().map_err(|_| "Invalid HEART index / Недійсний індекс HEART")?;
                let total = parts[3].parse().map_err(|_| "Invalid HEART total / Недійсна кількість HEART")?;
                Ok(CoordMessage::Heart { version: parts[1].to_string(), index, total, data: parts[4].to_string() })
            }
            "BYE" => {
                if parts.len() != 1 {
                    return Err("Invalid BYE fields count / Невірна кількість полів BYE");
                }
                Ok(CoordMessage::Bye)
            }
            _ => Err("Unknown coordinator message type / Невідомий тип повідомлення координатора"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Test hex encode and decode / Протестувати кодування та декодування шістнадцяткового формату
    #[test]
    fn test_hex_codec() {
        let original = b"Hello, World!";
        let encoded = hex_encode(original);
        assert_eq!(encoded, "48656c6c6f2c20576f726c6421");
        let decoded = hex_decode(&encoded).unwrap();
        assert_eq!(decoded, original);

        assert!(hex_decode("abc").is_err());
        assert!(hex_decode("zz").is_err());
    }

    // Test AntMessage parsing and formatting / Протестувати парсинг та форматування AntMessage
    #[test]
    fn test_ant_message() {
        let hello = AntMessage::Hello {
            id: "pc1-1234".to_string(),
            cpus: 8,
            version: "0.1.0".to_string(),
        };
        let line = hello.to_line();
        assert_eq!(line, "HELLO\tpc1-1234\t8\t0.1.0");
        let parsed = AntMessage::parse(&line).unwrap();
        assert_eq!(parsed, hello);

        let ask = AntMessage::Ask { id: "pc1-1234".to_string() };
        let line = ask.to_line();
        assert_eq!(line, "ASK\tpc1-1234");
        let parsed = AntMessage::parse(&line).unwrap();
        assert_eq!(parsed, ask);

        let result = AntMessage::Result {
            id: "pc1-1234".to_string(),
            task_id: "t1".to_string(),
            exit_code: 0,
            output: "48656c6c6f".to_string(),
        };
        let line = result.to_line();
        assert_eq!(line, "RESULT\tpc1-1234\tt1\t0\t48656c6c6f");
        let parsed = AntMessage::parse(&line).unwrap();
        assert_eq!(parsed, result);

        let beat = AntMessage::Beat { id: "pc1-1234".to_string() };
        let line = beat.to_line();
        assert_eq!(line, "BEAT\tpc1-1234");
        let parsed = AntMessage::parse(&line).unwrap();
        assert_eq!(parsed, beat);

        // Test invalid lines / Протестувати недійсні рядки
        assert!(AntMessage::parse("UNKNOWN\t1").is_err());
        assert!(AntMessage::parse("HELLO\tonlyone").is_err());
    }

    // Test CoordMessage parsing and formatting / Протестувати парсинг та форматування CoordMessage
    #[test]
    fn test_coord_message() {
        let task = CoordMessage::Task {
            task_id: "t1".to_string(),
            timeout_s: 30,
            command: "echo hi".to_string(),
        };
        let line = task.to_line();
        assert_eq!(line, "TASK\tt1\t30\techo hi");
        let parsed = CoordMessage::parse(&line).unwrap();
        assert_eq!(parsed, task);

        let wait = CoordMessage::Wait { seconds: 5 };
        let line = wait.to_line();
        assert_eq!(line, "WAIT\t5");
        let parsed = CoordMessage::parse(&line).unwrap();
        assert_eq!(parsed, wait);

        let snap = CoordMessage::Snap { data: "1234".to_string() };
        let line = snap.to_line();
        assert_eq!(line, "SNAP\t1234");
        let parsed = CoordMessage::parse(&line).unwrap();
        assert_eq!(parsed, snap);

        let bye = CoordMessage::Bye;
        let line = bye.to_line();
        assert_eq!(line, "BYE");
        let parsed = CoordMessage::parse(&line).unwrap();
        assert_eq!(parsed, bye);

        // Test invalid lines / Протестувати недійсні рядки
        assert!(CoordMessage::parse("BAD\t1").is_err());
        assert!(CoordMessage::parse("TASK\tonly\ttwo").is_err());
    }
}
