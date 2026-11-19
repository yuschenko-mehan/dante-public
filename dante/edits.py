"""Parse file edits out of an LLM answer.

The model is asked to answer only with blocks of this exact form:

    === FILE: relative/path.py ===
    <full new content of the file>
    === END FILE ===

Whole-file replacement is the simplest format that is hard to get wrong.
(Smarter formats such as search/replace come later, once this works.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_BLOCK = re.compile(
    r"^=== FILE: (?P<path>[^\n=]+?) ===\n(?P<body>.*?)^=== END FILE ===\s*$",
    re.MULTILINE | re.DOTALL,
)

FORMAT_INSTRUCTIONS = (
    "Answer ONLY with file blocks in this exact format, one block per file, "
    "each containing the COMPLETE new file content:\n"
    "=== FILE: relative/path/to/file ===\n"
    "<file content>\n"
    "=== END FILE ===\n"
    "Use forward slashes in paths. No other text."
)


@dataclass(frozen=True)
class FileEdit:
    path: str
    content: str


def parse_edits(answer: str) -> list[FileEdit]:
    text = answer.replace("\r\n", "\n")
    edits = [
        FileEdit(path=m.group("path").strip(), content=m.group("body"))
        for m in _BLOCK.finditer(text)
    ]
    if not edits:
        raise ValueError("The model answer contains no file blocks.")
    return edits
