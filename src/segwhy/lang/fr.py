"""Textes en français. Mêmes clés que en.py (la référence).

Les mots entre {accolades} sont remplis par segwhy : ne les traduis pas.
"""

LABELS = {
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
    "crash_ub": "Comportement indéfini",

    "ok": "Aucun plantage, aucune erreur mémoire détectée.",
    "ok_gdb": "Aucun plantage.",
    "ok_gdb_note": "(Compilé sans AddressSanitizer : les erreurs mémoire silencieuses ne sont pas détectées. "
                   "Lance segwhy --flags.)",
    "leaks": "Mais {count} fuite(s) mémoire : {bytes} octets jamais libérés. La première est allouée à {where}.",
    "leaks_only": "{count} fuite(s) mémoire : {bytes} octets jamais libérés. La première est allouée à {where}.",
    "exit_code": "Le programme s'est terminé avec le code {code}.",
    "killed": "Le programme a été tué par {signal}.",

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

    "more_frames": "... {count} de plus (utilise --verbose)",
    "repeated": "(appelée {count} fois d'affilée)",
    "repeated_many": "(appelée encore et encore)",
}

REASONS = {
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
}

HINTS = {
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
    "div_zero": "Vérifie que le diviseur n'est pas 0 avant de diviser (ou d'utiliser %). Certains "
                "processeurs (Apple Silicon, ARM) ne plantent pas ici et renvoient 0 en silence.",
    "ubsan": "C'est un comportement indéfini : le programme peut sembler marcher aujourd'hui et "
             "casser ailleurs.",
    "abort": "Si un assert() a échoué, son message est juste au-dessus. Sinon malloc a détecté une "
             "corruption : cherche un débordement ou un double free plus tôt.",
    "bus_error": "Vérifie les conversions de pointeurs et que la mémoire accédée existe encore.",
    "illegal_instruction": "Vérifie les pointeurs de fonction et qu'aucun débordement n'a écrasé la pile.",
    "no_debug_info": "Pas d'information de fichier/ligne : recompile avec -g (voir segwhy --flags).",
    "generic": "Recompile avec AddressSanitizer pour plus de détails (voir segwhy --flags).",
}

FLAGS = """Pour avoir le fichier, la ligne et la raison de chaque erreur mémoire, compile avec :

  Options de compilation :  -g -O0 -fsanitize=address -fno-omit-frame-pointer -fno-common
  Options d'édition de liens :  -fsanitize=address

Makefile :
  CFLAGS  += -g -O0 -fsanitize=address -fno-omit-frame-pointer -fno-common
  LDFLAGS += -fsanitize=address

CMake :
  cmake -DCMAKE_BUILD_TYPE=Debug \\
        -DCMAKE_C_FLAGS="-fsanitize=address -fno-omit-frame-pointer" \\
        -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address" ..

Puis lance :  segwhy ./ton_programme [arguments...]
(Retire ces options pour la version finale : elles ralentissent le programme d'environ 2x.)
"""

HELP = """segwhy - explique pourquoi ton programme C a planté, en clair.

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
"""
