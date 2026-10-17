"""Data shared by the ASan parser, the gdb runner and the renderer."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

# Paths that never belong to the user's own code.
_SYSTEM_MARKERS = (
    "/libsanitizer/",
    "/compiler-rt/",
    "/sanitizer_common/",
    "/sysdeps/",
    "/glibc",
    "/usr/include/",
    "/usr/lib/",
    "/usr/src/",
    "/usr/local/Cellar/",
    "/Library/Developer/",
    "/Applications/Xcode",
)

# Suffixes glibc adds to optimized variants of string functions.
_LIB_SUFFIX = re.compile(
    r"_(?:avx2|avx512|evex|sse2|sse4_1|sse4_2|ssse3|erms|unaligned|aligned|"
    r"rtm|base|internal|l_internal|l|chk|nocancel|generic)(?:_\w+)?$"
)


@dataclass
class Frame:
    func: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    module: Optional[str] = None

    @property
    def has_location(self) -> bool:
        return bool(self.file) and self.line is not None

    def is_user_code(self) -> bool:
        """True when the frame points into the user's own source files."""
        if not self.has_location:
            return False
        path = self.file or ""
        if path.startswith("../") or path.startswith("<"):
            return False
        if any(marker in path for marker in _SYSTEM_MARKERS):
            return False
        if os.path.isabs(path):
            return True
        # Relative paths like "nptl/pthread_kill.c" come from system libraries
        # built elsewhere: only trust the ones that exist here (resolve_frames
        # has already turned the user's own relative paths into real ones).
        return os.path.exists(path)

    def clean_func(self) -> Optional[str]:
        """Public-looking name of a library function (__strlen_avx2 -> strlen)."""
        if not self.func:
            return None
        name = self.func.split("(")[0].strip()
        name = re.sub(r"\+0x[0-9a-fA-F]+$", "", name)  # macOS: atoi+0x50
        for prefix in ("___interceptor_", "__interceptor_", "__GI_", "__libc_"):
            if name.startswith(prefix):
                name = name[len(prefix):]
        name = name.lstrip("_")
        for prefix in ("GI_", "platform_", "wrap_", "interceptor_"):  # glibc, macOS libplatform, ASan
            if name.startswith(prefix):
                name = name[len(prefix):].lstrip("_")
        previous = None
        while previous != name:
            previous = name
            name = _LIB_SUFFIX.sub("", name)
        return name or self.func


@dataclass
class Diagnosis:
    """Everything segwhy found out about one crash."""

    kind: str  # see messages.REASONS for the list
    source: str = "asan"  # "asan" or "gdb"
    access: Optional[str] = None  # "READ" or "WRITE"
    access_size: Optional[int] = None
    address: Optional[int] = None
    signal: Optional[str] = None
    frames: List[Frame] = field(default_factory=list)
    freed_at: Optional[Frame] = None
    allocated_at: Optional[Frame] = None
    region_size: Optional[int] = None
    region_relation: Optional[str] = None  # "after", "before", "inside"
    region_distance: Optional[int] = None
    var_name: Optional[str] = None
    var_line: Optional[int] = None
    raw_kind: Optional[str] = None
    raw: str = ""

    # ---- helpers used by the renderer -------------------------------------

    def user_frames(self) -> List[Frame]:
        return [f for f in self.frames if f.is_user_code()]

    def main_frame(self) -> Optional[Frame]:
        """The line to show: first frame in the user's code."""
        if self.kind == "stack_exhaustion":
            recursive = self.recursive_function()
            if recursive:
                # Show the recursive call, not the function's first line.
                calls = [f for f in self.user_frames() if f.func == recursive]
                if len(calls) > 1:
                    return calls[1]
            else:
                top = next(iter(self.user_frames()), None)
                if top is not None:
                    line = find_recursive_call(top.file, top.func, top.line)
                    if line is not None:
                        return Frame(func=top.func, file=top.file, line=line)
        user = self.user_frames()
        if user:
            return user[0]
        return self.frames[0] if self.frames else None

    def library_function(self) -> Optional[str]:
        """Name of the library function the crash happened in, if any."""
        if not self.frames or self.frames[0].is_user_code():
            return None
        if not self.user_frames():
            return None
        # The frame right before the user's code is the call they wrote.
        previous = None
        for frame in self.frames:
            if frame.is_user_code():
                break
            previous = frame
        return previous.clean_func() if previous else None

    def recursive_function(self) -> Optional[str]:
        head = [f.func for f in self.frames[:64] if f.func]
        if not head:
            return None
        counts = {}
        for name in head:
            counts[name] = counts.get(name, 0) + 1
        name, count = max(counts.items(), key=lambda item: item[1])
        return name if count >= 8 else None

    def self_calling_function(self) -> Optional[str]:
        """Recursive function seen in the stack, or found in the source code."""
        name = self.recursive_function()
        if name:
            return name
        top = next(iter(self.user_frames()), None)
        if top is not None and find_recursive_call(top.file, top.func, top.line) is not None:
            return top.func
        return None

    def has_debug_info(self) -> bool:
        return bool(self.user_frames())


