"""The three ways to use segwhy. Each one returns segwhy's exit code.

    compile_mode   segwhy main.c utils.c -- args    compile, run, explain
    run_mode       segwhy ./program args            run an existing program, explain
    pipe_mode      ./tests 2>&1 | segwhy            explain the reports in a text

segwhy's own messages go to stderr (so they never mix with what the program
writes to stdout), except in pipe mode where everything goes to stdout.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from typing import List

from . import lang
from .debugger import diagnosis_from_gdb, gdb_available, run_with_gdb, signal_name
from .render import Style, render
from .runner import SanitizedRun, compile_program, find_compiler, has_asan, run_plain, run_sanitized
from .sanitizers import find_reports, parse_leaks, parse_report, parse_ubsan
from .source import SourceFinder, display_path, resolve_frames

# segwhy's own exit codes (otherwise it returns the program's exit code).
EXIT_USAGE = 2         # file not found, no compiler, compilation failed
EXIT_INTERRUPTED = 130  # Ctrl+C
EXIT_CANNOT_RUN = 126   # the program couldn't be started


def say(text: str = "") -> None:
    """Print one of segwhy's messages, after anything the program printed."""
    sys.stdout.flush()
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


def exit_code_of(returncode: int) -> int:
    """The shell's exit code for a return code: 139 for a program killed by SIGSEGV (-11)."""
    return 128 - returncode if returncode < 0 else returncode


# ---- segwhy main.c ------------------------------------------------------------------

def compile_mode(opts) -> int:
    """Compile the user's .c files, run the program, explain what happened."""
    labels = lang.get(opts.lang).LABELS
    style = Style(sys.stderr)
    for arg in opts.compile_args:
        if arg.endswith(".c") and not os.path.exists(arg):
            say(labels["not_found"].format(path=arg))
            return EXIT_USAGE
    compiler = find_compiler()
    if compiler is None:
        say(labels["no_compiler"])
        return EXIT_USAGE

    first_source = next(a for a in opts.compile_args if a.endswith(".c"))
    workdir = tempfile.mkdtemp(prefix="segwhy-")
    binary = os.path.join(workdir, os.path.splitext(os.path.basename(first_source))[0])
    try:
        compiled = compile_program(compiler, opts.compile_args, binary)
        if not compiled.ok:
            sys.stderr.write(compiled.messages)
            say()
            say(style.title("💥 " + labels["compile_failed"]))
            return EXIT_USAGE
        if compiled.messages.strip():
            sys.stderr.write(compiled.messages)  # warnings
        if compiled.sanitized:
            return run_and_explain_sanitized(binary, opts, style, workdir)
        say(style.dim(labels["no_asan"].format(cc=" ".join(compiler))))
        return run_and_explain_with_gdb(binary, opts, style)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---- segwhy ./program -----------------------------------------------------------------

