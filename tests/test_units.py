"""Small pieces tested directly, without running segwhy: reading C lines,
command line arguments, languages."""

import pytest

from helpers import segwhy  # also puts src/ on the path

from segwhy import lang
from segwhy.cli import parse_args
from segwhy.sanitizers import parse_ubsan
from segwhy.source import call_arguments, pointer_candidates


# ---- source.py: reading a line of C -----------------------------------------------------

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


# ---- sanitizers.py ----------------------------------------------------------------------

def test_ubsan_division():
    text = "div_zero.c:5:18: runtime error: division by zero\n"
    reports = parse_ubsan(text)
    assert len(reports) == 1 and reports[0].kind == "div_zero"
    assert reports[0].frames[0].line == 5


# ---- cli.py ----------------------------------------------------------------------------

def test_parse_compile_mode():
    opts = parse_args(["--fr", "main.c", "utils.c", "-lm", "--", "input.txt", "-v"])
    assert opts.lang == "fr"
    assert opts.compile_args == ["main.c", "utils.c", "-lm"]
    assert opts.program_args == ["input.txt", "-v"]


def test_parse_run_mode():
    opts = parse_args(["--verbose", "./server", "--port", "80"])
    assert opts.verbose
    assert opts.target == "./server"
    assert opts.program_args == ["--port", "80"]  # options after the program are the program's


def test_flags_and_help():
    code, output = segwhy("--flags")
    assert code == 0 and "-fsanitize=address" in output
    code, output = segwhy("--help")
    assert code == 0 and "Usage" in output
    code, output = segwhy("--fr", "--help")
    assert "Utilisation" in output


# ---- lang/ -----------------------------------------------------------------------------

@pytest.mark.parametrize("code", sorted(lang.LANGUAGES))
def test_language_has_the_same_keys_as_english(code):
    """Catches typos in keys, and lists what a new translation still misses."""
    module = lang.LANGUAGES[code]
    for table in ("LABELS", "REASONS", "HINTS"):
        english = set(getattr(lang.en, table))
        translated = set(getattr(module, table, {}))
        assert translated <= english, f"{code}.{table}: unknown keys {sorted(translated - english)}"
        assert translated == english, f"{code}.{table}: not translated yet {sorted(english - translated)}"


def test_unknown_language_falls_back_to_english():
    assert lang.get("xx").LABELS["reason"] == "Reason:"
