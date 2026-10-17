"""Turn an AddressSanitizer report into a Diagnosis."""

from __future__ import annotations

import re
from typing import List, Optional

from .model import Diagnosis, Frame

_ERROR = re.compile(r"==\d+==\s*ERROR: AddressSanitizer: (?P<kind>[\w-]+(?: on unknown address)?)(?P<rest>.*)")
_ADDRESS = re.compile(r"(?:on (?:unknown )?address|on) (0x[0-9a-fA-F]+)")
_PC = re.compile(r"\bpc (0x[0-9a-fA-F]+)")
_ACCESS = re.compile(r"^(READ|WRITE) of size (\d+) at")
_SIGNAL_ACCESS = re.compile(r"The signal is caused by a (READ|WRITE) memory access")
_FRAME = re.compile(r"^\s*#(\d+)\s+0x[0-9a-fA-F]+\s+(?:in\s+)?(?P<rest>.*)$")
_LOCATION = re.compile(r"^(?P<file>.+?):(?P<line>\d+)(?::(?P<col>\d+))?$")
_MODULE = re.compile(r"^(?P<func>.*?)\s*\((?P<module>[^()]+?)\+0x[0-9a-fA-F]+\)$")
_HEAP_REGION = re.compile(
    r"is located (\d+) bytes (after|before|to the right of|to the left of|inside of) (\d+)-byte region"
)
_GLOBAL = re.compile(
    r"is located (\d+) bytes (after|before|to the right of|to the left of|inside of) global variable "
    r"'([^']+)' defined in '([^']+)' \(0x[0-9a-fA-F]+\) of size (\d+)"
)
_STACK_FRAME = re.compile(r"in stack of thread \S+ at offset (\d+) in frame")
_STACK_OBJECT = re.compile(r"\[(\d+), (\d+)\) '([^']+)'(?: \(line (\d+)\))?(.*)")

# ASan bug type -> segwhy reason
_KINDS = {
    "heap-buffer-overflow": "heap_overflow",
    "stack-buffer-overflow": "stack_array_overflow",
    "stack-buffer-underflow": "stack_array_overflow",
    "dynamic-stack-buffer-overflow": "stack_array_overflow",
    "global-buffer-overflow": "global_overflow",
    "heap-use-after-free": "use_after_free",
    "double-free": "double_free",
    "attempting double-free": "double_free",
    "attempting free on address which was not malloc()-ed": "bad_free",
    "bad-free": "bad_free",
    "stack-overflow": "stack_exhaustion",
    "stack-use-after-return": "use_after_return",
    "stack-use-after-scope": "use_after_scope",
    "FPE": "div_zero",
    "ABRT": "abort",
    "ILL": "illegal_instruction",
    "memcpy-param-overlap": "overlap",
    "negative-size-param": "negative_size",
}

_RELATION = {
    "after": "after",
    "to the right of": "after",
    "before": "before",
    "to the left of": "before",
    "inside of": "inside",
}

# Addresses below this are treated as "NULL plus a small offset" (NULL->field).
NULL_PAGE_LIMIT = 0x10000


def find_reports(text: str) -> List[str]:
    """Split any text (a log file, a CI output) into individual ASan reports."""
    reports: List[str] = []
    current: Optional[List[str]] = None
    for line in text.splitlines():
        if "ERROR: AddressSanitizer:" in line:
            if current:
                reports.append("\n".join(current))
            current = [line]
        elif current is not None:
            current.append(line)
            if line.startswith("SUMMARY: AddressSanitizer") or line.rstrip().endswith("==ABORTING"):
                # Keep going until ABORTING when possible, but SUMMARY is enough.
                if line.rstrip().endswith("==ABORTING"):
                    reports.append("\n".join(current))
                    current = None
    if current:
        reports.append("\n".join(current))
    return reports


