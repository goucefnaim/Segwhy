# segwhy

**Your C program crashed. segwhy tells you why, and where.**

```
$ segwhy main.c

💥 Segmentation fault
Reason: NULL pointer dereference
Line:   list.c:11 in get_value()
        11 |  return n->value;
From:   main.c:18 in main()
Hint:   'n' is NULL here. Check it before using it (malloc() and many functions can return NULL).
```

No debugger to learn, no wall of text: one command, the line, the reason, and a hint to fix it.
For students writing their first C programs and for developers hunting a crash in a big codebase.

🇫🇷 [Version française plus bas](#en-français)

## Install

```sh
pip install git+https://github.com/goucefnaim/Segwhy
```

(Coming soon to PyPI as `pip install segwhy`. If pip refuses with "externally-managed-environment",
use `pipx install git+https://github.com/goucefnaim/Segwhy` or add `--user`.)

Requirements: Python 3.8+, and `gcc` or `clang`. Works on Linux, macOS and Windows through WSL.
`gdb` is optional: it is only used for programs built without AddressSanitizer (Linux).

## Usage

**A school project: give it your `.c` files.** segwhy compiles, runs and explains.

```sh
segwhy main.c
segwhy main.c utils.c parser.c -lm      # compiler options go next to the files
segwhy *.c -- input.txt 42              # program arguments go after --
```

**A big project: give it your program,** built by your own Makefile or CMake.

```sh
segwhy ./my_server --port 8080
```

If the program was built with AddressSanitizer, segwhy translates its report.
If not, segwhy runs it under gdb behind the scenes and still finds the line and a probable reason.
`segwhy --flags` prints the exact flags to add to a Makefile or CMake project for the best results.

**A test suite or CI: pipe the output into it.**

```sh
./run_tests 2>&1 | segwhy
```

The output goes through unchanged, and every AddressSanitizer report in it gets a short explanation.
The exit code is 1 when a report was found, so the CI job fails.

### Options

| Option | |
|---|---|
| `--fr` | messages in French (or `SEGWHY_LANG=fr`) |
| `--verbose` | full call stack |
| `--flags` | compiler flags to add to a Makefile / CMake project |
| `--version`, `--help` | |

That's all. There is nothing to configure.

## What it detects

| Problem | Example of what segwhy says |
|---|---|
| NULL pointer | `'n' is NULL here` |
| NULL passed to a library function | `NULL pointer passed to strlen()` / `'line' is probably NULL` |
| Array out of bounds (heap, stack, global) | `You accessed index 5, but valid indices go from 0 to 4` |
| Use after free | `This memory was freed at list.c:42` |
| Double free | `It was already freed at list.c:40` |
| Infinite recursion | `stack overflow: factorial() calls itself endlessly` |
| Writing to a string literal | `Use an array instead: char s[] = "...";` |
| Invalid / uninitialized pointer | `invalid pointer (uninitialized, already freed, or corrupted)` |
| Division by zero | `division by zero` |
| Failed `assert()` / `abort()` | the line of the assert |
| Memory leaks (when nothing crashed, Linux) | `1 memory leak(s): 40 bytes never freed. First one allocated at main.c:5` |

When the crash happens inside a library function, segwhy points to **the line in your code**
that called it, not to the library.

## How it works

segwhy builds on two tools that already know everything, and translates what they say:

- [AddressSanitizer](https://github.com/google/sanitizers/wiki/AddressSanitizer), built into gcc and clang.
  In `.c` mode segwhy compiles with `-g -fsanitize=address` for you. It also catches memory bugs that
  don't crash *this time* but would later.
- gdb, for programs built without AddressSanitizer. segwhy runs the program under gdb, reads the signal,
  the faulting address and the call stack, then classifies the crash.
  The program keeps your terminal: same input, output, arguments, environment and file descriptors.

If your compiler can't do AddressSanitizer (clang without its runtime, for example), segwhy falls back
to gdb automatically.

## Exit codes

segwhy returns the program's exit code, so it fits in scripts. A memory error found by AddressSanitizer
returns 1, a crash under gdb returns 128 + the signal number (139 for a segfault), a compilation error 2.

## Limitations

- The crash line is where the program died, not always where the bug is.
  AddressSanitizer (the default in `.c` mode) usually catches the real bug earlier.
- macOS (Apple clang, Intel and Apple Silicon) is tested in CI with AddressSanitizer, which is what
  `segwhy main.c` uses. For an existing program built *without* AddressSanitizer, segwhy needs gdb,
  so that fallback is Linux-only for now (lldb on macOS is planned): rebuild with `segwhy --flags`.
- On ARM processors (Apple Silicon, Raspberry Pi), a division by zero doesn't crash: it silently gives 0.
  segwhy's `.c` mode turns on the check that catches it anyway.
- Under gdb, `argv[0]` is the absolute path of the program.
- AddressSanitizer makes the program about 2x slower: fine for debugging, not for production builds.

## Contributing

Each case segwhy understands has a small crashing program in `tests/crashes/`.
To add one: write the program, add what segwhy should say to `tests/test_segwhy.py`, run `pytest`.
Found an output that is wrong or unclear? [Open an issue](https://github.com/goucefnaim/Segwhy/issues)
with the C code and what segwhy printed.
Reports from other compilers and systems (macOS, Alpine, older gcc) are very welcome: open an issue with
the raw AddressSanitizer output (`--verbose` helps).

## License

MIT

---

## En français

**Ton programme C a planté. segwhy te dit pourquoi, et où.**

```
$ segwhy --fr main.c

💥 Erreur de segmentation (segfault)
Raison : déréférencement d'un pointeur NULL
Ligne :  list.c:11 dans get_value()
         11 |  return n->value;
Depuis : main.c:18 dans main()
Piste :  'n' vaut NULL ici. Vérifie-le avant de l'utiliser (malloc() et beaucoup de fonctions
         peuvent renvoyer NULL).
```

Installation : `pip install git+https://github.com/goucefnaim/Segwhy` (bientôt `pip install segwhy`).
Il faut Python 3.8+ et `gcc` ou `clang` (Linux, macOS, WSL). Si pip refuse avec
« externally-managed-environment », utilise `pipx install git+https://github.com/goucefnaim/Segwhy`
ou ajoute `--user`.

- **Projet d'école :** `segwhy main.c utils.c`, avec les arguments du programme après `--`.
- **Gros projet :** `segwhy ./mon_programme args`. `segwhy --flags` donne les options à ajouter au Makefile ou au CMake.
- **Tests / CI :** `./tests 2>&1 | segwhy`.

Pour avoir les messages en français à chaque fois sans taper `--fr`, ajoute `export SEGWHY_LANG=fr`
à ton `~/.bashrc` ou `~/.zshrc`.

segwhy détecte les pointeurs NULL, les dépassements de tableau (avec l'indice fautif), l'utilisation
après `free()`, les doubles `free()`, les récursions infinies, l'écriture dans une chaîne littérale,
les divisions par zéro, les `assert()` ratés et, quand rien n'a planté, les fuites mémoire.
