"""Command line entry point: segwhy main.c | segwhy ./program | ... | segwhy"""

from __future__ import annotations

import glob
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional

from . import __version__
from . import messages as M
from .asan import find_reports, parse_leaks, parse_report, parse_ubsan
from .gdbrun import diagnosis_from_gdb, gdb_available, run_with_gdb
from .model import SourceFinder, display_path, resolve_frames
from .render import Style, render

SOURCE_EXTENSIONS = (".c", ".o", ".a")
# Tried in order. -fno-common lets ASan see global arrays declared without
# initializer (Apple clang still puts them in "common" sections). The division
# check matters on ARM (Apple Silicon), where x / 0 silently returns 0.
SANITIZER_FLAG_SETS = [
    ["-g", "-O0", "-fsanitize=address,integer-divide-by-zero",
     "-fno-sanitize-recover=integer-divide-by-zero", "-fno-omit-frame-pointer", "-fno-common"],
    ["-g", "-O0", "-fsanitize=address", "-fno-omit-frame-pointer", "-fno-common"],
]
PLAIN_COMPILE_FLAGS = ["-g", "-O0"]
_STDERR_KEEP = 1 << 20  # bytes of program stderr kept to look for UBSan reports


class Options:
    def __init__(self) -> None:
        self.lang = M.FR if os.environ.get("SEGWHY_LANG", "").lower().startswith("fr") else M.EN
        self.verbose = False
        self.action: Optional[str] = None  # "help", "version", "flags"
        self.compile_args: List[str] = []
        self.target: Optional[str] = None
        self.program_args: List[str] = []


def parse_args(argv: List[str]) -> Options:
    opts = Options()
    seen_source = False
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            opts.program_args = argv[index + 1:]
            break
        if arg == "--fr":
            opts.lang = M.FR
        elif arg == "--en":
            opts.lang = M.EN
        elif arg == "--verbose":
            opts.verbose = True
        elif arg in ("--help", "-h"):
            opts.action = "help"
        elif arg in ("--version", "-V"):
            opts.action = "version"
        elif arg == "--flags":
            opts.action = "flags"
        elif arg.endswith(SOURCE_EXTENSIONS) or arg.startswith("-") or seen_source:
            opts.compile_args.append(arg)
            seen_source = seen_source or arg.endswith(".c")
        else:
            # An existing program: everything after it belongs to the program.
            opts.target = arg
            rest = argv[index + 1:]
            opts.program_args = rest[1:] if rest[:1] == ["--"] else rest
            break
        index += 1
    return opts


# ---- output helpers -----------------------------------------------------------

def say(text: str = "") -> None:
    sys.stdout.flush()
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


def exit_code_of(returncode: int) -> int:
    return 128 - returncode if returncode < 0 else returncode


def find_compiler() -> Optional[List[str]]:
    env_cc = os.environ.get("CC")
    if env_cc:
        parts = shlex.split(env_cc)
        if parts and shutil.which(parts[0]):
            return parts
    for name in ("gcc", "clang", "cc"):
        if shutil.which(name):
            return [name]
    return None


def has_asan(binary: str) -> bool:
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


# ---- running ----------------------------------------------------------------------

_ASAN_NOISE = b"AddressSanitizer:DEADLYSIGNAL\n"


def _run_filtering_stderr(command: List[str], env: dict, keep: Optional[bytearray] = None) -> subprocess.CompletedProcess:
    """Run the program with the real stdin/stdout, forwarding its stderr live
    minus the "AddressSanitizer:DEADLYSIGNAL" line ASan prints even with log_path.
    The last part of stderr is copied into `keep` (UBSan writes its reports there)."""
    import threading

    process = subprocess.Popen(command, env=env, stderr=subprocess.PIPE)
    out = getattr(sys.stderr, "buffer", None)

    def write(data: bytes) -> None:
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
    return subprocess.CompletedProcess(command, returncode)

def run_with_asan(binary: str, args: List[str], opts: Options, style: Style, workdir: str) -> int:
    prefix = os.path.join(workdir, "asan")
    ours = [
        "log_path=" + prefix,
        "detect_leaks=" + ("1" if sys.platform.startswith("linux") else "0"),
        "detect_stack_use_after_return=1",
        "handle_abort=1",
        "abort_on_error=0",
        "color=never",
        "symbolize=1",
    ]
    user = os.environ.get("ASAN_OPTIONS", "")
    user_ub = os.environ.get("UBSAN_OPTIONS", "")
    env = dict(
        os.environ,
        ASAN_OPTIONS=":".join(([user] if user else []) + ours),
        UBSAN_OPTIONS=":".join(([user_ub] if user_ub else []) + ["print_stacktrace=0", "color=never"]),
    )
    stderr_copy = bytearray()
    try:
        completed = _run_filtering_stderr([binary, *args], env, stderr_copy)
    except KeyboardInterrupt:
        return 130
    except OSError as error:
        say(str(error))
        return 126

    text = ""
    for path in sorted(glob.glob(prefix + ".*")):
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text += handle.read() + "\n"
        except OSError:
            pass

    reports = [d for d in (parse_report(r) for r in find_reports(text)) if d is not None]
    if not reports:
        # UBSan writes to ASan's log file on macOS (clang), to stderr with gcc.
        reports = parse_ubsan(text + "\n" + stderr_copy.decode("utf-8", errors="replace"))
    finder = SourceFinder([a for a in opts.compile_args if a.endswith(".c")])
    reports = [resolve_frames(d, finder) for d in reports]
    code = exit_code_of(completed.returncode)
    if reports:
        say()
        say(render(reports[0], opts.lang, opts.verbose, style))
        return code or 1
    if completed.returncode < 0:
        say()
        say(style.title("💥 " + M.LABELS[opts.lang]["killed"].format(signal=_signal_name(-completed.returncode))))
        return code
    say()
    line = style.good("✅ " + M.LABELS[opts.lang]["ok"])
    if code != 0:
        line += " " + style.dim(M.LABELS[opts.lang]["exit_code"].format(code=code))
    say(line)
    leaks = parse_leaks(text)
    if leaks:
        count, size, frame = leaks
        where = f"{display_path(finder.resolve(frame.file))}:{frame.line}" if frame else "?"
        say("   " + M.LABELS[opts.lang]["leaks"].format(count=count, bytes=size, where=where))
    return code


