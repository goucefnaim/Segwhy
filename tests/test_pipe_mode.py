"""... 2>&1 | segwhy: explain reports found in a text.

This is also where the real reports of tests/reports/ are checked. They come
from other systems (macOS, other compilers) and keep segwhy working there
even when the tests run on Linux.

To add one: save the raw report (run your program with ASAN_OPTIONS=color=never)
as tests/reports/<system>_<case>.txt and add a line to EXPECTED.
"""

import pytest

from helpers import read_report, segwhy

# report file -> pieces of text that must appear in segwhy's output
EXPECTED = {
    "linux_heap_overflow.txt": ["/src/heap_overflow.c:8", "index 5", "0 to 4"],
    "mac_strlen_null.txt": ["NULL pointer passed to strlen()", "libc_null.c:9"],
    "mac_string_literal.txt": ["write to read-only memory"],
    "mac_string_literal_no_address.txt": ["write to read-only memory"],
    # macOS shows only the top frame: the recursive call is found in the source.
    "mac_recursion.txt": ["factorial() calls itself endlessly", "recursion.c:5"],
    # macOS gives "parser.c" for "project/parser.c": the real file is found.
    "mac_project_null.txt": ["project/parser.c:17", "'value' is NULL"],
    "ubsan_div_zero.txt": ["division by zero", "div_zero.c:5"],
}


@pytest.mark.parametrize("report", sorted(EXPECTED))
def test_explains_report(report):
    code, output = segwhy(stdin=read_report(report))
    assert code == 1, output  # a report was found: fail the CI job
    for expected in EXPECTED[report]:
        assert expected in output, f"missing {expected!r} in:\n{output}"
    assert "rebuild with -g" not in output


def test_input_is_passed_through():
    code, output = segwhy(stdin="some test output\n" + read_report("linux_heap_overflow.txt"))
    assert "some test output" in output
    assert "index 5" in output


def test_without_report():
    code, output = segwhy(stdin="all tests passed\n")
    assert code == 0
    assert "No AddressSanitizer report" in output
