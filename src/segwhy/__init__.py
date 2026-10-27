"""segwhy: tells you why your C program crashed, in plain words.

How the code is organized (each file starts with a longer explanation):

    cli.py          the `segwhy` command: arguments, picks a mode
    modes.py        the 3 modes: segwhy main.c / segwhy ./program / ... | segwhy
    runner.py       compiles and runs programs with the sanitizers
    debugger.py     runs programs under gdb when there are no sanitizers
    gdb_helper.py     (the script gdb runs for debugger.py)
    sanitizers.py   reads AddressSanitizer / UBSan / LeakSanitizer reports
    model.py        Frame and Diagnosis: what the readers produce
    kinds.py        the list of problems segwhy knows
    source.py       reads the user's C code (which variable is NULL...)
    render.py       turns a Diagnosis into the lines segwhy prints
    lang/           all the texts, one file per language

The path of a crash:  runner/debugger -> sanitizers/debugger -> Diagnosis -> render
"""

__version__ = "0.1.0"