def run_with_debugger(binary: str, args: List[str], opts: Options, style: Style) -> int:
    labels = M.LABELS[opts.lang]
    if gdb_available() and sys.platform.startswith("linux"):
        result, code = run_with_gdb(binary, args)
        if code == 130 and (result is None or result.get("signo") == 2):
            return 130
        if result and result.get("status") == "exited":
            say()
            say(style.good("✅ " + labels["ok_gdb"]) + " " + style.dim(labels["ok_gdb_note"]))
            return code
        if result and result.get("status") == "signal":
            say()
            say(render(diagnosis_from_gdb(result), opts.lang, opts.verbose, style))
            return code
        # gdb could not run the program (ptrace not allowed...): run it directly.
    try:
        completed = subprocess.run([binary, *args])
    except KeyboardInterrupt:
        return 130
    if completed.returncode < 0:
        say()
        say(style.title("💥 " + labels["no_debugger"].format(signal=_signal_name(-completed.returncode))))
        say(labels["no_debugger_hint"])
    return exit_code_of(completed.returncode)


def _signal_name(number: int) -> str:
    import signal as signals
    try:
        return signals.Signals(number).name
    except ValueError:
        return f"signal {number}"


# ---- modes --------------------------------------------------------------------------

def compile_mode(opts: Options, style: Style) -> int:
    labels = M.LABELS[opts.lang]
    for arg in opts.compile_args:
        if arg.endswith(".c") and not os.path.exists(arg):
            say(labels["not_found"].format(path=arg))
            return 2
    compiler = find_compiler()
    if compiler is None:
        say(labels["no_compiler"])
        return 2

    first_source = next(a for a in opts.compile_args if a.endswith(".c"))
    workdir = tempfile.mkdtemp(prefix="segwhy-")
    binary = os.path.join(workdir, os.path.splitext(os.path.basename(first_source))[0])
    try:
        for flags in SANITIZER_FLAG_SETS:
            with_asan = subprocess.run(
                [*compiler, *flags, *opts.compile_args, "-o", binary, "-lm"],
                capture_output=True, text=True, errors="replace",
            )
            if with_asan.returncode == 0:
                if with_asan.stderr.strip():
                    sys.stderr.write(with_asan.stderr)
                return run_with_asan(binary, opts.program_args, opts, style, workdir)

        plain = subprocess.run(
            [*compiler, *PLAIN_COMPILE_FLAGS, *opts.compile_args, "-o", binary, "-lm"],
            capture_output=True, text=True, errors="replace",
        )
        if plain.returncode != 0:
            sys.stderr.write(plain.stderr)
            say()
            say(style.title("💥 " + labels["compile_failed"]))
            return 2
        if plain.stderr.strip():
            sys.stderr.write(plain.stderr)
        say(style.dim(labels["no_asan"].format(cc=" ".join(compiler))))
        return run_with_debugger(binary, opts.program_args, opts, style)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_mode(opts: Options, style: Style) -> int:
    labels = M.LABELS[opts.lang]
    target = opts.target or ""
    if not os.path.exists(target):
        say(labels["not_found"].format(path=target))
        return 2
    if os.path.isdir(target) or not os.access(target, os.X_OK):
        say(labels["not_executable"].format(path=target))
        return 2
    binary = target if os.sep in target else os.path.join(".", target)
    if has_asan(binary):
        workdir = tempfile.mkdtemp(prefix="segwhy-")
        try:
            return run_with_asan(binary, opts.program_args, opts, style, workdir)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    return run_with_debugger(binary, opts.program_args, opts, style)


def pipe_mode(opts: Options) -> int:
    """Act as a filter: copy the input, then add the explanations (all on stdout,
    so `... 2>&1 | segwhy | tee log` keeps everything together)."""
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
    reports = [resolve_frames(d, finder) for d in reports]
    for diag in reports:
        print()
        print(render(diag, opts.lang, opts.verbose, style))
    leaks = parse_leaks(text)
    if leaks:
        count, size, frame = leaks
        where = f"{display_path(frame.file)}:{frame.line}" if frame else "?"
        print()
        print("💧 " + M.LABELS[opts.lang]["leaks_only"].format(count=count, bytes=size, where=where))
    if not reports and not leaks:
        print(style.dim(M.LABELS[opts.lang]["no_report"]))
        return 0
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    opts = parse_args(list(sys.argv[1:] if argv is None else argv))
    style = Style(sys.stderr)

    if opts.action == "version":
        print(f"segwhy {__version__}")
        return 0
    if opts.action == "flags":
        print(M.FLAGS_TEXT[opts.lang], end="")
        return 0
    if opts.action == "help":
        print(M.HELP_TEXT[opts.lang], end="")
        return 0

    if any(arg.endswith(".c") for arg in opts.compile_args):
        return compile_mode(opts, style)
    if opts.target:
        return run_mode(opts, style)
    if not sys.stdin.isatty():
        return pipe_mode(opts)
    print(M.HELP_TEXT[opts.lang], end="")
    return 0
