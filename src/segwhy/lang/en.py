"""English texts. This is the reference language: every key must exist here.

To translate segwhy, copy this file to lang/<code>.py (for example es.py),
translate the strings, and register it in lang/__init__.py. Keys you don't
translate yet fall back to English automatically.

Words in {braces} are filled in by segwhy: keep them as they are.
"""

# Labels and one-line messages printed around a diagnosis.
LABELS = {
    # Left column of the diagnosis. They are aligned automatically.
    "reason": "Reason:",
    "line": "Line:",
    "from": "From:",
    "hint": "Hint:",
    "stack": "Stack:",
    "in": "in",  # "main.c:12 in main()"

    # Titles (the first line, after 💥). kinds.py says which kind uses which title.
    "crash_segv": "Segmentation fault",
    "crash_memory": "Memory error",
    "crash_fpe": "Floating point exception",
    "crash_abort": "Program aborted",
    "crash_bus": "Bus error",
    "crash_ill": "Illegal instruction",
    "crash_signal": "Crash",
    "crash_ub": "Undefined behavior",

    # When nothing crashed.
    "ok": "No crash, no memory error detected.",
    "ok_gdb": "No crash.",
    "ok_gdb_note": "(Built without AddressSanitizer: silent memory errors can't be detected. Run segwhy --flags.)",
    "leaks": "But {count} memory leak(s): {bytes} bytes never freed. First one allocated at {where}.",
    "leaks_only": "{count} memory leak(s): {bytes} bytes never freed. First one allocated at {where}.",
    "exit_code": "Program exited with code {code}.",
    "killed": "Program was killed by {signal}.",

    # Problems before or around running the program.
    "compile_failed": "Compilation failed (see the compiler errors above).",
    "no_asan": "AddressSanitizer is not available with {cc}: using gdb instead (fewer details).",
    "no_report": "No AddressSanitizer report found in the input.",
    "no_debugger": "The program crashed ({signal}), but segwhy can't tell where: it was built without "
                   "AddressSanitizer and gdb is not installed.",
    "no_debugger_hint": "Rebuild with the flags from `segwhy --flags`, then run segwhy again.",
    "not_found": "File not found: {path}",
    "not_executable": "Not an executable or a .c file: {path}",
    "no_compiler": "No C compiler found (tried $CC, gcc, clang, cc).",

    # Call stack details.
    "more_frames": "... {count} more (use --verbose)",
    "repeated": "(called {count} times in a row)",
    "repeated_many": "(called over and over)",
}

# The "Reason:" line, one per kind of problem (see kinds.py).
REASONS = {
    "null_deref": "NULL pointer dereference",
    "null_in_library": "NULL pointer passed to {func}()",
    "wild_pointer": "invalid pointer (uninitialized, already freed, or corrupted)",
    "readonly_write": "write to read-only memory",
    "stack_exhaustion": "stack overflow: {func}() calls itself endlessly",
    "stack_exhaustion_plain": "stack overflow: too much memory used on the stack",
    "heap_overflow": "out-of-bounds {access} on a block allocated with malloc",
    "stack_array_overflow": "out-of-bounds {access} on local array '{var}'",
    "global_overflow": "out-of-bounds {access} on global variable '{var}'",
    "use_after_free": "use of memory after free()",
    "double_free": "double free (free() called twice on the same pointer)",
    "bad_free": "free() on memory that was not allocated with malloc",
    "use_after_return": "use of local variable '{var}' after its function returned",
    "use_after_scope": "use of local variable '{var}' outside of its block",
    "overlap": "memcpy() with overlapping source and destination",
    "negative_size": "negative size passed to a memory function",
    "div_zero": "division by zero",
    "fpe": "arithmetic error",
    "abort": "abort() was called (failed assert or corruption detected by malloc)",
    "bus_error": "misaligned or invalid memory access",
    "illegal_instruction": "the CPU hit an invalid instruction (often a corrupted function pointer)",
    "signal": "killed by {signal}",
    "unknown": "{raw}",
    # Words used in {access} above.
    "read": "read",
    "write": "write",
    "access": "access",
}

