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
        # built elsewhere: only trust the ones that exist here.
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

    def has_debug_info(self) -> bool:
        return bool(self.user_frames())


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
