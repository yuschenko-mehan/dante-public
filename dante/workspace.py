"""Safe file operations inside one project folder.

- The model may only write inside the project root (no `..`, no absolute paths).
- Protected paths (.env, .git, ...) are refused.
- Every write is backed up first, so a failed attempt can be rolled back.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from dante.edits import FileEdit


class UnsafePathError(ValueError):
    pass


class Workspace:
    def __init__(self, root: Path, protected: tuple[str, ...] = ()):
        self.root = root.resolve()
        self.protected = tuple(PurePosixPath(p) for p in protected)
        self._backup: dict[Path, str | None] = {}

    def resolve(self, rel: str) -> Path:
        p = PurePosixPath(rel.replace("\\", "/"))
        if p.is_absolute() or ".." in p.parts or not p.parts or ":" in p.parts[0]:
            raise UnsafePathError(f"Path not allowed: {rel}")
        for prot in self.protected:
            if p == prot or prot in p.parents:
                raise UnsafePathError(f"Protected path: {rel}")
        full = (self.root / Path(*p.parts)).resolve()
        if self.root != full and self.root not in full.parents:
            raise UnsafePathError(f"Path escapes project: {rel}")
        return full

    def check(self, edits: list[FileEdit]) -> None:
        """Validate all paths before touching anything."""
        for e in edits:
            self.resolve(e.path)

    def apply(self, edits: list[FileEdit]) -> list[str]:
        self.check(edits)
        written = []
        for e in edits:
            full = self.resolve(e.path)
            if full not in self._backup:
                self._backup[full] = (
                    full.read_text(encoding="utf-8") if full.exists() else None
                )
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(e.content, encoding="utf-8", newline="\n")
            written.append(e.path)
        return written

    def rollback(self) -> None:
        """Restore every file touched since the last commit_point()."""
        for full, old in self._backup.items():
            if old is None:
                full.unlink(missing_ok=True)
            else:
                full.write_text(old, encoding="utf-8", newline="\n")
        self._backup.clear()

    def commit_point(self) -> None:
        """Accept current state: forget backups."""
        self._backup.clear()

    def read_files(self, rels: list[str], max_chars: int = 20000, check: bool = True) -> str:
        """Current content of files, formatted for the model.

        check=False allows reading protected files (e.g. tests shown read-only).
        """
        parts = []
        for rel in rels:
            full = self.resolve(rel) if check else (self.root / rel).resolve()
            if self.root not in full.parents:
                continue
            if full.exists():
                text = full.read_text(encoding="utf-8", errors="replace")[:max_chars]
                parts.append(f"=== FILE: {rel} ===\n{text}\n=== END FILE ===")
        return "\n".join(parts)
