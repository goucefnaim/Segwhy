"""End-to-end tests: compile each crashing program and check what segwhy says.

Run with:  python -m pytest -q
"""

import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
CRASHES = os.path.join(HERE, "crashes")
SRC = os.path.join(os.path.dirname(HERE), "src")

sys.path.insert(0, SRC)

from segwhy.render import call_arguments, pointer_candidates  # noqa: E402


def segwhy(*args, stdin=None, cwd=CRASHES, env_extra=None):
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


def asan_works():
    compiler = shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")
    if not compiler:
        return False
    out = os.path.join(HERE, ".asan_probe")
    probe = subprocess.run(
        [compiler, "-fsanitize=address", "-x", "c", "-", "-o", out],
        input="int main(void){return 0;}", capture_output=True, text=True,
    )
    if os.path.exists(out):
        os.remove(out)
    return probe.returncode == 0


needs_asan = pytest.mark.skipif(not asan_works(), reason="no compiler with AddressSanitizer")
needs_gdb = pytest.mark.skipif(
    shutil.which("gdb") is None or not sys.platform.startswith("linux") or not shutil.which("gcc"),
    reason="gdb fallback is Linux-only",
)


# ---- compile mode (beginners) ------------------------------------------------------

EXPECTED = {
    "null_deref.c": ["Segmentation fault", "NULL pointer dereference", "null_deref.c:11", "'n' is NULL"],
    "heap_overflow.c": ["out-of-bounds write on a block allocated with malloc", "index 5", "0 to 4"],
    "stack_array.c": ["out-of-bounds write on local array 'scores'", "index 5"],
    "global_array.c": ["global variable 'grid'", "index 4", "0 to 3"],
    "use_after_free.c": ["use of memory after free()", "use_after_free.c:11", "freed at use_after_free.c:10"],
    "double_free.c": ["double free", "double_free.c:13", "already freed at double_free.c:5"],
    "recursion.c": ["stack overflow", "factorial() calls itself endlessly", "recursion.c:5"],
    "string_literal.c": ["write to read-only memory", "string_literal.c:7", "char s[]"],
    "wild_pointer.c": ["invalid pointer", "wild_pointer.c:9"],
    "libc_null.c": ["NULL pointer passed to strlen()", "libc_null.c:9", "'line'"],
    "div_zero.c": ["division by zero", "div_zero.c:5"],
    "args.c": ["NULL pointer passed to atoi()", "'argv[1]'"],
    "assert_fail.c": ["Program aborted", "assert_fail.c:8"],
}


@needs_asan
@pytest.mark.parametrize("source", sorted(EXPECTED))
def test_compile_mode_explains_crash(source):
    code, output = segwhy(source)
    assert code != 0, output
    for expected in EXPECTED[source]:
        assert expected in output, f"missing {expected!r} in:\n{output}"
    assert "DEADLYSIGNAL" not in output


@needs_asan
def test_return_local():
    # gcc turns the address of a dead local into NULL; clang reports it as is.
    code, output = segwhy("return_local.c")
    assert code != 0
    assert "NULL pointer dereference" in output or "after its function returned" in output


@needs_asan
def test_multi_file_project():
    code, output = segwhy("project/main.c", "project/parser.c")
    assert code != 0
    for expected in ["project/parser.c:17", "value_length()", "project/parser.c:29", "project/main.c:9",
                     "'value' is NULL"]:
        assert expected in output, output


@needs_asan
def test_program_arguments_after_double_dash():
    code, output = segwhy("args.c", "--", "7")
    assert code == 0, output
    assert "7 squared is 49" in output
    assert "No crash" in output


@needs_asan
def test_clean_program():
    code, output = segwhy("ok.c")
    assert code == 0
    assert "Hello, no crash here." in output
    assert "No crash, no memory error detected." in output


