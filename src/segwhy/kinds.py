"""Every kind of problem segwhy knows, and the title it is shown with.

A "kind" is a short name like "null_deref". It is decided by the parsers
(sanitizers.py, debugger.py), then used to pick the texts in lang/*.py:
REASONS[kind] for the "Reason:" line, HINTS[kind] for the "Hint:" line
(render.py builds some hints itself, with details from the report).

Adding a kind: add it here, give it a reason and a hint in lang/en.py (and the
other languages if you can), then make a parser return it.
"""

# kind -> title key in LABELS (the first line, after 💥)
TITLES = {
    # Segmentation faults
    "null_deref": "crash_segv",            # *p, p->x or p[i] with p == NULL
    "null_in_library": "crash_segv",       # NULL given to strlen(), atoi()...
    "wild_pointer": "crash_segv",          # pointer to nowhere (garbage, freed...)
    "readonly_write": "crash_segv",        # writing into a string literal
    "stack_exhaustion": "crash_segv",      # infinite recursion, huge local array

    # Memory errors found by AddressSanitizer (often before any crash)
    "heap_overflow": "crash_memory",       # tab[i] out of a malloc'd block
    "stack_array_overflow": "crash_memory",  # out of a local array
    "global_overflow": "crash_memory",     # out of a global array
    "use_after_free": "crash_memory",      # using memory after free()
    "double_free": "crash_memory",         # free() twice
    "bad_free": "crash_memory",            # free() of something not from malloc
    "use_after_return": "crash_memory",    # returned the address of a local variable
    "use_after_scope": "crash_memory",     # used a variable after its { } block
    "overlap": "crash_memory",             # memcpy() with overlapping buffers
    "negative_size": "crash_memory",       # negative size given to memcpy()...

    # Other signals
    "div_zero": "crash_fpe",               # x / 0 or x % 0
    "fpe": "crash_fpe",                    # other arithmetic errors
    "abort": "crash_abort",                # failed assert(), abort()
    "bus_error": "crash_bus",              # misaligned or invalid access
    "illegal_instruction": "crash_ill",    # jumped into garbage
    "signal": "crash_signal",              # any other signal
    "ubsan": "crash_ub",                   # other UndefinedBehaviorSanitizer errors
    "unknown": "crash_memory",             # an ASan error segwhy doesn't know yet
}


def title_key(kind: str) -> str:
    """Key of the title to show for `kind` (unknown kinds get a generic one)."""
    return TITLES.get(kind, "crash_memory")