def parse_frame(line: str) -> Optional[Frame]:
    match = _FRAME.match(line)
    if not match:
        return None
    rest = re.sub(r"\s*\(BuildId: [0-9a-fA-F]+\)\s*$", "", match.group("rest").strip())
    module_match = _MODULE.match(rest)
    if module_match and not _LOCATION.match(rest.rsplit(" ", 1)[-1]):
        return Frame(func=module_match.group("func") or None, module=module_match.group("module"))
    if " " in rest:
        func, location = rest.rsplit(" ", 1)
    else:
        func, location = rest, ""
    loc = _LOCATION.match(location)
    if loc:
        return Frame(
            func=func.strip() or None,
            file=loc.group("file"),
            line=int(loc.group("line")),
            column=int(loc.group("col")) if loc.group("col") else None,
        )
    return Frame(func=rest or None)


def _stack_after(lines: List[str], start: int) -> List[Frame]:
    """Read the frames that follow line `start`."""
    frames: List[Frame] = []
    for line in lines[start + 1:]:
        frame = parse_frame(line)
        if frame is None:
            if frames or line.strip():
                break
            continue
        frames.append(frame)
    return frames


def _first_user(frames: List[Frame]) -> Optional[Frame]:
    for frame in frames:
        if frame.is_user_code():
            return frame
    return None


def parse_report(report: str) -> Optional[Diagnosis]:
    lines = report.splitlines()
    head = None
    for index, line in enumerate(lines):
        match = _ERROR.search(line)
        if match:
            head = (index, match)
            break
    if head is None:
        return None
    head_index, match = head
    raw_kind = match.group("kind")
    rest = match.group("rest")
    if raw_kind.endswith(" on unknown address"):
        raw_kind = raw_kind[: -len(" on unknown address")]
        rest = " on unknown address" + rest
    if raw_kind == "attempting":
        raw_kind = "attempting " + rest.strip().split(" on ")[0]

    diag = Diagnosis(kind="unknown", source="asan", raw=report, raw_kind=raw_kind)

    address = _ADDRESS.search(line_after_kind(lines[head_index]))
    if address:
        diag.address = int(address.group(1), 16)
    pc_match = _PC.search(lines[head_index])
    pc = int(pc_match.group(1), 16) if pc_match else None

    diag.frames = _stack_after(lines, head_index)
    # Some reports put "READ of size N" between the header and the stack.
    for index, line in enumerate(lines[head_index + 1:], start=head_index + 1):
        access = _ACCESS.match(line)
        if access:
            diag.access = access.group(1)
            diag.access_size = int(access.group(2))
            if not diag.frames:
                diag.frames = _stack_after(lines, index)
            break
        signal_access = _SIGNAL_ACCESS.search(line)
        if signal_access:
            diag.access = signal_access.group(1)
        if line.lstrip().startswith("#"):
            break
    if not diag.frames:
        for index, line in enumerate(lines):
            if _FRAME.match(line):
                diag.frames = _stack_after(lines, index - 1)
                break

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("freed by thread"):
            diag.freed_at = _first_user(_stack_after(lines, index))
        elif stripped.startswith("previously allocated by thread") or stripped.startswith("allocated by thread"):
            diag.allocated_at = _first_user(_stack_after(lines, index))
        region = _HEAP_REGION.search(line)
        if region:
            diag.region_distance = int(region.group(1))
            diag.region_relation = _RELATION[region.group(2)]
            diag.region_size = int(region.group(3))
        glob = _GLOBAL.search(line)
        if glob:
            diag.region_distance = int(glob.group(1))
            diag.region_relation = _RELATION[glob.group(2)]
            diag.var_name = glob.group(3)
            diag.region_size = int(glob.group(5))
        stack = _STACK_FRAME.search(line)
        if stack:
            _parse_stack_object(diag, lines, index, int(stack.group(1)))

    diag.kind = _classify(diag, raw_kind, report, pc)
    return diag


_UBSAN = re.compile(r"^(?P<file>\S+?):(?P<line>\d+):(?P<col>\d+): runtime error: (?P<msg>.+)$")
_UBSAN_KINDS = (
    ("division by zero", "div_zero"),
    ("null pointer", "null_deref"),
)


