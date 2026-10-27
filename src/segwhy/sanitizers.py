"""Read sanitizer reports and turn them into Diagnosis objects.

Three tools built into gcc and clang print reports segwhy understands:
- AddressSanitizer (ASan): memory errors      "==123==ERROR: AddressSanitizer: ..."
- UndefinedBehaviorSanitizer (UBSan): x / 0   "main.c:5:18: runtime error: ..."
- LeakSanitizer (LSan): memory never freed     "ERROR: LeakSanitizer: detected memory leaks"

The entry points are find_reports() + parse_report() for ASan, parse_ubsan()
and parse_leaks(). The real reports used in the tests (tests/reports/) are
the best way to see what the input looks like.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .model import Diagnosis, Frame

# Addresses below this are "NULL plus a small offset" (reading NULL->field).
NULL_PAGE_LIMIT = 0x10000

# A write this close to the program's code is a write into its read-only data.
NEAR_CODE_DISTANCE = 0x4000000

# ---- what the lines of a report look like --------------------------------------------

# "==123==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x..."
_ERROR = re.compile(r"==\d+==\s*ERROR: AddressSanitizer: (?P<kind>[\w-]+(?: on unknown address)?)(?P<rest>.*)")
_ADDRESS = re.compile(r"(?:on (?:unknown )?address|on) (0x[0-9a-fA-F]+)")
_PC = re.compile(r"\bpc (0x[0-9a-fA-F]+)")
# "WRITE of size 4 at 0x..."
_ACCESS = re.compile(r"^(READ|WRITE) of size (\d+) at")
# "==123==The signal is caused by a READ memory access."
_SIGNAL_ACCESS = re.compile(r"The signal is caused by a (READ|WRITE) memory access")
# "    #0 0x55b996773237 in main /src/main.c:8"   (one stack frame)
_FRAME = re.compile(r"^\s*#(\d+)\s+0x[0-9a-fA-F]+\s+(?:in\s+)?(?P<rest>.*)$")
# "/src/main.c:8" or "main.c:8:3"
_LOCATION = re.compile(r"^(?P<file>.+?):(?P<line>\d+)(?::(?P<col>\d+))?$")
# "strlen (libc.so.6+0x1234)"   (a frame without source file)
_MODULE = re.compile(r"^(?P<func>.*?)\s*\((?P<module>[^()]+?)\+0x[0-9a-fA-F]+\)$")
# "0x... is located 0 bytes after 20-byte region [0x...,0x...)"
_HEAP_REGION = re.compile(
    r"is located (\d+) bytes (after|before|to the right of|to the left of|inside of) (\d+)-byte region"
)
# "0x... is located 0 bytes after global variable 'grid' defined in 'a.c:3:5' (0x...) of size 16"
_GLOBAL = re.compile(
    r"is located (\d+) bytes (after|before|to the right of|to the left of|inside of) global variable "
    r"'([^']+)' defined in '([^']+)' \(0x[0-9a-fA-F]+\) of size (\d+)"
)
# "Address 0x... is located in stack of thread T0 at offset 52 in frame"
_STACK_FRAME = re.compile(r"in stack of thread \S+ at offset (\d+) in frame")
# "    [32, 52) 'scores' (line 5) <== Memory access at offset 52 overflows this variable"
_STACK_OBJECT = re.compile(r"\[(\d+), (\d+)\) '([^']+)'(?: \(line (\d+)\))?(.*)")
# "main.c:5:18: runtime error: division by zero"
_UBSAN = re.compile(r"^(?P<file>\S+?):(?P<line>\d+):(?P<col>\d+): runtime error: (?P<msg>.+)$")
# "SUMMARY: AddressSanitizer: 40 byte(s) leaked in 1 allocation(s)."
_LEAK_SUMMARY = re.compile(r"SUMMARY: \w+Sanitizer: (\d+) byte\(s\) leaked in (\d+) allocation\(s\)")

# ---- ASan / UBSan error names -> segwhy kinds (see kinds.py) --------------------------

ASAN_KINDS = {
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
    # "SEGV" and "BUS" need a closer look: see _classify().
}

# Words found in a UBSan message -> segwhy kind. Anything else is "ubsan".
UBSAN_KINDS = (
    ("division by zero", "div_zero"),
    ("null pointer", "null_deref"),
)

# How ASan says where the bad address is compared to the array.
_RELATION = {
    "after": "after",
    "to the right of": "after",
    "before": "before",
    "to the left of": "before",
    "inside of": "inside",
}


# ---- AddressSanitizer ------------------------------------------------------------------

def find_reports(text: str) -> List[str]:
    """Cut any text (a log file, the output of a test suite) into separate
    ASan reports, from their "ERROR:" line to their "ABORTING" line."""
    reports: List[str] = []
    current: Optional[List[str]] = None
    for line in text.splitlines():
        if "ERROR: AddressSanitizer:" in line:
            if current:
                reports.append("\n".join(current))
            current = [line]
        elif current is not None:
            current.append(line)
            if line.rstrip().endswith("==ABORTING"):
                reports.append("\n".join(current))
                current = None
    if current:
        reports.append("\n".join(current))
    return reports


def parse_frame(line: str) -> Optional[Frame]:
    """Read one stack line ("    #0 0x... in main /src/main.c:8"), or None
    if `line` is not a stack line."""
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


def parse_stack(lines: List[str], start: int) -> List[Frame]:
    """Read the stack that follows line number `start` (blank lines before it
    are skipped, the first non-stack line ends it)."""
    frames: List[Frame] = []
    for line in lines[start + 1:]:
        frame = parse_frame(line)
        if frame is None:
            if frames or line.strip():
                break
            continue
        frames.append(frame)
    return frames


def first_user_frame(frames: List[Frame]) -> Optional[Frame]:
    """The first frame in the user's own code, or None."""
    for frame in frames:
        if frame.is_user_code():
            return frame
    return None