def run_mode(opts) -> int:
    """Run an existing program (built by the user's Makefile...), explain what happened."""
    labels = lang.get(opts.lang).LABELS
    style = Style(sys.stderr)
    target = opts.target or ""
    if not os.path.exists(target):
        say(labels["not_found"].format(path=target))
        return EXIT_USAGE
    if os.path.isdir(target) or not os.access(target, os.X_OK):
        say(labels["not_executable"].format(path=target))
        return EXIT_USAGE
    binary = target if os.sep in target else os.path.join(".", target)
    if not has_asan(binary):
        return run_and_explain_with_gdb(binary, opts, style)
    workdir = tempfile.mkdtemp(prefix="segwhy-")
    try:
        return run_and_explain_sanitized(binary, opts, style, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---- ./tests 2>&1 | segwhy ---------------------------------------------------------------

def pipe_mode(opts) -> int:
    """Copy stdin to stdout, then explain every report found in it.
    Everything goes to stdout so that `... | segwhy | tee log` keeps it together."""
    texts = lang.get(opts.lang)
    style = Style(sys.stdout)
    chunks: List[str] = []
    try:
        for line in sys.stdin:
            sys.stdout.write(line)
            sys.stdout.flush()
            chunks.append(line)
    except KeyboardInterrupt:
        pass
    text = "".join(chunks)

    reports = [d for d in (parse_report(r) for r in find_reports(text)) if d is not None]
    reports += parse_ubsan(text)
    finder = SourceFinder()
    for diag in reports:
        resolve_frames(diag, finder)
        print()
        print(render(diag, opts.lang, opts.verbose, style))
    leaks = parse_leaks(text)
    if leaks:
        count, size, frame = leaks
        where = f"{display_path(frame.file)}:{frame.line}" if frame else "?"
        print()
        print("💧 " + texts.LABELS["leaks_only"].format(count=count, bytes=size, where=where))
    if not reports and not leaks:
        print(style.dim(texts.LABELS["no_report"]))
        return 0
    return 1  # makes a CI job fail when a report was found


# ---- shared by compile_mode and run_mode -----------------------------------------------------

def run_and_explain_sanitized(binary: str, opts, style: Style, workdir: str) -> int:
    """Run a program built with AddressSanitizer, then print the explanation."""
    try:
        run = run_sanitized(binary, opts.program_args, workdir)
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except OSError as error:
        say(str(error))
        return EXIT_CANNOT_RUN
    return explain_sanitized_run(run, opts, style)


def explain_sanitized_run(run: SanitizedRun, opts, style: Style) -> int:
    """Print what the sanitizers found during `run` (or that all went well)."""
    labels = lang.get(opts.lang).LABELS
    reports = [d for d in (parse_report(r) for r in find_reports(run.log)) if d is not None]
    if not reports:
        # UBSan writes to ASan's log file on macOS (clang), to stderr with gcc.
        reports = parse_ubsan(run.log + "\n" + run.stderr)
    finder = SourceFinder([a for a in opts.compile_args if a.endswith(".c")])
    for diag in reports:
        resolve_frames(diag, finder)
    code = exit_code_of(run.returncode)

    if reports:
        say()
        say(render(reports[0], opts.lang, opts.verbose, style))  # the first error is the real one
        return code or 1
    if run.returncode < 0:  # killed by a signal the sanitizers didn't report
        say()
        say(style.title("💥 " + labels["killed"].format(signal=signal_name(-run.returncode))))
        return code

    say()
    line = style.good("✅ " + labels["ok"])
    if code != 0:
        line += " " + style.dim(labels["exit_code"].format(code=code))
    say(line)
    leaks = parse_leaks(run.log)
    if leaks:
        count, size, frame = leaks
        where = f"{display_path(finder.resolve(frame.file))}:{frame.line}" if frame else "?"
        say("   " + labels["leaks"].format(count=count, bytes=size, where=where))
    return code


def run_and_explain_with_gdb(binary: str, opts, style: Style) -> int:
    """Run a program built without AddressSanitizer under gdb, then print the
    explanation. Without gdb, just run it and say what can't be known."""
    labels = lang.get(opts.lang).LABELS
    if gdb_available():
        result, code = run_with_gdb(binary, opts.program_args)
        if code == EXIT_INTERRUPTED and (result is None or result.get("signo") == 2):
            return EXIT_INTERRUPTED
        if result and result.get("status") == "exited":
            say()
            say(style.good("✅ " + labels["ok_gdb"]) + " " + style.dim(labels["ok_gdb_note"]))
            return code
        if result and result.get("status") == "signal":
            say()
            say(render(diagnosis_from_gdb(result), opts.lang, opts.verbose, style))
            return code
        # gdb couldn't run the program (ptrace not allowed...): run it directly.
    try:
        returncode = run_plain(binary, opts.program_args)
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    if returncode < 0:
        say()
        say(style.title("💥 " + labels["no_debugger"].format(signal=signal_name(-returncode))))
        say(labels["no_debugger_hint"])
    return exit_code_of(returncode)