def parse_ubsan(text: str) -> List[Diagnosis]:
    """UndefinedBehaviorSanitizer reports ("file.c:5:18: runtime error: ...")."""
    lines = text.splitlines()
    found: List[Diagnosis] = []
    for index, line in enumerate(lines):
        match = _UBSAN.match(line.strip())
        if not match:
            continue
        message = match.group("msg").strip()
        kind = next((k for needle, k in _UBSAN_KINDS if needle in message), "ubsan")
        frames = _stack_after(lines, index)
        if not any(f.is_user_code() for f in frames):
            frames.insert(0, Frame(file=match.group("file"), line=int(match.group("line")),
                                   column=int(match.group("col"))))
        found.append(Diagnosis(kind=kind, source="ubsan", frames=frames, raw_kind=message,
                               raw="\n".join(lines[index:index + 1 + len(frames)])))
    return found


_LEAK_SUMMARY = re.compile(r"SUMMARY: \w+Sanitizer: (\d+) byte\(s\) leaked in (\d+) allocation\(s\)")


def parse_leaks(text: str):
    """Return (allocations, bytes, first user frame) for a LeakSanitizer report, or None."""
    if "LeakSanitizer: detected memory leaks" not in text:
        return None
    summary = _LEAK_SUMMARY.search(text)
    if not summary:
        return None
    lines = text.splitlines()
    first = None
    for index, line in enumerate(lines):
        if re.match(r"^(Direct|Indirect) leak of", line.strip()):
            first = _first_user(_stack_after(lines, index))
            if first:
                break
    return int(summary.group(2)), int(summary.group(1)), first


def line_after_kind(line: str) -> str:
    return line.split("AddressSanitizer:", 1)[-1]


def _parse_stack_object(diag: Diagnosis, lines: List[str], start: int, offset: int) -> None:
    objects = []
    for line in lines[start + 1:]:
        found = _STACK_OBJECT.search(line)
        if found:
            objects.append(found)
        elif objects and line.strip() and not line.strip().startswith("#"):
            break
    if not objects:
        return
    chosen = None
    for obj in objects:
        if "<==" in (obj.group(5) or ""):
            chosen = obj
            break
    if chosen is None:
        chosen = min(objects, key=lambda o: min(abs(offset - int(o.group(1))), abs(offset - int(o.group(2)))))
    begin, end = int(chosen.group(1)), int(chosen.group(2))
    diag.var_name = chosen.group(3)
    diag.var_line = int(chosen.group(4)) if chosen.group(4) else None
    diag.region_size = end - begin
    if offset >= end:
        diag.region_relation, diag.region_distance = "after", offset - end
    elif offset < begin:
        diag.region_relation, diag.region_distance = "before", begin - offset
    else:
        diag.region_relation, diag.region_distance = "inside", offset - begin


def _classify(diag: Diagnosis, raw_kind: str, report: str, pc: Optional[int]) -> str:
    if raw_kind in _KINDS:
        return _KINDS[raw_kind]
    if raw_kind.startswith("attempting double-free"):
        return "double_free"
    if raw_kind.startswith("attempting free"):
        return "bad_free"
    if raw_kind in ("SEGV", "BUS"):
        # macOS reports most invalid accesses (string literal writes included) as BUS.
        addr = diag.address
        if "address points to the zero page" in report or (addr is not None and addr < NULL_PAGE_LIMIT):
            return "null_in_library" if diag.library_function() else "null_deref"
        if diag.recursive_function():
            return "stack_exhaustion"
        near_code = addr is not None and pc is not None and abs(addr - pc) < 0x4000000
        # A write close to the code is a write into the program's read-only
        # data: almost always a string literal. macOS reports these as BUS and
        # doesn't always say whether the access was a READ or a WRITE.
        if near_code and (diag.access == "WRITE" or (raw_kind == "BUS" and diag.access != "READ")):
            return "readonly_write"
        return "wild_pointer" if raw_kind == "SEGV" else "bus_error"
    return "unknown"
