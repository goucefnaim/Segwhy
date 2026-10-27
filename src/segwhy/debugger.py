"""For programs built without AddressSanitizer: run them under gdb.

The user never sees gdb. run_with_gdb() starts gdb with gdb_helper.py, which
runs the program and saves the crash details to a JSON file. Then
diagnosis_from_gdb() turns those details into a Diagnosis.

Linux only for now (lldb on macOS would be a nice contribution).
"""

from __future__ import annotations

import json
import os
import shutil
import signal as signals
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple

from .model import Diagnosis, Frame
from .sanitizers import NULL_PAGE_LIMIT

HELPER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gdb_helper.py")

# A crash this close to the stack pointer, outside any mapping, is a stack overflow.
STACK_DISTANCE = 1 << 20


def gdb_available() -> bool:
    """True when gdb can be used on this system."""
    return shutil.which("gdb") is not None and sys.platform.startswith("linux")


def run_with_gdb(binary: str, args: List[str]) -> Tuple[Optional[dict], int]:
    """Run `binary args...` under gdb. The program keeps the real terminal.

    Returns (what gdb_helper.py found, exit code). The dict has a "status":
    "exited" (no crash), "signal" (crash, with "signo", "frames"...), or
    "failed" (gdb couldn't run it). It is None if the user pressed Ctrl+C."""
    workdir = tempfile.mkdtemp(prefix="segwhy-")
    out_path = os.path.join(workdir, "result.json")
    env = dict(
        os.environ,
        SEGWHY_GDB_OUT=out_path,
        SEGWHY_SHELL=os.environ.get("SHELL", ""),
        SEGWHY_HAD_LINES="1" if "LINES" in os.environ else "",
        SEGWHY_HAD_COLUMNS="1" if "COLUMNS" in os.environ else "",
        SHELL="/bin/sh",  # gdb_helper's redirections use POSIX sh syntax
    )
    command = ["gdb", "-q", "-nx", "-batch", "-x", HELPER_SCRIPT, "--args", binary, *args]

    # Give the program our stdout/stderr through two extra descriptors, and
    # send gdb's own messages to /dev/null (see gdb_helper.output_redirection).
    sys.stdout.flush()
    sys.stderr.flush()
    out_fd, err_fd = os.dup(1), os.dup(2)
    quiet = out_fd <= 9 and err_fd <= 9  # sh only handles one-digit descriptors
    if quiet:
        env["SEGWHY_FDS"] = f"{out_fd},{err_fd}"
    try:
        subprocess.run(
            command,
            env=env,
            stdout=subprocess.DEVNULL if quiet else None,
            stderr=subprocess.DEVNULL if quiet else None,
            pass_fds=(out_fd, err_fd) if quiet else (),
        )
    except KeyboardInterrupt:
        shutil.rmtree(workdir, ignore_errors=True)
        return None, 130
    finally:
        os.close(out_fd)
        os.close(err_fd)

    try:
        with open(out_path) as handle:
            result = json.load(handle)
    except (OSError, ValueError):
        result = {"status": "failed"}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if result.get("status") == "exited":
        return result, int(result.get("exit_code") or 0)
    if result.get("status") == "signal":
        return result, 128 + int(result.get("signo") or 0)
    return result, -1


def signal_name(number: Optional[int]) -> str:
    """"SIGSEGV" for 11, and so on."""
    try:
        return signals.Signals(int(number)).name
    except (TypeError, ValueError):
        return f"signal {number}"


def _mapping_for(maps: str, address: int) -> Optional[Tuple[str, str]]:
    """In a /proc/<pid>/maps text: (permissions, name) of the mapping that
    contains `address`, or None if the address is not mapped."""
    for line in maps.splitlines():
        parts = line.split(None, 5)
        if len(parts) < 2:
            continue
        start, _, end = parts[0].partition("-")
        try:
            if int(start, 16) <= address < int(end, 16):
                return parts[1], parts[5].strip() if len(parts) > 5 else ""
        except ValueError:
            continue
    return None


def diagnosis_from_gdb(result: dict) -> Diagnosis:
    """Turn what gdb_helper.py found (status "signal") into a Diagnosis."""
    frames = [
        Frame(func=f.get("func"), file=f.get("file"), line=f.get("line"), module=f.get("module"))
        for f in result.get("frames", [])
    ]
    name = signal_name(result.get("signo"))
    address = result.get("address")
    diag = Diagnosis(kind="signal", source="gdb", signal=name, address=address, frames=frames, raw_kind=name)
    diag.kind = _classify(diag, name, address, result)
    if diag.kind == "readonly_write":
        diag.access = "WRITE"
    return diag


def _classify(diag: Diagnosis, name: str, address: Optional[int], result: dict) -> str:
    """Decide the segwhy kind from the signal, the address and the memory map."""
    if name in ("SIGSEGV", "SIGBUS") and diag.recursive_function():
        return "stack_exhaustion"
    if name == "SIGSEGV":
        if address is not None and address < NULL_PAGE_LIMIT:
            return "null_in_library" if diag.library_function() else "null_deref"
        mapping = _mapping_for(result.get("maps", ""), address) if address is not None else None
        sp = result.get("sp")
        if mapping and "w" not in mapping[0]:
            return "readonly_write"  # the address exists but can't be written
        if sp is not None and address is not None and abs(address - sp) < STACK_DISTANCE and mapping is None:
            return "stack_exhaustion"
        return "wild_pointer"
    if name == "SIGFPE":
        return "div_zero" if result.get("si_code") in (1, 2) else "fpe"  # FPE_INTDIV, FPE_INTOVF
    if name == "SIGABRT":
        return "abort"
    if name == "SIGBUS":
        return "bus_error"
    if name == "SIGILL":
        return "illegal_instruction"
    return "signal"
