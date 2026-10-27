"""The two data types everything else works on.

- Frame: one line of a call stack ("main.c:12 in main()").
- Diagnosis: everything segwhy found out about one crash.

Parsers (sanitizers.py, debugger.py) create a Diagnosis, render.py prints it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .source import find_recursive_call

# Paths that never belong to the user's own code (compiler and C library sources).
SYSTEM_PATH_MARKERS = (
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

# Suffixes glibc adds to its optimized string functions (__strlen_avx2 -> strlen).
_LIBRARY_SUFFIX = re.compile(
    r"_(?:avx2|avx512|evex|sse2|sse4_1|sse4_2|ssse3|erms|unaligned|aligned|"
    r"rtm|base|internal|l_internal|l|chk|nocancel|generic)(?:_\w+)?$"
)

# How many times a function must appear at the top of the stack to call it recursive.
RECURSION_MIN_REPEATS = 8


@dataclass
class Frame:
    """One line of a call stack. Every field can be missing."""

    func: Optional[str] = None    # function name: "main", "__strlen_avx2"
    file: Optional[str] = None    # source file: "main.c", "/home/me/project/main.c"
    line: Optional[int] = None    # line number in that file
    column: Optional[int] = None
    module: Optional[str] = None  # binary or library, when there is no file: "libc.so.6"

    @property
    def has_location(self) -> bool:
        """True when we know the file and the line."""
        return bool(self.file) and self.line is not None

    def is_user_code(self) -> bool:
        """True when the frame points into the user's own source files,
        not into the C library or the sanitizer runtime."""
        if not self.has_location:
            return False
        path = self.file or ""
        if path.startswith("../") or path.startswith("<"):
            return False
        if any(marker in path for marker in SYSTEM_PATH_MARKERS):
            return False
        if os.path.isabs(path):
            return True
        # Relative paths like "nptl/pthread_kill.c" come from system libraries
        # built elsewhere: only trust the ones that exist here (source.resolve_frames
        # has already turned the user's own relative paths into real ones).
        return os.path.exists(path)

    def clean_func(self) -> Optional[str]:
        """The public name of a library function, as the user wrote it in their
        code: __strlen_avx2 -> strlen, _platform_strlen+0x4 -> strlen."""
        if not self.func:
            return None
        name = self.func.split("(")[0].strip()
        name = re.sub(r"\+0x[0-9a-fA-F]+$", "", name)  # macOS: atoi+0x50
        for prefix in ("___interceptor_", "__interceptor_", "__GI_", "__libc_"):
            if name.startswith(prefix):
                name = name[len(prefix):]
        name = name.lstrip("_")
        for prefix in ("GI_", "platform_", "wrap_", "interceptor_"):  # glibc, macOS, ASan
            if name.startswith(prefix):
                name = name[len(prefix):].lstrip("_")
        previous = None
        while previous != name:
            previous = name
            name = _LIBRARY_SUFFIX.sub("", name)
        return name or self.func


@dataclass
class Diagnosis:
    """Everything segwhy found out about one crash.

    `kind` says what went wrong (see kinds.py). The other fields are details
    that make the explanation more precise; each parser fills what it can."""

    kind: str
    source: str = "asan"                     # who found it: "asan", "ubsan" or "gdb"
    frames: List[Frame] = field(default_factory=list)  # call stack, innermost first
    access: Optional[str] = None             # "READ" or "WRITE"
    access_size: Optional[int] = None        # bytes read or written (4 for an int)
    address: Optional[int] = None            # the bad address
    signal: Optional[str] = None             # "SIGSEGV"... (gdb only)
    freed_at: Optional[Frame] = None         # where the memory was freed (use after free)
    allocated_at: Optional[Frame] = None     # where the memory was allocated
    region_size: Optional[int] = None        # size of the array or block, in bytes
    region_relation: Optional[str] = None    # the access was "after", "before" or "inside" it
    region_distance: Optional[int] = None    # how many bytes away
    var_name: Optional[str] = None           # name of the array, when known
    var_line: Optional[int] = None           # line where that array is declared
    raw_kind: Optional[str] = None           # the tool's own name for the error
    raw: str = ""                            # the original report text

    def user_frames(self) -> List[Frame]:
        """The frames that are in the user's own code."""
        return [f for f in self.frames if f.is_user_code()]

    def has_debug_info(self) -> bool:
        """True when at least one frame has a file and line in the user's code
        (false when the program was compiled without -g)."""
        return bool(self.user_frames())

    def main_frame(self) -> Optional[Frame]:
        """The line to show the user: the first one in their own code.

        For an infinite recursion, that's the line of the recursive call rather
        than the first line of the function."""
        if self.kind == "stack_exhaustion":
            recursive = self.recursive_function()
            if recursive:
                calls = [f for f in self.user_frames() if f.func == recursive]
                if len(calls) > 1:
                    return calls[1]
            else:
                # Only the top of the recursion is known (macOS): read the source.
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
        """When the crash happened inside a library function called by the
        user (strlen(NULL)...), the name of that function. None otherwise."""
        if not self.frames or self.frames[0].is_user_code():
            return None
        if not self.user_frames():
            return None
        # The last library frame before the user's code is the call they wrote.
        previous = None
        for frame in self.frames:
            if frame.is_user_code():
                break
            previous = frame
        return previous.clean_func() if previous else None

    def recursive_function(self) -> Optional[str]:
        """Name of the function that fills the top of the stack, if one does."""
        head = [f.func for f in self.frames[:64] if f.func]
        if not head:
            return None
        counts = {}
        for name in head:
            counts[name] = counts.get(name, 0) + 1
        name, count = max(counts.items(), key=lambda item: item[1])
        return name if count >= RECURSION_MIN_REPEATS else None

    def self_calling_function(self) -> Optional[str]:
        """Like recursive_function(), but also checks the source code when the
        report only shows the top of the stack (macOS)."""
        name = self.recursive_function()
        if name:
            return name
        top = next(iter(self.user_frames()), None)
        if top is not None and find_recursive_call(top.file, top.func, top.line) is not None:
            return top.func
        return None