def parse_report(report: str) -> Optional[Diagnosis]:
    """Turn one ASan report (from find_reports) into a Diagnosis."""
    lines = report.splitlines()
    head_index, match = _find_error_line(lines)
    if match is None:
        return None

    raw_kind = match.group("kind")
    rest = match.group("rest")
    if raw_kind.endswith(" on unknown address"):
        raw_kind = raw_kind[: -len(" on unknown address")]
        rest = " on unknown address" + rest
    if raw_kind == "attempting":  # "attempting double-free on 0x..."
        raw_kind = "attempting " + rest.strip().split(" on ")[0]

    diag = Diagnosis(kind="unknown", source="asan", raw=report, raw_kind=raw_kind)
    header = lines[head_index]
    address = _ADDRESS.search(header.split("AddressSanitizer:", 1)[-1])
    if address:
        diag.address = int(address.group(1), 16)
    pc_match = _PC.search(header)
    pc = int(pc_match.group(1), 16) if pc_match else None

    _read_access_and_stack(diag, lines, head_index)
    _read_details(diag, lines)
    diag.kind = _classify(diag, raw_kind, report, pc)
    return diag


def _find_error_line(lines: List[str]) -> Tuple[int, Optional[re.Match]]:
    """Index and match of the "ERROR: AddressSanitizer:" line."""
    for index, line in enumerate(lines):
        match = _ERROR.search(line)
        if match:
            return index, match
    return -1, None


def _read_access_and_stack(diag: Diagnosis, lines: List[str], head_index: int) -> None:
    """Fill diag.access, diag.access_size and diag.frames (the crash stack)."""
    diag.frames = parse_stack(lines, head_index)
    # The "READ of size N" or "The signal is caused by a READ" line, when there is one,
    # sits between the header and the stack.
    for index, line in enumerate(lines[head_index + 1:], start=head_index + 1):
        access = _ACCESS.match(line)
        if access:
            diag.access = access.group(1)
            diag.access_size = int(access.group(2))
            if not diag.frames:
                diag.frames = parse_stack(lines, index)
            break
        signal_access = _SIGNAL_ACCESS.search(line)
        if signal_access:
            diag.access = signal_access.group(1)
        if line.lstrip().startswith("#"):
            break
    if not diag.frames:
        for index, line in enumerate(lines):
            if _FRAME.match(line):
                diag.frames = parse_stack(lines, index - 1)
                break


