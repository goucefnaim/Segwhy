"""Every sentence segwhy prints, in English and French."""

from __future__ import annotations

EN = "en"
FR = "fr"

LABELS = {
    EN: {
        "reason": "Reason:",
        "line": "Line:",
        "from": "From:",
        "hint": "Hint:",
        "stack": "Stack:",
        "in": "in",
        "crash_segv": "Segmentation fault",
        "crash_memory": "Memory error",
        "crash_fpe": "Floating point exception",
        "crash_abort": "Program aborted",
        "crash_bus": "Bus error",
        "crash_ill": "Illegal instruction",
        "crash_signal": "Crash",
        "ok": "No crash, no memory error detected.",
        "ok_gdb": "No crash.",
        "ok_gdb_note": "(Built without AddressSanitizer: silent memory errors can't be detected. Run segwhy --flags.)",
        "leaks": "But {count} memory leak(s): {bytes} bytes never freed. First one allocated at {where}.",
        "leaks_only": "{count} memory leak(s): {bytes} bytes never freed. First one allocated at {where}.",
        "compile_failed": "Compilation failed (see the compiler errors above).",
        "no_asan": "AddressSanitizer is not available with {cc}: using gdb instead (fewer details).",
        "no_report": "No AddressSanitizer report found in the input.",
        "no_debugger": "The program crashed ({signal}), but segwhy can't tell where: it was built without "
                       "AddressSanitizer and gdb is not installed.",
        "no_debugger_hint": "Rebuild with the flags from `segwhy --flags`, then run segwhy again.",
        "not_found": "File not found: {path}",
        "not_executable": "Not an executable or a .c file: {path}",
        "no_compiler": "No C compiler found (tried $CC, gcc, clang, cc).",
        "exit_code": "Program exited with code {code}.",
        "killed": "Program was killed by {signal}.",
        "more_frames": "... {count} more (use --verbose)",
        "repeated": "(called {count} times in a row)",
        "repeated_many": "(called over and over)",
    },
    FR: {
        "reason": "Raison :",
        "line": "Ligne :",
        "from": "Depuis :",
        "hint": "Piste :",
        "stack": "Pile :",
        "in": "dans",
        "crash_segv": "Erreur de segmentation (segfault)",
        "crash_memory": "Erreur mémoire",
        "crash_fpe": "Erreur de calcul (FPE)",
        "crash_abort": "Programme interrompu (abort)",
        "crash_bus": "Erreur de bus",
        "crash_ill": "Instruction illégale",
        "crash_signal": "Plantage",
        "ok": "Aucun plantage, aucune erreur mémoire détectée.",
        "ok_gdb": "Aucun plantage.",
        "ok_gdb_note": "(Compilé sans AddressSanitizer : les erreurs mémoire silencieuses ne sont pas détectées. "
                       "Lance segwhy --flags.)",
        "leaks": "Mais {count} fuite(s) mémoire : {bytes} octets jamais libérés. La première est allouée à {where}.",
        "leaks_only": "{count} fuite(s) mémoire : {bytes} octets jamais libérés. La première est allouée à {where}.",
        "compile_failed": "La compilation a échoué (voir les erreurs du compilateur ci-dessus).",
        "no_asan": "AddressSanitizer n'est pas disponible avec {cc} : segwhy utilise gdb à la place "
                   "(moins de détails).",
        "no_report": "Aucun rapport AddressSanitizer trouvé dans l'entrée.",
        "no_debugger": "Le programme a planté ({signal}), mais segwhy ne peut pas dire où : il a été compilé "
                       "sans AddressSanitizer et gdb n'est pas installé.",
        "no_debugger_hint": "Recompile avec les options de `segwhy --flags`, puis relance segwhy.",
        "not_found": "Fichier introuvable : {path}",
        "not_executable": "Ce n'est ni un exécutable ni un fichier .c : {path}",
        "no_compiler": "Aucun compilateur C trouvé (essayés : $CC, gcc, clang, cc).",
        "exit_code": "Le programme s'est terminé avec le code {code}.",
        "killed": "Le programme a été tué par {signal}.",
        "more_frames": "... {count} de plus (utilise --verbose)",
        "repeated": "(appelée {count} fois d'affilée)",
        "repeated_many": "(appelée encore et encore)",
    },
}

