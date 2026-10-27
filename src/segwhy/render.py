"""Turn a Diagnosis into the few lines segwhy prints:

    💥 Segmentation fault                  <- title       (kinds.py + LABELS)
    Reason: NULL pointer dereference       <- reason_text (REASONS)
    Line:   list.c:11 in get_value()       <- main frame
            11 |  return n->value;        <- source line
    From:   main.c:18 in main()            <- callers
    Hint:   'n' is NULL here. ...          <- hint_text   (HINTS + source.py)
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
from typing import List, Optional, Tuple

from . import lang
from .kinds import title_key
from .model import Diagnosis, Frame
from .source import call_arguments, display_path, pointer_candidates, read_source_line

# Callers shown under "From:" (the rest is behind --verbose).
MAX_CALLERS = 2
# Frames shown by --verbose.
MAX_VERBOSE_FRAMES = 60
# A function repeated this many times is shown as "called over and over".
MANY_REPEATS = 50


class Style:
    """Terminal colors, turned off when the output isn't a terminal or NO_COLOR is set."""

    def __init__(self, stream=None):
        """`stream` is where the text will be written (stderr by default)."""
        stream = stream or sys.stderr
        self.enabled = (
            hasattr(stream, "isatty") and stream.isatty()
            and "NO_COLOR" not in os.environ
            and os.environ.get("TERM") != "dumb"
        )

    def _wrap(self, code: str, text: str) -> str:
        """`text` in ANSI color `code`, or unchanged when colors are off."""
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def title(self, text: str) -> str:
        """Bold red: the 💥 line."""
        return self._wrap("1;31", text)

    def label(self, text: str) -> str:
        """Bold: "Reason:", "Line:"..."""
        return self._wrap("1", text)

    def hint_label(self, text: str) -> str:
        """Bold yellow: "Hint:"."""
        return self._wrap("1;33", text)

    def location(self, text: str) -> str:
        """Cyan: file:line."""
        return self._wrap("36", text)

    def dim(self, text: str) -> str:
        """Grey: secondary details."""
        return self._wrap("2", text)

    def good(self, text: str) -> str:
        """Bold green: the ✅ line."""
        return self._wrap("1;32", text)


# ---- the full output -----------------------------------------------------------------

def render(diag: Diagnosis, lang_code: str = lang.DEFAULT, verbose: bool = False,
           style: Optional[Style] = None) -> str:
    """The text explaining `diag`, ready to print."""
    style = style or Style()
    texts = lang.get(lang_code)
    labels = texts.LABELS
    width = max(len(labels[k]) for k in ("reason", "line", "from", "hint", "stack")) + 1
    pad = " " * width
    term = shutil.get_terminal_size((100, 20)).columns
    out: List[str] = []

    out.append(style.title("💥 " + labels[title_key(diag.kind)]))
    out.append(style.label(labels["reason"].ljust(width)) + reason_text(diag, texts))

    main = diag.main_frame()
    if main is not None:
        out.append(style.label(labels["line"].ljust(width)) + frame_text(main, labels, style))
        code = read_source_line(main.file, main.line)
        if code is not None:
            snippet = code.strip()
            if len(snippet) > term - width - 10:
                snippet = snippet[: max(20, term - width - 13)] + "..."
            out.append(pad + style.dim(f"{main.line} |") + "  " + snippet)

    if verbose:
        out.append(style.label(labels["stack"].ljust(width)) + stack_text(diag.frames, labels, style, pad))
    else:
        out.extend(_callers_lines(diag, main, labels, style, width))

    hint = hint_text(diag, texts)
    wrapped = textwrap.wrap(hint, width=max(40, min(term, 100) - width)) or [hint]
    out.append(style.hint_label(labels["hint"].ljust(width)) + wrapped[0])
    out.extend(pad + line for line in wrapped[1:])
    return "\n".join(out)


def _callers_lines(diag: Diagnosis, main: Optional[Frame], labels: dict, style: Style, width: int) -> List[str]:
    """The "From:" lines: who called the function that crashed."""
    callers = callers_of(diag, main)
    if not callers:
        return []
    pad = " " * width
    lines = []
    for index, (frame, repeat) in enumerate(callers[:MAX_CALLERS]):
        text = frame_text(frame, labels, style)
        if repeat >= MANY_REPEATS:
            text += " " + style.dim(labels["repeated_many"])
        elif repeat > 1:
            text += " " + style.dim(labels["repeated"].format(count=repeat))
        prefix = style.label(labels["from"].ljust(width)) if index == 0 else pad
        lines.append(prefix + text)
    hidden = len(callers) - MAX_CALLERS
    if hidden > 0:
        lines.append(pad + style.dim(labels["more_frames"].format(count=hidden)))
    return lines


# ---- the "Reason:" line -------------------------------------------------------------------

def reason_text(diag: Diagnosis, texts) -> str:
    """One sentence saying what went wrong."""
    reasons = texts.REASONS
    access = {"READ": reasons["read"], "WRITE": reasons["write"]}.get(diag.access or "", reasons["access"])
    if diag.kind == "stack_exhaustion":
        func = diag.self_calling_function()
        if func:
            return reasons["stack_exhaustion"].format(func=func)
        return reasons["stack_exhaustion_plain"]
    template = reasons.get(diag.kind, reasons["unknown"])
    return template.format(
        func=diag.library_function() or "?",
        var=diag.var_name or "?",
        access=access,
        raw=diag.raw_kind or diag.kind,
        signal=diag.signal or "?",
    )


