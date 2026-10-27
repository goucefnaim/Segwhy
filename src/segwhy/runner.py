"""Compile C files and run programs with the sanitizers turned on.

This module only runs things and collects what they printed. Deciding what
it means is the job of sanitizers.py, and printing it is the job of modes.py.
"""

from __future__ import annotations

import glob
import os
import shlex
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import List, Optional

# Compiler flags, tried in this order until one set works:
# - -fsanitize=address: AddressSanitizer, finds memory errors.
# - integer-divide-by-zero: on ARM (Apple Silicon), x / 0 silently gives 0
#   instead of crashing; this check catches it everywhere.
# - -fno-common: lets ASan see global arrays declared without a value
#   (Apple clang still puts those in "common" sections it can't check).
SANITIZER_FLAG_SETS = [
    ["-g", "-O0", "-fsanitize=address,integer-divide-by-zero",
     "-fno-sanitize-recover=integer-divide-by-zero", "-fno-omit-frame-pointer", "-fno-common"],
    ["-g", "-O0", "-fsanitize=address", "-fno-omit-frame-pointer", "-fno-common"],
]
# Used when the compiler has no sanitizers at all (segwhy then uses gdb).
PLAIN_FLAGS = ["-g", "-O0"]
# Always linked: so that programs using <math.h> compile without -lm.
EXTRA_LIBS = ["-lm"]

# Line ASan prints on stderr even when its report goes to a log file.
_ASAN_NOISE = b"AddressSanitizer:DEADLYSIGNAL\n"
# How much of the program's stderr is kept to look for UBSan reports.
_STDERR_KEEP = 1 << 20


@dataclass
class Compiled:
    """Result of compile_program()."""
    ok: bool           # False when the code doesn't compile
    sanitized: bool    # True when built with AddressSanitizer
    messages: str      # compiler warnings or errors


@dataclass
class SanitizedRun:
    """Result of run_sanitized()."""
    returncode: int    # like subprocess: negative when killed by a signal
    log: str           # what ASan wrote to its log files
    stderr: str        # the end of the program's stderr (UBSan writes there with gcc)


# ---- compiling ----------------------------------------------------------------------

def find_compiler() -> Optional[List[str]]:
    """The C compiler to use: $CC if set, else gcc, clang or cc."""
    env_cc = os.environ.get("CC")
    if env_cc:
        parts = shlex.split(env_cc)
        if parts and shutil.which(parts[0]):
            return parts
    for name in ("gcc", "clang", "cc"):
        if shutil.which(name):
            return [name]
    return None


def compile_program(compiler: List[str], compile_args: List[str], binary: str) -> Compiled:
    """Compile `compile_args` (the user's .c files and options) into `binary`,
    with sanitizers if the compiler supports them, without otherwise."""
    for flags in SANITIZER_FLAG_SETS:
        result = _compile(compiler, flags, compile_args, binary)
        if result.returncode == 0:
            return Compiled(ok=True, sanitized=True, messages=result.stderr)
    result = _compile(compiler, PLAIN_FLAGS, compile_args, binary)
    return Compiled(ok=result.returncode == 0, sanitized=False, messages=result.stderr)


def _compile(compiler: List[str], flags: List[str], compile_args: List[str], binary: str):
    """Run the compiler once and capture its messages."""
    return subprocess.run(
        [*compiler, *flags, *compile_args, "-o", binary, *EXTRA_LIBS],
        capture_output=True, text=True, errors="replace",
    )


def has_asan(binary: str) -> bool:
    """True when an existing program was built with AddressSanitizer."""
    marker = b"__asan_init"
    try:
        with open(binary, "rb") as handle:
            tail = b""
            while True:
                chunk = handle.read(1 << 20)
                if not chunk:
                    return False
                if marker in tail + chunk:
                    return True
                tail = chunk[-len(marker):]
    except OSError:
        return False


# ---- running ------------------------------------------------------------------------

def sanitizer_environment(log_prefix: str) -> dict:
    """Environment for a sanitized program: ASan writes its report to files
    starting with `log_prefix`. The user's own ASAN_OPTIONS/UBSAN_OPTIONS are kept."""
    asan = [
        "log_path=" + log_prefix,
        "detect_leaks=" + ("1" if sys.platform.startswith("linux") else "0"),  # LSan: Linux only
        "detect_stack_use_after_return=1",
        "handle_abort=1",
        "abort_on_error=0",
        "color=never",
        "symbolize=1",
    ]
    ubsan = ["print_stacktrace=0", "color=never"]
    user_asan = os.environ.get("ASAN_OPTIONS", "")
    user_ubsan = os.environ.get("UBSAN_OPTIONS", "")
    return dict(
        os.environ,
        ASAN_OPTIONS=":".join(([user_asan] if user_asan else []) + asan),
        UBSAN_OPTIONS=":".join(([user_ubsan] if user_ubsan else []) + ubsan),
    )


def run_sanitized(binary: str, args: List[str], workdir: str) -> SanitizedRun:
    """Run a program built with AddressSanitizer and collect its reports.

    The program keeps the real terminal (stdin, stdout, stderr). Raises
    KeyboardInterrupt on Ctrl+C and OSError if it can't be started."""
    prefix = os.path.join(workdir, "asan")
    stderr_copy = bytearray()
    returncode = run_filtering_stderr([binary, *args], sanitizer_environment(prefix), stderr_copy)
    log = ""
    for path in sorted(glob.glob(prefix + ".*")):  # one file per process: asan.<pid>
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                log += handle.read() + "\n"
        except OSError:
            pass
    return SanitizedRun(returncode, log, stderr_copy.decode("utf-8", errors="replace"))


def run_plain(binary: str, args: List[str]) -> int:
    """Run a program as is. Returns its return code (negative if killed by a signal)."""
    return subprocess.run([binary, *args]).returncode


def run_filtering_stderr(command: List[str], env: dict, keep: Optional[bytearray] = None) -> int:
    """Run `command` with the real stdin and stdout. Its stderr is forwarded
    live, minus ASan's "DEADLYSIGNAL" line, and the end of it is copied into
    `keep`. Returns the return code."""
    process = subprocess.Popen(command, env=env, stderr=subprocess.PIPE)
    out = getattr(sys.stderr, "buffer", None)

    def write(data: bytes) -> None:
        """Print `data` to our stderr and remember it."""
        if not data:
            return
        if keep is not None:
            keep.extend(data)
            if len(keep) > _STDERR_KEEP:
                del keep[: len(keep) - _STDERR_KEEP]
        if out is not None:
            sys.stdout.flush()
            out.write(data)
            out.flush()

    def forward() -> None:
        """Copy the program's stderr to ours until it closes."""
        assert process.stderr is not None
        fd = process.stderr.fileno()
        pending = b""
        while True:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            data = (pending + chunk).replace(_ASAN_NOISE, b"")
            # The noise line can arrive split across two reads: hold back a
            # tail that could be its beginning, print everything else now.
            pending = b""
            for size in range(min(len(data), len(_ASAN_NOISE) - 1), 0, -1):
                if _ASAN_NOISE.startswith(data[-size:]):
                    pending = data[-size:]
                    data = data[:-size]
                    break
            write(data)
        write(pending)

    thread = threading.Thread(target=forward, daemon=True)
    thread.start()
    try:
        returncode = process.wait()
    except KeyboardInterrupt:
        process.wait()
        raise
    thread.join(timeout=2)
    return returncode
