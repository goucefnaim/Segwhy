"""Shared by all the tests: run segwhy like a user would, and skip tests
that need a tool this machine doesn't have."""

import os
import shutil
import subprocess
import sys

import pytest

TESTS = os.path.dirname(os.path.abspath(__file__))
CRASHES = os.path.join(TESTS, "crashes")    # small C programs, one per kind of crash
REPORTS = os.path.join(TESTS, "reports")    # raw sanitizer reports from real systems
SRC = os.path.join(os.path.dirname(TESTS), "src")

if SRC not in sys.path:
    sys.path.insert(0, SRC)


def segwhy(*args, stdin=None, cwd=CRASHES, env_extra=None):
    """Run `segwhy args...` in a clean environment (no colors, English).
    Returns (exit code, everything it printed)."""
    env = dict(os.environ, NO_COLOR="1", PYTHONPATH=SRC)
    env.pop("SEGWHY_LANG", None)
    env.pop("CC", None)
    if env_extra:
        env.update(env_extra)
    completed = subprocess.run(
        [sys.executable, "-m", "segwhy", *args],
        cwd=cwd, env=env, input=stdin, capture_output=True, text=True, timeout=120,
    )
    return completed.returncode, completed.stdout + completed.stderr


def read_report(name):
    """The content of tests/reports/<name>."""
    with open(os.path.join(REPORTS, name)) as handle:
        return handle.read()


def compiler():
    """A C compiler on this machine, or None."""
    return shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")


def asan_works():
    """True when the compiler can build programs with AddressSanitizer."""
    cc = compiler()
    if not cc:
        return False
    out = os.path.join(TESTS, ".asan_probe")
    probe = subprocess.run(
        [cc, "-fsanitize=address", "-x", "c", "-", "-o", out],
        input="int main(void){return 0;}", capture_output=True, text=True,
    )
    if os.path.exists(out):
        os.remove(out)
    return probe.returncode == 0


def build(tmp_path, source, *flags):
    """Compile tests/crashes/<source> with gcc and `flags`. Returns the program's path."""
    binary = str(tmp_path / os.path.splitext(os.path.basename(source))[0])
    subprocess.run(["gcc", *flags, source, "-o", binary], cwd=CRASHES, check=True, capture_output=True)
    return binary


needs_compiler = pytest.mark.skipif(compiler() is None, reason="no C compiler")
needs_asan = pytest.mark.skipif(not asan_works(), reason="no compiler with AddressSanitizer")
needs_gdb = pytest.mark.skipif(
    shutil.which("gdb") is None or not sys.platform.startswith("linux") or not shutil.which("gcc"),
    reason="the gdb fallback is Linux-only",
)