def test_compile_error():
    if not (shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")):
        pytest.skip("no compiler")
    code, output = segwhy("compile_error.c")
    assert code == 2
    assert "Compilation failed" in output


@needs_asan
def test_french():
    code, output = segwhy("--fr", "heap_overflow.c")
    assert "Erreur mémoire" in output
    assert "l'indice 5" in output
    code, output = segwhy("null_deref.c", env_extra={"SEGWHY_LANG": "fr"})
    assert "pointeur NULL" in output


@needs_asan
def test_verbose_shows_full_stack():
    code, output = segwhy("--verbose", "null_deref.c")
    assert "#0" in output and "#1" in output


def test_missing_file():
    code, output = segwhy("does_not_exist.c")
    assert code == 2
    assert "File not found" in output


def test_flags_and_help():
    code, output = segwhy("--flags")
    assert code == 0 and "-fsanitize=address" in output
    code, output = segwhy("--help")
    assert code == 0 and "Usage" in output
    code, output = segwhy("--fr", "--help")
    assert "Utilisation" in output


# ---- existing binaries (big projects) ------------------------------------------------

def _build(tmp_path, source, *flags):
    binary = str(tmp_path / os.path.splitext(os.path.basename(source))[0])
    sources = source if isinstance(source, list) else [source]
    subprocess.run(["gcc", *flags, *sources, "-o", binary], cwd=CRASHES, check=True, capture_output=True)
    return binary


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
    binary = _build(tmp_path, source, "-g", "-O0")
    code, output = segwhy(binary)
    assert code > 128, output
    for item in expected:
        assert item in output, output
    assert "Program received signal" not in output  # gdb's own chatter is hidden


@needs_gdb
def test_gdb_without_debug_info(tmp_path):
    binary = _build(tmp_path, "null_deref.c", "-O0")
    code, output = segwhy(binary)
    assert "NULL pointer dereference" in output
    assert "rebuild with -g" in output


@needs_gdb
def test_gdb_keeps_program_io(tmp_path):
    binary = _build(tmp_path, "args.c", "-g")
    code, output = segwhy(binary, "12")
    assert code == 0
    assert "12 squared is 144" in output
    assert "Inferior" not in output


@needs_asan
def test_run_mode_with_asan_binary(tmp_path):
    compiler = shutil.which("gcc") or shutil.which("clang")
    binary = str(tmp_path / "uaf")
    subprocess.run([compiler, "-g", "-fsanitize=address", "use_after_free.c", "-o", binary],
                   cwd=CRASHES, check=True, capture_output=True)
    code, output = segwhy(binary)
    assert code != 0
    assert "use of memory after free()" in output


# ---- pipe mode (CI, test suites) --------------------------------------------------------

REPORT = """some test output
=================================================================
==42==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x503000000054 at pc 0x1 bp 0x2 sp 0x3
WRITE of size 4 at 0x503000000054 thread T0
    #0 0x55b996773237 in main /src/heap_overflow.c:8
    #1 0x7f3e5b62a1c9 in __libc_start_call_main ../sysdeps/nptl/libc_start_call_main.h:58

0x503000000054 is located 0 bytes after 20-byte region [0x503000000040,0x503000000054)
allocated by thread T0 here:
    #0 0x7f3e5bafd9c7 in malloc ../../../../src/libsanitizer/asan/asan_malloc_linux.cpp:69
    #1 0x55b9967731de in main /src/heap_overflow.c:5

SUMMARY: AddressSanitizer: heap-buffer-overflow /src/heap_overflow.c:8 in main
==42==ABORTING
"""


def test_pipe_mode_explains_report():
    code, output = segwhy(stdin=REPORT)
    assert code == 1
    assert "some test output" in output  # input is passed through
    assert "/src/heap_overflow.c:8" in output
    assert "index 5" in output


def test_pipe_mode_without_report():
    code, output = segwhy(stdin="all tests passed\n")
    assert code == 0
    assert "No AddressSanitizer report" in output


# ---- source heuristics -----------------------------------------------------------------

@pytest.mark.parametrize("line,expected", [
    ("return n->value;", ["n"]),
    ("*ptr = 42;", ["ptr"]),
    ("int x = a * b;", []),
    ("total += list->head->value;", ["list", "list->head"]),
    ("while (value[len] != ';')", ["value"]),
    ('printf("%s->%d", s, *p);', ["p"]),
    ("return *cursor;", ["cursor"]),
])
def test_pointer_candidates(line, expected):
    assert pointer_candidates(line) == expected


def test_call_arguments():
    assert call_arguments("n = atoi(argv[1]);", "atoi") == ["argv[1]"]
    assert call_arguments('printf("%zu", strlen(line));', "strlen") == ["line"]
    assert call_arguments("strcpy(dst, src);", "strcpy") == ["dst", "src"]


# ---- reports seen on macOS (Apple clang, arm64) ----------------------------------------

MAC_STRLEN = """==1==ERROR: AddressSanitizer: SEGV on unknown address 0x000000000000 (pc 0x1 bp 0x2 sp 0x3 T0)
==1==The signal is caused by a READ memory access.
==1==Hint: address points to the zero page.
    #0 0x000188c2e1b4 in _platform_strlen+0x4 (libsystem_platform.dylib:arm64e+0x11b4)
    #1 0x000104e2c9a0 in wrap_strlen+0x50 (libclang_rt.asan_osx_dynamic.dylib:arm64e+0x149a0)
    #2 0x0001044188ac in main libc_null.c:9
    #3 0x000188b104e0 in start+0x1b4c (dyld:arm64e+0x204e0)
SUMMARY: AddressSanitizer: SEGV (libsystem_platform.dylib:arm64e+0x11b4) in _platform_strlen+0x4
==1==ABORTING
"""

MAC_LITERAL = """==1==ERROR: AddressSanitizer: BUS on unknown address 0x000102a3bf80 (pc 0x000102a3b8f0 bp 0x2 sp 0x3 T0)
==1==The signal is caused by a WRITE memory access.
    #0 0x000102a3b8f0 in main string_literal.c:7
    #1 0x000188b104e0 in start+0x1b4c (dyld:arm64e+0x204e0)
SUMMARY: AddressSanitizer: BUS string_literal.c:7 in main
==1==ABORTING
"""


def test_mac_library_function_names():
    code, output = segwhy(stdin=MAC_STRLEN)
    assert "NULL pointer passed to strlen()" in output, output
    assert "libc_null.c:9" in output


def test_mac_bus_error_on_string_literal():
    code, output = segwhy(stdin=MAC_LITERAL)
    assert "write to read-only memory" in output, output