def _read_details(diag: Diagnosis, lines: List[str]) -> None:
    """Fill where the memory was freed/allocated and which array was overflowed."""
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("freed by thread"):
            diag.freed_at = first_user_frame(parse_stack(lines, index))
        elif stripped.startswith("previously allocated by thread") or stripped.startswith("allocated by thread"):
            diag.allocated_at = first_user_frame(parse_stack(lines, index))
        region = _HEAP_REGION.search(line)
        if region:
            diag.region_distance = int(region.group(1))
            diag.region_relation = _RELATION[region.group(2)]
            diag.region_size = int(region.group(3))
        global_var = _GLOBAL.search(line)
        if global_var:
            diag.region_distance = int(global_var.group(1))
            diag.region_relation = _RELATION[global_var.group(2)]
            diag.var_name = global_var.group(3)
            diag.region_size = int(global_var.group(5))
        stack = _STACK_FRAME.search(line)
        if stack:
            _read_stack_variable(diag, lines, index, int(stack.group(1)))


def _read_stack_variable(diag: Diagnosis, lines: List[str], start: int, offset: int) -> None:
    """For a local array overflow: find which variable of the function's frame
    was hit (ASan lists them as "[32, 52) 'scores'"), and how far off we were."""
    objects = []
    for line in lines[start + 1:]:
        found = _STACK_OBJECT.search(line)
        if found:
            objects.append(found)
        elif objects and line.strip() and not line.strip().startswith("#"):
            break
    if not objects:
        return
    chosen = next((obj for obj in objects if "<==" in (obj.group(5) or "")), None)
    if chosen is None:  # no "<==" marker: take the closest variable
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
    """Decide the segwhy kind of an ASan report.

    Most ASan error names map directly (ASAN_KINDS). A plain SEGV or BUS
    needs the address: NULL, near the code (string literal), or elsewhere."""
    if raw_kind in ASAN_KINDS:
        return ASAN_KINDS[raw_kind]
    if raw_kind.startswith("attempting double-free"):
        return "double_free"
    if raw_kind.startswith("attempting free"):
        return "bad_free"
    if raw_kind not in ("SEGV", "BUS"):  # macOS reports most invalid accesses as BUS
        return "unknown"

    addr = diag.address
    if "address points to the zero page" in report or (addr is not None and addr < NULL_PAGE_LIMIT):
        return "null_in_library" if diag.library_function() else "null_deref"
    if diag.recursive_function():
        return "stack_exhaustion"
    # A write close to the code is a write into the program's read-only data:
    # almost always a string literal. macOS reports these as BUS, doesn't always
    # say READ or WRITE, and sometimes doesn't give the address at all.
    near_code = addr is not None and pc is not None and abs(addr - pc) < NEAR_CODE_DISTANCE
    if near_code and (diag.access == "WRITE" or (raw_kind == "BUS" and diag.access != "READ")):
        return "readonly_write"
    if raw_kind == "BUS" and addr is None and diag.access == "WRITE":
        return "readonly_write"
    return "wild_pointer" if raw_kind == "SEGV" else "bus_error"


# ---- UndefinedBehaviorSanitizer -----------------------------------------------------------

def parse_ubsan(text: str) -> List[Diagnosis]:
    """Every UBSan report in `text` ("main.c:5:18: runtime error: ...")."""
    lines = text.splitlines()
    found: List[Diagnosis] = []
    for index, line in enumerate(lines):
        match = _UBSAN.match(line.strip())
        if not match:
            continue
        message = match.group("msg").strip()
        kind = next((k for needle, k in UBSAN_KINDS if needle in message), "ubsan")
        frames = parse_stack(lines, index)
        if not any(f.is_user_code() for f in frames):
            # No stack printed: the "file:line:col:" prefix is the location.
            frames.insert(0, Frame(file=match.group("file"), line=int(match.group("line")),
                                   column=int(match.group("col"))))
        found.append(Diagnosis(kind=kind, source="ubsan", frames=frames, raw_kind=message,
                               raw="\n".join(lines[index:index + 1 + len(frames)])))
    return found


# ---- LeakSanitizer -------------------------------------------------------------------------

def parse_leaks(text: str) -> Optional[Tuple[int, int, Optional[Frame]]]:
    """For a leak report: (number of leaks, bytes leaked, where the first leaked
    block was allocated in the user's code). None when there are no leaks."""
    if "LeakSanitizer: detected memory leaks" not in text:
        return None
    summary = _LEAK_SUMMARY.search(text)
    if not summary:
        return None
    lines = text.splitlines()
    first = None
    for index, line in enumerate(lines):
        if re.match(r"^(Direct|Indirect) leak of", line.strip()):
            first = first_user_frame(parse_stack(lines, index))
            if first:
                break
    return int(summary.group(2)), int(summary.group(1)), first