# Title shown for each kind of problem.
TITLES = {
    "null_deref": "crash_segv",
    "null_in_library": "crash_segv",
    "wild_pointer": "crash_segv",
    "readonly_write": "crash_segv",
    "stack_exhaustion": "crash_segv",
    "heap_overflow": "crash_memory",
    "stack_array_overflow": "crash_memory",
    "global_overflow": "crash_memory",
    "use_after_free": "crash_memory",
    "double_free": "crash_memory",
    "bad_free": "crash_memory",
    "use_after_return": "crash_memory",
    "use_after_scope": "crash_memory",
    "overlap": "crash_memory",
    "negative_size": "crash_memory",
    "div_zero": "crash_fpe",
    "fpe": "crash_fpe",
    "abort": "crash_abort",
    "bus_error": "crash_bus",
    "illegal_instruction": "crash_ill",
    "signal": "crash_signal",
    "unknown": "crash_memory",
}

REASONS = {
    EN: {
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
        "read": "read",
        "write": "write",
        "access": "access",
    },
    FR: {
        "null_deref": "déréférencement d'un pointeur NULL",
        "null_in_library": "pointeur NULL passé à {func}()",
        "wild_pointer": "pointeur invalide (non initialisé, déjà libéré ou corrompu)",
        "readonly_write": "écriture dans une zone mémoire en lecture seule",
        "stack_exhaustion": "dépassement de pile : {func}() s'appelle elle-même sans fin",
        "stack_exhaustion_plain": "dépassement de pile : trop de mémoire utilisée sur la pile",
        "heap_overflow": "{access} hors limites d'un bloc alloué avec malloc",
        "stack_array_overflow": "{access} hors limites du tableau local '{var}'",
        "global_overflow": "{access} hors limites de la variable globale '{var}'",
        "use_after_free": "utilisation de mémoire déjà libérée par free()",
        "double_free": "double libération (free() appelé deux fois sur le même pointeur)",
        "bad_free": "free() sur une mémoire qui n'a pas été allouée avec malloc",
        "use_after_return": "utilisation de la variable locale '{var}' après la fin de sa fonction",
        "use_after_scope": "utilisation de la variable locale '{var}' hors de son bloc",
        "overlap": "memcpy() avec une source et une destination qui se chevauchent",
        "negative_size": "taille négative passée à une fonction mémoire",
        "div_zero": "division par zéro",
        "fpe": "erreur de calcul",
        "abort": "abort() a été appelé (assert raté ou corruption détectée par malloc)",
        "bus_error": "accès mémoire mal aligné ou invalide",
        "illegal_instruction": "le processeur a rencontré une instruction invalide (souvent un pointeur de "
                               "fonction corrompu)",
        "signal": "tué par {signal}",
        "unknown": "{raw}",
        "read": "lecture",
        "write": "écriture",
        "access": "accès",
    },
}

