"""The `segwhy` command: read the arguments, pick a mode (see modes.py)."""

from __future__ import annotations

import sys
from typing import List, Optional

from . import __version__, lang
from .modes import compile_mode, pipe_mode, run_mode

# Arguments ending like this are for the compiler (compile mode).
SOURCE_EXTENSIONS = (".c", ".o", ".a")


class Options:
    """What the user asked for on the command line."""

    def __init__(self) -> None:
        """Defaults: language from SEGWHY_LANG, nothing else set."""
        self.lang = lang.from_environment()   # "en", "fr"...
        self.verbose = False                  # --verbose
        self.action: Optional[str] = None     # "help", "version" or "flags"
        self.compile_args: List[str] = []     # .c files and compiler options
        self.target: Optional[str] = None     # an existing program to run
        self.program_args: List[str] = []     # arguments for the user's program


def parse_args(argv: List[str]) -> Options:
    """Read segwhy's arguments.

    segwhy [options] main.c utils.c -lm -- program args
    segwhy [options] ./program program args
    The first argument that isn't an option or a .c file is the program to run:
    everything after it is passed to that program."""
    opts = Options()
    seen_source = False
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            opts.program_args = argv[index + 1:]
            break
        if arg.startswith("--") and arg[2:] in lang.LANGUAGES:  # --fr, --en...
            opts.lang = arg[2:]
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
            opts.target = arg
            rest = argv[index + 1:]
            opts.program_args = rest[1:] if rest[:1] == ["--"] else rest
            break
        index += 1
    return opts


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point of the `segwhy` command. Returns the exit code."""
    opts = parse_args(list(sys.argv[1:] if argv is None else argv))
    texts = lang.get(opts.lang)

    if opts.action == "version":
        print(f"segwhy {__version__}")
        return 0
    if opts.action == "flags":
        print(texts.FLAGS, end="")
        return 0
    if opts.action == "help":
        print(texts.HELP, end="")
        return 0

    if any(arg.endswith(".c") for arg in opts.compile_args):
        return compile_mode(opts)
    if opts.target:
        return run_mode(opts)
    if not sys.stdin.isatty():
        return pipe_mode(opts)
    print(texts.HELP, end="")
    return 0
