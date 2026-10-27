"""Everything that reads the user's C source code.

Reports say *where* the crash is; reading the line itself lets segwhy name
the guilty variable ("'n' is NULL here") or find a recursive call.
These are simple text heuristics, not a C parser: they can be wrong, so their
result is only used to make a hint more precise.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:  # only for type hints, avoids a circular import with model.py
    from .model import Diagnosis

# Words that look like variable names on a C line but never are pointers.
C_KEYWORDS = {
    "return", "if", "else", "while", "for", "do", "switch", "case", "sizeof", "int", "char", "void",
    "struct", "union", "enum", "const", "unsigned", "signed", "long", "short", "double", "float",
    "static", "extern", "volatile", "register", "goto", "break", "continue", "typedef", "NULL",
}

# Folders never searched when looking for a source file.
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", ".cache"}


# ---- reading files ------------------------------------------------------------------

def read_source_line(path: Optional[str], line: Optional[int]) -> Optional[str]:
    """The text of line `line` in file `path`, or None if it can't be read."""
    if not path or not line:
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for number, text in enumerate(handle, start=1):
                if number == line:
                    return text.rstrip("\n").rstrip()
    except OSError:
        return None
    return None


def display_path(path: Optional[str]) -> str:
    """A path as short as possible for display: relative to the current
    directory when it's close, absolute otherwise."""
    if not path:
        return "?"
    try:
        relative = os.path.relpath(path)
    except ValueError:
        return path
    if relative.startswith("../../"):
        return path
    return relative


# ---- finding files ------------------------------------------------------------------

class SourceFinder:
    """Find the real file behind a path from a report.

    macOS reports only "parser.c" for "project/parser.c". A relative path that
    doesn't exist is looked up by file name among the files given to segwhy,
    then in the current directory tree (scanned once, with limits)."""

    def __init__(self, sources: Optional[List[str]] = None, max_files: int = 20000, max_depth: int = 6):
        """`sources` are the .c files given on the command line, if any."""
        self.by_name = {}
        for source in sources or []:
            self.by_name.setdefault(os.path.basename(source), os.path.abspath(source))
        self.max_files = max_files
        self.max_depth = max_depth
        self._scanned = False

    def _scan(self) -> None:
        """Index the C files under the current directory by file name."""
        self._scanned = True
        count = 0
        root = os.getcwd()
        base_depth = root.rstrip(os.sep).count(os.sep)
        for directory, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
            if directory.count(os.sep) - base_depth >= self.max_depth:
                dirs[:] = []
            for name in files:
                if name.endswith((".c", ".h", ".cc", ".cpp", ".inc")):
                    self.by_name.setdefault(name, os.path.join(directory, name))
                count += 1
                if count > self.max_files:
                    return

    def resolve(self, path: Optional[str]) -> Optional[str]:
        """The real path of `path`, or `path` unchanged if nothing better is found."""
        if not path or os.path.isabs(path) or os.path.exists(path):
            return path
        if path.startswith("../") or path.startswith("<") or "/" in path.strip("./"):
            return path  # system library paths like nptl/pthread_kill.c
        name = os.path.basename(path)
        if name not in self.by_name and not self._scanned:
            self._scan()
        return self.by_name.get(name, path)


def resolve_frames(diag: "Diagnosis", finder: SourceFinder) -> "Diagnosis":
    """Replace every file path of a diagnosis by its real path."""
    for frame in [*diag.frames, diag.freed_at, diag.allocated_at]:
        if frame is not None and frame.file:
            frame.file = finder.resolve(frame.file)
    return diag


# ---- understanding a line of C --------------------------------------------------------

def strip_literals(code: str) -> str:
    """Empty the strings and chars of a C line and drop its // comment, so
    that "a->b" inside a string isn't taken for code."""
    code = re.sub(r'"(?:\\.|[^"\\])*"', '""', code)
    code = re.sub(r"'(?:\\.|[^'\\])*'", "''", code)
    code = code.split("//", 1)[0]
    return code


def pointer_candidates(code: Optional[str]) -> List[str]:
    """Pointers dereferenced on a line of C: "p" for *p, p->x and p[i].

    For a->b->c, both "a" and "a->b" are returned (either can be NULL)."""
    if not code:
        return []
    code = strip_literals(code)
    found: List[str] = []

    # p->field, a->b->c
    for match in re.finditer(r"([A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)\s*->", code):
        parts = re.split(r"\s*->\s*", match.group(1))
        for end in range(1, len(parts) + 1):
            found.append("->".join(parts[:end]))

    # *p (a unary star only, not a multiplication like a * b)
    for match in re.finditer(r"\*", code):
        before = code[: match.start()].rstrip()
        if before and (before[-1].isalnum() or before[-1] in "_)]"):
            last_word = re.search(r"([A-Za-z_]\w*)$", before)
            if not (last_word and last_word.group(1) == "return"):
                continue
        after = re.match(r"\s*\(?\s*([A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)", code[match.end():])
        if after:
            found.append(re.sub(r"\s+", "", after.group(1)))

    # p[i]
    for match in re.finditer(r"([A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)\s*\[", code):
        found.append(re.sub(r"\s+", "", match.group(1)))

    result: List[str] = []
    for name in found:
        root = re.split(r"->|\.", name)[0]
        if root in C_KEYWORDS or name in result:
            continue
        result.append(name)
    return result


def call_arguments(code: Optional[str], func: Optional[str]) -> List[str]:
    """The simple arguments (variables, argv[1], p->name) of a call to `func`
    on this line: "strlen(line)" -> ["line"]. Expressions are skipped."""
    if not code or not func:
        return []
    code = strip_literals(code)
    match = re.search(r"\b" + re.escape(func) + r"\s*\(", code)
    if not match:
        return []
    depth, args, current = 1, [], ""
    for char in code[match.end():]:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                break
        if char == "," and depth == 1:
            args.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        args.append(current.strip())
    return [a for a in args if re.fullmatch(r"[A-Za-z_][\w\[\]\->. ]*", a) and a not in ('""', "''")]


def find_recursive_call(path: Optional[str], func: Optional[str], near_line: Optional[int]) -> Optional[int]:
    """Line number where function `func` calls itself, or None.

    `near_line` is a line inside the function (from the report). Used when a
    report only shows the top of an infinite recursion, as on macOS."""
    if not path or not func or not near_line:
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    call = re.compile(r"\b" + re.escape(func) + r"\s*\(")

    # Go up from near_line to the function's definition ("int f(int n)", no ';').
    start = None
    for number in range(min(near_line, len(lines)), 0, -1):
        text = lines[number - 1]
        if call.search(text) and ";" not in text.split("//")[0]:
            start = number
            break
    if start is None:
        return None

    # Go down through the body, counting braces, until a call to func.
    depth, opened = 0, False
    for number in range(start, len(lines) + 1):
        text = re.sub(r'"(?:\\.|[^"\\])*"', '""', lines[number - 1].split("//")[0])
        if opened and call.search(text):
            return number
        if number == start and not opened and "{" in text:
            # Body starting on the definition line: look after the brace.
            if call.search(text.split("{", 1)[1]):
                return number
        depth += text.count("{") - text.count("}")
        if "{" in text:
            opened = True
        if opened and depth <= 0:
            return None
    return None