HINTS = {
    EN: {
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
        "div_zero": "Check that the divisor is not 0 before dividing (or using %).",
        "abort": "If an assert() failed, its message is just above. Otherwise malloc detected a corruption: "
                 "look for an overflow or a double free earlier.",
        "bus_error": "Check pointer casts and that the memory you access still exists (mmap'd file, alignment).",
        "illegal_instruction": "Check function pointers and that no buffer overflow overwrote the stack.",
        "no_debug_info": "No file/line information: rebuild with -g (see segwhy --flags).",
        "generic": "Rebuild with AddressSanitizer for more details (see segwhy --flags).",
    },
    FR: {
        "null_named": "'{var}' vaut NULL ici. Vérifie-le avant de l'utiliser (malloc() et beaucoup de fonctions "
                      "peuvent renvoyer NULL).",
        "null_several": "Un de ces pointeurs vaut NULL : {vars}. Vérifie-les avant de les utiliser.",
        "null_generic": "Un pointeur utilisé sur cette ligne vaut NULL. Vérifie-le avant de l'utiliser.",
        "null_in_func": "Un pointeur utilisé dans {func}() vaut NULL.",
        "null_library_named": "'{var}' vaut probablement NULL. Vérifie-le avant de le passer à {func}().",
        "null_library": "{func}() a reçu un pointeur NULL. Vérifie ce que tu lui passes sur cette ligne.",
        "wild_pointer": "Vérifie que le pointeur a été initialisé, pointe encore vers une mémoire valide "
                        "et n'a pas été libéré avant.",
        "readonly_write": "C'est souvent une chaîne littérale (char *s = \"...\"), qu'on ne peut pas modifier. "
                          "Utilise un tableau : char s[] = \"...\";",
        "recursion": "Vérifie le cas de base de {func}() : la condition qui arrête la récursion.",
        "stack_big": "Un tableau local est peut-être trop gros pour la pile. Alloue-le avec malloc().",
        "index": "Tu as accédé à l'indice {index}, mais les indices valides vont de 0 à {last}.",
        "index_negative": "Tu as accédé à un indice avant 0.",
        "bytes_after": "Tu as dépassé de {distance} octet(s) la fin d'un bloc de {size} octets.",
        "bytes_before": "Tu as accédé à {distance} octet(s) avant le début d'un bloc de {size} octets.",
        "bounds_check": "Vérifie les bornes de tes boucles (< ou <=) et la taille allouée.",
        "allocated_at": "Alloué à {where}.",
        "use_after_free": "Cette mémoire a été libérée à {where}. Mets le pointeur à NULL juste après free().",
        "use_after_free_plain": "N'utilise pas un pointeur après free(). Mets-le à NULL juste après free().",
        "double_free": "Déjà libéré à {where}. Ne libère chaque bloc qu'une fois, puis mets le pointeur à NULL.",
        "double_free_plain": "Ne libère chaque bloc qu'une fois, puis mets le pointeur à NULL.",
        "bad_free": "Ne passe à free() que ce que malloc(), calloc(), realloc() ou strdup() ont renvoyé, "
                    "jamais un pointeur déplacé avec ++.",
        "use_after_return": "Ne renvoie pas l'adresse d'une variable locale : renvoie sa valeur, "
                            "ou alloue-la avec malloc().",
        "use_after_scope": "La variable n'existe plus en dehors de son bloc { }. Déclare-la plus haut.",
        "overlap": "Utilise memmove() quand la source et la destination peuvent se chevaucher.",
        "negative_size": "Vérifie le calcul de la taille : il est négatif (ou énorme après conversion).",
        "div_zero": "Vérifie que le diviseur n'est pas 0 avant de diviser (ou d'utiliser %).",
        "abort": "Si un assert() a échoué, son message est juste au-dessus. Sinon malloc a détecté une "
                 "corruption : cherche un débordement ou un double free plus tôt.",
        "bus_error": "Vérifie les conversions de pointeurs et que la mémoire accédée existe encore.",
        "illegal_instruction": "Vérifie les pointeurs de fonction et qu'aucun débordement n'a écrasé la pile.",
        "no_debug_info": "Pas d'information de fichier/ligne : recompile avec -g (voir segwhy --flags).",
        "generic": "Recompile avec AddressSanitizer pour plus de détails (voir segwhy --flags).",
    },
}

FLAGS_TEXT = {
    EN: """To get file, line and reason for every memory error, build with:

  Compile flags:  -g -O0 -fsanitize=address -fno-omit-frame-pointer
  Link flags:     -fsanitize=address

Makefile:
  CFLAGS  += -g -O0 -fsanitize=address -fno-omit-frame-pointer
  LDFLAGS += -fsanitize=address

CMake:
  cmake -DCMAKE_BUILD_TYPE=Debug \\
        -DCMAKE_C_FLAGS="-fsanitize=address -fno-omit-frame-pointer" \\
        -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address" ..

Then run:  segwhy ./your_program [args...]
(Remove these flags for release builds: they slow the program down about 2x.)
""",
    FR: """Pour avoir le fichier, la ligne et la raison de chaque erreur mémoire, compile avec :

  Options de compilation :  -g -O0 -fsanitize=address -fno-omit-frame-pointer
  Options d'édition de liens :  -fsanitize=address

Makefile :
  CFLAGS  += -g -O0 -fsanitize=address -fno-omit-frame-pointer
  LDFLAGS += -fsanitize=address

CMake :
  cmake -DCMAKE_BUILD_TYPE=Debug \\
        -DCMAKE_C_FLAGS="-fsanitize=address -fno-omit-frame-pointer" \\
        -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address" ..

Puis lance :  segwhy ./ton_programme [arguments...]
(Retire ces options pour la version finale : elles ralentissent le programme d'environ 2x.)
""",
}

HELP_TEXT = {
    EN: """segwhy - tells you why your C program crashed, in plain words.

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
""",
    FR: """segwhy - explique pourquoi ton programme C a planté, en clair.

Utilisation :
  segwhy main.c [autre.c ...] [-- arguments]   compile, lance, explique
  segwhy ./programme [arguments]               lance un programme déjà compilé, explique
  ./programme 2>&1 | segwhy                    explique un rapport AddressSanitizer

Options :
  --fr        messages en français (ou SEGWHY_LANG=fr)
  --verbose   affiche toute la pile d'appels
  --flags     affiche les options à ajouter à un Makefile ou un projet CMake
  --version   affiche la version
  --help      affiche cette aide

Les options du compilateur (-lm, -I, -Wall...) peuvent être ajoutées à côté des fichiers .c.
""",
}
