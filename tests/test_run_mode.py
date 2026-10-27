"""segwhy ./program: programs built by the user, with or without AddressSanitizer."""

import shutil
import subprocess

import pytest

from helpers import CRASHES, build, needs_asan, needs_gdb, segwhy


# ---- built without AddressSanitizer: segwhy uses gdb ------------------------------------

@needs_gdb
@pytest.mark.parametrize("source,expected", [
    ("null_deref.c", ["NULL pointer dereference", "null_deref.c:11", "'n' is NULL"]),
    ("string_literal.c", ["write to read-only memory"]),
    ("recursion.c", ["factorial() calls itself endlessly"]),
    ("libc_null.c", ["NULL pointer passed to strlen()"]),
    ("div_zero.c", ["division by zero", "div_zero.c:5"]),
    ("assert_fail.c", ["Program aborted", "assert_fail.c:8"]),
])
def test_gdb_fallback(tmp_path, source, expected):
    binary = build(tmp_path, source, "-g", "-O0")
    code, output = segwhy(binary)
    assert code > 128, output  # 128 + signal number, like the shell
    for item in expected:
        assert item in output, output
    assert "Program received signal" not in output  # gdb's own messages are hidden


@needs_gdb
def test_gdb_without_debug_info(tmp_path):
    binary = build(tmp_path, "null_deref.c", "-O0")
    code, output = segwhy(binary)
    assert "NULL pointer dereference" in output
    assert "rebuild with -g" in output


@needs_gdb
def test_gdb_keeps_program_io(tmp_path):
    binary = build(tmp_path, "args.c", "-g")
    code, output = segwhy(binary, "12")
    assert code == 0
    assert "12 squared is 144" in output
    assert "Inferior" not in output


# ---- built with AddressSanitizer --------------------------------------------------------

@needs_asan
def test_asan_binary(tmp_path):
    compiler = shutil.which("gcc") or shutil.which("clang")
    binary = str(tmp_path / "uaf")
    subprocess.run([compiler, "-g", "-fsanitize=address", "use_after_free.c", "-o", binary],
                   cwd=CRASHES, check=True, capture_output=True)
    code, output = segwhy(binary)
    assert code != 0
    assert "use of memory after free()" in output