# The "Hint:" line: what to check to fix the problem.
HINTS = {
    "null_named": "'{var}' is NULL here. Check it before using it (malloc() and many functions can return NULL).",
    "null_several": "One of these pointers is NULL: {vars}. Check them before using them.",
    "null_generic": "A pointer used on this line is NULL. Check it before using it.",
    "null_in_func": "A pointer used in {func}() is NULL.",
    "null_library_named": "'{var}' is probably NULL. Check it before passing it to {func}().",
    "null_library": "{func}() received a NULL pointer. Check the values you pass to it on this line.",
    "wild_pointer": "Make sure the pointer was initialized, still points to valid memory, "
                    "and wasn't freed before.",
    "readonly_write": "This is usually a string literal (char *s = \"...\"), which can't be modified. "
                      "Use an array instead: char s[] = \"...\";",
    "recursion": "Check the base case of {func}(): the condition that stops the recursion.",
    "stack_big": "A local array may be too big for the stack. Allocate it with malloc() instead.",
    "index": "You accessed index {index}, but valid indices go from 0 to {last}.",
    "index_negative": "You accessed an index before 0.",
    "bytes_after": "You went {distance} byte(s) past the end of a {size}-byte block.",
    "bytes_before": "You accessed {distance} byte(s) before the start of a {size}-byte block.",
    "bounds_check": "Check your loop bounds (< vs <=) and the size you allocated.",
    "allocated_at": "Allocated at {where}.",
    "use_after_free": "This memory was freed at {where}. Set the pointer to NULL right after free().",
    "use_after_free_plain": "Don't use a pointer after free(). Set it to NULL right after free().",
    "double_free": "It was already freed at {where}. Free each block only once, then set the pointer to NULL.",
    "double_free_plain": "Free each block only once, then set the pointer to NULL.",
    "bad_free": "Only free() what malloc(), calloc(), realloc() or strdup() returned, "
                "and never a pointer you moved with ++.",
    "use_after_return": "Don't return the address of a local variable: return the value, "
                        "or allocate it with malloc().",
    "use_after_scope": "The variable no longer exists outside its { } block. Declare it in a wider scope.",
    "overlap": "Use memmove() when the source and destination can overlap.",
    "negative_size": "Check the size computation: it is negative (or huge after conversion).",
    "div_zero": "Check that the divisor is not 0 before dividing (or using %). Some processors "
                "(Apple Silicon, ARM) don't crash here and silently return 0.",
    "ubsan": "This is undefined behavior: the program may seem to work today and break elsewhere.",
    "abort": "If an assert() failed, its message is just above. Otherwise malloc detected a corruption: "
             "look for an overflow or a double free earlier.",
    "bus_error": "Check pointer casts and that the memory you access still exists (mmap'd file, alignment).",
    "illegal_instruction": "Check function pointers and that no buffer overflow overwrote the stack.",
    "no_debug_info": "No file/line information: rebuild with -g (see segwhy --flags).",
    "generic": "Rebuild with AddressSanitizer for more details (see segwhy --flags).",
}

# Printed by `segwhy --flags`.
FLAGS = """To get file, line and reason for every memory error, build with:

  Compile flags:  -g -O0 -fsanitize=address -fno-omit-frame-pointer -fno-common
  Link flags:     -fsanitize=address

Makefile:
  CFLAGS  += -g -O0 -fsanitize=address -fno-omit-frame-pointer -fno-common
  LDFLAGS += -fsanitize=address

CMake:
  cmake -DCMAKE_BUILD_TYPE=Debug \\
        -DCMAKE_C_FLAGS="-fsanitize=address -fno-omit-frame-pointer" \\
        -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address" ..

Then run:  segwhy ./your_program [args...]
(Remove these flags for release builds: they slow the program down about 2x.)
"""

# Printed by `segwhy --help`.
HELP = """segwhy - tells you why your C program crashed, in plain words.

Usage:
  segwhy main.c [other.c ...] [-- program args]   compile, run, explain
  segwhy ./program [program args]                 run an existing program, explain
  ./program 2>&1 | segwhy                         explain an AddressSanitizer report

Options:
  --fr        messages in French (or set SEGWHY_LANG=fr)
  --verbose   show the full call stack
  --flags     print the compiler flags to add to a Makefile or CMake project
  --version   print the version
  --help      print this help

Compiler options (-lm, -I, -Wall...) can be added next to the .c files.
"""
