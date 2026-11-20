use std::fs;
use std::io;
use std::path::Path;
use crate::survive::checksum;
pub const MAGIC: &[u8] = b"DANTE-HEART-1\n";
pub const MAX_BYTES: usize = 64 * 1024 * 1024;
const SKIP_DIRS: &[&str] = &[".git", "__pycache__", "audit", "outbox", "inbox", "target", "graphify-out", "update-backup", "kopiya-roju", "node_modules"];
const NEVER: &[&str] = &["keys.txt", ".env", "credentials.json", "update.json"];
const EXT: &[&str] = &["py", "json", "toml", "md", "txt", "bat", "cmd", "ps1", "rs", "ttf", "otf", "png"];
pub fn wanted(rel: &str) -> bool {
    let parts: Vec<&str> = rel.split('/').collect();
    if parts.iter().any(|p| SKIP_DIRS.contains(p) || p.starts_with('.')) { return false; }
    let name = parts.last().unwrap_or(&"").to_lowercase();
    if NEVER.contains(&name.as_str()) || name.ends_with(".key") || name.ends_with(".pem") || name.ends_with(".log") { return false; }
    match name.rsplit_once('.') { Some((_, e)) => EXT.contains(&e), None => false }
}
fn walk(root: &Path, dir: &Path, out: &mut Vec<String>) -> io::Result<()> {
    for e in fs::read_dir(dir)? {
        let e = e?; let p = e.path();
        let rel = p.strip_prefix(root).unwrap().to_string_lossy().replace('\\', "/");
        if e.file_type()?.is_dir() {
            if rel.split('/').any(|x| SKIP_DIRS.contains(&x) || x.starts_with('.')) { continue; }
            walk(root, &p, out)?;
        } else if wanted(&rel) { out.push(rel); }
    }
    Ok(())
}
pub fn pack(root: &Path) -> io::Result<Vec<u8>> {
    let mut files = Vec::new();
    walk(root, root, &mut files)?;
    files.sort();
    let mut b = MAGIC.to_vec();
    for rel in files {
        let data = fs::read(root.join(&rel))?;
        b.extend_from_slice(format!("F\t{}\t{}\n", rel, data.len()).as_bytes());
        b.extend_from_slice(&data); b.push(b'\n');
        if b.len() > MAX_BYTES { return Err(io::Error::new(io::ErrorKind::InvalidData, "heart too big")); }
    }
    let sum = checksum(&b);
    b.extend_from_slice(format!("END\t{:016x}\n", sum).as_bytes());
    Ok(b)
}
fn parse(bundle: &[u8]) -> Result<Vec<(String, usize, usize)>, String> {
    if !bundle.starts_with(MAGIC) { return Err("not a DANTE heart".into()); }
    let mut i = MAGIC.len(); let mut out = Vec::new();
    loop {
        let nl = bundle[i..].iter().position(|&c| c == b'\n').ok_or("broken header")? + i;
        let line = std::str::from_utf8(&bundle[i..nl]).map_err(|_| "bad header")?;
        let f: Vec<&str> = line.split('\t').collect();
        if f.len() == 2 && f[0] == "END" {
            let want = format!("{:016x}", checksum(&bundle[..i]));
            if f[1] != want || nl + 1 != bundle.len() { return Err("checksum mismatch".into()); }
            return Ok(out);
        }
        if f.len() != 3 || f[0] != "F" { return Err("bad entry".into()); }
        let len: usize = f[2].parse().map_err(|_| "bad length")?;
        let start = nl + 1; let end = start.checked_add(len).ok_or("bad length")?;
        if end + 1 > bundle.len() || bundle[end] != b'\n' { return Err("truncated".into()); }
        out.push((f[1].to_string(), start, len));
        i = end + 1;
    }
}
pub fn list(bundle: &[u8]) -> Result<Vec<(String, usize)>, String> {
    Ok(parse(bundle)?.into_iter().map(|(n, _, l)| (n, l)).collect())
}
fn unsafe_path(p: &str) -> bool {
    p.is_empty() || p.starts_with('/') || p.contains('\\') || p.chars().nth(1) == Some(':') || p.split('/').any(|x| x == "..")
}
pub fn unpack(bundle: &[u8], dest: &Path) -> io::Result<usize> {
    let bad = |m: String| io::Error::new(io::ErrorKind::InvalidData, m);
    let entries = parse(bundle).map_err(bad)?;
    if let Some((n, _, _)) = entries.iter().find(|(n, _, _)| unsafe_path(n)) { return Err(bad(format!("unsafe path {n}"))); }
    for (n, s, l) in &entries {
        let f = dest.join(n);
        if let Some(p) = f.parent() { fs::create_dir_all(p)?; }
        fs::write(f, &bundle[*s..*s + *l])?;
    }
    Ok(entries.len())
}
pub fn chunks(bundle: &[u8], size: usize) -> Vec<Vec<u8>> {
    if size == 0 || bundle.is_empty() { return vec![bundle.to_vec()]; }
    bundle.chunks(size).map(|c| c.to_vec()).collect()
}
pub struct Assembler { parts: Vec<Option<Vec<u8>>> }
impl Assembler {
    pub fn new(total: usize) -> Assembler { Assembler { parts: vec![None; total] } }
    pub fn add(&mut self, index: usize, data: Vec<u8>) -> bool {
        if index >= self.parts.len() { return false; }
        self.parts[index] = Some(data);
        self.parts.iter().all(|p| p.is_some())
    }
    pub fn finish(&self) -> Option<Vec<u8>> {
        let mut out = Vec::new();
        for p in &self.parts { out.extend_from_slice(p.as_ref()?); }
        Some(out)
    }
}
