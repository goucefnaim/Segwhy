"""Fallback for programs built without AddressSanitizer: run them under gdb."""

from __future__ import annotations

import json
import os
import shutil
import signal as signals
import subprocess
import sys
import tempfile
from typing import Optional, Tuple

from .asan import NULL_PAGE_LIMIT
from .model import Diagnosis, Frame

# Runs inside gdb's embedded Python. The program keeps the real terminal
# (stdin/stdout/stderr); only gdb's own messages are captured.
GDB_SCRIPT = r'''
import gdb
import json
import os

out_path = os.environ["SEGWHY_GDB_OUT"]
result = {"status": "unknown"}

for command in (
    "set pagination off",
    "set confirm off",
    "set width 0",
    "set print thread-events off",
    "set print inferior-events off",
    "set debuginfod enabled off",
    "set disable-randomization off",
    "handle SIGPIPE nostop noprint pass",
    "handle SIGALRM nostop noprint pass",
    "handle SIGUSR1 nostop noprint pass",
    "handle SIGUSR2 nostop noprint pass",
    "handle SIGCHLD nostop noprint pass",
    "handle SIGWINCH nostop noprint pass",
):
    try:
        gdb.execute(command, to_string=True)
    except gdb.error:
        pass

exit_info = {}


def on_exit(event):
    if hasattr(event, "exit_code"):
        exit_info["code"] = event.exit_code
    exit_info["exited"] = True


gdb.events.exited.connect(on_exit)

# Give the program the environment segwhy was started with, without the
# variables segwhy and gdb add.
for name in ("SEGWHY_GDB_OUT", "SEGWHY_FDS", "SEGWHY_SHELL", "SEGWHY_HAD_LINES", "SEGWHY_HAD_COLUMNS"):
    try:
        gdb.execute("unset environment " + name, to_string=True)
    except gdb.error:
        pass
original_shell = os.environ.get("SEGWHY_SHELL")
try:
    if original_shell:
        gdb.execute("set environment SHELL=" + original_shell, to_string=True)
    else:
        gdb.execute("unset environment SHELL", to_string=True)
    for name in ("LINES", "COLUMNS"):
        if not os.environ.get("SEGWHY_HAD_" + name):
            gdb.execute("unset environment " + name, to_string=True)
except gdb.error:
    pass

# gdb's own output goes to /dev/null. The program gets segwhy's real stdout and
# stderr back through two inherited descriptors, closed right after use so the
# program sees exactly the descriptors it would see without segwhy.
redirect = ""
fds = os.environ.get("SEGWHY_FDS")
if fds:
    out_fd, err_fd = fds.split(",")
    redirect = " 1>&%s 2>&%s %s>&- %s>&-" % (out_fd, err_fd, out_fd, err_fd)
arguments = gdb.parameter("args") or ""

try:
    gdb.execute("run " + arguments + redirect, to_string=True)
except gdb.error as error:
    result["error"] = str(error)

inferior = gdb.selected_inferior()
if exit_info.get("exited") or not inferior.pid:
    result["status"] = "exited" if exit_info.get("exited") else "failed"
    result["exit_code"] = exit_info.get("code", 0)
else:
    result["status"] = "signal"
    try:
        info = gdb.parse_and_eval("$_siginfo")
        result["signo"] = int(info["si_signo"])
        result["si_code"] = int(info["si_code"])
        try:
            result["address"] = int(info["_sifields"]["_sigfault"]["si_addr"])
        except gdb.error:
            pass
    except gdb.error as error:
        result["siginfo_error"] = str(error)
    try:
        result["sp"] = int(gdb.parse_and_eval("$sp"))
    except gdb.error:
        pass
    frames = []
    frame = gdb.newest_frame()
    while frame is not None and len(frames) < 3000:
        entry = {"func": frame.name()}
        try:
            sal = frame.find_sal()
            if sal.symtab is not None and sal.line:
                entry["file"] = sal.symtab.fullname()
                entry["line"] = sal.line
        except Exception:
            pass
        try:
            entry["module"] = gdb.solib_name(frame.pc()) or gdb.current_progspace().filename
        except Exception:
            pass
        frames.append(entry)
        try:
            frame = frame.older()
        except gdb.error:
            break
    result["frames"] = frames
    try:
        with open("/proc/%d/maps" % inferior.pid) as maps:
            result["maps"] = maps.read()
    except OSError:
        pass
    try:
        gdb.execute("kill", to_string=True)
    except gdb.error:
        pass

with open(out_path, "w") as handle:
    json.dump(result, handle)
'''


def gdb_available() -> bool:
    return shutil.which("gdb") is not None


def run_with_gdb(binary: str, args) -> Tuple[Optional[dict], int]:
    """Run the program under gdb. Returns (gdb result, exit code)."""
    workdir = tempfile.mkdtemp(prefix="segwhy-")
    script = os.path.join(workdir, "segwhy_gdb.py")
    out_path = os.path.join(workdir, "result.json")
    with open(script, "w") as handle:
        handle.write(GDB_SCRIPT)
    env = dict(
        os.environ,
        SEGWHY_GDB_OUT=out_path,
        SEGWHY_SHELL=os.environ.get("SHELL", ""),
        SEGWHY_HAD_LINES="1" if "LINES" in os.environ else "",
        SEGWHY_HAD_COLUMNS="1" if "COLUMNS" in os.environ else "",
        SHELL="/bin/sh",  # the redirections below use POSIX sh syntax
    )
    command = ["gdb", "-q", "-nx", "-batch", "-x", script, "--args", binary, *args]
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


def _signal_name(number: Optional[int]) -> str:
    try:
        return signals.Signals(int(number)).name
    except (TypeError, ValueError):
        return f"signal {number}"


def _mapping_for(maps: str, address: int) -> Optional[Tuple[str, str]]:
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
    frames = [
        Frame(func=f.get("func"), file=f.get("file"), line=f.get("line"), module=f.get("module"))
        for f in result.get("frames", [])
    ]
    name = _signal_name(result.get("signo"))
    address = result.get("address")
    diag = Diagnosis(kind="signal", source="gdb", signal=name, address=address, frames=frames, raw_kind=name)

    if name in ("SIGSEGV", "SIGBUS") and diag.recursive_function():
        diag.kind = "stack_exhaustion"
    elif name == "SIGSEGV":
        if address is not None and address < NULL_PAGE_LIMIT:
            diag.kind = "null_in_library" if diag.library_function() else "null_deref"
        else:
            mapping = _mapping_for(result.get("maps", ""), address) if address is not None else None
            sp = result.get("sp")
            if mapping and "w" not in mapping[0]:
                diag.kind = "readonly_write"
                diag.access = "WRITE"
            elif sp is not None and address is not None and abs(address - sp) < (1 << 20) and mapping is None:
                diag.kind = "stack_exhaustion"
            else:
                diag.kind = "wild_pointer"
    elif name == "SIGFPE":
        diag.kind = "div_zero" if result.get("si_code") in (1, 2) else "fpe"
    elif name == "SIGABRT":
        diag.kind = "abort"
    elif name == "SIGBUS":
        diag.kind = "bus_error"
    elif name == "SIGILL":
        diag.kind = "illegal_instruction"
    return diag