_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", ".cache"}


class SourceFinder:
    """Find the real file behind a path from a report.

    macOS reports only "parser.c" for "project/parser.c", so a relative path
    that doesn't exist is looked up by name among the files given to segwhy,
    then in the current directory tree."""

    def __init__(self, sources: Optional[List[str]] = None, max_files: int = 20000, max_depth: int = 6):
        self.by_name = {}
        for source in sources or []:
            self.by_name.setdefault(os.path.basename(source), os.path.abspath(source))
        self.max_files = max_files
        self.max_depth = max_depth
        self._scanned = False

    def _scan(self) -> None:
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
        if not path or os.path.isabs(path) or os.path.exists(path):
            return path
        if path.startswith("../") or path.startswith("<") or "/" in path.strip("./"):
            return path  # system library paths like nptl/pthread_kill.c
        name = os.path.basename(path)
        if name not in self.by_name and not self._scanned:
            self._scan()
        return self.by_name.get(name, path)


def resolve_frames(diag: "Diagnosis", finder: SourceFinder) -> "Diagnosis":
    for frame in [*diag.frames, diag.freed_at, diag.allocated_at]:
        if frame is not None and frame.file:
            frame.file = finder.resolve(frame.file)
    return diag


def find_recursive_call(path: Optional[str], func: Optional[str], near_line: Optional[int]) -> Optional[int]:
    """Line where `func` calls itself, read from the source (for reports that
    show only the top of an infinite recursion, like macOS)."""
    if not path or not func or not near_line:
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    call = re.compile(r"\b" + re.escape(func) + r"\s*\(")
    start = None
    for number in range(min(near_line, len(lines)), 0, -1):
        text = lines[number - 1]
        if call.search(text) and ";" not in text.split("//")[0]:
            start = number  # the function's definition line
            break
    if start is None:
        return None
    depth, opened = 0, False
    for number in range(start, len(lines) + 1):
        text = re.sub(r'"(?:\\.|[^"\\])*"', '""', lines[number - 1].split("//")[0])
        if opened and call.search(text):
            return number
        if number == start and opened is False and "{" in text:
            # Body starting on the definition line: look after the brace.
            after = text.split("{", 1)[1]
            if call.search(after):
                return number
        depth += text.count("{") - text.count("}")
        if "{" in text:
            opened = True
        if opened and depth <= 0:
            return None
    return None


def display_path(path: Optional[str]) -> str:
    """Shorten a path relative to the current directory when possible."""
    if not path:
        return "?"
    try:
        relative = os.path.relpath(path)
    except ValueError:
        return path
    if relative.startswith("../../"):
        return path
    return relative


def read_source_line(path: Optional[str], line: Optional[int]) -> Optional[str]:
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
