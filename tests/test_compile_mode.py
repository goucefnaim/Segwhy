"""segwhy main.c: compile each program of tests/crashes/ and check what segwhy says.

To add a case: put a small crashing program in tests/crashes/ and add a line
to EXPECTED with the words segwhy must print.
"""

import pytest

from helpers import needs_asan, needs_compiler, segwhy

# program -> pieces of text that must appear in segwhy's output
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
def test_explains_crash(source):
    code, output = segwhy(source)
    assert code != 0, output
    for expected in EXPECTED[source]:
        assert expected in output, f"missing {expected!r} in:\n{output}"
    assert "DEADLYSIGNAL" not in output  # ASan's noise is hidden


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


@needs_compiler
def test_compile_error():
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
