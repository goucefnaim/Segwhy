"""Turn a Diagnosis into the few lines segwhy prints."""

from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap
from typing import List, Optional

from . import messages as M
from .model import Diagnosis, Frame, display_path, read_source_line

_KEYWORDS = {
    "return", "if", "else", "while", "for", "do", "switch", "case", "sizeof", "int", "char", "void",
    "struct", "union", "enum", "const", "unsigned", "signed", "long", "short", "double", "float",
    "static", "extern", "volatile", "register", "goto", "break", "continue", "typedef", "NULL",
}


class Style:
    def __init__(self, stream=None):
        stream = stream or sys.stderr
        self.enabled = (
            hasattr(stream, "isatty") and stream.isatty()
            and "NO_COLOR" not in os.environ
            and os.environ.get("TERM") != "dumb"
        )

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def title(self, text: str) -> str:
        return self._wrap("1;31", text)

    def label(self, text: str) -> str:
        return self._wrap("1", text)

    def hint_label(self, text: str) -> str:
        return self._wrap("1;33", text)

    def location(self, text: str) -> str:
        return self._wrap("36", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def good(self, text: str) -> str:
        return self._wrap("1;32", text)


# ---- source code heuristics ------------------------------------------------

def _strip_literals(code: str) -> str:
    code = re.sub(r'"(?:\\.|[^"\\])*"', '""', code)
    code = re.sub(r"'(?:\\.|[^'\\])*'", "''", code)
    code = code.split("//", 1)[0]
    return code


def pointer_candidates(code: Optional[str]) -> List[str]:
    """Pointers that are dereferenced on a line of C code."""
    if not code:
        return []
    code = _strip_literals(code)
    found: List[str] = []

    # p->field, a->b->c (each prefix can be the NULL one)
    for match in re.finditer(r"([A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)\s*->", code):
        parts = re.split(r"\s*->\s*", match.group(1))
        for end in range(1, len(parts) + 1):
            found.append("->".join(parts[:end]))

    # *p (unary star only, not a multiplication)
    for match in re.finditer(r"\*", code):
        before = code[: match.start()].rstrip()
        if before and (before[-1].isalnum() or before[-1] in "_)]"):
            last_word = re.search(r"([A-Za-z_]\w*)$", before)
            if not (last_word and last_word.group(1) == "return"):
                continue
        after = re.match(r"\s*\(?\s*([A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)", code[match.end():])
        if after:
            found.append(re.sub(r"\s+", "", after.group(1)))

    # p[i]
    for match in re.finditer(r"([A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)\s*\[", code):
        found.append(re.sub(r"\s+", "", match.group(1)))

    result: List[str] = []
    for name in found:
        root = re.split(r"->|\.", name)[0]
        if root in _KEYWORDS or name in result:
            continue
        result.append(name)
    return result


def call_arguments(code: Optional[str], func: Optional[str]) -> List[str]:
    """Arguments written in a call to `func` on this line."""
    if not code or not func:
        return []
    code = _strip_literals(code)
    match = re.search(r"\b" + re.escape(func) + r"\s*\(", code)
    if not match:
        return []
    depth, start, args = 1, match.end(), []
    current = ""
    for char in code[start:]:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                break
        if char == "," and depth == 1:
            args.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        args.append(current.strip())
    return [a for a in args if re.fullmatch(r"[A-Za-z_][\w\[\]\->. ]*", a) and a not in ('""', "''")]


# ---- rendering ---------------------------------------------------------------

def _where(frame: Optional[Frame]) -> str:
    if frame is None:
        return "?"
    text = f"{display_path(frame.file)}:{frame.line}"
    if frame.func:
        text += f" ({frame.func})"
    return text


def reason_text(diag: Diagnosis, lang: str) -> str:
    reasons = M.REASONS[lang]
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


def hint_text(diag: Diagnosis, lang: str) -> str:
    hints = M.HINTS[lang]
    frame = diag.main_frame()
    code = read_source_line(frame.file, frame.line) if frame else None
    parts: List[str] = []
    kind = diag.kind

    if kind == "null_deref":
        names = pointer_candidates(code)
        if len(names) == 1:
            parts.append(hints["null_named"].format(var=names[0]))
        elif names:
            parts.append(hints["null_several"].format(vars=", ".join(names[:4])))
        elif code is None and frame is not None and frame.func:
            parts.append(hints["null_in_func"].format(func=frame.func))
        else:
            parts.append(hints["null_generic"])
    elif kind == "null_in_library":
        func = diag.library_function() or "?"
        args = call_arguments(code, func)
        if len(args) == 1:
            parts.append(hints["null_library_named"].format(var=args[0], func=func))
        elif args:
            parts.append(hints["null_several"].format(vars=", ".join(args[:4])))
        else:
            parts.append(hints["null_library"].format(func=func))
    elif kind == "stack_exhaustion":
        func = diag.self_calling_function()
        parts.append(hints["recursion"].format(func=func) if func else hints["stack_big"])
    elif kind in ("heap_overflow", "stack_array_overflow", "global_overflow"):
        parts.extend(_bounds_hint(diag, hints))
        if kind == "heap_overflow" and diag.allocated_at:
            parts.append(hints["allocated_at"].format(where=_where(diag.allocated_at)))
    elif kind in ("use_after_free", "double_free"):
        if diag.freed_at:
            parts.append(hints[kind].format(where=_where(diag.freed_at)))
        else:
            parts.append(hints[kind + "_plain"])
    elif kind in hints:
        parts.append(hints[kind])
    else:
        parts.append(hints["generic"])

    if not diag.has_debug_info():
        parts.append(hints["no_debug_info"])
    return " ".join(parts)


def _bounds_hint(diag: Diagnosis, hints: dict) -> List[str]:
    parts: List[str] = []
    size, dist, rel, step = diag.region_size, diag.region_distance, diag.region_relation, diag.access_size
    if rel == "before":
        parts.append(hints["index_negative"])
    elif rel == "after" and size and step and dist is not None and size % step == 0 and (size + dist) % step == 0:
        parts.append(hints["index"].format(index=(size + dist) // step, last=size // step - 1))
    elif rel == "after" and size is not None and dist is not None:
        parts.append(hints["bytes_after"].format(distance=dist + (step or 1), size=size))
    parts.append(hints["bounds_check"])
    return parts


def _frame_line(frame: Frame, lang: str, style: Style) -> str:
    word = M.LABELS[lang]["in"]
    func = f" {word} {frame.func}()" if frame.func else ""
    if frame.has_location:
        return style.location(f"{display_path(frame.file)}:{frame.line}") + func
    module = f" ({os.path.basename(frame.module)})" if frame.module else ""
    return (frame.func + "()" if frame.func else "??") + module


def render(diag: Diagnosis, lang: str = M.EN, verbose: bool = False, style: Optional[Style] = None) -> str:
    style = style or Style()
    labels = M.LABELS[lang]
    width = max(len(labels[k]) for k in ("reason", "line", "from", "hint", "stack")) + 1
    pad = " " * width
    term = shutil.get_terminal_size((100, 20)).columns
    out: List[str] = []

    title = labels[M.TITLES.get(diag.kind, "crash_memory")]
    out.append(style.title(f"💥 {title}"))
    out.append(style.label(labels["reason"].ljust(width)) + reason_text(diag, lang))

    main = diag.main_frame()
    if main is not None:
        out.append(style.label(labels["line"].ljust(width)) + _frame_line(main, lang, style))
        code = read_source_line(main.file, main.line)
        if code is not None:
            snippet = code.strip()
            if len(snippet) > term - width - 10:
                snippet = snippet[: max(20, term - width - 13)] + "..."
            out.append(pad + style.dim(f"{main.line} |") + "  " + snippet)

    if verbose:
        out.append(style.label(labels["stack"].ljust(width)) + _stack_lines(diag.frames, lang, style, pad))
    else:
        callers = _callers(diag, main)
        if callers:
            first = True
            for frame, repeat in callers[:2]:
                text = _frame_line(frame, lang, style)
                if repeat >= 50:
                    text += " " + style.dim(labels["repeated_many"])
                elif repeat > 1:
                    text += " " + style.dim(labels["repeated"].format(count=repeat))
                prefix = labels["from"].ljust(width) if first else pad
                out.append((style.label(prefix) if first else prefix) + text)
                first = False
            hidden = len(callers) - 2
            if hidden > 0:
                out.append(pad + style.dim(labels["more_frames"].format(count=hidden)))

    hint = hint_text(diag, lang)
    wrapped = textwrap.wrap(hint, width=max(40, min(term, 100) - width)) or [hint]
    out.append(style.hint_label(labels["hint"].ljust(width)) + wrapped[0])
    out.extend(pad + line for line in wrapped[1:])
    return "\n".join(out)


def _callers(diag: Diagnosis, main: Optional[Frame]):
    """User frames after the main one, with consecutive repeats collapsed."""
    frames = diag.user_frames()
    if main in frames:
        frames = frames[frames.index(main) + 1:]
    grouped = []
    for frame in frames:
        if grouped and grouped[-1][0].func == frame.func and grouped[-1][0].file == frame.file \
                and grouped[-1][0].line == frame.line:
            grouped[-1][1] += 1
        else:
            grouped.append([frame, 1])
    return [(f, n) for f, n in grouped]


def _stack_lines(frames: List[Frame], lang: str, style: Style, pad: str) -> str:
    lines = []
    shown = frames[:60]
    for index, frame in enumerate(shown):
        text = f"#{index} " + _frame_line(frame, lang, style)
        if not frame.is_user_code():
            text = style.dim(text)
        lines.append(text if index == 0 else pad + text)
    if len(frames) > len(shown):
        lines.append(pad + f"... (+{len(frames) - len(shown)})")
    return "\n".join(lines)