# ---- the "Hint:" line -------------------------------------------------------------------

def hint_text(diag: Diagnosis, texts) -> str:
    """What to check to fix it, as precise as the report and the source allow."""
    hints = texts.HINTS
    frame = diag.main_frame()
    code = read_source_line(frame.file, frame.line) if frame else None
    kind = diag.kind

    if kind == "null_deref":
        parts = [_null_hint(code, frame, hints)]
    elif kind == "null_in_library":
        parts = [_null_in_library_hint(diag, code, hints)]
    elif kind == "stack_exhaustion":
        func = diag.self_calling_function()
        parts = [hints["recursion"].format(func=func) if func else hints["stack_big"]]
    elif kind in ("heap_overflow", "stack_array_overflow", "global_overflow"):
        parts = _bounds_hint(diag, hints)
        if kind == "heap_overflow" and diag.allocated_at:
            parts.append(hints["allocated_at"].format(where=where_text(diag.allocated_at)))
    elif kind in ("use_after_free", "double_free"):
        if diag.freed_at:
            parts = [hints[kind].format(where=where_text(diag.freed_at))]
        else:
            parts = [hints[kind + "_plain"]]
    elif kind in hints:
        parts = [hints[kind]]
    else:
        parts = [hints["generic"]]

    if not diag.has_debug_info():
        parts.append(hints["no_debug_info"])
    return " ".join(parts)


def _null_hint(code: Optional[str], frame: Optional[Frame], hints: dict) -> str:
    """Name the NULL pointer when the source line makes it clear."""
    names = pointer_candidates(code)
    if len(names) == 1:
        return hints["null_named"].format(var=names[0])
    if names:
        return hints["null_several"].format(vars=", ".join(names[:4]))
    if code is None and frame is not None and frame.func:
        return hints["null_in_func"].format(func=frame.func)
    return hints["null_generic"]


def _null_in_library_hint(diag: Diagnosis, code: Optional[str], hints: dict) -> str:
    """Name the argument that is probably NULL in a call like strlen(line)."""
    func = diag.library_function() or "?"
    args = call_arguments(code, func)
    if len(args) == 1:
        return hints["null_library_named"].format(var=args[0], func=func)
    if args:
        return hints["null_several"].format(vars=", ".join(args[:4]))
    return hints["null_library"].format(func=func)


def _bounds_hint(diag: Diagnosis, hints: dict) -> List[str]:
    """For an out-of-bounds access: which index was used, which ones are valid."""
    parts: List[str] = []
    size, dist, rel, step = diag.region_size, diag.region_distance, diag.region_relation, diag.access_size
    if rel == "before":
        parts.append(hints["index_negative"])
    elif rel == "after" and size and step and dist is not None and size % step == 0 and (size + dist) % step == 0:
        # Sizes line up with the element size: we can speak in indices.
        parts.append(hints["index"].format(index=(size + dist) // step, last=size // step - 1))
    elif rel == "after" and size is not None and dist is not None:
        parts.append(hints["bytes_after"].format(distance=dist + (step or 1), size=size))
    parts.append(hints["bounds_check"])
    return parts


# ---- frames ------------------------------------------------------------------------------

def where_text(frame: Optional[Frame]) -> str:
    """"main.c:12 (main)", used inside hints."""
    if frame is None:
        return "?"
    text = f"{display_path(frame.file)}:{frame.line}"
    if frame.func:
        text += f" ({frame.func})"
    return text


def frame_text(frame: Frame, labels: dict, style: Style) -> str:
    """"main.c:12 in main()", or "strlen() (libc.so.6)" without source file."""
    func = f" {labels['in']} {frame.func}()" if frame.func else ""
    if frame.has_location:
        return style.location(f"{display_path(frame.file)}:{frame.line}") + func
    module = f" ({os.path.basename(frame.module)})" if frame.module else ""
    return (frame.func + "()" if frame.func else "??") + module


def callers_of(diag: Diagnosis, main: Optional[Frame]) -> List[Tuple[Frame, int]]:
    """The user's frames below the main one, as (frame, times repeated in a row)."""
    frames = diag.user_frames()
    if main in frames:
        frames = frames[frames.index(main) + 1:]
    elif main is not None and frames and frames[0].func == main.func and frames[0].file == main.file:
        frames = frames[1:]  # main was rebuilt from the source (same function, better line)
    grouped: List[list] = []
    for frame in frames:
        last = grouped[-1][0] if grouped else None
        if last is not None and (last.func, last.file, last.line) == (frame.func, frame.file, frame.line):
            grouped[-1][1] += 1
        else:
            grouped.append([frame, 1])
    return [(frame, count) for frame, count in grouped]


def stack_text(frames: List[Frame], labels: dict, style: Style, pad: str) -> str:
    """The whole stack for --verbose, library frames in grey."""
    lines = []
    shown = frames[:MAX_VERBOSE_FRAMES]
    for index, frame in enumerate(shown):
        text = f"#{index} " + frame_text(frame, labels, style)
        if not frame.is_user_code():
            text = style.dim(text)
        lines.append(text if index == 0 else pad + text)
    if len(frames) > len(shown):
        lines.append(pad + f"... (+{len(frames) - len(shown)})")
    return "\n".join(lines)
