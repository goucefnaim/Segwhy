# Contributing to segwhy

segwhy is small on purpose: plain Python, no dependencies, one file per job.
This page explains how the pieces fit, then how to make the most common changes.

🇫🇷 [Résumé en français plus bas](#en-français)

## Getting started

```sh
git clone https://github.com/goucefnaim/Segwhy && cd Segwhy
git checkout -b my-change           # work on your own branch
pip install -e . pytest             # -e: your edits are used right away
pytest -q                           # every test should pass before you start
```

Want your own version instead? Fork the repository on GitHub, change what you
like, and keep the MIT license notice. Pull requests back are always welcome.

## How it works

When you run `segwhy main.c`, the crash goes through these steps:

```
cli.py        reads the arguments, picks a mode
  │
modes.py      compile_mode / run_mode / pipe_mode
  │
runner.py     compiles with -fsanitize=address, runs the program,
  │           collects the sanitizer reports
  │           (or debugger.py + gdb_helper.py: runs it under gdb)
  │
sanitizers.py reads the report text  ──►  Diagnosis  (model.py)
  │           (or debugger.py reads gdb's findings)       │
  │                                                       │
render.py     builds the output from the Diagnosis  ◄─────┘
              texts from lang/, title from kinds.py,
              variable names from source.py (reads the user's C code)
```

| File | Its job |
|---|---|
| `cli.py` | Command line arguments, then calls a mode |
| `modes.py` | The 3 modes; prints the result or "No crash" |
| `runner.py` | Finds the compiler, compiles, runs with sanitizers |
| `debugger.py` | Runs programs built without sanitizers under gdb (Linux) |
| `gdb_helper.py` | The script gdb runs; never imported by segwhy |
| `sanitizers.py` | Reads AddressSanitizer, UBSan and LeakSanitizer reports |
| `model.py` | `Frame` (one line of a call stack) and `Diagnosis` (one crash) |
| `kinds.py` | The list of problems segwhy knows, and their titles |
| `source.py` | Reads the user's C code: which variable is NULL, where the recursion is |
| `render.py` | Turns a `Diagnosis` into the lines segwhy prints |
| `lang/en.py`, `lang/fr.py` | Every sentence segwhy prints |

Every file starts with a docstring explaining it, and every function has one.

### The key idea: the `kind`

Every crash gets a short name, its **kind**: `null_deref`, `heap_overflow`,
`double_free`... (all listed in `kinds.py`). The parsers decide the kind; the
texts are looked up by kind: `REASONS[kind]` for the "Reason:" line, `HINTS[kind]`
for the "Hint:" line. So most changes touch only one side.

## Common changes

### A crash segwhy explains badly, or not at all

1. Write the smallest C program that shows it, in `tests/crashes/`.
2. See what segwhy says: `segwhy tests/crashes/my_case.c` (`--verbose` adds the
   full stack). To see the raw report behind it, compile the program yourself
   with `-g -fsanitize=address` and run it.
3. Add the expected words to `EXPECTED` in `tests/test_compile_mode.py`.
4. Fix it: usually `_classify()` in `sanitizers.py` (wrong kind) or
   `hint_text()` in `render.py` (vague hint).

### A report from another system (macOS, another compiler...)

Reports differ between systems, and segwhy can only be tested on the systems
of its CI. Saving real reports keeps segwhy working everywhere:

1. Run the program with `ASAN_OPTIONS=color=never ./program 2> report.txt`.
2. Save it as `tests/reports/<system>_<case>.txt`.
3. Add the expected words to `EXPECTED` in `tests/test_pipe_mode.py`.

Even without a fix, an issue with such a report is a great contribution.

### A new kind of problem

1. Add it to `TITLES` in `kinds.py`.
2. Add its reason and hint to `lang/en.py` (and the other languages if you can).
3. Make a parser return it: `ASAN_KINDS` or `_classify()` in `sanitizers.py`,
   `_classify()` in `debugger.py`.
4. Add a test program, as above.

### A new language

1. Copy `lang/en.py` to `lang/<code>.py` (for example `es.py`) and translate the strings.
   Keep the words in `{braces}` as they are.
2. Add it to `LANGUAGES` in `lang/__init__.py`.

That's all: `segwhy --es main.c` and `SEGWHY_LANG=es` now work. Untranslated
keys fall back to English, and `pytest` lists the ones still missing.

## Guidelines

- Keep the output short. A beginner should understand it in five seconds;
  details belong behind `--verbose`.
- A hint must be right or stay general. When unsure, say less.
- No dependencies: segwhy must install anywhere with a plain `pip install`.
- Python 3.8 or newer (no `match`, no `str.removeprefix`).
- Every new function gets a docstring saying what it does.

---

## En français

Le code est découpé en un fichier par rôle (voir le tableau plus haut), et
chaque fonction a un commentaire qui explique ce qu'elle fait. Le principe à
retenir : chaque plantage reçoit un **type** (`null_deref`, `heap_overflow`...,
liste dans `kinds.py`). Les analyseurs (`sanitizers.py`, `debugger.py`) décident
du type, et les textes affichés sont choisis selon ce type dans `lang/`.

- **Un cas mal expliqué :** ajoute un petit programme C dans `tests/crashes/`,
  ce que segwhy doit dire dans `tests/test_compile_mode.py`, puis corrige
  `sanitizers.py` (mauvais type) ou `render.py` (piste trop vague).
- **Un rapport venant d'un autre système (Mac...) :** enregistre-le dans
  `tests/reports/` et ajoute ce que segwhy doit dire dans `tests/test_pipe_mode.py`.
- **Une nouvelle langue :** copie `lang/en.py` vers `lang/xx.py`, traduis,
  et ajoute-la dans `lang/__init__.py`.

Travaille sur ta propre branche (`git checkout -b ma-modif`), lance `pytest -q`
avant et après, puis ouvre une pull request. Pour faire ta propre version,
fais un fork et garde la mention de la licence MIT.
