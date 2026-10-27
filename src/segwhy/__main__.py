"""Lets segwhy run as `python -m segwhy` (same as the `segwhy` command)."""

import sys

from .cli import main

sys.exit(main())
