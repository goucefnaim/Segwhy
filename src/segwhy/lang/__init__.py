"""Languages segwhy can speak.

Each language is one file in this folder (en.py, fr.py...) with the same five
names: LABELS, REASONS, HINTS, FLAGS, HELP. English is the reference: a key
missing from another language is shown in English instead of crashing.

Adding a language:
  1. copy en.py to xx.py and translate it,
  2. add it to LANGUAGES below.
It is then available as `segwhy --xx ...` and `SEGWHY_LANG=xx`.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

from . import en, fr

DEFAULT = "en"
LANGUAGES = {
    "en": en,
    "fr": fr,
}


def get(code: str) -> SimpleNamespace:
    """Texts for language `code`, completed with English for missing keys."""
    module = LANGUAGES.get(code, en)
    return SimpleNamespace(
        LABELS={**en.LABELS, **getattr(module, "LABELS", {})},
        REASONS={**en.REASONS, **getattr(module, "REASONS", {})},
        HINTS={**en.HINTS, **getattr(module, "HINTS", {})},
        FLAGS=getattr(module, "FLAGS", en.FLAGS),
        HELP=getattr(module, "HELP", en.HELP),
    )


def from_environment() -> str:
    """Language asked for with SEGWHY_LANG (fr, fr_FR, FR...), English otherwise."""
    wanted = os.environ.get("SEGWHY_LANG", "").lower()
    for code in LANGUAGES:
        if wanted.startswith(code):
            return code
    return DEFAULT
